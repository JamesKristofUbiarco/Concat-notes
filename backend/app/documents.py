"""API-side orchestration for deterministic PDF/EPUB processing jobs."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
import zipfile
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app import crud, llm_models, models, schemas
from app.storage import public_object_url, upload_stream_to_rustfs

MAX_DOCUMENT_BYTES = 100 * 1024 * 1024
MAX_PDF_PAGES = 1000
MAX_EPUB_ENTRIES = 10_000
MAX_EPUB_UNCOMPRESSED = 500 * 1024 * 1024


class DocumentError(ValueError):
    pass


def _file_facts(file: UploadFile) -> tuple[int, str, bytes]:
    stream = file.file
    stream.seek(0)
    digest = hashlib.sha256()
    size = 0
    prefix = b""
    while chunk := stream.read(1024 * 1024):
        if not prefix:
            prefix = chunk[:16]
        size += len(chunk)
        if size > MAX_DOCUMENT_BYTES:
            raise DocumentError("El archivo supera el límite de 100 MB.")
        digest.update(chunk)
    stream.seek(0)
    return size, digest.hexdigest(), prefix


def _validate_epub(file: UploadFile) -> None:
    file.file.seek(0)
    try:
        with zipfile.ZipFile(file.file) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_EPUB_ENTRIES:
                raise DocumentError("El EPUB contiene demasiadas entradas.")
            total = sum(item.file_size for item in entries)
            if total > MAX_EPUB_UNCOMPRESSED:
                raise DocumentError("El EPUB supera 500 MB una vez descomprimido.")
            for item in entries:
                path = Path(item.filename)
                if path.is_absolute() or ".." in path.parts:
                    raise DocumentError("El EPUB contiene una ruta insegura.")
                if item.compress_size and item.file_size / item.compress_size > 100:
                    raise DocumentError("El EPUB contiene una entrada con compresión sospechosa.")
            try:
                mime = archive.read("mimetype").decode("ascii").strip()
            except KeyError as exc:
                raise DocumentError("El EPUB no contiene su descriptor mimetype.") from exc
            if mime != "application/epub+zip":
                raise DocumentError("El contenedor ZIP no es un EPUB válido.")
    except zipfile.BadZipFile as exc:
        raise DocumentError("El EPUB está corrupto o no es un ZIP válido.") from exc
    finally:
        file.file.seek(0)


def create_document(db: Session, file: UploadFile) -> tuple[models.SourceDocument, models.DocumentJob, bool]:
    filename = Path(file.filename or "documento").name
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pdf", ".epub"}:
        raise DocumentError("Sólo se aceptan archivos PDF o EPUB.")
    size, sha256, prefix = _file_facts(file)
    doc_format = suffix[1:]
    if doc_format == "pdf" and not prefix.startswith(b"%PDF-"):
        raise DocumentError("El contenido no corresponde a un PDF válido.")
    if doc_format == "epub":
        _validate_epub(file)

    existing = db.query(models.SourceDocument).filter(
        models.SourceDocument.sha256 == sha256,
        models.SourceDocument.status.notin_(["failed", "deleted"]),
    ).order_by(models.SourceDocument.created_at.desc()).first()
    if existing:
        job = db.query(models.DocumentJob).filter(
            models.DocumentJob.document_id == existing.id,
            models.DocumentJob.kind == "inspect",
        ).order_by(models.DocumentJob.created_at.desc()).first()
        return existing, job, True

    document_id = uuid.uuid4()
    storage_key = f"documents/{document_id}/original{suffix}"
    media_type = "application/pdf" if doc_format == "pdf" else "application/epub+zip"
    upload_stream_to_rustfs(storage_key, file.file, media_type)
    document = models.SourceDocument(
        id=document_id, filename=filename, media_type=media_type, format=doc_format,
        size_bytes=size, sha256=sha256, storage_key=storage_key,
        title=Path(filename).stem, status="uploaded",
    )
    db.add(document)
    db.flush()
    job = models.DocumentJob(document_id=document_id, kind="inspect", message="Esperando inspección")
    db.add(job)
    db.commit()
    db.refresh(document)
    db.refresh(job)
    return document, job, False


def serialize_document(document: models.SourceDocument) -> dict[str, Any]:
    return {
        "id": str(document.id), "filename": document.filename, "format": document.format,
        "size_bytes": document.size_bytes, "sha256": document.sha256, "page_count": document.page_count,
        "title": document.title, "author": document.author, "language": document.language,
        "status": document.status, "capabilities": document.capabilities or {},
        "warnings": document.warnings or [], "error": document.error,
        "created_at": document.created_at.isoformat() if document.created_at else None,
    }


def serialize_job(job: models.DocumentJob | None) -> dict[str, Any] | None:
    if not job:
        return None
    return {
        "id": str(job.id), "document_id": str(job.document_id), "kind": job.kind,
        "status": job.status, "stage": job.stage, "progress": job.progress,
        "message": job.message, "error": job.error, "warnings": job.warnings or [],
        "heartbeat_at": job.heartbeat_at.isoformat() if job.heartbeat_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "cancel_requested": job.cancel_requested,
    }


def section_tree(db: Session, document_id) -> list[dict[str, Any]]:
    sections = db.query(models.DocumentSection).filter(
        models.DocumentSection.document_id == document_id
    ).order_by(models.DocumentSection.order_index).all()
    nodes = {
        section.id: {
            "id": str(section.id), "title": section.title, "level": section.level,
            "source_kind": section.source_kind, "page_start": section.page_start,
            "page_end": section.page_end, "confidence": section.confidence, "children": [],
        }
        for section in sections
    }
    roots = []
    for section in sections:
        node = nodes[section.id]
        if section.parent_id and section.parent_id in nodes:
            nodes[section.parent_id]["children"].append(node)
        else:
            roots.append(node)
    return roots


def normalize_ranges(ranges: list[dict[str, int]], page_count: int | None) -> list[dict[str, int]]:
    normalized = []
    for item in ranges:
        start, end = int(item["start"]), int(item["end"])
        if start > end:
            raise DocumentError(f"Rango invertido: {start}-{end}.")
        if start < 1 or (page_count and end > page_count):
            raise DocumentError("Uno de los rangos está fuera de los límites del PDF.")
        normalized.append((start, end))
    merged: list[list[int]] = []
    for start, end in sorted(normalized):
        if merged and start <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [{"start": start, "end": end} for start, end in merged]


def estimate_visual_cost(model_id: str, candidates: int, profile: str) -> float:
    """Estimate against OpenRouter's live catalog; use a conservative fallback offline."""
    if profile == "local" or candidates <= 0:
        return 0.0
    fraction = 0.55 if profile == "balanced" else 1.0
    routed = max(1, round(candidates * fraction))
    try:
        request = urllib.request.Request("https://openrouter.ai/api/v1/models")
        if os.getenv("OPENROUTER_API_KEY"):
            request.add_header("Authorization", f"Bearer {os.environ['OPENROUTER_API_KEY']}")
        with urllib.request.urlopen(request, timeout=3) as response:
            catalog = json.load(response).get("data", [])
        model = next(item for item in catalog if item.get("id") == model_id)
        pricing = model.get("pricing") or {}
        # Upper-bound assumption per crop: 2k input/vision tokens and 600 output.
        return round(routed * (2000 * float(pricing.get("prompt") or 0) + 600 * float(pricing.get("completion") or 0)), 4)
    except Exception:
        return round(routed * (0.01 if profile == "balanced" else 0.025), 4)


