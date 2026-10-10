"""Administración del RAG y trabajos de regeneración desde la web."""
from typing import Literal
from uuid import UUID
import asyncio
import hashlib
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, literal, union_all, func
from sqlalchemy.orm import Session, load_only, selectinload

from app import models
from app.database import get_db
from app.knowledge import ZERO_VECTOR, embed_texts, _normalise, _hash
from app.regeneration import content_digest, serialize_job
from app.worker import processing_lock

router = APIRouter(prefix="/api")
KINDS = {"note": models.NoteChunk, "source": models.SourceChunk, "claim": models.NoteClaim, "flashcard": models.FlashcardRecord}


def rag_index():
    chunks = select(literal("note").label("kind"), models.NoteChunk.id.label("id"), models.ProcessedNote.raw_note_id.label("note_id"), models.NoteChunk.content.label("content"), models.NoteChunk.is_dummy_embedding.label("dummy"), models.NoteChunk.created_at.label("created_at")).join(models.ProcessedNote, models.NoteChunk.processed_note_id == models.ProcessedNote.id)
    sources = select(literal("source"), models.SourceChunk.id, models.SourceChunk.raw_note_id, models.SourceChunk.content, models.SourceChunk.is_dummy_embedding, models.SourceChunk.created_at)
    claims = select(literal("claim"), models.NoteClaim.id, models.NoteClaim.raw_note_id, models.NoteClaim.statement, models.NoteClaim.is_dummy_embedding, models.NoteClaim.created_at)
    cards = select(literal("flashcard"), models.FlashcardRecord.id, models.FlashcardRecord.raw_note_id, models.FlashcardRecord.question + literal("\n") + models.FlashcardRecord.answer, models.FlashcardRecord.is_dummy_embedding, models.FlashcardRecord.created_at).where(models.FlashcardRecord.raw_note_id.isnot(None))
    return union_all(chunks, sources, claims, cards).subquery()


def row_content(row, kind):
    return row.statement if kind == "claim" else f"{row.question}\n{row.answer}" if kind == "flashcard" else row.content


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def get_rag_row(db, kind, row_id, *, lock=False):
    model = KINDS.get(kind)
    if model is None:
        raise HTTPException(400, "Tipo de fragmento inválido.")
    query = db.query(model).filter(model.id == row_id)
    row = (query.with_for_update() if lock else query).first()
    if row is None:
        raise HTTPException(404, "El fragmento ya no existe. Actualiza la lista.")
    return row


@router.get("/rag/classes")
def class_tree(db: Session = Depends(get_db)):
    return [{"id": str(note.id), "course": note.course_name, "module": note.course_module, "title": note.class_title, "status": note.status.value, "can_regenerate": note.processed_note is not None}
            for note in db.query(models.RawNote).options(
                load_only(models.RawNote.course_name, models.RawNote.course_module, models.RawNote.class_title, models.RawNote.status),
                selectinload(models.RawNote.processed_note).load_only(models.ProcessedNote.id),
            ).order_by(models.RawNote.course_name, models.RawNote.order_index, models.RawNote.created_at, models.RawNote.id).all()]


@router.get("/rag/chunks")
def list_chunks(course: str | None = None, note_id: UUID | None = None, kind: Literal["note", "source", "claim", "flashcard"] | None = None,
                embedding: Literal["all", "real", "missing"] = "all", search: str = "", page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), db: Session = Depends(get_db)):
    index = rag_index()
    query = db.query(index.c.kind, index.c.id, index.c.note_id, index.c.content, index.c.dummy, models.RawNote.course_name, models.RawNote.class_title).join(models.RawNote, index.c.note_id == models.RawNote.id)
    if course:
        query = query.filter(models.RawNote.course_name == course)
    if note_id:
        query = query.filter(index.c.note_id == note_id)
    if kind:
        query = query.filter(index.c.kind == kind)
    if embedding != "all":
        query = query.filter(index.c.dummy.is_(embedding == "missing"))
    if search.strip():
        query = query.filter(index.c.content.ilike(f"%{search.strip()}%"))
    total = query.count()
    rows = query.order_by(models.RawNote.course_name, models.RawNote.order_index, index.c.kind, index.c.created_at, index.c.id).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "page": page, "page_size": page_size, "items": [{"kind": row.kind, "id": str(row.id), "note_id": str(row.note_id), "course": row.course_name, "class_title": row.class_title, "preview": row.content[:280], "chars": len(row.content), "has_embedding": not row.dummy} for row in rows]}


@router.get("/rag/stats")
def rag_stats(db: Session = Depends(get_db)):
    index = rag_index()
    rows = db.query(index.c.kind, index.c.dummy, func.count()).group_by(index.c.kind, index.c.dummy).all()
    counts = {kind: {"total": 0, "real": 0, "missing": 0} for kind in KINDS}
    for kind, dummy, count in rows:
        counts[kind]["total"] += count
        counts[kind]["missing" if dummy else "real"] += count
    return {"counts": counts, "embedding_configured": bool(os.getenv("VOYAGE_API_KEY"))}


