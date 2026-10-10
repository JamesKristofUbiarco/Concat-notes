"""Pipeline v2: evidencia/novelty -> cuerpo -> glosario y tarjetas en paralelo."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
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
from app.evidence_inputs import brief_claims, terms, relevant_history, novelty_outline
from app.generation_runtime import GenerationClient, GenerationTimeout, array_schema, update_metrics
from app.note_sections import split_note_markdown
from app.reference_checks import reference_checks


class V2State(TypedDict, total=False):
    raw_note_id: str
    raw_note_data: dict[str, Any]
    flashcard_count: int
    historical_context: dict[str, Any]
    evidence_manifest: list[dict[str, Any]]
    class_knowledge_model: dict[str, Any]
    coverage_plan: list[dict[str, Any]]
    body_markdown: str
    glossary_markdown: str
    flashcards_markdown: str
    structured_markdown: str
    ai_comments: str
    metrics: dict[str, Any]
    additional_instructions: str
    original_glossary: str
    reference_checks: list[dict[str, str]]


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


def _invoke_json(llm: Any, prompt: str, attempts: int = 2, collection: str | None = None) -> Any:
    last_error: Exception | None = None
    for attempt in range(attempts):
        suffix = "" if attempt == 0 else "\nLa respuesta anterior no era JSON válido. Repite toda la salida sin Markdown y con comillas internas escapadas."
        try:
            payload = _json_payload(llm.invoke(prompt + suffix))
            if collection:
                rows = payload.get(collection) if isinstance(payload, dict) else payload
                if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                    raise ValueError("La colección JSON no es una lista de objetos")
            return payload
        except (ValueError, json.JSONDecodeError) as exc:
            last_error = exc
    raise ValueError(f"El modelo auxiliar no produjo JSON válido: {last_error}")


def _clean_markdown(value: str) -> str:
    value = value.strip()
    wrapper = re.match(r"\A(`{3,})(?:markdown|md|txt)?[ \t]*\n", value, re.IGNORECASE)
    if wrapper and re.search(rf"\n{re.escape(wrapper.group(1))}[ \t]*\Z", value):
        value = value[wrapper.end():]
        value = re.sub(rf"\n{re.escape(wrapper.group(1))}[ \t]*\Z", "", value)
    return value.strip()


_FRONTMATTER_RE = re.compile(r"\A(---[ \t]*\r?\n.*?\r?\n---[ \t]*(?:\r?\n|$))", re.DOTALL)
_VISIBLE_METADATA_RE = re.compile(
    r"^\*\*(?:Curso|Módulo|Módulo del curso|Instructor|Instructor/Autor|Plataforma|Fecha de clase):\*\*",
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
    if not frontmatter:
        frontmatter = "\n".join((
            "---", "tipo: fuente", "formato: curso_online",
            "estado: en_proceso", f"fecha: {_note_local_date(note)}", "---",
        ))
    visible_header = "\n".join((
        f"# 📚 {title}",
        f"**Curso:** [[{course}]]",
        f"**Módulo:** {module}",
        f"**Instructor:** {teacher} | **Plataforma:** {_single_line(getattr(note, 'platform', None))}",
    ))
    return "\n\n".join(part for part in (frontmatter, visible_header, remainder) if part).strip()


def normalize_body_headings(body: str) -> str:
    """Normalize recognizable headings only, never text inside fenced examples."""
    lines, fence = [], None
    for line in body.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if marker:
            value = marker.group(1)
            if fence is None:
                fence = value
            elif value[0] == fence[0] and len(value) >= len(fence) and not line[marker.end():].strip():
                fence = None
            lines.append(line)
            continue
        if fence is None:
            if re.match(r"^##\s+(?:🗺️?\s*)?Contexto Inicial(?:\s*\(Fase 1\))?\s*$", line, re.I):
                line = "## 🗺️ Contexto Inicial (Fase 1)"
            elif re.match(r"^##\s+(?:📝\s*)?Apuntes de Clase(?:\s*\(Captura Híbrida\))?\s*$", line, re.I):
                line = "## 📝 Apuntes de Clase (Captura Híbrida)"
            elif re.match(r"^###\s+\S", line) and not line.startswith("### 📌 "):
                line = re.sub(r"^###\s+", "### 📌 ", line)
        lines.append(line)
    return "\n".join(lines)


def validate_body_markdown(body: str) -> str:
    """Evita archivar una respuesta incompleta o una simulación como nota terminada."""
    body = _clean_markdown(body)
    frontmatter = _FRONTMATTER_RE.match(body)
    if frontmatter:
        body = body[frontmatter.end():].lstrip()
    lines = body.splitlines()
    if lines and re.match(r"^#(?!#)\s+", lines[0]):
        lines.pop(0)
        while lines and (not lines[0].strip() or _VISIBLE_METADATA_RE.match(lines[0].strip())):
            lines.pop(0)
        body = "\n".join(lines).strip()
    if not re.search(r"(?m)^## 🗺️ Contexto Inicial \(Fase 1\)\s*$", body):
        raise ValueError("Falta el contexto inicial de la nota.")
    if not re.search(r"(?m)^## 📝 Apuntes de Clase \(Captura Híbrida\)\s*$", body):
        raise ValueError("Falta la sección de apuntes de clase.")
    if not re.search(r"(?m)^### 📌 ", body):
        raise ValueError("Falta el desarrollo temático de la clase.")
    if re.search(r"(?i)simulated concept|synapse scholar|directiva e|pregunta de repaso \d+", body):
        raise ValueError("La salida contiene texto de simulación o instrucciones internas.")
    fence = None
    for line in body.splitlines():
        match = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if match:
            marker = match.group(1)
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence) and not line[match.end():].strip():
                fence = None
    if fence is not None:
        raise ValueError("La nota contiene un bloque de código sin cerrar.")
    return body


def _request_progress(config, phase):
    callback = config["configurable"].get("progress")
    return (lambda metrics: callback(phase, metrics)) if callback else None


def invoke_synthesis(messages: list[Any], resolved: llm_models.ResolvedModel, metrics=None, progress=None) -> tuple[Any, llm_models.ResolvedModel]:
    """Prueba otro modelo del catálogo ante indisponibilidad temporal del proveedor."""
    try:
        llm = GenerationClient(resolved, "content", max_tokens=10000, metrics=metrics, progress=progress)
        return llm.invoke(messages), resolved
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        temporary = isinstance(exc, GenerationTimeout) or status in {429, 502, 503, 504} or re.search(r"\b(?:429|502|503|504|rate.limit|timed? out)\b", str(exc), re.IGNORECASE)
        if not temporary:
            raise
        alternate = next((option for option in llm_models.MODEL_CATALOG["synthesis"]
                          if option["id"] != resolved.model_id and llm_models.model_is_configured(option)), None)
        if alternate is None:
            raise
        candidate = llm_models.resolve_model("synthesis", alternate["id"], allow_fallback=False)
        fallback = replace(candidate, requested_model=resolved.requested_model, fallback_used=True,
                           fallback_reason="El proveedor del modelo seleccionado no respondió temporalmente.")
        llm = GenerationClient(fallback, "content", max_tokens=10000, metrics=metrics, progress=progress)
        return llm.invoke(messages), fallback


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
        "retrieval": historical.get("retrieval", {}),
    }
    return state


def evidence_node(state: V2State, config: RunnableConfig) -> V2State:
    db = config["configurable"]["db"]
    note = db.query(models.RawNote).filter(models.RawNote.id == state["raw_note_id"]).first()
    started = time.monotonic()
    historical_ids = {item["id"] for item in state.get("historical_context", {}).get("claims", [])}
    historical = db.query(models.NoteClaim).filter(models.NoteClaim.id.in_(historical_ids)).all() if historical_ids else None
    resolved = llm_models.resolve_selected_model(db, "query_expansion")
    progress = config["configurable"].get("progress")
    state["evidence_manifest"] = extract_claims(note, db, historical=historical, metrics=state["metrics"],
        progress=(lambda details: progress("evidence", details)) if progress else None)
    state["metrics"].update({
        "evidence_ms": round((time.monotonic() - started) * 1000),
        "evidence_claims": len(state["evidence_manifest"]),
        "evidence_model_requested": resolved.requested_model,
        "evidence_model_effective": state["metrics"].get("evidence_model_effective", resolved.model_id),
    })
    return state


def knowledge_model_node(state: V2State, config: RunnableConfig) -> V2State:
    """Construye cobertura verificable sin imponer una metodología de composición."""
    db = config["configurable"]["db"]
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
    state["reference_checks"] = reference_checks(source)
    state["metrics"]["reference_checks"] = len(state["reference_checks"])
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
    state["metrics"].update({"knowledge_concepts": len(concepts), "coverage_units": len(plan)})
    return state


BODY_SYSTEM = """Redacta la nota de una clase en español claro, con el rigor de alguien que estudió y entendió el material.

