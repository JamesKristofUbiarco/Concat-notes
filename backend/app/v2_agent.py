"""Pipeline v2: evidencia/novelty -> cuerpo -> glosario y tarjetas en paralelo."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import re
import time
from typing import Any, TypedDict
from zoneinfo import ZoneInfo

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from app import crud, llm_models, models
from app.agent import preprocess_transcription
from app.knowledge import extract_claims, retrieve_prior_knowledge


class V2State(TypedDict, total=False):
    raw_note_id: str
    raw_note_data: dict[str, Any]
    flashcard_count: int
    historical_context: dict[str, Any]
    evidence_manifest: list[dict[str, Any]]
    body_markdown: str
    glossary_markdown: str
    flashcards_markdown: str
    structured_markdown: str
    ai_comments: str
    metrics: dict[str, Any]


class BodyOutput(BaseModel):
    markdown_body: str = Field(description="Nota con frontmatter y cuerpo, sin cabecera visible, glosario, flashcards ni zona de procesamiento")
    ai_comments: str = ""


def _content(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return " ".join(str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in content).strip()
    return str(content).strip()


def _json_payload(response: Any) -> Any:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", _content(response), flags=re.IGNORECASE)
    starts = [item for item in (text.find("["), text.find("{")) if item >= 0]
    if not starts:
        raise ValueError("Respuesta sin JSON")
    return json.loads(text[min(starts):max(text.rfind("]"), text.rfind("}")) + 1])


def _invoke_json(llm: Any, prompt: str, attempts: int = 3) -> Any:
    last_error: Exception | None = None
    for attempt in range(attempts):
        suffix = "" if attempt == 0 else "\nLa respuesta anterior no era JSON válido. Repite toda la salida sin Markdown y con comillas internas escapadas."
        try:
            return _json_payload(llm.invoke(prompt + suffix))
        except (ValueError, json.JSONDecodeError) as exc:
            last_error = exc
    raise ValueError(f"El modelo auxiliar no produjo JSON válido: {last_error}")


def _clean_markdown(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^```(?:markdown|md|txt)?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*```$", "", value)
    return value.strip()


_FRONTMATTER_RE = re.compile(r"\A(---[ \t]*\r?\n.*?\r?\n---[ \t]*(?:\r?\n|$))", re.DOTALL)
_VISIBLE_METADATA_RE = re.compile(
    r"^\*\*(?:Curso|Instructor/Autor|Fecha de clase):\*\*",
    re.IGNORECASE,
)


def _single_line(value: Any, fallback: str = "---") -> str:
    """Evita que metadatos introduzcan encabezados o líneas Markdown accidentales."""
    normalized = re.sub(r"\s+", " ", str(value or "")).strip()
    return normalized or fallback


def _note_local_date(note: Any) -> str:
    created_at = getattr(note, "created_at", None)
    if isinstance(created_at, datetime):
        if created_at.tzinfo is not None:
            created_at = created_at.astimezone(ZoneInfo("America/Mexico_City"))
        return created_at.date().isoformat()
    return time.strftime("%Y-%m-%d")


def ensure_visible_class_header(markdown: str, note: Any) -> str:
    """Inserta una cabecera que sobrevive al purgado de frontmatter del concatenador."""
    document = _clean_markdown(markdown)
    match = _FRONTMATTER_RE.match(document)
    frontmatter = match.group(1).strip() if match else ""
    remainder = document[match.end():].lstrip() if match else document

    # Sustituye una cabecera visible previa para que reintentos y reparaciones sean idempotentes.
    lines = remainder.splitlines()
    if lines and re.match(r"^#(?!#)\s+", lines[0]):
        lines.pop(0)
        while lines and (not lines[0].strip() or _VISIBLE_METADATA_RE.match(lines[0].strip())):
            lines.pop(0)
    remainder = "\n".join(lines).strip()

    title = _single_line(getattr(note, "class_title", None), "Clase sin título")
    course = _single_line(getattr(note, "course_name", None))
    teacher = _single_line(getattr(note, "teacher", None))
    module = _single_line(getattr(note, "course_module", None))
    visible_header = "\n".join((
        f"# 📚 {title}",
        f"**Curso:** {course}",
        f"**Instructor/Autor:** {teacher} | **Módulo del curso:** {module}",
        f"**Fecha de clase:** {_note_local_date(note)}",
    ))
    return "\n\n".join(part for part in (frontmatter, visible_header, remainder) if part).strip()


def context_node(state: V2State, config: RunnableConfig) -> V2State:
    db = config["configurable"]["db"]
    note = db.query(models.RawNote).filter(models.RawNote.id == state["raw_note_id"]).first()
    if not note:
        raise ValueError("No existe la nota cruda")
    started = time.monotonic()
    historical = retrieve_prior_knowledge(db, note)
    density = crud.get_flashcard_density(db)
    target = note.flashcard_target if note.flashcard_target and note.flashcard_target > 0 else max(3, round((len(note.transcription or "") / 5000) * density))
    state["historical_context"] = historical
    state["flashcard_count"] = target
    state["metrics"] = {
        "pipeline_version": "v2",
        "context_ms": round((time.monotonic() - started) * 1000),
        "source_chars": len(note.transcription or "") + len(note.my_notes or "") + len(note.class_summary or ""),
    }
    return state


def evidence_node(state: V2State, config: RunnableConfig) -> V2State:
    db = config["configurable"]["db"]
    note = db.query(models.RawNote).filter(models.RawNote.id == state["raw_note_id"]).first()
    started = time.monotonic()
    historical_ids = {item["id"] for item in state.get("historical_context", {}).get("claims", [])}
    historical = db.query(models.NoteClaim).filter(models.NoteClaim.id.in_(historical_ids)).all() if historical_ids else None
    resolved = llm_models.resolve_selected_model(db, "query_expansion")
    state["evidence_manifest"] = extract_claims(note, db, historical=historical)
    state["metrics"].update({
        "evidence_ms": round((time.monotonic() - started) * 1000),
        "evidence_claims": len(state["evidence_manifest"]),
        "evidence_model_requested": resolved.requested_model,
        "evidence_model_effective": resolved.model_id,
    })
    return state


BODY_SYSTEM = """Eres Synapse Scholar, editor de apuntes académicos progresivos para Obsidian.
Tu prioridad es extraer toda la información respaldada por la clase actual y hacerla interesante de leer, sin reexplicar extensamente conocimientos anteriores.
NEW se explica por completo; EXTENDS desarrolla sólo el detalle nuevo; REPEATS se resume como prerrequisito; APPLIES documenta el procedimiento o contexto nuevo; CLARIFIES y CONTRADICTS destacan la diferencia.
Conserva fórmulas, código, comandos, ejemplos, excepciones y advertencias. Usa backlinks proporcionados. Nunca atribuyas al material actual información que sólo aparezca en el historial.
DIRECTIVA DE CONSISTENCIA TERMINOLÓGICA: prioriza el término técnico canónico en inglés en títulos, subtítulos y explicaciones. Redacta las explicaciones en español y, la primera vez que introduzcas cada concepto, escribe el término inglés seguido de su traducción breve al español entre paréntesis; por ejemplo: `Un deadlock (interbloqueo) es...`. Después usa sólo el término inglés. No inviertas el orden como `interbloqueo (deadlock)` ni repitas la traducción en cada mención.
Devuelve exclusivamente Markdown con frontmatter YAML y el cuerpo de la nota. Después del frontmatter comienza directamente con secciones `##`: no generes título H1 ni líneas visibles de curso, instructor, módulo o fecha porque el ensamblador las añade. No uses cercas alrededor del documento y no incluyas glosario, flashcards ni zona de procesamiento."""


def body_node(state: V2State, config: RunnableConfig) -> V2State:
    db = config["configurable"]["db"]
    note = db.query(models.RawNote).filter(models.RawNote.id == state["raw_note_id"]).first()
    resolved = llm_models.resolve_selected_model(db, "synthesis")
    llm = llm_models.create_chat_model(resolved, timeout=150, max_retries=2)
    processed, orphaned = preprocess_transcription(note.transcription or "", note.code_snippets or [], note.command_snippets or [], note.images or [])
    historical = state.get("historical_context", {})
    prompt = f"""Fecha: {time.strftime('%Y-%m-%d')}
