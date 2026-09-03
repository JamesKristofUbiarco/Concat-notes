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
from app.deck_names import canonical_deck_tag
from app.knowledge import extract_claims, retrieve_prior_knowledge


class V2State(TypedDict, total=False):
    raw_note_id: str
    raw_note_data: dict[str, Any]
    flashcard_count: int
    historical_context: dict[str, Any]
    evidence_manifest: list[dict[str, Any]]
    class_knowledge_model: dict[str, Any]
    coverage_plan: list[dict[str, Any]]
    style_context: dict[str, Any]
    body_markdown: str
    glossary_markdown: str
    flashcards_markdown: str
    structured_markdown: str
    cornell_document: dict[str, Any]
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
        f"# {title}",
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


def knowledge_model_node(state: V2State, config: RunnableConfig) -> V2State:
    """Separa qué debe cubrirse de la decisión posterior de cómo redactarlo."""
    db = config["configurable"]["db"]
    from app.structured_notes import ensure_builtin_profiles
    ensure_builtin_profiles(db)
    note = db.query(models.RawNote).filter(models.RawNote.id == state["raw_note_id"]).first()
    claims = state.get("evidence_manifest", [])
    concepts = []
    seen = set()
    for claim in claims:
        concept = str(claim.get("concept") or "").strip()
        if concept and concept.casefold() not in seen:
            seen.add(concept.casefold())
            concepts.append({
                "name": concept,
                "importance": "core" if claim.get("novelty_relation") == "NEW" else "supporting",
                "statement": claim.get("statement", ""),
                "source": claim.get("evidence_source_type", "transcription"),
            })
    source = "\n".join((note.transcription or "", note.my_notes or "", note.class_summary or ""))
    method_lines = [
        line.strip() for line in source.splitlines()
        if re.search(r"\b(?:paso|primero|después|luego|ejecuta|crea|configura|implementa)\b", line, re.IGNORECASE)
    ][:30]
    model = {
        "concepts": concepts,
        "methods": method_lines,
        "code_snippets": note.code_snippets or [],
        "command_snippets": note.command_snippets or [],
        "user_notes": note.my_notes or "",
        "images": [
            {"id": str(image.id), "description": image.descripcion_llm or "", "filename": image.filename}
            for image in note.images or []
        ],
        "uncertainties": [item for item in claims if float(item.get("confidence", 1.0) or 1.0) < 0.7],
    }
    plan = []
    for index, concept in enumerate(concepts):
        plan.append({"id": f"concept-{index + 1}", "kind": "concept", "label": concept["name"], "required": concept["importance"] == "core"})
    if method_lines:
        plan.append({"id": "methods", "kind": "procedure", "label": "Métodos y pasos descritos", "required": True})
    if note.code_snippets:
        plan.append({"id": "code", "kind": "code", "label": "Código con explicación", "required": True})
    if note.images:
        plan.append({"id": "images", "kind": "image", "label": "Imágenes relevantes situadas", "required": True})
    state["class_knowledge_model"] = model
    state["coverage_plan"] = plan
    profile_slug = note.composition_profile or "adaptive"
    if profile_slug == "adaptive":
        profile_slug = "laboratorio-tecnico" if note.code_snippets or note.command_snippets else "procedimiento-guiado" if method_lines else "cornell-conceptual"
    profile = db.query(models.NoteStyleProfile).filter(models.NoteStyleProfile.slug == profile_slug).first()
    examples = []
    if profile:
        rows = db.query(models.NoteStyleExample, models.StructuredNoteDocument).join(
            models.StructuredNoteDocument,
            models.StructuredNoteDocument.id == models.NoteStyleExample.document_id,
        ).filter(models.NoteStyleExample.profile_id == profile.id).limit(4).all()
        for example, document in rows:
            payload = document.document_json or {}
            examples.append({
                "methodology": example.methodology_summary,
                "section_count": len(payload.get("sections", [])),
                "block_sequence": [
                    {"type": block.get("type"), "lane": block.get("lane"), "length": len(str(block.get("content", "")))}
                    for block in payload.get("blocks", [])
                ],
                "relation_types": [item.get("type") for item in payload.get("relations", [])],
            })
    state["style_context"] = {
        "profile_slug": profile_slug,
        "rules": profile.rules_json if profile else {},
        "examples": examples,
    }
    state["metrics"].update({"knowledge_concepts": len(concepts), "coverage_units": len(plan)})
    return state