Toma como referencia editorial este recorrido, sin copiar información de otras clases:
## 🗺️ Contexto Inicial (Fase 1)
Explica en dos o tres frases el problema específico de ESTA clase, qué parte del curso continúa y qué aprenderá el estudiante.

## 📝 Apuntes de Clase (Captura Híbrida)
### 📌 1. [Tema concreto de la clase]
**Contexto:** [qué se intenta resolver y por qué].
[Explicación causal en párrafos breves, seguida del código, fórmula, comparación o pasos que realmente se mostraron. Explica lo que hace cada pieza importante y el resultado observado.]
### 📌 2. [Siguiente tema, solo si hay otro]

Elige los subtítulos según los temas reales; agrupa detalles de un mismo tema. Usa listas para pasos o enumeraciones y tablas solo cuando ayuden a comparar. No hagas una lista exhaustiva de términos sin explicación. No añadas apartados vacíos, preguntas decorativas, citas inventadas ni comentarios genéricos sobre pedagogía o arquitectura.

Los hechos de la nota deben venir del material actual. El historial sirve para continuidad y enlaces `[[título de clase]]`, nunca como fuente de hechos nuevos. Si el material contiene un error técnico, indícalo con precisión y explica la corrección sin atribuirla al instructor. Si hay incertidumbre, márcala para revisión en vez de inventar. Distingue con cuidado `range(10)` de `range(n)`, tiempo de espacio y otros detalles que cambien el resultado.

