"""Regeneración selectiva: generación aislada y guardado atómico por clase."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import hashlib
import logging
import threading
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

from app import models, crud, llm_models
from app.database import SessionLocal
from app import v2_agent as agent
from app.worker import processing_lock, _store_embedding
from app.note_sections import split_note_markdown as markdown_parts
from app.generation_runtime import snapshot_metrics

logger = logging.getLogger(__name__)
COMPONENTS = {"content", "glossary", "flashcards"}


def content_digest(note) -> str:
    import json
    source = {key: getattr(note, key) for key in (
        "course_name", "class_title", "course_module", "teacher", "platform", "writing_mode",
        "transcription", "my_notes", "class_summary", "code_snippets", "command_snippets", "flashcard_target",
    )}
    source["markdown"] = note.processed_note.structured_markdown if note.processed_note else None
    source["images"] = [(str(image.id), image.image_url, image.descripcion_llm) for image in note.images]
    return hashlib.sha256(json.dumps(source, sort_keys=True, default=str).encode()).hexdigest()


def generate_selection(db, note, components: list[str], instructions: str, progress=None) -> dict:
    state = {"raw_note_id": str(note.id), "additional_instructions": instructions, "metrics": {}}
    if progress:
        sink, progress_lock = progress, threading.Lock()
        def progress(phase, _metrics):
            # Parallel supplement callbacks must serialize fresh snapshots;
            # an older snapshot must not overwrite another request's progress.
            with progress_lock:
                sink(phase, snapshot_metrics(state["metrics"]))
    config = {"configurable": {"db": db, "progress": progress}}
    stages = {}
    def stage(name, call):
        if progress: progress(name, dict(state["metrics"]))
        started = time.monotonic()
        try:
            return call()
        finally:
            stages[name] = stages.get(name, 0) + round((time.monotonic() - started) * 1000)
            state["metrics"]["stage_ms"] = dict(stages)
            logger.info("Regeneration note=%s phase=%s elapsed_ms=%s", note.id, name, stages[name])
            if progress: progress(name, dict(state["metrics"]))
    stage("context", lambda: agent.context_node(state, config))
    stage("evidence", lambda: agent.evidence_node(state, config))
    stage("coverage", lambda: agent.knowledge_model_node(state, config))
    parts = markdown_parts(note.processed_note.structured_markdown)
    if "content" in components:
        stage("content", lambda: agent.body_node(state, config))
        stage("diagrams", lambda: agent.mermaid_repair_node(state, config))
        parts["content"] = agent.ensure_visible_class_header(state["body_markdown"], note) + "\n\n"
    else:
        state["body_markdown"] = parts["content"]
    resolved = llm_models.resolve_selected_model(db, "query_expansion")
    if "glossary" in components:
        from app.glossary import parse_glossary_entries
        from app.knowledge import prior_note_ids
        state["original_glossary"] = parts["glossary"]
        prior = db.query(models.RawNote).filter(models.RawNote.id.in_(prior_note_ids(db, note))).all()
        terms = [entry["term"] for other in prior if other.processed_note
                 for entry in parse_glossary_entries(other.processed_note.structured_markdown, other.class_title)]
    def supplements():
        # All DB reads finished above; worker threads only operate on loaded data.
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {}
            if "glossary" in components:
                futures["glossary"] = executor.submit(agent._glossary_call, agent.supplement_client(resolved, "glossary", state, progress=agent._request_progress(config, "supplements")), note, state, terms)
            if "flashcards" in components:
                futures["flashcards"] = executor.submit(agent._flashcard_call, agent.supplement_client(resolved, "flashcards", state, progress=agent._request_progress(config, "supplements")), note, state)
            for key, future in futures.items():
                parts[key] = future.result() + "\n\n"
    if "glossary" in components or "flashcards" in components:
        stage("supplements", supplements)
    if set(components) == COMPONENTS:
        state["glossary_markdown"] = parts["glossary"]
        state["flashcards_markdown"] = parts["flashcards"]
        stage("assembly", lambda: agent.assemble_node(state, config))
    else:
        state["structured_markdown"] = "".join(parts.values())
    state["glossary_markdown"] = parts["glossary"]
    state["flashcards_markdown"] = parts["flashcards"]
    return state


def rebuild_glossary(db, course: str):
    from app.glossary import parse_glossary_entries, merge_entries, compile_glossary_markdown
    notes = db.query(models.RawNote).filter(models.RawNote.course_name == course).order_by(models.RawNote.order_index, models.RawNote.created_at, models.RawNote.id).all()
    entries = [entry for note in notes if note.processed_note
               for entry in parse_glossary_entries(note.processed_note.structured_markdown, note.class_title)]
    merged = merge_entries([], entries)
    glossary = db.query(models.CourseGlossary).filter(models.CourseGlossary.course_name == course).first()
    if glossary is None:
        glossary = models.CourseGlossary(course_name=course)
        db.add(glossary)
    glossary.entries = merged
    glossary.compiled_markdown = compile_glossary_markdown(merged, course)


def persist_selection(db, note, state, components):
    from app.knowledge import persist_v2_derivatives, embed_texts
    from app.flashcards import refresh_note
    from app.structured_notes import markdown_to_document, _create_revision, get_default_workspace
    previous_markdown = note.processed_note.structured_markdown
    processed = crud.archive_note(db, note.id, state["structured_markdown"], state.get("ai_comments", note.processed_note.ai_comments or ""), commit=False)
    if "content" in components:
        persist_v2_derivatives(db, note, processed, state, update_glossary="glossary" in components)
    else:
        artifact = db.query(models.GenerationArtifact).filter(models.GenerationArtifact.processed_note_id == processed.id).first()
        if artifact:
            # Cache the new extraction without rewriting the evidence of preserved content.
            artifact.metrics = {**(artifact.metrics or {}), **state.get("metrics", {})}
            if state.get("metrics", {}).get("evidence_cache_key"):
                artifact.evidence_manifest = {**(artifact.evidence_manifest or {}), "cached_extraction": {
                    "key": state["metrics"]["evidence_cache_key"], "claims": state.get("evidence_manifest", []),
                }}
            if "glossary" in components:
                artifact.glossary_markdown = state["glossary_markdown"]
            if "flashcards" in components:
                artifact.flashcards_markdown = state["flashcards_markdown"]
        if "flashcards" in components:
            refresh_note(db, note)
            cards = db.query(models.FlashcardRecord).filter(models.FlashcardRecord.raw_note_id == note.id, models.FlashcardRecord.is_dummy_embedding.is_(True)).all()
            vectors, dummies = embed_texts([f"{card.question}\n{card.answer}" for card in cards])
            for card, vector, dummy in zip(cards, vectors, dummies):
                card.embedding, card.is_dummy_embedding = vector, dummy
    if "glossary" in components:
        rebuild_glossary(db, note.course_name)
    _store_embedding(db, processed, note, commit=False)
    record = db.query(models.StructuredNoteDocument).filter(models.StructuredNoteDocument.raw_note_id == note.id, models.StructuredNoteDocument.origin_kind == "generated_class").first()
    if record is None:
        record = models.StructuredNoteDocument(workspace_id=get_default_workspace(db).id, raw_note_id=note.id, origin_kind="generated_class", migration_status="parsed", document_json={})
        db.add(record)
        db.flush()
        _create_revision(db, record, markdown_to_document(previous_markdown, note, str(record.id)), change_kind="generated", summary="Versión anterior a la regeneración", actor="system")
    public = processed.structured_markdown
    _create_revision(db, record, markdown_to_document(public, note, str(record.id)), change_kind="regenerated", summary="Regeneración: " + ", ".join(components), actor="agent", provenance={"components": components})
    processed.structured_markdown = public


def serialize_job(job):
    return {"id": str(job.id), "status": job.status, "components": job.components, "instructions": job.instructions,
            "items": job.items, "created_at": job.created_at.isoformat(), "updated_at": job.updated_at.isoformat()}


def process_item(job_id, index):
    """La misma transacción guarda nota, derivados y éxito del trabajo."""
    db = SessionLocal()
    try:
        job = db.get(models.RegenerationJob, job_id)
        item = job.items[index]
        note = db.get(models.RawNote, item["note_id"])
        if not note or not note.processed_note:
            raise ValueError("La clase fue eliminada o no tiene nota procesada.")
        if content_digest(note) != item["digest"]:
            raise ValueError("La clase cambió desde que se solicitó regenerar. Selecciónala de nuevo.")
        def progress(phase, metrics):
            # Separate short transactions make progress visible while an API call runs.
            with SessionLocal() as tracking:
                current = tracking.query(models.RegenerationJob).filter_by(id=job_id).with_for_update().one_or_none()
                if not current or current.status != "running": return
                items = deepcopy(current.items)
                if items[index]["status"] != "running": return
                if items[index].get("phase") != phase:
                    items[index]["phase_started_at"] = datetime.now(timezone.utc).isoformat()
                items[index]["phase"] = phase
                items[index]["metrics"] = {**items[index].get("metrics", {}), **{key: value for key, value in metrics.items() if key != "evidence_cache_key"}}
                current.items = items
                current.updated_at = datetime.now(timezone.utc)
                tracking.commit()
        state = generate_selection(db, note, job.components, job.instructions, progress=progress)
        progress("saving", state.get("metrics", {}))
        saved_at = time.monotonic()
        # Revalidar tras la llamada al modelo por si hubo una edición concurrente.
        db.expire_all()
        note = db.query(models.RawNote).filter(models.RawNote.id == item["note_id"]).with_for_update().first()
        db.query(models.ProcessedNote).filter(models.ProcessedNote.raw_note_id == item["note_id"]).with_for_update().first()
        if not note or not note.processed_note or content_digest(note) != item["digest"]:
            raise ValueError("La clase cambió durante la generación; se conservó la versión actual.")
        persist_selection(db, note, state, job.components)
        db.refresh(job)
        items = deepcopy(job.items)
        items[index]["status"] = "complete"
        items[index]["error"] = None
        items[index]["phase"] = "complete"
        items[index].setdefault("metrics", {}).setdefault("stage_ms", {})["saving"] = round((time.monotonic() - saved_at) * 1000)
        logger.info("Regeneration note=%s phase=saving elapsed_ms=%s", note.id, items[index]["metrics"]["stage_ms"]["saving"])
        job.items = items
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.get(models.RegenerationJob, job_id)
        items = deepcopy(job.items)
        items[index]["status"] = "failed"
        items[index]["error"] = str(exc)[:1500]
        job.items = items
        db.commit()
        logger.exception("Falló regeneración de clase")
    finally:
        db.close()


async def regeneration_loop():
    # Un reinicio deja visibles los trabajos interrumpidos, nunca repite cargos automáticamente.
    with SessionLocal() as db:
        for job in db.query(models.RegenerationJob).filter(models.RegenerationJob.status == "running").all():
            items = deepcopy(job.items)
            for item in items:
                if item["status"] in {"pending", "running"}:
                    item.update(status="failed", error="Trabajo interrumpido por reinicio. Puedes volver a seleccionar esta clase.")
            job.items, job.status = items, "failed"
        db.commit()
    while True:
        try:
            with SessionLocal() as db:
                job = db.query(models.RegenerationJob).filter(models.RegenerationJob.status == "pending").order_by(models.RegenerationJob.created_at).first()
                job_id = job.id if job else None
                count = len(job.items) if job else 0
                if job:
                    job.status = "running"
                    db.commit()
            if job_id:
                for index in range(count):
                    async with processing_lock:
                        with SessionLocal() as db:
                            job = db.get(models.RegenerationJob, job_id)
                            items = deepcopy(job.items)
                            items[index]["status"] = "running"
                            job.items = items
                            db.commit()
                        await asyncio.to_thread(process_item, job_id, index)
                with SessionLocal() as db:
                    job = db.get(models.RegenerationJob, job_id)
                    job.status = "complete" if all(item["status"] == "complete" for item in job.items) else "failed"
                    db.commit()
            else:
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Error del worker de regeneración")
            await asyncio.sleep(5)
