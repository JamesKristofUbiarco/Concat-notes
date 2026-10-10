from datetime import datetime, timezone
from typing import Literal
from uuid import UUID
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, llm_models
from app.database import get_db
from app.global_agent import active_tasks, apply_saved_proposal, run_payload
from app.worker import processing_lock

router = APIRouter(prefix="/api/agent")


def conversation(db, conversation_id):
    row = db.get(models.AgentConversation, conversation_id)
    if not row:
        raise HTTPException(404, "La conversación ya no existe.")
    return row


def serialize_conversation(row):
    return {"id": str(row.id), "title": row.title, "updated_at": row.updated_at.isoformat()}


@router.get("/models")
def agent_models(db: Session = Depends(get_db)):
    return {"selected": llm_models.resolve_selected_model(db, "image_analysis").model_id,
            "options": [{"id": option["id"], "name": option["name"], "configured": llm_models.model_is_configured(option)} for option in llm_models.VISION_MODELS]}


@router.get("/conversations")
def conversations(db: Session = Depends(get_db)):
    return [serialize_conversation(row) for row in db.query(models.AgentConversation).order_by(models.AgentConversation.updated_at.desc(), models.AgentConversation.id).all()]


@router.post("/conversations", status_code=201)
def create_conversation(db: Session = Depends(get_db)):
    row = models.AgentConversation()
    db.add(row)
    db.commit()
    db.refresh(row)
    return serialize_conversation(row)


class Rename(BaseModel):
    title: str = Field(min_length=1, max_length=255)


@router.patch("/conversations/{conversation_id}")
def rename(conversation_id: UUID, payload: Rename, db: Session = Depends(get_db)):
    row = conversation(db, conversation_id)
    title = payload.title.strip()
    if not title:
        raise HTTPException(400, "El nombre no puede estar vacío.")
    row.title, row.title_is_manual = title, True
    db.commit()
    return serialize_conversation(row)


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: UUID, db: Session = Depends(get_db)):
    async with processing_lock:
        row = conversation(db, conversation_id)
        runs = db.query(models.AgentRun).filter_by(conversation_id=row.id).all()
        for run in runs:
            if task := active_tasks.get(run.id):
                task.cancel()
        db.delete(row)
        db.commit()


@router.get("/conversations/{conversation_id}")
def conversation_detail(conversation_id: UUID, before: UUID | None = None, limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    row = conversation(db, conversation_id)
    query = db.query(models.AgentMessage).filter_by(conversation_id=row.id)
    if before:
        anchor = db.get(models.AgentMessage, before)
        if not anchor or anchor.conversation_id != row.id:
            raise HTTPException(400, "El mensaje no pertenece a esta conversación.")
        query = query.filter(or_(models.AgentMessage.created_at < anchor.created_at, and_(models.AgentMessage.created_at == anchor.created_at, models.AgentMessage.id < anchor.id)))
    messages = query.order_by(models.AgentMessage.created_at.desc(), models.AgentMessage.id.desc()).limit(limit + 1).all()
    selected = messages[:limit]
    runs = db.query(models.AgentRun).filter(models.AgentRun.conversation_id == row.id, models.AgentRun.user_message_id.in_([message.id for message in selected])).order_by(models.AgentRun.created_at).all()
    image_ids = {UUID(value) for message in selected for value in (message.attachments or [])}
    images = {str(image.id): {"id": str(image.id), "url": image.image_url, "filename": image.filename} for image in db.query(models.RawNoteImage).filter(models.RawNoteImage.id.in_(image_ids)).all()} if image_ids else {}
    return {**serialize_conversation(row), "messages": [{"id": str(message.id), "role": message.role, "content": message.content, "created_at": message.created_at.isoformat(), "attachments": [images[key] for key in message.attachments or [] if key in images]} for message in reversed(selected)], "runs": [run_payload(run) for run in runs], "has_more": len(messages) > limit}


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
    model_id: str
    course: str | None = None
    preset: Literal["duplicates"] | None = None
    components: list[Literal["content", "glossary", "flashcards"]] = Field(default_factory=lambda: ["content", "glossary", "flashcards"], min_length=1)
    image_ids: list[UUID] = Field(default_factory=list, max_length=6)


@router.post("/conversations/{conversation_id}/messages", status_code=202)
def send_message(conversation_id: UUID, payload: MessageCreate, db: Session = Depends(get_db)):
    row = conversation(db, conversation_id)
    if not payload.content.strip():
        raise HTTPException(400, "Escribe un mensaje.")
    try:
        llm_models.resolve_model("image_analysis", payload.model_id, allow_fallback=False)
    except llm_models.ModelResolutionError as exc:
        raise HTTPException(400, str(exc))
    if db.query(models.AgentRun).filter(models.AgentRun.conversation_id == row.id, models.AgentRun.status.in_(["pending", "running"])).first():
        raise HTTPException(409, "Esta conversación ya está procesando un mensaje. Puedes cancelarlo primero.")
    if payload.image_ids and db.query(models.RawNoteImage).filter(models.RawNoteImage.id.in_(set(payload.image_ids))).count() != len(set(payload.image_ids)):
        raise HTTPException(400, "No se encontró una imagen adjunta.")
    message = models.AgentMessage(conversation_id=row.id, role="user", content=payload.content.strip(), attachments=[str(value) for value in payload.image_ids])
    db.add(message)
    db.flush()
    run = models.AgentRun(conversation_id=row.id, user_message_id=message.id, model_id=payload.model_id, scope={"course": payload.course or None, "preset": payload.preset, "components": payload.components})
    db.add(run)
    row.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Esta conversación ya tiene un mensaje en proceso.")
    db.refresh(run)
    return run_payload(run)


@router.post("/runs/{run_id}/cancel")
def cancel(run_id: UUID, db: Session = Depends(get_db)):
    run = db.query(models.AgentRun).filter_by(id=run_id).with_for_update().one_or_none()
    if not run:
        raise HTTPException(404, "La ejecución ya no existe.")
    if run.status in {"pending", "running"}:
        run.status, run.progress = "cancelled", "Envío cancelado"
        db.commit()
        if task := active_tasks.get(run.id):
            task.get_loop().call_soon_threadsafe(task.cancel)
    return run_payload(run)


@router.post("/runs/{run_id}/apply")
async def apply_proposal(run_id: UUID):
    async with processing_lock:
        try:
            await asyncio.to_thread(apply_saved_proposal, run_id)
        except (ValueError, KeyError) as exc:
            raise HTTPException(409, str(exc))
        except Exception:
            raise HTTPException(500, "No se pudieron guardar los cambios; la propuesta no se aplicó.")
    return {"status": "applied"}


@router.post("/runs/{run_id}/reject")
def reject(run_id: UUID, db: Session = Depends(get_db)):
    run = db.query(models.AgentRun).filter_by(id=run_id).with_for_update().one_or_none()
    if not run or run.proposal_status != "pending":
        raise HTTPException(409, "La propuesta ya fue aplicada o descartada.")
    run.proposal_status = "rejected"
    db.commit()
    return {"status": "rejected"}
