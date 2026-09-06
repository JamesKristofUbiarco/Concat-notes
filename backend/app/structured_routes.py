"""API pública del workspace Cornell y del editor atómico."""

from __future__ import annotations

import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app import models, schemas, structured_notes
from app.database import get_db


router = APIRouter(prefix="/api", tags=["structured-notes"])


def _raise(exc: Exception) -> None:
    code = status.HTTP_409_CONFLICT if isinstance(exc, structured_notes.StaleRevisionError) else status.HTTP_400_BAD_REQUEST
    raise HTTPException(status_code=code, detail=str(exc)) from exc


def _record(db: Session, document_id: UUID) -> models.StructuredNoteDocument:
    record = db.get(models.StructuredNoteDocument, document_id)
    if record is None:
        raise HTTPException(status_code=404, detail="La nota estructurada no existe.")
    return record


def _serialize_revision(item: models.NoteRevision, *, include_document: bool = False) -> dict:
    result = {
        "id": str(item.id), "document_id": str(item.document_id),
        "parent_revision_id": str(item.parent_revision_id) if item.parent_revision_id else None,
        "revision_number": item.revision_number, "change_kind": item.change_kind,
        "change_summary": item.change_summary, "actor": item.actor,
        "provenance": item.provenance, "created_at": item.created_at.isoformat(),
    }
    if include_document:
        result.update(document=item.document_json, rendered_markdown=item.rendered_markdown)
    return result


def _serialize_proposal(item: models.NotePatchProposal) -> dict:
    return {
        "id": str(item.id), "session_id": str(item.session_id),
        "base_revision_id": str(item.base_revision_id), "status": item.status,
        "intent": item.intent, "summary": item.summary, "operations": item.operations,
        "validation": item.validation, "model_snapshot": item.model_snapshot,
        "applied_revision_id": str(item.applied_revision_id) if item.applied_revision_id else None,
        "created_at": item.created_at.isoformat(),
    }


@router.get("/note-documents")
def get_note_documents(
    origin: str | None = Query(None), collection_id: UUID | None = Query(None),
    db: Session = Depends(get_db),
):
    return structured_notes.list_documents(db, origin=origin, collection_id=collection_id)


@router.post("/note-documents", status_code=status.HTTP_201_CREATED)
def create_note_document(payload: schemas.StructuredNoteCreate, db: Session = Depends(get_db)):
    try:
        return structured_notes.serialize_document(structured_notes.create_manual_document(db, payload))
    except structured_notes.StructuredNoteError as exc:
        _raise(exc)


@router.get("/note-documents/{document_id}")
def get_note_document(document_id: UUID, db: Session = Depends(get_db)):
    return structured_notes.serialize_document(_record(db, document_id))