Curso: {note.course_name}
Módulo: {note.course_module}
Clase: {note.class_title}
Profesor: {note.teacher}
Plataforma: {note.platform}
Modo de escritura: {note.writing_mode}

MANIFIESTO DE EVIDENCIA Y NOVEDAD:
{json.dumps(state.get('evidence_manifest', []), ensure_ascii=False)}

ANTECEDENTE INMEDIATO PARA BACKLINK:
{json.dumps(historical.get('previous'), ensure_ascii=False)}

AFIRMACIONES HISTÓRICAS RELACIONADAS (sólo contraste, consistencia y enlaces):
{json.dumps(historical.get('claims', []), ensure_ascii=False)}

TRANSCRIPCIÓN Y MATERIAL ACTUAL:
{processed}

APUNTES DEL ALUMNO:
{note.my_notes or ''}

RESUMEN SUMINISTRADO:
{note.class_summary or ''}

IMÁGENES SIN MARCADOR:
{json.dumps(orphaned, ensure_ascii=False)}

Escribe una nota autosuficiente pero progresiva. Incluye una sección temprana `## Qué aporta esta clase`; usa secciones de conceptos nuevos, ampliaciones o aplicación sólo cuando correspondan. No crees contenido para llenar una plantilla."""
    started = time.monotonic()
    output = llm.invoke([
        SystemMessage(content=BODY_SYSTEM), HumanMessage(content=prompt)
    ])
    body = _clean_markdown(_content(output))
    # Defensa ante modelos que ignoran la separación de responsabilidades.
    body = re.split(r"^##\s+(?:📖\s+Conceptos Clave|🗃️\s+Flashcards|🧠\s+Zona de Procesamiento)", body, maxsplit=1, flags=re.MULTILINE)[0].rstrip()
    state["body_markdown"] = body
    state["ai_comments"] = ""
    state["metrics"].update({
        "synthesis_ms": round((time.monotonic() - started) * 1000),
        "synthesis_model_requested": resolved.requested_model,
        "synthesis_model_effective": resolved.model_id,
        "synthesis_fallback": resolved.fallback_used,
    })
    return state


def mermaid_repair_node(state: V2State, config: RunnableConfig) -> V2State:
    """Valida el cuerpo y, si hace falta, reemplaza sólo bloques Mermaid."""
    from app.agent import mermaid_validation_node

    blocks = re.findall(r"```mermaid\s*\n([\s\S]*?)```", state.get("body_markdown", ""), re.IGNORECASE)
    if not blocks:
        return state
    validation_state = {
        "structured_markdown": state["body_markdown"],
        "mermaid_validation_errors": "",
        "mermaid_retries": 0,
    }
    mermaid_validation_node(validation_state, config)
    errors = validation_state.get("mermaid_validation_errors", "")
    if not errors:
        return state
    db = config["configurable"]["db"]
    resolved = llm_models.resolve_selected_model(db, "synthesis")
    llm = llm_models.create_chat_model(resolved, timeout=90, max_retries=2)
    prompt = f"""Corrige exclusivamente la sintaxis de estos bloques Mermaid.