def create_process_job(db: Session, document: models.SourceDocument, payload: schemas.DocumentProcessRequest) -> tuple[models.DocumentRun, models.DocumentJob]:
    if document.status != "ready":
        raise DocumentError("El documento todavía no está listo para seleccionar contenido.")
    selection = payload.selection.model_dump(mode="json")
    if selection["mode"] == "pages":
        if document.format != "pdf":
            raise DocumentError("Los rangos físicos de páginas sólo están disponibles para PDF.")
        if not selection["ranges"]:
            raise DocumentError("Añade al menos un rango de páginas.")
        selection["ranges"] = normalize_ranges(selection["ranges"], document.page_count)
    if selection["mode"] == "sections":
        if not selection["section_ids"]:
            raise DocumentError("Selecciona al menos un capítulo o subcapítulo.")
        valid = {str(row[0]) for row in db.query(models.DocumentSection.id).filter(models.DocumentSection.document_id == document.id)}
        if any(str(item) not in valid for item in selection["section_ids"] + selection["excluded_section_ids"]):
            raise DocumentError("La selección contiene secciones de otro documento.")

    try:
        resolved = llm_models.resolve_selected_model(db, "document_vision") if payload.profile != "local" else None
        model_snapshot = resolved.public_dict() | {"api_model_id": resolved.api_model_id} if resolved else {}
    except llm_models.ModelResolutionError as exc:
        raise DocumentError(str(exc)) from exc
    visual_estimate = int((document.capabilities or {}).get("visual_candidates", 0))
    estimate = estimate_visual_cost(model_snapshot.get("api_model_id", ""), visual_estimate, payload.profile)
    if estimate > 1.0 and payload.approved_cost_usd + 1e-9 < estimate:
        raise DocumentError(f"La estimación es US${estimate:.2f}; confirma ese presupuesto para continuar.")
    identity = hashlib.sha256(json.dumps({"document": document.sha256, "selection": selection, "profile": payload.profile, "model": model_snapshot.get("effective_model"), "parser": "1"}, sort_keys=True).encode()).hexdigest()
    existing_job = db.query(models.DocumentJob).filter(
        models.DocumentJob.idempotency_key == identity,
        models.DocumentJob.status.in_(["pending", "running", "completed"]),
    ).first()
    if existing_job:
        run = db.query(models.DocumentRun).filter(models.DocumentRun.job_id == existing_job.id).first()
        return run, existing_job
    run = models.DocumentRun(
        document_id=document.id, selection_json=selection, profile=payload.profile,
        model_snapshot=model_snapshot, estimated_cost_usd=estimate,
        approved_cost_usd=payload.approved_cost_usd,
    )
    db.add(run)
    db.flush()
    job = models.DocumentJob(
        document_id=document.id, kind="process", profile=payload.profile,
        selection_json=selection, options_json={"run_id": str(run.id), "model": model_snapshot},
        idempotency_key=identity, message="Esperando extracción",
    )
    db.add(job)
    db.flush()
    run.job_id = job.id
    db.commit()
    db.refresh(run)
    db.refresh(job)
    return run, job