BODY_SYSTEM = """Eres Synapse Scholar, compositor de documentos de aprendizaje Cornell híbridos.
Tu prioridad es extraer toda la información respaldada por la clase actual y hacerla interesante de leer, sin reexplicar extensamente conocimientos anteriores.
NEW se explica por completo; EXTENDS desarrolla sólo el detalle nuevo; REPEATS se resume como prerrequisito; APPLIES documenta el procedimiento o contexto nuevo; CLARIFIES y CONTRADICTS destacan la diferencia.
Conserva fórmulas, código, comandos, ejemplos, excepciones y advertencias. Usa backlinks proporcionados. Nunca atribuyas al material actual información que sólo aparezca en el historial.
DIRECTIVA DE CONSISTENCIA TERMINOLÓGICA: prioriza el término técnico canónico en inglés en títulos, subtítulos y explicaciones. Redacta las explicaciones en español y, la primera vez que introduzcas cada concepto, escribe el término inglés seguido de su traducción breve al español entre paréntesis; por ejemplo: `Un deadlock (interbloqueo) es...`. Después usa sólo el término inglés. No inviertas el orden como `interbloqueo (deadlock)` ni repitas la traducción en cada mención.
Devuelve exclusivamente JSON, sin cercas Markdown, con esta forma:
{"sections":[{"key":"sec_1","title":"Heading limpio","order":10}],"blocks":[{"key":"b1","section_key":"sec_1","type":"question|concept|paragraph|bullet_list|numbered_list|procedure|code|code_output|command|image|table|formula|mermaid|quote|warning|callout|resource|quiz|project_goal|summary|markdown","lane":"left|right","reading_order":10,"content":"...","sources":[]}],"relations":[{"from_key":"b1","to_key":"b2","type":"answers|defines|explains|demonstrates|produces|warns_about|references|summarizes|contrasts_with|depends_on"}]}.
Los keys sólo son referencias internas de esta respuesta. No incluyas glosario, flashcards ni zona de procesamiento.
Si una imagen del modelo de conocimiento aporta comprensión, crea un bloque image y añade `asset` con `raw_note_image_id` usando exactamente su ID; no inventes IDs ni URLs."""


