"""Documento Cornell canónico, renderer, revisiones y patches atómicos."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
import re
import uuid
from typing import Any, Iterable

from sqlalchemy.orm import Session, object_session

from app import llm_models, models, schemas


SCHEMA_VERSION = "1.0"
DEFAULT_WORKSPACE_SLUG = "default"
ALLOWED_OPERATIONS = {
    "replace_text", "replace_block", "insert_before", "insert_after", "delete_block",
    "move_block", "change_block_type", "move_to_lane", "create_relation",
    "delete_relation", "change_relation", "rename_section", "insert_section",
    "delete_section", "move_section",
}
HEADING_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0000FE0F]+"
)
FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n?", re.DOTALL)


class StructuredNoteError(ValueError):
    pass


class StaleRevisionError(StructuredNoteError):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


def _as_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None:
        return None
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _content(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return " ".join(
            str(item.get("text", "")) if isinstance(item, dict) else str(item)
            for item in content
        ).strip()
    return str(content).strip()


def _json_payload(response: Any) -> dict[str, Any]:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", _content(response), flags=re.IGNORECASE)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise StructuredNoteError("El agente editor no devolvió JSON válido.")
    payload = json.loads(text[start:end + 1])
    if not isinstance(payload, dict):
        raise StructuredNoteError("La propuesta del agente debe ser un objeto JSON.")
    return payload


def get_default_workspace(db: Session) -> models.Workspace:
    workspace = db.query(models.Workspace).filter(models.Workspace.slug == DEFAULT_WORKSPACE_SLUG).first()
    if workspace is None:
        workspace = models.Workspace(slug=DEFAULT_WORKSPACE_SLUG, name="Mi espacio")
        db.add(workspace)
        db.flush()
    return workspace


BUILTIN_STYLE_PROFILES = (
    ("cornell-conceptual", "Cornell conceptual", "Preguntas de recuperación y explicaciones progresivas."),
    ("laboratorio-tecnico", "Laboratorio técnico", "Código, salida, explicación y advertencias en secuencia."),
    ("procedimiento-guiado", "Procedimiento guiado", "Métodos completos con pasos, decisiones y comprobaciones."),
    ("comparativa-decisiones", "Comparativa y decisiones", "Alternativas, criterios, contrastes y consecuencias."),
    ("proyecto-referencia", "Proyecto y referencia práctica", "Objetivos, implementación, recursos y resultados."),
)


def ensure_builtin_profiles(db: Session) -> list[models.NoteStyleProfile]:
    workspace = get_default_workspace(db)
    existing = {
        item.slug: item
        for item in db.query(models.NoteStyleProfile).filter(
            models.NoteStyleProfile.workspace_id == workspace.id
        ).all()
    }
    for slug, name, description in BUILTIN_STYLE_PROFILES:
        if slug not in existing:
            profile = models.NoteStyleProfile(
                workspace_id=workspace.id,
                slug=slug,
                name=name,
                description=description,
                is_builtin=True,
                rules_json={
                    "headings": {"allow_generated_emoji": False},
                    "progression": ["intuition", "context", "technical_explanation", "examples", "caveats"],
                    "preserve_code": True,
                    "glossary": {"primary_language": "en", "explanation_language": "es"},
                },
            )
            db.add(profile)
            existing[slug] = profile
    db.flush()
    return list(existing.values())


def clean_generated_heading(value: str) -> str:
    value = HEADING_EMOJI_RE.sub("", str(value or ""))
    value = re.sub(r"\s+", " ", value).strip(" #-\t")
    return value or "Sección"


def empty_document(
    *,
    document_id: str,
    title: str,
    origin_kind: str,
    raw_note_id: str | None = None,
    course_name: str = "",
    course_module: str = "",
    class_title: str = "",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    section_id = _uuid()
    cue_id = _uuid()
    detail_id = _uuid()
    return {
        "schema_version": SCHEMA_VERSION,
        "document_id": document_id,
        "origin": {"kind": origin_kind, "raw_note_id": raw_note_id},
        "metadata": {
            "title": title,
            "course_name": course_name,
            "course_module": course_module,
            "class_title": class_title or title,
            "teacher": "",
            "platform": "",
            "tags": tags or [],
        },
        "composition": {"profile_slug": "cornell-conceptual", "profile_version": 1},
        "sections": [{"id": section_id, "title": "Notas", "order": 10}],
        "blocks": [
            {"id": cue_id, "section_id": section_id, "type": "question", "lane": "left", "reading_order": 10, "content": "", "layout": {"gap_before": 0}, "sources": []},
            {"id": detail_id, "section_id": section_id, "type": "paragraph", "lane": "right", "reading_order": 20, "content": "", "layout": {"gap_before": 0}, "sources": []},
        ],
        "relations": [],
    }


def validate_document(document: dict[str, Any]) -> dict[str, Any]:
    try:
        validated = schemas.NoteDocumentData.model_validate(document).model_dump(mode="json")
    except Exception as exc:
        raise StructuredNoteError(f"Documento Cornell inválido: {exc}") from exc

    section_ids = [item["id"] for item in validated["sections"]]
    block_ids = [item["id"] for item in validated["blocks"]]
    relation_ids = [item["id"] for item in validated["relations"]]
    if len(section_ids) != len(set(section_ids)):
        raise StructuredNoteError("Los IDs de sección deben ser únicos.")
    if len(block_ids) != len(set(block_ids)):
        raise StructuredNoteError("Los IDs de bloque deben ser únicos.")
    if len(relation_ids) != len(set(relation_ids)):
        raise StructuredNoteError("Los IDs de relación deben ser únicos.")
    section_set = set(section_ids)
    block_set = set(block_ids)
    for block in validated["blocks"]:
        if block["section_id"] not in section_set:
            raise StructuredNoteError("Un bloque apunta a una sección inexistente.")
        gap = int(block.get("layout", {}).get("gap_before", 0) or 0)
        if not 0 <= gap <= 40:
            raise StructuredNoteError("El espacio anterior debe estar entre 0 y 40 unidades.")
    for relation in validated["relations"]:
        if relation["from_block_id"] not in block_set or relation["to_block_id"] not in block_set:
            raise StructuredNoteError("Una relación apunta a un bloque inexistente.")
        if relation["from_block_id"] == relation["to_block_id"]:
            raise StructuredNoteError("Un bloque no puede relacionarse consigo mismo.")
    return validated


def validate_asset_references(db: Session, document: dict[str, Any]) -> None:
    for block in document.get("blocks", []):
        asset = block.get("asset")
        if block.get("type") != "image" or not isinstance(asset, dict):
            continue
        raw_id = _as_uuid(asset.get("raw_note_image_id"))
        document_id = _as_uuid(asset.get("document_asset_id"))
        storage_key = str(asset.get("storage_key") or "")
        valid = bool(raw_id and db.get(models.RawNoteImage, raw_id)) or bool(
            document_id and db.get(models.DocumentAsset, document_id)
        )
        if storage_key and not valid:
            valid = bool(db.query(models.RawNoteImage).filter(models.RawNoteImage.filename == storage_key).first()) or bool(
                db.query(models.DocumentAsset).filter(models.DocumentAsset.storage_key == storage_key).first()
            )
        if not valid:
            raise StructuredNoteError("Una imagen referencia un asset inexistente.")


def _render_block(block: dict[str, Any], *, assets_subdirectory: str = "ANEXOS") -> str:
    kind = block["type"]
    content = block.get("content", "")
    if isinstance(content, dict):
        text = str(content.get("text", content.get("code", content.get("value", ""))))
    elif isinstance(content, list):
        text = "\n".join(str(item) for item in content)
    else:
        text = str(content or "")
    text = text.strip()
    if not text and kind != "image":
        return ""
    if kind == "question":
        return f"### {text}"
    if kind in {"concept", "heading"}:
        return f"### {text}"
    if kind in {"bullet_list", "numbered_list"}:
        items = content if isinstance(content, list) else [line.strip(" -*0123456789.") for line in text.splitlines() if line.strip()]
        marker = "-" if kind == "bullet_list" else None
        return "\n".join(f"{marker or f'{index}.'} {item}" for index, item in enumerate(items, 1))
    if kind in {"code", "command", "code_output"}:
        language = ""
        code = text
        if isinstance(content, dict):
            language = str(content.get("language", content.get("lang", "")))
            code = str(content.get("code", content.get("text", "")))
        if kind == "command" and not language:
            language = "bash"
        if kind == "code_output" and not language:
            language = "text"
        return f"```{language}\n{code.rstrip()}\n```"
    if kind == "mermaid":
        return f"```mermaid\n{text}\n```"
    if kind == "image":
        asset = block.get("asset") or {}
        alt = str(asset.get("alt", text or "Imagen"))
        path = str(asset.get("relative_path") or asset.get("url") or "")
        if path and not path.startswith(("http://", "https://", "/")) and "/" not in path:
            path = f"{assets_subdirectory}/{path}"
        return f"![{alt}]({path})" if path else f"> Imagen pendiente: {alt}"
    if kind in {"warning", "callout"}:
        label = "WARNING" if kind == "warning" else "NOTE"
        lines = text.splitlines() or [""]
        return "\n".join([f"> [!{label}]", *(f"> {line}" for line in lines)])
    if kind == "quote":
        return "\n".join(f"> {line}" for line in text.splitlines())
    return text


def render_markdown(document: dict[str, Any], *, assets_subdirectory: str = "ANEXOS") -> str:
    document = validate_document(document)
    metadata = document["metadata"]
    title = str(metadata.get("title") or metadata.get("class_title") or "Nota").strip()
    course = str(metadata.get("course_name") or "").strip()
    module = str(metadata.get("course_module") or "").strip()
    teacher = str(metadata.get("teacher") or "").strip()
    platform = str(metadata.get("platform") or "").strip()
    lines = [f"# {title}"]
    if course:
        lines.append(f"**Curso:** {course}")
    details = []
    if module:
        details.append(f"**Módulo:** {module}")
    if teacher:
        details.append(f"**Instructor/Autor:** {teacher}")
    if platform:
        details.append(f"**Plataforma:** {platform}")
    if details:
        lines.append(" | ".join(details))

    blocks_by_section: dict[str, list[dict[str, Any]]] = {}
    for block in document["blocks"]:
        blocks_by_section.setdefault(block["section_id"], []).append(block)
    for section in sorted(document["sections"], key=lambda item: item["order"]):
        section_blocks = sorted(blocks_by_section.get(section["id"], []), key=lambda item: item["reading_order"])
        if not section_blocks:
            continue
        lines.append(f"## {section['title']}")
        for block in section_blocks:
            rendered = _render_block(block, assets_subdirectory=assets_subdirectory)
            if rendered:
                lines.append(rendered)
    return "\n\n".join(lines).strip() + "\n"


def markdown_to_document(markdown: str, note: models.RawNote, document_id: str) -> dict[str, Any]:
    """Parser conservador: preserva cada sección como Markdown y añade una pista conceptual."""
    body = FRONTMATTER_RE.sub("", markdown.strip(), count=1)
    body = re.sub(r"^#\s+[^\n]+\n", "", body, count=1)
    body = re.sub(r"^(?:\*\*(?:Curso|Instructor/Autor|Módulo|Fecha de clase):\*\*.*\n?)+", "", body, flags=re.MULTILINE)
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", body, flags=re.MULTILINE))
    sections: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    if not matches:
        matches = [re.match(r"", body)] if body else []
    for index, match in enumerate(matches):
        start = match.end() if match and match.group(0) else 0
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        raw_title = match.group(1) if match and match.group(0) else "Contenido"
        title = clean_generated_heading(raw_title)
        content = body[start:end].strip()
        section_id = _uuid()
        cue_id = _uuid()
        detail_id = _uuid()
        sections.append({"id": section_id, "title": title, "order": (index + 1) * 10})
        blocks.extend([
            {
                "id": cue_id, "section_id": section_id, "type": "concept", "lane": "left",
                "reading_order": (index + 1) * 100, "content": title,
                "layout": {"gap_before": 0}, "sources": [],
            },
            {
                "id": detail_id, "section_id": section_id, "type": "markdown", "lane": "right",
                "reading_order": (index + 1) * 100 + 10, "content": content,
                "layout": {"gap_before": 0}, "sources": [],
            },
        ])
        relations.append({
            "id": _uuid(), "from_block_id": cue_id, "to_block_id": detail_id,
            "type": "explains", "order": (index + 1) * 10,
        })
    document = {
        "schema_version": SCHEMA_VERSION,
        "document_id": document_id,
        "origin": {"kind": "generated_class", "raw_note_id": str(note.id)},
        "metadata": {
            "title": note.class_title,
            "course_name": note.course_name,
            "course_module": note.course_module,
            "class_title": note.class_title,
            "teacher": note.teacher,
            "platform": note.platform,
            "tags": [],
        },
        "composition": {"profile_slug": "cornell-conceptual", "profile_version": 1, "imported_from_markdown": True},
        "sections": sections or [{"id": _uuid(), "title": "Contenido", "order": 10}],
        "blocks": blocks,
        "relations": relations,
    }
    return validate_document(document)


def _create_revision(
    db: Session,
    record: models.StructuredNoteDocument,
    document: dict[str, Any],
    *,
    change_kind: str,
    summary: str,
    actor: str,
    provenance: dict[str, Any] | None = None,
) -> models.NoteRevision:
    validated = validate_document(document)
    validate_asset_references(db, validated)
    rendered = render_markdown(validated)
    revision = models.NoteRevision(
        document_id=record.id,
        parent_revision_id=record.current_revision_id,
        revision_number=record.revision_number + 1,
        change_kind=change_kind,
        change_summary=summary,
        actor=actor,
        document_json=validated,
        rendered_markdown=rendered,
        provenance=provenance or {},
    )
    db.add(revision)
    db.flush()
    record.document_json = validated
    record.rendered_markdown = rendered
    record.current_revision_id = revision.id
    record.revision_number = revision.revision_number
    if record.raw_note_id and record.origin_kind == "generated_class" and record.migration_status == "native":
        processed = db.query(models.ProcessedNote).filter(
            models.ProcessedNote.raw_note_id == record.raw_note_id
        ).first()
        if processed is not None:
            processed.structured_markdown = rendered
    _reconcile_flashcard_candidates(db, record, revision)
    db.flush()
    return revision


def _reconcile_flashcard_candidates(
    db: Session, record: models.StructuredNoteDocument, revision: models.NoteRevision,
) -> None:
    """Crea candidatas desde relaciones answers sin alterar tarjetas estudiadas."""
    from app.flashcards import fingerprint
    from app.knowledge import ZERO_VECTOR

    blocks = {str(item["id"]): item for item in record.document_json.get("blocks", [])}
    for relation in record.document_json.get("relations", []):
        if relation.get("type") != "answers":
            continue
        question_block = blocks.get(str(relation.get("from_block_id")))
        answer_block = blocks.get(str(relation.get("to_block_id")))
        if not question_block or not answer_block:
            continue
        question = str(question_block.get("content") or "").strip()
        answer = str(answer_block.get("content") or "").strip()
        if len(question) < 3 or len(answer) < 3:
            continue
        card_fingerprint = fingerprint(question)
        card = db.query(models.FlashcardRecord).filter(
            models.FlashcardRecord.fingerprint == card_fingerprint,
            models.FlashcardRecord.raw_note_id == record.raw_note_id,
        ).first() if record.raw_note_id else None
        if card is None:
            card = db.query(models.FlashcardRecord).filter(
                models.FlashcardRecord.structured_document_id == record.id,
                models.FlashcardRecord.fingerprint == card_fingerprint,
            ).first()
        if card is None:
            card = models.FlashcardRecord(
                raw_note_id=record.raw_note_id,
                structured_document_id=record.id,
                question=question,
                answer=answer,
                fingerprint=card_fingerprint,
                embedding=ZERO_VECTOR,
                is_dummy_embedding=True,
                is_active=False,
                candidate_status="candidate",
            )
            db.add(card)
            db.flush()
        else:
            card.structured_document_id = record.id
            if card.answer != answer:
                card.answer = answer
                card.embedding = ZERO_VECTOR
                card.is_dummy_embedding = True
                if card.is_active:
                    card.candidate_status = "needs_review"
        source = db.query(models.FlashcardSource).filter(
            models.FlashcardSource.flashcard_id == card.id,
            models.FlashcardSource.document_id == record.id,
            models.FlashcardSource.block_id == _as_uuid(question_block["id"]),
        ).first()
        if source is None:
            source = models.FlashcardSource(
                flashcard_id=card.id, document_id=record.id,
                block_id=_as_uuid(question_block["id"]), source_revision_id=revision.id,
            )
            db.add(source)
        else:
            source.source_revision_id = revision.id


def create_manual_document(db: Session, payload: schemas.StructuredNoteCreate) -> models.StructuredNoteDocument:
    workspace = get_default_workspace(db)
    ensure_builtin_profiles(db)
    if payload.collection_id and not db.get(models.NoteCollection, payload.collection_id):
        raise StructuredNoteError("La colección indicada no existe.")
    if payload.origin_kind == "manual_class_companion" and not payload.linked_raw_note_id:
        raise StructuredNoteError("Una nota complementaria debe vincularse con una clase.")
    record = models.StructuredNoteDocument(
        workspace_id=workspace.id,
        raw_note_id=payload.linked_raw_note_id,
        collection_id=payload.collection_id,
        origin_kind=payload.origin_kind,
        migration_status="native",
        document_json={},
    )
    db.add(record)
    db.flush()
    document = empty_document(
        document_id=str(record.id), title=payload.title, origin_kind=payload.origin_kind,
        raw_note_id=str(payload.linked_raw_note_id) if payload.linked_raw_note_id else None,
        course_name=payload.course_name, course_module=payload.course_module,
        class_title=payload.class_title, tags=payload.tags,
    )
    _create_revision(db, record, document, change_kind="created", summary="Nota creada", actor="user")
    db.commit()
    db.refresh(record)
    return record


def ensure_document_for_processed_note(
    db: Session, note: models.RawNote, processed: models.ProcessedNote,
    native_document: dict[str, Any] | None = None,
) -> models.StructuredNoteDocument:
    existing = db.query(models.StructuredNoteDocument).filter(
        models.StructuredNoteDocument.raw_note_id == note.id,
        models.StructuredNoteDocument.origin_kind == "generated_class",
    ).first()
    if existing:
        if native_document is not None:
            public_markdown = processed.structured_markdown
            document = deepcopy(native_document)
            document["document_id"] = str(existing.id)
            document.setdefault("origin", {})["raw_note_id"] = str(note.id)
            existing.migration_status = "native"
            _create_revision(
                db, existing, document, change_kind="regenerated",
                summary="Nota Cornell regenerada", actor="agent",
                provenance={"pipeline": "cornell-v1"},
            )
            # La salida pública incluye todavía los derivados compatibles del pipeline.
            processed.structured_markdown = public_markdown
            db.commit()
            db.refresh(existing)
        return existing
    workspace = get_default_workspace(db)
    ensure_builtin_profiles(db)
    record = models.StructuredNoteDocument(
        workspace_id=workspace.id,
        raw_note_id=note.id,
        origin_kind="generated_class",
        migration_status="native" if native_document is not None else "parsed",
        document_json={},
    )
    db.add(record)
    db.flush()
    if native_document is not None:
        document = deepcopy(native_document)
        document["document_id"] = str(record.id)
        document.setdefault("origin", {})["raw_note_id"] = str(note.id)
    else:
        document = markdown_to_document(processed.structured_markdown, note, str(record.id))
    public_markdown = processed.structured_markdown
    _create_revision(
        db, record, document, change_kind="generated", summary="Documento Cornell generado",
        actor="agent", provenance={"pipeline": "cornell-v1" if native_document is not None else "markdown-transition"},
    )
    if native_document is not None:
        processed.structured_markdown = public_markdown
    db.commit()
    db.refresh(record)
    return record


def serialize_document(record: models.StructuredNoteDocument) -> dict[str, Any]:
    payload = deepcopy(record.document_json or {})
    metadata = payload.get("metadata", {})
    db = object_session(record)
    # Las URLs públicas son una proyección de lectura, no se vuelven canónicas.
    for block in payload.get("blocks", []):
        asset = block.get("asset")
        if block.get("type") == "image" and isinstance(asset, dict) and asset.get("raw_note_image_id"):
            image = db.get(models.RawNoteImage, _as_uuid(asset["raw_note_image_id"])) if db else None
            if image:
                asset["url"] = image.image_url
                asset.setdefault("filename", image.filename)
    return {
        "id": str(record.id),
        "raw_note_id": str(record.raw_note_id) if record.raw_note_id else None,
        "collection_id": str(record.collection_id) if record.collection_id else None,
        "origin_kind": record.origin_kind,
        "schema_version": record.schema_version,
        "migration_status": record.migration_status,
        "current_revision_id": str(record.current_revision_id) if record.current_revision_id else None,
        "revision_number": record.revision_number,
        "title": metadata.get("title") or metadata.get("class_title") or "Nota",
        "course_name": metadata.get("course_name", ""),
        "tags": metadata.get("tags", []),
        "document": payload,
        "rendered_markdown": record.rendered_markdown,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def list_documents(
    db: Session, *, origin: str | None = None, collection_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    workspace = get_default_workspace(db)
    query = db.query(models.StructuredNoteDocument).filter(
        models.StructuredNoteDocument.workspace_id == workspace.id
    )
    if origin:
        query = query.filter(models.StructuredNoteDocument.origin_kind == origin)
    if collection_id:
        query = query.filter(models.StructuredNoteDocument.collection_id == collection_id)
    return [serialize_document(item) for item in query.order_by(models.StructuredNoteDocument.updated_at.desc()).all()]


def _find(items: list[dict[str, Any]], target_id: str, label: str) -> tuple[int, dict[str, Any]]:
    for index, item in enumerate(items):
        if str(item.get("id")) == target_id:
            return index, item
    raise StructuredNoteError(f"No existe {label} con ID {target_id}.")


def _server_block(raw: dict[str, Any], section_id: str | None = None) -> dict[str, Any]:
    block = deepcopy(raw)
    block["id"] = _uuid()
    if section_id:
        block.setdefault("section_id", section_id)
    block.setdefault("type", "paragraph")
    block.setdefault("lane", "right")
    block.setdefault("reading_order", 0)
    block.setdefault("content", "")
    block.setdefault("layout", {"gap_before": 0})
    block.setdefault("sources", [])
    return block


def apply_operations(document: dict[str, Any], operations: Iterable[dict[str, Any]]) -> dict[str, Any]:
    result = deepcopy(document)
    for raw_operation in operations:
        operation = deepcopy(raw_operation)
        op = operation.get("op")
        if op not in ALLOWED_OPERATIONS:
            raise StructuredNoteError(f"Operación no permitida: {op}")
        target_id = str(operation.get("target_id") or "")
        value = operation.get("value")
        if op == "replace_text":
            _, block = _find(result["blocks"], target_id, "el bloque")
            if isinstance(block.get("content"), dict):
                current = str(block["content"].get("text", ""))
                holder = block["content"]
                key = "text"
            else:
                current = str(block.get("content", ""))
                holder = block
                key = "content"
            if isinstance(value, dict):
                old, new = str(value.get("old", "")), str(value.get("new", ""))
                if not old or current.count(old) != 1:
                    raise StructuredNoteError("replace_text exige una coincidencia antigua única.")
                holder[key] = current.replace(old, new, 1)
            else:
                holder[key] = str(value or "")
        elif op == "replace_block":
            index, old = _find(result["blocks"], target_id, "el bloque")
            replacement = deepcopy(value or operation.get("block") or {})
            replacement["id"] = old["id"]
            replacement.setdefault("section_id", old["section_id"])
            replacement.setdefault("lane", old["lane"])
            replacement.setdefault("reading_order", old["reading_order"])
            replacement.setdefault("layout", old.get("layout", {"gap_before": 0}))
            replacement.setdefault("sources", old.get("sources", []))
            result["blocks"][index] = replacement
        elif op in {"insert_before", "insert_after"}:
            index, anchor = _find(result["blocks"], target_id, "el bloque")
            block = _server_block(operation.get("block") or value or {}, anchor["section_id"])
            result["blocks"].insert(index + (op == "insert_after"), block)
        elif op == "delete_block":
            index, _ = _find(result["blocks"], target_id, "el bloque")
            result["blocks"].pop(index)
            result["relations"] = [
                relation for relation in result["relations"]
                if str(relation["from_block_id"]) != target_id and str(relation["to_block_id"]) != target_id
            ]
        elif op == "move_block":
            _, block = _find(result["blocks"], target_id, "el bloque")
            move = value or {}
            for key in ("section_id", "lane", "reading_order", "layout"):
                if key in move:
                    block[key] = move[key]
        elif op == "change_block_type":
            _, block = _find(result["blocks"], target_id, "el bloque")
            block["type"] = str(value)
        elif op == "move_to_lane":
            _, block = _find(result["blocks"], target_id, "el bloque")
            block["lane"] = str(value)
        elif op == "create_relation":
            relation = deepcopy(operation.get("relation") or value or {})
            relation["id"] = _uuid()
            relation.setdefault("type", "explains")
            relation.setdefault("order", len(result["relations"]) * 10 + 10)
            result["relations"].append(relation)
        elif op == "delete_relation":
            index, _ = _find(result["relations"], target_id, "la relación")
            result["relations"].pop(index)
        elif op == "change_relation":
            _, relation = _find(result["relations"], target_id, "la relación")
            relation.update(value or {})
            relation["id"] = target_id
        elif op == "rename_section":
            _, section = _find(result["sections"], target_id, "la sección")
            section["title"] = str(value or "").strip()
        elif op == "insert_section":
            section = deepcopy(operation.get("section") or value or {})
            section["id"] = _uuid()
            section.setdefault("title", "Nueva sección")
            section.setdefault("order", len(result["sections"]) * 10 + 10)
            result["sections"].append(section)
            result["blocks"].extend([
                _server_block({"type": "question", "lane": "left", "content": "", "reading_order": 10}, section["id"]),
                _server_block({"type": "paragraph", "lane": "right", "content": "", "reading_order": 20}, section["id"]),
            ])
        elif op == "delete_section":
            index, _ = _find(result["sections"], target_id, "la sección")
            result["sections"].pop(index)
            deleted_blocks = {str(item["id"]) for item in result["blocks"] if str(item["section_id"]) == target_id}
            result["blocks"] = [item for item in result["blocks"] if str(item["id"]) not in deleted_blocks]
            result["relations"] = [
                item for item in result["relations"]
                if str(item["from_block_id"]) not in deleted_blocks and str(item["to_block_id"]) not in deleted_blocks
            ]
        elif op == "move_section":
            _, section = _find(result["sections"], target_id, "la sección")
            section["order"] = int(value)

    for section in result["sections"]:
        section_blocks = sorted(
            (item for item in result["blocks"] if item["section_id"] == section["id"]),
            key=lambda item: item.get("reading_order", 0),
        )
        for index, block in enumerate(section_blocks, 1):
            block["reading_order"] = index * 10
    return validate_document(result)


def commit_operations(
    db: Session,
    record: models.StructuredNoteDocument,
    base_revision_id: uuid.UUID,
    operations: list[dict[str, Any]],
    *,
    summary: str,
    actor: str = "user",
    change_kind: str = "manual_patch",
    provenance: dict[str, Any] | None = None,
) -> models.NoteRevision:
    if record.current_revision_id != base_revision_id:
        raise StaleRevisionError("La nota cambió; recarga antes de aplicar esta edición.")
    updated = apply_operations(record.document_json, operations)
    revision = _create_revision(
        db, record, updated, change_kind=change_kind, summary=summary,
        actor=actor, provenance=provenance,
    )
    db.commit()
    db.refresh(record)
    return revision


def restore_revision(db: Session, record: models.StructuredNoteDocument, revision_id: uuid.UUID) -> models.NoteRevision:
    source = db.query(models.NoteRevision).filter(
        models.NoteRevision.id == revision_id,
        models.NoteRevision.document_id == record.id,
    ).first()
    if source is None:
        raise StructuredNoteError("La revisión indicada no existe.")
    revision = _create_revision(
        db, record, source.document_json, change_kind="restore",
        summary=f"Restauración de revisión {source.revision_number}", actor="user",
        provenance={"restored_revision_id": str(source.id)},
    )
    db.commit()
    db.refresh(record)
    return revision


EDITOR_SYSTEM = """Eres el editor atómico de Concat Notes.
La nota existente se considera correcta salvo en las partes solicitadas.
Devuelve el menor número de operaciones posible. Prefiere replace_text sobre replace_block,
y replace_block sobre cambios de sección. No reformules ni reorganices contenido ajeno.
No uses emojis en headings que tú generes. No apliques cambios: devuelve sólo una propuesta JSON.
Operaciones permitidas: replace_text, replace_block, insert_before, insert_after, delete_block,
move_block, change_block_type, move_to_lane, create_relation, delete_relation,
change_relation, rename_section, insert_section, delete_section, move_section.
Formato: {"intent":"...","summary":"...","operations":[{"op":"...","target_id":"uuid","value":...}]}.
Para bloques/secciones/relaciones nuevas no inventes IDs: el servidor los asignará."""


def propose_ai_patch(
    db: Session,
    session: models.NoteEditSession,
    request: schemas.NoteEditMessageCreate,
) -> models.NotePatchProposal:
    record = db.get(models.StructuredNoteDocument, session.document_id)
    if record is None or record.current_revision_id is None:
        raise StructuredNoteError("La nota no tiene una revisión editable.")
    selected = {str(item) for item in request.block_ids}
    if request.scope == "selected_blocks" and not selected:
        raise StructuredNoteError("Selecciona al menos un bloque para limitar la edición.")
    context = record.document_json
    if request.scope == "selected_blocks":
        relevant = [item for item in context["blocks"] if str(item["id"]) in selected]
        relation_blocks = set(selected)
        for relation in context["relations"]:
            if str(relation["from_block_id"]) in selected or str(relation["to_block_id"]) in selected:
                relation_blocks.update((str(relation["from_block_id"]), str(relation["to_block_id"])))
        context = {
            **context,
            "blocks": [item for item in context["blocks"] if str(item["id"]) in relation_blocks],
            "relations": [
                item for item in context["relations"]
                if str(item["from_block_id"]) in relation_blocks or str(item["to_block_id"]) in relation_blocks
            ],
        }
    user_message = models.NoteEditMessage(
        session_id=session.id, role="user", content=request.content,
        scope_json={"scope": request.scope, "block_ids": list(selected)},
    )
    db.add(user_message)
    resolved = llm_models.resolve_selected_model(db, "synthesis")
    llm = llm_models.create_chat_model(resolved, timeout=150, max_retries=2)
    response = llm.invoke([
        {"role": "system", "content": EDITOR_SYSTEM},
        {"role": "user", "content": f"PETICIÓN:\n{request.content}\n\nREVISIÓN ACTUAL:\n{json.dumps(context, ensure_ascii=False)}"},
    ])
    payload = _json_payload(response)
    operations = payload.get("operations") or []
    if not isinstance(operations, list) or not operations:
        raise StructuredNoteError("El agente no propuso cambios concretos.")
    if request.scope == "selected_blocks":
        for operation in operations:
            target = str(operation.get("target_id") or "")
            if target and target not in selected and operation.get("op") not in {"create_relation"}:
                raise StructuredNoteError("La propuesta intentó modificar un bloque fuera del alcance seleccionado.")
    validated_candidate = apply_operations(record.document_json, operations)
    proposal = models.NotePatchProposal(
        session_id=session.id,
        base_revision_id=record.current_revision_id,
        intent=str(payload.get("intent") or request.content),
        summary=str(payload.get("summary") or "Propuesta de edición"),
        operations=operations,
        validation={
            "valid": True,
            "affected_blocks": sorted({str(item.get("target_id")) for item in operations if item.get("target_id")}),
            "rendered_preview": render_markdown(validated_candidate),
        },
        model_snapshot={"requested": resolved.requested_model, "effective": resolved.model_id},
    )
    db.add(proposal)
    db.add(models.NoteEditMessage(
        session_id=session.id, role="assistant",
        content=proposal.summary, scope_json={"proposal_id": str(proposal.id)},
    ))
    db.commit()
    db.refresh(proposal)
    return proposal


def apply_proposal(
    db: Session, proposal: models.NotePatchProposal, indexes: list[int],
) -> models.NoteRevision:
    if proposal.status != "validated":
        raise StructuredNoteError("La propuesta ya no está disponible para aplicar.")
    session = db.get(models.NoteEditSession, proposal.session_id)
    record = db.get(models.StructuredNoteDocument, session.document_id) if session else None
    if record is None or record.current_revision_id != proposal.base_revision_id:
        proposal.status = "stale"
        db.commit()
        raise StaleRevisionError("La propuesta quedó obsoleta porque la nota cambió.")
    operations = proposal.operations or []
    if not indexes:
        raise StructuredNoteError("Selecciona al menos un cambio.")
    if min(indexes) < 0 or max(indexes) >= len(operations):
        raise StructuredNoteError("La selección contiene operaciones inexistentes.")
    selected_operations = [operations[index] for index in sorted(set(indexes))]
    revision = commit_operations(
        db, record, proposal.base_revision_id, selected_operations,
        summary=proposal.summary, actor="agent", change_kind="ai_patch",
        provenance={"proposal_id": str(proposal.id), "selected_indexes": sorted(set(indexes))},
    )
    proposal.status = "applied"
    proposal.applied_revision_id = revision.id
    db.commit()
    return revision