Esta nota es progresiva: dedica el desarrollo a NEW, EXTENDS, APPLIES, CLARIFIES y CONTRADICTS. Para REPEATS basta un recordatorio mínimo y un enlace a la clase correspondiente si su título está disponible; no vuelvas a desarrollar una definición o explicación anterior. No elimines aplicaciones, ejemplos, cambios de opciones, valores o matices realmente nuevos. Si toda la clase es repaso, explícalo de forma breve sin inventar novedades.

Preserva los fragmentos de código, comandos y valores medidos tal como aparecen en la fuente. No cambies la sintaxis de Python 2 a Python 3 en silencio; explica la diferencia si importa. No atribuyas un lenguaje de programación equivocado a un fragmento. Coloca cada fragmento junto al tema que demuestra y explica su significado. No conviertas salidas de terminal en código ejecutable.

Mantén los términos técnicos canónicos en inglés cuando aporten precisión, con explicación en español. La primera vez que introduzcas un término, puedes poner una traducción breve entre paréntesis; evita repetirla en cada oración y evita escribir párrafos enteros en inglés. Los nombres de APIs, variables y funciones se respetan literalmente.

Antes de responder, revisa ortografía y concordancia del español; evita palabras inglesas sueltas que no sean términos técnicos. Elimina frases redundantes y no repitas la misma explicación entre temas.