No cambies etiquetas ni contenido fuera de lo necesario para compilar.
Errores del compilador: {errors}
Bloques: {json.dumps(blocks, ensure_ascii=False)}
Devuelve sólo JSON: {{"blocks":["bloque corregido 1", "..."]}} con igual cantidad y orden."""
    payload = _invoke_json(llm, prompt)
    corrected = payload.get("blocks", []) if isinstance(payload, dict) else []
    if len(corrected) != len(blocks):
        raise ValueError("La reparación Mermaid no conservó la cantidad de bloques")
    iterator = iter(str(item).strip() for item in corrected)
    repaired = re.sub(
        r"```mermaid\s*\n[\s\S]*?```",
        lambda _: f"```mermaid\n{next(iterator)}\n```",
        state["body_markdown"], flags=re.IGNORECASE,
    )
    check_state = {"structured_markdown": repaired, "mermaid_validation_errors": "", "mermaid_retries": 0}
    mermaid_validation_node(check_state, config)
    if check_state.get("mermaid_validation_errors"):
        raise ValueError("Los bloques Mermaid siguen siendo inválidos tras la reparación localizada")
    state["body_markdown"] = repaired
    state["metrics"]["mermaid_repaired_blocks"] = len(blocks)
    return state


def _glossary_call(llm: Any, note: models.RawNote, state: V2State, existing_terms: list[str]) -> str:
    prompt = f"""Genera únicamente el delta de glosario de esta clase.