@router.delete("/note-documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note_document(document_id: UUID, db: Session = Depends(get_db)):
    record = _record(db, document_id)
    if not record.origin_kind.startswith("manual_"):
        raise HTTPException(status_code=400, detail="Las notas automáticas se administran desde su clase.")
    db.delete(record)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/note-documents/{document_id}/operations")
def mutate_note_document(
    document_id: UUID, payload: schemas.NoteOperationsRequest, db: Session = Depends(get_db),
):
    record = _record(db, document_id)
    try:
        revision = structured_notes.commit_operations(
            db, record, payload.base_revision_id,
            [item.model_dump(mode="json", exclude_none=True) for item in payload.operations],
            summary=payload.summary,
        )
        return {"document": structured_notes.serialize_document(record), "revision": _serialize_revision(revision)}
    except structured_notes.StructuredNoteError as exc:
        _raise(exc)


@router.get("/note-documents/{document_id}/revisions")
def list_note_revisions(document_id: UUID, db: Session = Depends(get_db)):
    _record(db, document_id)
    revisions = db.query(models.NoteRevision).filter(
        models.NoteRevision.document_id == document_id
    ).order_by(models.NoteRevision.revision_number.desc()).all()
    return [_serialize_revision(item) for item in revisions]


@router.get("/note-documents/{document_id}/revisions/{revision_id}")
def get_note_revision(document_id: UUID, revision_id: UUID, db: Session = Depends(get_db)):
    revision = db.query(models.NoteRevision).filter(
        models.NoteRevision.id == revision_id,
        models.NoteRevision.document_id == document_id,
    ).first()
    if revision is None:
        raise HTTPException(status_code=404, detail="La revisión no existe.")
    return _serialize_revision(revision, include_document=True)


@router.post("/note-documents/{document_id}/restore/{revision_id}")
def restore_note_revision(document_id: UUID, revision_id: UUID, db: Session = Depends(get_db)):
    record = _record(db, document_id)
    try:
        revision = structured_notes.restore_revision(db, record, revision_id)
        return {"document": structured_notes.serialize_document(record), "revision": _serialize_revision(revision)}
    except structured_notes.StructuredNoteError as exc:
        _raise(exc)


@router.get("/notes/{note_id}/structured-document")
def get_or_create_structured_document(note_id: UUID, db: Session = Depends(get_db)):
    note = db.get(models.RawNote, note_id)
    if note is None or note.processed_note is None:
        raise HTTPException(status_code=404, detail="La clase todavía no tiene una nota procesada.")
    record = structured_notes.ensure_document_for_processed_note(db, note, note.processed_note)
    return structured_notes.serialize_document(record)


@router.post("/notes/{note_id}/composition-plan")
def composition_plan(note_id: UUID, db: Session = Depends(get_db)):
    """Preflight determinista; el Composer puede refinarlo durante la generación."""
    note = db.get(models.RawNote, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="La clase no existe.")
    source = "\n".join((note.transcription or "", note.my_notes or "", note.class_summary or ""))
    code_weight = len(note.code_snippets or []) + len(note.command_snippets or []) + len(re.findall(r"```", source)) // 2
    procedure_weight = len(re.findall(r"\b(?:paso|primero|después|luego|procedimiento)\b", source, re.IGNORECASE))
    comparison_weight = len(re.findall(r"\b(?:versus|vs\.?|diferencia|comparación|alternativa)\b", source, re.IGNORECASE))
    if code_weight >= 2:
        slug, reason = "laboratorio-tecnico", "Hay código o comandos que conviene conectar con salida y explicación."
    elif procedure_weight >= 3:
        slug, reason = "procedimiento-guiado", "El material contiene una secuencia operativa relevante."
    elif comparison_weight >= 3:
        slug, reason = "comparativa-decisiones", "El material contrasta alternativas o conceptos."
    else:
        slug, reason = "cornell-conceptual", "Predominan conceptos que se benefician de pistas de recuperación."
    headings = [item.strip() for item in re.findall(r"^(?:#{1,3}\s+|\d+[.)]\s+)(.+)$", source, re.MULTILINE)]
    return {
        "profile_slug": slug, "reason": reason,
        "coverage_preview": headings[:20],
        "rules": {"generated_heading_emojis": False, "critic_policy": "threshold"},
    }


@router.get("/collections")
def list_collections(db: Session = Depends(get_db)):
    workspace = structured_notes.get_default_workspace(db)
    return [
        {"id": str(item.id), "name": item.name, "description": item.description, "order_index": item.order_index}
        for item in db.query(models.NoteCollection).filter(
            models.NoteCollection.workspace_id == workspace.id
        ).order_by(models.NoteCollection.order_index, models.NoteCollection.name).all()
    ]


@router.post("/collections", status_code=status.HTTP_201_CREATED)
def create_collection(payload: schemas.CollectionCreate, db: Session = Depends(get_db)):
    workspace = structured_notes.get_default_workspace(db)
    item = models.NoteCollection(
        workspace_id=workspace.id, name=payload.name.strip(), description=payload.description.strip()
    )
    db.add(item)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Ya existe una colección con ese nombre.") from exc
    db.refresh(item)
    return {"id": str(item.id), "name": item.name, "description": item.description}


@router.get("/style-profiles")
def list_style_profiles(db: Session = Depends(get_db)):
    profiles = structured_notes.ensure_builtin_profiles(db)
    db.commit()
    return [
        {"id": str(item.id), "slug": item.slug, "name": item.name,
         "description": item.description, "version": item.version, "is_builtin": item.is_builtin}
        for item in sorted(profiles, key=lambda value: value.name)
    ]


@router.post("/note-documents/{document_id}/style-example")
def mark_style_example(document_id: UUID, profile_id: UUID, db: Session = Depends(get_db)):
    _record(db, document_id)
    if db.get(models.NoteStyleProfile, profile_id) is None:
        raise HTTPException(status_code=404, detail="El perfil de estilo no existe.")
    example = db.query(models.NoteStyleExample).filter(
        models.NoteStyleExample.document_id == document_id,
        models.NoteStyleExample.profile_id == profile_id,
    ).first()
    if example is None:
        example = models.NoteStyleExample(profile_id=profile_id, document_id=document_id)
        db.add(example)
        db.commit()
        db.refresh(example)
    return {"id": str(example.id), "document_id": str(document_id), "profile_id": str(profile_id)}


@router.get("/note-editor/models")
def editor_models():
    from app import llm_models
    return [{"id": item["id"], "name": item["name"]} for item in llm_models.MODEL_CATALOG["image_analysis"]
            if "vision" in item["capabilities"] and llm_models.model_is_configured(item)]


@router.get("/note-documents/{document_id}/edit-sessions")
def list_edit_sessions(document_id: UUID, db: Session = Depends(get_db)):
    _record(db, document_id)
    return [{"id": str(item.id), "title": item.title} for item in db.query(models.NoteEditSession)
            .filter(models.NoteEditSession.document_id == document_id)
            .order_by(models.NoteEditSession.created_at.desc()).all()]


@router.post("/note-documents/{document_id}/edit-sessions", status_code=status.HTTP_201_CREATED)
def create_edit_session(
    document_id: UUID, payload: schemas.NoteEditSessionCreate, db: Session = Depends(get_db),
):
    _record(db, document_id)
    item = models.NoteEditSession(document_id=document_id, title=payload.title)
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": str(item.id), "document_id": str(document_id), "title": item.title}


@router.get("/note-edit-sessions/{session_id}/messages")
def list_edit_messages(session_id: UUID, db: Session = Depends(get_db)):
    if db.get(models.NoteEditSession, session_id) is None:
        raise HTTPException(status_code=404, detail="La sesión no existe.")
    return [
        {"id": str(item.id), "role": item.role, "content": item.content,
         "scope": item.scope_json, "created_at": item.created_at.isoformat()}
        for item in db.query(models.NoteEditMessage).filter(
            models.NoteEditMessage.session_id == session_id
        ).order_by(models.NoteEditMessage.created_at).all()
    ]


@router.post("/note-edit-sessions/{session_id}/messages")
def send_edit_message(
    session_id: UUID, payload: schemas.NoteEditMessageCreate, db: Session = Depends(get_db),
):
    session = db.get(models.NoteEditSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="La sesión no existe.")
    try:
        return _serialize_proposal(structured_notes.propose_ai_patch(db, session, payload))
    except structured_notes.StructuredNoteError as exc:
        db.rollback()
        db.add(models.NoteEditMessage(session_id=session_id, role="assistant", content=str(exc), scope_json={"error": True}))
        db.commit()
        _raise(exc)
    except Exception as exc:
        db.rollback()
        message = "No se pudo completar la respuesta del modelo. Intenta enviar el mensaje de nuevo."
        db.add(models.NoteEditMessage(session_id=session_id, role="assistant", content=message, scope_json={"error": True}))
        db.commit()
        raise HTTPException(status_code=502, detail=message) from exc


@router.get("/note-patch-proposals/{proposal_id}")
def get_patch_proposal(proposal_id: UUID, db: Session = Depends(get_db)):
    item = db.get(models.NotePatchProposal, proposal_id)
    if item is None:
        raise HTTPException(status_code=404, detail="La propuesta no existe.")
    return _serialize_proposal(item)


@router.post("/note-patch-proposals/{proposal_id}/apply")
def apply_patch_proposal(
    proposal_id: UUID, payload: schemas.PatchApplyRequest, db: Session = Depends(get_db),
):
    item = db.get(models.NotePatchProposal, proposal_id)
    if item is None:
        raise HTTPException(status_code=404, detail="La propuesta no existe.")
    try:
        revision = structured_notes.apply_proposal(db, item, payload.operation_indexes)
        session = db.get(models.NoteEditSession, item.session_id)
        record = _record(db, session.document_id)
        return {"document": structured_notes.serialize_document(record), "revision": _serialize_revision(revision)}
    except structured_notes.StructuredNoteError as exc:
        _raise(exc)


@router.post("/note-patch-proposals/{proposal_id}/reject")
def reject_patch_proposal(proposal_id: UUID, db: Session = Depends(get_db)):
    item = db.get(models.NotePatchProposal, proposal_id)
    if item is None:
        raise HTTPException(status_code=404, detail="La propuesta no existe.")
    if item.status == "applied":
        raise HTTPException(status_code=409, detail="Una propuesta aplicada no puede rechazarse.")
    item.status = "rejected"
    db.commit()
    return _serialize_proposal(item)


@router.get("/flashcards/candidates")
def list_flashcard_candidates(db: Session = Depends(get_db)):
    from app.flashcards import _base_query, serialize
    rows = _base_query(db).filter(
        models.FlashcardRecord.candidate_status == "candidate"
    ).order_by(models.FlashcardRecord.created_at.desc()).all()
    return [serialize(card, note, document) for card, note, document in rows]


@router.post("/flashcards/candidates/{card_id}/activate")
def activate_flashcard_candidate(card_id: UUID, db: Session = Depends(get_db)):
    from app.flashcards import _base_query, serialize
    row = _base_query(db).filter(models.FlashcardRecord.id == card_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="La candidata no existe.")
    card, note, document = row
    card.is_active = True
    card.candidate_status = "active"
    db.commit()
    db.refresh(card)
    return serialize(card, note, document)


@router.post("/flashcards/candidates/{card_id}/reject")
def reject_flashcard_candidate(card_id: UUID, db: Session = Depends(get_db)):
    card = db.get(models.FlashcardRecord, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="La candidata no existe.")
    card.is_active = False
    card.candidate_status = "rejected"
    db.commit()
    return {"id": str(card.id), "candidate_status": card.candidate_status}