Devuelve solo el cuerpo Markdown que empieza por `## 🗺️ Contexto Inicial (Fase 1)` y contiene `## 📝 Apuntes de Clase (Captura Híbrida)` con al menos un tema `### 📌`. No generes frontmatter, H1, metadatos visibles, glosario, flashcards ni zona de procesamiento: los añade el sistema. No envuelvas la nota en una cerca de código."""


def body_node(state: V2State, config: RunnableConfig) -> V2State:
    db = config["configurable"]["db"]
    note = db.query(models.RawNote).filter(models.RawNote.id == state["raw_note_id"]).first()
    resolved = llm_models.resolve_selected_model(db, "synthesis")
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
{json.dumps(brief_claims(state.get('evidence_manifest', [])), ensure_ascii=False)}

MODELO DE CONOCIMIENTO DE LA CLASE:
{json.dumps({key: value for key, value in state.get('class_knowledge_model', {}).items() if key in ('methods', 'uncertainties')}, ensure_ascii=False)}

PLAN DE COBERTURA VERIFICABLE:
{json.dumps(state.get('coverage_plan', []), ensure_ascii=False)}

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

INSTRUCCIONES ADICIONALES DEL USUARIO PARA ESTA REGENERACIÓN:
{state.get('additional_instructions', '')}

REFERENCIAS REVISADAS PARA ERRORES FRECUENTES, SEPARADAS DEL MATERIAL DEL INSTRUCTOR:
{json.dumps(state.get('reference_checks', []), ensure_ascii=False)}
Si el material contradice estas referencias, explica la corrección y cita su URL. No repitas el error como hecho ni atribuyas la corrección al instructor. Estos matices tienen prioridad también en el glosario y las tarjetas.

Escribe la nota siguiendo la estructura editorial indicada. Usa el plan de cobertura solo para revisar que no falten temas respaldados: no conviertas cada entrada en un subtítulo. Conecta conceptos con ejemplos concretos del material."""
    started = time.monotonic()
    output, resolved = invoke_synthesis([
        SystemMessage(content=BODY_SYSTEM), HumanMessage(content=prompt)
    ], resolved, state["metrics"], progress=_request_progress(config, "content"))
    body = _clean_markdown(_content(output))
    # Glosario, flashcards y deconstrucción pertenecen a nodos especializados.
    body = split_note_markdown(body)["content"].rstrip()
    body = normalize_body_headings(body)
    try:
        state["body_markdown"] = validate_body_markdown(body)
    except ValueError as error:
        # Repair presentation only; do not reprocess the source or overwrite good output.
        repair = GenerationClient(resolved, "content_repair", max_tokens=10000, metrics=state["metrics"], progress=_request_progress(config, "content"))
        repaired = repair.invoke([SystemMessage(content="Repara únicamente la estructura Markdown de la nota proporcionada. Conserva todos los hechos, código y explicaciones, sin añadir hechos. " + BODY_SYSTEM),
            HumanMessage(content=f"Error de formato: {error}\nNOTA A REPARAR:\n{body}")])
        state["body_markdown"] = validate_body_markdown(normalize_body_headings(_clean_markdown(_content(repaired))))
        state["metrics"]["body_format_repairs"] = 1
    state["ai_comments"] = (
        f"El modelo seleccionado no respondió temporalmente; esta nota se generó con {resolved.model_id}."
        if resolved.fallback_used else ""
    )
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
    llm = GenerationClient(resolved, "diagrams", max_tokens=4096, metrics=state["metrics"], progress=_request_progress(config, "diagrams"))
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
    related_terms = relevant_history(existing_terms,
        state.get("body_markdown", "") + json.dumps(brief_claims(state.get("evidence_manifest", [])), ensure_ascii=False)
        + json.dumps(state.get("historical_context", {}).get("claims", []), ensure_ascii=False),
        text=lambda term: term, limit=60, budget=4000)
    prompt = f"""Genera únicamente el delta de glosario de esta clase.
No redefinas términos existentes ni conviertas REPEATS/APPLIES en definiciones nuevas. Para EXTENDS usa kind=extension; para conocimiento NEW usa kind=definition.
Incluye solo conceptos técnicos que la clase realmente define o amplía. Una tarea de lectura, un consejo de entrevista, un nombre de sección o una categoría inventada no son entradas de glosario. No hagas una entrada por cada punto del manifiesto.
Usa siempre el término técnico canónico en inglés como `term`, incluso si la clase lo menciona en español. Incluye su traducción breve al español en `term_es`.
Escribe `content` en español. En una definición nueva, presenta el término inglés y menciona su traducción una sola vez entre paréntesis; ejemplo: "Un deadlock (interbloqueo) es una situación...". No pongas la traducción en el título.
Términos existentes relacionados: {json.dumps(related_terms, ensure_ascii=False)}
Mapa de novedad (los hechos están en el cuerpo): {json.dumps(novelty_outline(state.get('evidence_manifest', [])), ensure_ascii=False)}
Cuerpo final: {state.get('body_markdown', '')}
Referencias revisadas: {json.dumps(state.get('reference_checks', []), ensure_ascii=False)}
Instrucciones adicionales del usuario: {state.get('additional_instructions', '')}
Glosario anterior de esta clase, sólo como referencia de qué corregir, no como fuente de hechos: {state.get('original_glossary', '')}
Si se proporciona un glosario anterior, corrige sus conceptos respaldados por el material, pero no repitas definiciones ya presentes en clases anteriores. Una ampliación debe explicar sólo la diferencia. Descarta entradas erróneas.
Devuelve sólo {{"entries":[{{"term":"English term","term_es":"traducción al español","kind":"definition|extension","content":"..."}}]}}."""
    payload = _invoke_json(llm, prompt, collection="entries")
    if isinstance(payload, dict):
        payload = payload.get("entries", [])
    lines = ["## 📖 Conceptos Clave (Glosario)", ""]
    seen = set()
    if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
        raise ValueError("Glosario inválido")
    existing_keys = {term.casefold() for term in existing_terms}
    for item in payload:
        term = str(item.get("term", "")).strip()
        content = str(item.get("content", "")).strip()
        key = term.casefold()
        if not term or not content or key in seen or (key in existing_keys and item.get("kind") != "extension"):
            continue
        seen.add(key)
        tag = "#definicion-ampliada" if item.get("kind") == "extension" else "#definicion"
        lines.extend([f"**{term}** {tag}", content, ""])
    return "\n".join(lines).strip()