@router.get("/rag/chunks/{kind}/{row_id}")
def chunk_detail(kind: str, row_id: UUID, db: Session = Depends(get_db)):
    row = get_rag_row(db, kind, row_id)
    content = row_content(row, kind)
    return {"kind": kind, "id": str(row.id), "content": content, "digest": digest(content), "embedding": [float(value) for value in row.embedding], "has_embedding": not row.is_dummy_embedding, "editable": kind != "flashcard", "source_type": getattr(row, "source_type", None), "concept": getattr(row, "concept", None), "evidence": getattr(row, "evidence_text", None)}


class ChunkEdit(BaseModel):
    content: str = Field(min_length=1, max_length=100000)
    digest: str


@router.put("/rag/chunks/{kind}/{row_id}")
async def edit_chunk(kind: str, row_id: UUID, payload: ChunkEdit, db: Session = Depends(get_db)):
    async with processing_lock:
        row = get_rag_row(db, kind, row_id, lock=True)
        if kind == "flashcard":
            raise HTTPException(400, "Edita la tarjeta en Flashcards; aquí se administra su embedding.")
        if payload.digest != digest(row_content(row, kind)):
            raise HTTPException(409, "El fragmento cambió. Actualiza antes de editar.")
        content = payload.content.strip()
        if not content:
            raise HTTPException(400, "El contenido no puede estar vacío.")
        if kind == "claim":
            row.statement, row.claim_hash = content, _hash(_normalise(content))
        else:
            row.content = content
        if kind == "source":
            row.content_hash = _hash(f"{row.source_type}\0edited\0{content}")
            row.char_start = row.char_end = None
        # Un vector del texto anterior nunca debe seguir asociado al texto editado.
        vectors, dummies = await asyncio.to_thread(embed_texts, [content])
        row.embedding, row.is_dummy_embedding = vectors[0], dummies[0]
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise HTTPException(409, "El contenido coincide con otro fragmento de esta clase.")
        return {"has_embedding": not row.is_dummy_embedding}


class ChunkTarget(BaseModel):
    kind: Literal["note", "source", "claim", "flashcard"]
    id: UUID


class RagAction(BaseModel):
    action: Literal["delete_chunks", "delete_embeddings", "reembed"]
    targets: list[ChunkTarget] = Field(min_length=1, max_length=200)


@router.post("/rag/actions")
async def rag_action(payload: RagAction, db: Session = Depends(get_db)):
    async with processing_lock:
        keys = sorted({(target.kind, target.id) for target in payload.targets})
        if payload.action == "delete_chunks" and any(kind == "flashcard" for kind, _ in keys):
            raise HTTPException(400, "Las tarjetas se borran desde Flashcards. Aquí puedes borrar sus embeddings.")
        rows = [(kind, get_rag_row(db, kind, row_id, lock=True)) for kind, row_id in keys]
        if payload.action == "reembed":
            vectors, dummies = await asyncio.to_thread(embed_texts, [row_content(row, kind) for kind, row in rows])
            if any(dummies):
                raise HTTPException(502, "VoyageAI no produjo embeddings reales. Comprueba la API y vuelve a intentar; se conservaron los vectores anteriores.")
            for (_, row), vector in zip(rows, vectors):
                row.embedding, row.is_dummy_embedding = vector, False
        else:
            for _, row in rows:
                if payload.action == "delete_chunks":
                    db.delete(row)
                else:
                    row.embedding, row.is_dummy_embedding = ZERO_VECTOR[:], True
        db.commit()
        return {"affected": len(rows)}


class RegenerationRequest(BaseModel):
    note_ids: list[UUID] = Field(min_length=1, max_length=1000)
    components: list[Literal["content", "glossary", "flashcards"]] = Field(default_factory=lambda: ["content", "glossary", "flashcards"], min_length=1)
    instructions: str = Field(default="", max_length=12000)


@router.post("/regeneration/jobs", status_code=202)
async def create_regeneration(payload: RegenerationRequest, db: Session = Depends(get_db)):
    async with processing_lock:
        ids = set(payload.note_ids)
        notes = db.query(models.RawNote).filter(models.RawNote.id.in_(ids)).order_by(models.RawNote.course_name, models.RawNote.order_index, models.RawNote.created_at, models.RawNote.id).all()
        if len(notes) != len(ids) or any(not note.processed_note for note in notes):
            raise HTTPException(400, "Selecciona únicamente clases existentes con notas procesadas.")
        active = db.query(models.RegenerationJob).filter(models.RegenerationJob.status.in_(["pending", "running"])).all()
        if any(item["note_id"] in {str(value) for value in ids} for job in active for item in job.items):
            raise HTTPException(409, "Una clase seleccionada ya tiene una regeneración pendiente.")
        job = models.RegenerationJob(instructions=payload.instructions.strip(), components=[key for key in ("content", "glossary", "flashcards") if key in payload.components], items=[{"note_id": str(note.id), "title": note.class_title, "course": note.course_name, "status": "pending", "error": None, "digest": content_digest(note)} for note in notes])
        db.add(job)
        db.commit()
        db.refresh(job)
        return serialize_job(job)


@router.get("/regeneration/jobs")
def regeneration_jobs(db: Session = Depends(get_db)):
    return [serialize_job(job) for job in db.query(models.RegenerationJob).order_by(models.RegenerationJob.created_at.desc()).limit(30).all()]