def _cornell_document(payload: dict[str, Any], note: models.RawNote) -> dict[str, Any]:
    """Convierte keys efímeros del modelo a IDs persistibles y valida el contrato."""
    import uuid
    from app.structured_notes import clean_generated_heading, validate_document

    allowed_blocks = {
        "question", "concept", "paragraph", "heading", "bullet_list", "numbered_list",
        "procedure", "code", "code_output", "command", "image", "table", "formula",
        "mermaid", "quote", "warning", "callout", "resource", "quiz", "project_goal",
        "summary", "markdown",
    }
    allowed_relations = {
        "answers", "defines", "explains", "demonstrates", "produces", "warns_about",
        "references", "summarizes", "contrasts_with", "depends_on",
    }
    section_ids: dict[str, str] = {}
    block_ids: dict[str, str] = {}
    sections = []
    for index, item in enumerate(payload.get("sections") or []):
        key = str(item.get("key") or f"sec_{index}")
        section_ids[key] = str(uuid.uuid4())
        sections.append({"id": section_ids[key], "title": clean_generated_heading(item.get("title", "Sección")), "order": int(item.get("order", (index + 1) * 10))})
    if not sections:
        raise ValueError("El Composer no produjo secciones")
    blocks = []
    for index, item in enumerate(payload.get("blocks") or []):
        section_id = section_ids.get(str(item.get("section_key")))
        if not section_id:
            continue
        key = str(item.get("key") or f"block_{index}")
        block_ids[key] = str(uuid.uuid4())
        kind = str(item.get("type") or "paragraph")
        lane = str(item.get("lane") or "right")
        blocks.append({
            "id": block_ids[key], "section_id": section_id,
            "type": kind if kind in allowed_blocks else "markdown",
            "lane": lane if lane in {"left", "right"} else "right",
            "reading_order": int(item.get("reading_order", (index + 1) * 10)),
            "content": item.get("content", ""), "layout": {"gap_before": 0},
            "sources": item.get("sources") if isinstance(item.get("sources"), list) else [],
            **({"asset": item["asset"]} if isinstance(item.get("asset"), dict) else {}),
        })
    relations = []
    for index, item in enumerate(payload.get("relations") or []):
        source = block_ids.get(str(item.get("from_key")))
        target = block_ids.get(str(item.get("to_key")))
        kind = str(item.get("type") or "explains")
        if source and target:
            relations.append({"id": str(uuid.uuid4()), "from_block_id": source, "to_block_id": target, "type": kind if kind in allowed_relations else "explains", "order": (index + 1) * 10})
    return validate_document({
        "schema_version": "1.0", "document_id": str(uuid.uuid4()),
        "origin": {"kind": "generated_class", "raw_note_id": str(note.id)},
        "metadata": {"title": note.class_title, "course_name": note.course_name, "course_module": note.course_module, "class_title": note.class_title, "teacher": note.teacher, "platform": note.platform, "tags": []},
        "composition": {"profile_slug": note.composition_profile or "adaptive", "profile_version": 1},
        "sections": sections, "blocks": blocks, "relations": relations,
    })


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
Perfil de composición: {note.composition_profile or 'adaptive'}

MANIFIESTO DE EVIDENCIA Y NOVEDAD:
{json.dumps(state.get('evidence_manifest', []), ensure_ascii=False)}

MODELO DE CONOCIMIENTO DE LA CLASE:
{json.dumps(state.get('class_knowledge_model', {}), ensure_ascii=False)}

PLAN DE COBERTURA VERIFICABLE:
{json.dumps(state.get('coverage_plan', []), ensure_ascii=False)}

PERFIL Y PATRONES DE ESTILO (sólo estructura, nunca hechos):
{json.dumps(state.get('style_context', {}), ensure_ascii=False)}

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

Escribe una nota autosuficiente pero progresiva. Incluye una sección temprana `## Qué aporta esta clase`; usa secciones de conceptos nuevos, ampliaciones o aplicación sólo cuando correspondan. No crees contenido para llenar una plantilla. Los headings deben ser limpios y no contener emojis. Para cada tema importante combina una pista de recuperación breve con un desarrollo profundo; conserva secuencias código → salida → explicación y métodos completos cuando existan."""
    started = time.monotonic()
    output = llm.invoke([
        SystemMessage(content=BODY_SYSTEM), HumanMessage(content=prompt)
    ])
    payload = _json_payload(output)
    cornell = _cornell_document(payload, note)
    cornell["composition"]["profile_slug"] = state.get("style_context", {}).get("profile_slug", note.composition_profile or "adaptive")
    from app.structured_notes import render_markdown
    body = render_markdown(cornell)
    state["cornell_document"] = cornell
    state["body_markdown"] = body
    state["ai_comments"] = ""
    state["metrics"].update({
        "synthesis_ms": round((time.monotonic() - started) * 1000),
        "synthesis_model_requested": resolved.requested_model,
        "synthesis_model_effective": resolved.model_id,
        "synthesis_fallback": resolved.fallback_used,
    })
    return state


def critic_node(state: V2State, config: RunnableConfig) -> V2State:
    """Una sola corrección localizada cuando la cobertura cae bajo el umbral."""
    import uuid
    from app.structured_notes import clean_generated_heading, render_markdown, validate_document

    document = state.get("cornell_document")
    if not document:
        return state
    searchable = " ".join(str(block.get("content", "")) for block in document.get("blocks", [])).casefold()
    required = [item for item in state.get("coverage_plan", []) if item.get("required")]
    missing = [item for item in required if item.get("kind") == "concept" and str(item.get("label", "")).casefold() not in searchable]
    covered = len(required) - len(missing)
    ratio = covered / max(1, len(required))
    state["metrics"]["coverage_ratio"] = round(ratio, 3)
    state["metrics"]["critic_triggered"] = bool(missing and ratio < 0.8)
    if not missing or ratio >= 0.8:
        return state
    db = config["configurable"]["db"]
    note = db.query(models.RawNote).filter(models.RawNote.id == state["raw_note_id"]).first()
    resolved = llm_models.resolve_selected_model(db, "synthesis")
    llm = llm_models.create_chat_model(resolved, timeout=90, max_retries=2)
    payload = _invoke_json(llm, f"""Añade exclusivamente unidades faltantes a una nota Cornell; no reescribas lo existente.