def _card_key(question: str) -> str:
    return re.sub(r"[^a-z0-9áéíóúüñ]+", "", question.lower()) + "|" + "|".join(sorted(_card_literals(question)))


def _card_literals(text: str) -> set[str]:
    return set(re.findall(r"(?<!\w)-{1,2}[A-Za-z]\w*|\b\w*\d[\w.]*\b|`[^`]+`", text))


def _card_terms(question: str) -> set[str]:
    return terms(question)


def _flashcard_call(llm: Any, note: models.RawNote, state: V2State) -> str:
    context = state.get("historical_context", {})
    historical = context.get("flashcards", [])
    all_historical = context.get("flashcard_history", historical)
    claims = state.get("evidence_manifest", [])
    eligible = [item for item in claims if item.get("novelty_relation", "NEW") != "REPEATS"]
    target = min(state.get("flashcard_count", 5), max(1, len(eligible)))
    lines = ["## 🗃️ Flashcards", canonical_deck_tag(note.course_name, note.course_module), ""]
    if claims and not eligible:
        update_metrics(state["metrics"], flashcards_generated=0, flashcards_reason="repaso_sin_novedades")
        return "\n\n".join(lines).strip()
    prompt = f"""Crea hasta {target} flashcards sobre información nueva relevante: NEW, EXTENDS, APPLIES, CLARIFIES o CONTRADICTS.
La cantidad es un máximo, no una cuota. Devuelve menos si no hay suficientes ideas diferentes; nunca inventes tarjetas ni dividas una idea en paráfrasis para completar la cantidad. No generes otra tarjeta para decir la misma idea al revés o en forma negativa.
Cada respuesta debe justificarse con el cuerpo actual. Pregunta una idea concreta y responde en una o dos frases precisas. No repitas teoría de las tarjetas históricas; conserva preguntas sobre aplicaciones o matices realmente nuevos.
Preguntas históricas relevantes: {json.dumps([item.get('question', '') for item in historical], ensure_ascii=False)}
Mapa de novedades (los hechos están en el cuerpo): {json.dumps(novelty_outline(eligible), ensure_ascii=False)}
Cuerpo: {state.get('body_markdown', '')}
Referencias revisadas: {json.dumps(state.get('reference_checks', []), ensure_ascii=False)}
Si la fuente original contiene una simplificación incorrecta, usa la corrección del cuerpo y de estas referencias, no repitas el error en la respuesta.
Instrucciones adicionales: {state.get('additional_instructions', '')}
Devuelve sólo {{"flashcards":[{{"question":"...","answer":"..."}}]}}."""
    historical_keys = {_card_key(item.get("question", "") + " " + item.get("answer", "")) for item in all_historical}
    historical_terms = [(_card_terms(item.get("question", "") + " " + item.get("answer", "")),
        _card_literals(item.get("question", "") + " " + item.get("answer", ""))) for item in all_historical]
    cards = []
    seen = set(historical_keys)
    rejected = 0
    for attempt in range(2):
        suffix = "" if attempt == 0 else "\nEl intento anterior no produjo tarjetas válidas nuevas. Corrige JSON y usa únicamente diferencias reales respecto del historial. Si es sólo repaso, devuelve flashcards vacío."
        try:
            payload = _json_payload(llm.invoke(prompt + suffix))
            if isinstance(payload, dict):
                payload = payload.get("flashcards")
            if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
                raise ValueError("Flashcards inválidas")
        except (ValueError, json.JSONDecodeError):
            if attempt == 1:
                raise
            continue
        for item in payload:
            question = str(item.get("question", "")).strip()
            answer = str(item.get("answer", "")).strip()
            key = _card_key(question + " " + answer)
            words = _card_terms(question + " " + answer)
            literals = _card_literals(question + " " + answer)
            too_similar = any(literals == previous_literals and words and len(words & previous) / max(1, len(words | previous)) >= 0.92 for previous, previous_literals in historical_terms)
            if not question or not answer or key in seen or too_similar:
                rejected += 1
                continue
            seen.add(key)
            cards.append((question, answer))
            historical_terms.append((words, literals))
            if len(cards) == target:
                break
        if cards or not payload:
            break
    update_metrics(state["metrics"], flashcards_requested=state.get("flashcard_count", 5), flashcards_generated=len(cards), flashcards_duplicates_rejected=rejected)
    if not cards:
        update_metrics(state["metrics"], flashcards_reason="sin_tarjetas_nuevas_validas")
        state["ai_comments"] = (state.get("ai_comments", "") + " No se encontraron flashcards nuevas válidas; se conservó el contenido sin inventar tarjetas.").strip()
    lines.extend(f"{question}::{answer}" for question, answer in cards)
    return "\n\n".join(lines).strip()


