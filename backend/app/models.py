import enum
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, Enum, ForeignKey, Integer, JSON, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from app.database import Base

class QueueStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"

class RawNote(Base):
    __tablename__ = "raw_notes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    writing_mode = Column(Text, default="")
    platform = Column(String(100), default="")
    course_name = Column(String(255), nullable=False)
    teacher = Column(String(255), default="")
    course_module = Column(String(255), default="")
    class_title = Column(String(255), nullable=False)
    transcription = Column(Text, default="")
    class_summary = Column(Text, default="")
    my_notes = Column(Text, default="")
    
    # Snippets dinámicos de código y comandos almacenados como JSON
    code_snippets = Column(JSON, default=list)
    command_snippets = Column(JSON, default=list)
    
    # Estado de la cola y marcas de tiempo
    status = Column(Enum(QueueStatus, name="queue_status", values_callable=lambda x: [e.value for e in x]), default=QueueStatus.PENDING)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    order_index = Column(Integer, default=0)

    # Relación 1:1 con la nota procesada
    processed_note = relationship("ProcessedNote", back_populates="raw_note", uselist=False, cascade="all, delete-orphan")


class ProcessedNote(Base):
    __tablename__ = "processed_notes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_note_id = Column(UUID(as_uuid=True), ForeignKey("raw_notes.id", ondelete="CASCADE"), unique=True)
    structured_markdown = Column(Text, nullable=False)
    ai_comments = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relaciones
    raw_note = relationship("RawNote", back_populates="processed_note")
    chunks = relationship("NoteChunk", back_populates="processed_note", cascade="all, delete-orphan")


class NoteChunk(Base):
    __tablename__ = "note_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    processed_note_id = Column(UUID(as_uuid=True), ForeignKey("processed_notes.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    
    # Vector de pgvector especializado para embeddings de 1024 dimensiones (Voyage-4)
    embedding = Column(Vector(1024), nullable=False)
    is_dummy_embedding = Column(Boolean, default=False, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relación
    processed_note = relationship("ProcessedNote", back_populates="chunks")