def serialize_run(db: Session, run: models.DocumentRun) -> dict[str, Any]:
    drafts = db.query(models.DocumentDraft).filter(models.DocumentDraft.run_id == run.id).order_by(models.DocumentDraft.order_index).all()
    assets = {str(asset.id): asset for asset in db.query(models.DocumentAsset).filter(models.DocumentAsset.document_id == run.document_id)}
    return {
        "id": str(run.id), "document_id": str(run.document_id), "status": run.status,
        "profile": run.profile, "selection": run.selection_json,
        "estimated_cost_usd": run.estimated_cost_usd, "actual_cost_usd": run.actual_cost_usd,
        "warnings": run.warnings or [],
        "drafts": [{
            "id": str(draft.id), "title": draft.title, "heading_path": draft.heading_path,
            "page_ranges": draft.page_ranges, "source_markdown": draft.source_markdown,
            "course_name": draft.course_name, "course_module": draft.course_module,
            "class_title": draft.class_title, "confirmed": bool(draft.raw_note_id),
            "assets": [{"id": asset_id, "url": public_object_url(assets[asset_id].storage_key), "description": assets[asset_id].description}
                       for asset_id in (draft.asset_ids or []) if asset_id in assets],
        } for draft in drafts],
    }


def confirm_run(db: Session, run: models.DocumentRun, payload: schemas.DocumentConfirmRequest) -> list[models.RawNote]:
    if run.status != "ready":
        raise DocumentError("La extracción todavía no está lista para confirmar.")
    drafts = {draft.id: draft for draft in db.query(models.DocumentDraft).filter(models.DocumentDraft.run_id == run.id)}
    if not payload.drafts or any(item.id not in drafts for item in payload.drafts):
        raise DocumentError("La confirmación contiene borradores inválidos.")
    created = []
    for item in payload.drafts:
        draft = drafts[item.id]
        if draft.raw_note_id:
            note = db.query(models.RawNote).filter(models.RawNote.id == draft.raw_note_id).first()
            if note:
                created.append(note)
            continue
        image_schemas = []
        for asset_id in draft.asset_ids or []:
            asset = db.query(models.DocumentAsset).filter(models.DocumentAsset.id == asset_id).first()
            if not asset:
                continue
            image = models.RawNoteImage(
                image_url=public_object_url(asset.storage_key), filename=asset.storage_key,
                descripcion_llm=asset.description or "Figura extraída del documento fuente.",
                image_type="image", document_asset_id=asset.id,
            )
            db.add(image)
            db.flush()
            image_schemas.append(schemas.ImageSnippetBase.model_validate(image))
        note = crud.create_raw_note(db, schemas.NoteCreate(
            writing_mode=payload.writing_mode, platform="Documento",
            course_name=item.course_name.strip(), teacher="",
            course_module=item.course_module.strip(), class_title=item.class_title.strip(),
            transcription=(item.source_markdown if item.source_markdown is not None else draft.source_markdown),
            class_summary=f"Fuente documental: {draft.title}", my_notes=payload.my_notes.strip(), class_minutes=0,
            image_snippets=image_schemas, flashcard_target=payload.flashcard_target,
        ))
        draft.course_name = item.course_name.strip()
        draft.course_module = item.course_module.strip()
        draft.class_title = item.class_title.strip()
        draft.source_markdown = item.source_markdown if item.source_markdown is not None else draft.source_markdown
        draft.raw_note_id = note.id
        draft.confirmed_at = datetime.now(timezone.utc)
        created.append(note)
    db.commit()
    return created