No redefinas términos existentes ni conviertas REPEATS/APPLIES en definiciones nuevas. Para EXTENDS usa kind=extension; para conocimiento NEW usa kind=definition.
Usa siempre el término técnico canónico en inglés como `term`, incluso si la clase lo menciona en español. Incluye su traducción breve al español en `term_es`.
Escribe `content` en español. En una definición nueva, presenta el término inglés y menciona su traducción una sola vez entre paréntesis; ejemplo: "Un deadlock (interbloqueo) es una situación...". No pongas la traducción en el título.
Términos existentes: {json.dumps(existing_terms, ensure_ascii=False)}
Manifiesto: {json.dumps(state.get('evidence_manifest', []), ensure_ascii=False)}
Cuerpo final: {state.get('body_markdown', '')}
Devuelve sólo un array JSON: [{{"term":"English term","term_es":"traducción al español","kind":"definition|extension","content":"..."}}]."""
    payload = _invoke_json(llm, prompt)
    if isinstance(payload, dict):
        payload = payload.get("entries", [])
    lines = ["## 📖 Conceptos Clave (Glosario)", ""]
    seen = set()
    for item in payload if isinstance(payload, list) else []:
        term = str(item.get("term", "")).strip()
        content = str(item.get("content", "")).strip()
        key = term.casefold()
        if not term or not content or key in seen:
            continue
        seen.add(key)
        tag = "#definicion-ampliada" if item.get("kind") == "extension" else "#definicion"
        lines.extend([f"**{term}** {tag}", content, ""])
    return "\n".join(lines).strip()


def _card_key(question: str) -> str:
    return re.sub(r"[^a-z0-9áéíóúüñ]+", "", question.lower())


def _card_terms(question: str) -> set[str]:
    return {word for word in re.findall(r"[\wáéíóúüñ]{4,}", question.lower())}


def _flashcard_call(llm: Any, note: models.RawNote, state: V2State) -> str:
    target = state.get("flashcard_count", 5)
    historical = state.get("historical_context", {}).get("flashcards", [])
    prompt = f"""Crea {target + 5} candidatos de flashcards centrados en conocimiento NEW, EXTENDS, APPLIES, CLARIFIES o CONTRADICTS de la clase actual.