Faltantes: {json.dumps(missing, ensure_ascii=False)}
Evidencia: {json.dumps(state.get('class_knowledge_model', {}), ensure_ascii=False)}
Devuelve sólo JSON: {{"additions":[{{"title":"heading sin emoji","cue":"pista o pregunta","development":"explicación respaldada"}}]}}.""")
    additions = payload.get("additions", []) if isinstance(payload, dict) else []
    next_order = max((section["order"] for section in document["sections"]), default=0) + 10
    for item in additions[:len(missing)]:
        title = clean_generated_heading(item.get("title", "Concepto pendiente"))
        cue = str(item.get("cue", "")).strip()
        development = str(item.get("development", "")).strip()
        if not cue or not development:
            continue
        section_id, cue_id, answer_id = (str(uuid.uuid4()) for _ in range(3))
        document["sections"].append({"id": section_id, "title": title, "order": next_order})
        document["blocks"].extend([
            {"id": cue_id, "section_id": section_id, "type": "question", "lane": "left", "reading_order": 10, "content": cue, "layout": {"gap_before": 0}, "sources": []},
            {"id": answer_id, "section_id": section_id, "type": "paragraph", "lane": "right", "reading_order": 20, "content": development, "layout": {"gap_before": 0}, "sources": []},
        ])
        document["relations"].append({"id": str(uuid.uuid4()), "from_block_id": cue_id, "to_block_id": answer_id, "type": "answers", "order": len(document["relations"]) * 10 + 10})
        next_order += 10
    state["cornell_document"] = validate_document(document)
    state["body_markdown"] = render_markdown(state["cornell_document"])
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
    if state.get("cornell_document"):
        repaired_blocks = iter(str(item).strip() for item in corrected)
        for block in state["cornell_document"].get("blocks", []):
            if block.get("type") == "mermaid":
                block["content"] = next(repaired_blocks)
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
    lines = ["## Conceptos Clave (Glosario)", ""]
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
    lines = ["## Flashcards", canonical_deck_tag(note.course_name, note.course_module), ""]
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
    processing = ["## Zona de Procesamiento (Fase 2: Deconstrucción)"]
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
    workflow.add_node("knowledge_model", knowledge_model_node)
    workflow.add_node("body", body_node)
    workflow.add_node("critic", critic_node)
    workflow.add_node("mermaid_repair", mermaid_repair_node)
    workflow.add_node("supplements", supplements_node)
    workflow.add_node("assemble", assemble_node)
    workflow.set_entry_point("context")
    workflow.add_edge("context", "evidence")
    workflow.add_edge("evidence", "knowledge_model")
    workflow.add_edge("knowledge_model", "body")
    workflow.add_edge("body", "critic")
    workflow.add_edge("critic", "mermaid_repair")
    workflow.add_edge("mermaid_repair", "supplements")
    workflow.add_edge("supplements", "assemble")
    workflow.add_edge("assemble", END)
    return workflow.compile(checkpointer=MemorySaver())