def supplement_client(resolved, purpose, state, progress=None):
    properties = ({"term": {"type": "string"}, "term_es": {"type": "string"},
        "kind": {"type": "string", "enum": ["definition", "extension"]}, "content": {"type": "string"}}
        if purpose == "glossary" else {"question": {"type": "string"}, "answer": {"type": "string"}})
    return GenerationClient(resolved, purpose, max_tokens=4096, schema=array_schema("entries" if purpose == "glossary" else "flashcards", properties), metrics=state["metrics"], progress=progress)


def supplements_node(state: V2State, config: RunnableConfig) -> V2State:
    db = config["configurable"]["db"]
    note = db.query(models.RawNote).filter(models.RawNote.id == state["raw_note_id"]).first()
    from app.glossary import parse_glossary_entries
    from app.knowledge import prior_note_ids
    preceding = db.query(models.RawNote).filter(models.RawNote.id.in_(prior_note_ids(db, note))).all()
    existing_terms = [entry["term"] for other in preceding if other.processed_note
        for entry in parse_glossary_entries(other.processed_note.structured_markdown, other.class_title)]
    resolved = llm_models.resolve_selected_model(db, "query_expansion")
    started = time.monotonic()

    def glossary_job() -> str:
        return _glossary_call(supplement_client(resolved, "glossary", state, progress=_request_progress(config, "supplements")), note, state, existing_terms)

    def flashcards_job() -> str:
        return _flashcard_call(supplement_client(resolved, "flashcards", state, progress=_request_progress(config, "supplements")), note, state)

    with ThreadPoolExecutor(max_workers=2) as executor:
        glossary_future = executor.submit(glossary_job)
        flashcards_future = executor.submit(flashcards_job)
        state["glossary_markdown"] = glossary_future.result()
        state["flashcards_markdown"] = flashcards_future.result()
    state["metrics"].update({
        "supplements_ms": round((time.monotonic() - started) * 1000),
        "auxiliary_model_requested": resolved.requested_model,
        "auxiliary_model_effective": state["metrics"].get("auxiliary_model_effective", resolved.model_id),
        "auxiliary_fallback": state["metrics"].get("auxiliary_fallback", resolved.fallback_used),
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
    workflow.add_node("knowledge_model", knowledge_model_node)
    workflow.add_node("body", body_node)
    workflow.add_node("mermaid_repair", mermaid_repair_node)
    workflow.add_node("supplements", supplements_node)
    workflow.add_node("assemble", assemble_node)
    workflow.set_entry_point("context")
    workflow.add_edge("context", "evidence")
    workflow.add_edge("evidence", "knowledge_model")
    workflow.add_edge("knowledge_model", "body")
    workflow.add_edge("body", "mermaid_repair")
    workflow.add_edge("mermaid_repair", "supplements")
    workflow.add_edge("supplements", "assemble")
    workflow.add_edge("assemble", END)
    return workflow.compile(checkpointer=MemorySaver())