No preguntes de nuevo lo mismo que las tarjetas históricas. Cada respuesta debe poder justificarse con el cuerpo actual.
Históricas: {json.dumps(historical, ensure_ascii=False)}
Manifiesto: {json.dumps(state.get('evidence_manifest', []), ensure_ascii=False)}
Cuerpo: {state.get('body_markdown', '')}
Devuelve sólo un array JSON: [{{"question":"...","answer":"..."}}]."""
    payload = _json_payload(llm.invoke(prompt))
    if isinstance(payload, dict):
        payload = payload.get("flashcards", [])
    historical_keys = {_card_key(item.get("question", "")) for item in historical}
    historical_terms = [_card_terms(item.get("question", "")) for item in historical]
    cards = []
    seen = set(historical_keys)
    for item in payload if isinstance(payload, list) else []:
        question = str(item.get("question", "")).strip()
        answer = str(item.get("answer", "")).strip()
        key = _card_key(question)
        terms = _card_terms(question)
        too_similar = any(
            len(terms & previous) / max(1, len(terms | previous)) >= 0.75
            for previous in historical_terms
        )
        if not question or not answer or not key or key in seen or too_similar:
            continue
        seen.add(key)
        cards.append((question, answer))
        if len(cards) == target:
            break
    if len(cards) < target:
        raise ValueError(f"El modelo auxiliar produjo {len(cards)} tarjetas únicas de {target}")
    course_tag = re.sub(r"[^A-Za-z0-9]", "", note.course_name.title().replace(" ", "")) or "Curso"
    module_tag = re.sub(r"[^A-Za-z0-9]", "", (note.course_module or "General").title().replace(" ", "")) or "General"
    lines = ["## 🗃️ Flashcards", f"#flashcards/{course_tag}/{module_tag}", ""]
    lines.extend(f"{question}::{answer}" for question, answer in cards)
    return "\n\n".join(lines).strip()


def supplements_node(state: V2State, config: RunnableConfig) -> V2State:
    db = config["configurable"]["db"]
    note = db.query(models.RawNote).filter(models.RawNote.id == state["raw_note_id"]).first()
    glossary = db.query(models.CourseGlossary).filter(models.CourseGlossary.course_name == note.course_name).first()
    existing_terms = [item.get("term", "") for item in (glossary.entries or [])] if glossary else []
    resolved = llm_models.resolve_selected_model(db, "query_expansion")
    started = time.monotonic()

    def glossary_job() -> str:
        return _glossary_call(llm_models.create_chat_model(resolved, timeout=90, max_retries=2), note, state, existing_terms)

    def flashcards_job() -> str:
        llm = llm_models.create_chat_model(resolved, timeout=90, max_retries=2)
        try:
            return _flashcard_call(llm, note, state)
        except ValueError:
            return _flashcard_call(llm, note, state)

    with ThreadPoolExecutor(max_workers=2) as executor:
        glossary_future = executor.submit(glossary_job)
        flashcards_future = executor.submit(flashcards_job)
        state["glossary_markdown"] = glossary_future.result()
        state["flashcards_markdown"] = flashcards_future.result()
    state["metrics"].update({
        "supplements_ms": round((time.monotonic() - started) * 1000),
        "auxiliary_model_requested": resolved.requested_model,
        "auxiliary_model_effective": resolved.model_id,
        "auxiliary_fallback": resolved.fallback_used,
    })
    return state


def assemble_node(state: V2State, config: RunnableConfig) -> V2State:
    db = config["configurable"]["db"]
    note = db.query(models.RawNote).filter(models.RawNote.id == state["raw_note_id"]).first()
    if not note:
        raise ValueError("No existe la nota cruda al ensamblar")
    body = ensure_visible_class_header(state.get("body_markdown", ""), note)
    claims = state.get("evidence_manifest", [])
    processing = ["## 🧠 Zona de Procesamiento (Fase 2: Deconstrucción)"]
    seen = set()
    for item in claims:
        concept = str(item.get("concept", "")).strip()
        if not concept or concept.casefold() in seen:
            continue
        seen.add(concept.casefold())
        processing.append(f"* [[{concept}]] #{str(item.get('novelty_relation', 'NEW')).lower()}")
    state["structured_markdown"] = "\n\n".join(part.strip() for part in (
        body,
        state.get("glossary_markdown", ""),
        state.get("flashcards_markdown", ""),
        "\n".join(processing),
    ) if part and part.strip())
    state["metrics"]["output_chars"] = len(state["structured_markdown"])
    state["metrics"]["estimated_output_tokens"] = round(len(state["structured_markdown"]) / 4)
    return state


def compile_agent_v2():
    workflow = StateGraph(V2State)
    workflow.add_node("context", context_node)
    workflow.add_node("evidence", evidence_node)
    workflow.add_node("body", body_node)
    workflow.add_node("mermaid_repair", mermaid_repair_node)
    workflow.add_node("supplements", supplements_node)
    workflow.add_node("assemble", assemble_node)
    workflow.set_entry_point("context")
    workflow.add_edge("context", "evidence")
    workflow.add_edge("evidence", "body")
    workflow.add_edge("body", "mermaid_repair")
    workflow.add_edge("mermaid_repair", "supplements")
    workflow.add_edge("supplements", "assemble")
    workflow.add_edge("assemble", END)
    return workflow.compile(checkpointer=MemorySaver())
