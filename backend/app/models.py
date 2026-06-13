import enum
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, Enum, ForeignKey, Integer, JSON, Boolean, Date, Float
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
    class_minutes = Column(Integer, default=0, nullable=False)

    # Relación 1:1 con la nota procesada
    processed_note = relationship("ProcessedNote", back_populates="raw_note", uselist=False, cascade="all, delete-orphan")
    images = relationship("RawNoteImage", back_populates="raw_note", cascade="all, delete-orphan")


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


class RawNoteImage(Base):
    __tablename__ = "raw_note_images"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_note_id = Column(UUID(as_uuid=True), ForeignKey("raw_notes.id", ondelete="CASCADE"), nullable=True)
    image_url = Column(String(500), nullable=False)
    filename = Column(String(255), nullable=False)
    descripcion_llm = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relación
    raw_note = relationship("RawNote", back_populates="images")


class StudyLog(Base):
    """Registro diario de minutos estudiados. Un registro por día."""
    __tablename__ = "study_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    study_date = Column(Date, nullable=False, unique=True)
    total_minutes = Column(Integer, nullable=False, default=0)
    daily_goal_at_time = Column(Integer, nullable=False)
    goal_percentage = Column(Float, nullable=False, default=0.0)
    goal_met = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class UserSetting(Base):
    """Configuración del usuario como pares clave-valor."""
    __tablename__ = "user_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = Column(String(100), nullable=False, unique=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
