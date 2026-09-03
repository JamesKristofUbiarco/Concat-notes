import enum
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, Enum, ForeignKey, Integer, JSON, Boolean, Date, Float, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
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
    flashcard_target = Column(Integer, nullable=True)
    composition_profile = Column(String(100), nullable=False, default="adaptive")

    # Relación 1:1 con la nota procesada
    processed_note = relationship("ProcessedNote", back_populates="raw_note", uselist=False, cascade="all, delete-orphan")
    images = relationship("RawNoteImage", back_populates="raw_note", cascade="all, delete-orphan", order_by="RawNoteImage.created_at.asc()")


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
    image_type = Column(String(20), default="image", nullable=False)
    document_asset_id = Column(UUID(as_uuid=True), ForeignKey("document_assets.id", ondelete="SET NULL"), nullable=True)
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


class LocalSyncConfig(Base):
    """Configuración única del exportador de Markdown a una carpeta montada."""
    __tablename__ = "local_sync_config"

    id = Column(Integer, primary_key=True, default=1)
    enabled = Column(Boolean, nullable=False, default=False)
    destination_subpath = Column(String(500), nullable=False, default="Cursos")
    assets_subdirectory = Column(String(120), nullable=False, default="ANEXOS")
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class CourseSyncState(Base):
    """Selección y checkpoint de sincronización de un curso."""
    __tablename__ = "course_sync_states"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_name = Column(String(255), nullable=False, unique=True)
    enabled = Column(Boolean, nullable=False, default=False)
    filename = Column(String(255), nullable=False, default="")
    status = Column(String(32), nullable=False, default="disabled")
    last_export_hash = Column(String(64), nullable=True)
    last_file_hash = Column(String(64), nullable=True)
    conflict_db_path = Column(String(700), nullable=True)
    last_error = Column(Text, nullable=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    external_changed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class CourseGlossary(Base):
    """Glosario compilado de términos para un curso completo."""
    __tablename__ = "course_glossaries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_name = Column(String(255), nullable=False, unique=True)
    entries = Column(JSON, default=list)
    compiled_markdown = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class SourceChunk(Base):
    """Evidencia original indexada; nunca sustituye ni modifica la nota cruda."""
    __tablename__ = "source_chunks"
    __table_args__ = (UniqueConstraint("raw_note_id", "content_hash", name="uq_source_chunk_note_hash"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_note_id = Column(UUID(as_uuid=True), ForeignKey("raw_notes.id", ondelete="CASCADE"), nullable=False)
    source_type = Column(String(32), nullable=False)
    content = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    char_start = Column(Integer, nullable=True)
    char_end = Column(Integer, nullable=True)
    embedding = Column(Vector(1024), nullable=False)
    is_dummy_embedding = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class NoteClaim(Base):
    """Afirmación atómica con evidencia y relación respecto al conocimiento previo."""
    __tablename__ = "note_claims"
    __table_args__ = (UniqueConstraint("raw_note_id", "claim_hash", name="uq_note_claim_hash"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_note_id = Column(UUID(as_uuid=True), ForeignKey("raw_notes.id", ondelete="CASCADE"), nullable=False)
    prior_claim_id = Column(UUID(as_uuid=True), ForeignKey("note_claims.id", ondelete="SET NULL"), nullable=True)
    concept = Column(String(255), default="", nullable=False)
    statement = Column(Text, nullable=False)
    claim_hash = Column(String(64), nullable=False)
    novelty_relation = Column(String(16), default="NEW", nullable=False)
    evidence_source_type = Column(String(32), default="transcription", nullable=False)
    evidence_text = Column(Text, default="", nullable=False)
    evidence_start = Column(Integer, nullable=True)
    evidence_end = Column(Integer, nullable=True)
    confidence = Column(Float, default=1.0, nullable=False)
    embedding = Column(Vector(1024), nullable=False)
    is_dummy_embedding = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class FlashcardRecord(Base):
    """Registro histórico para deduplicación semántica de tarjetas por curso."""
    __tablename__ = "flashcard_records"
    __table_args__ = (UniqueConstraint("raw_note_id", "fingerprint", name="uq_flashcard_note_fingerprint"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_note_id = Column(UUID(as_uuid=True), ForeignKey("raw_notes.id", ondelete="CASCADE"), nullable=True)
    structured_document_id = Column(UUID(as_uuid=True), ForeignKey("structured_note_documents.id", ondelete="CASCADE"), nullable=True, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    fingerprint = Column(String(64), nullable=False)
    embedding = Column(Vector(1024), nullable=False)
    is_dummy_embedding = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    candidate_status = Column(String(16), nullable=False, default="active")
    learning_state = Column(String(16), nullable=False, default="new")
    due_at = Column(DateTime(timezone=True), nullable=True)
    last_reviewed_at = Column(DateTime(timezone=True), nullable=True)
    interval_days = Column(Integer, nullable=False, default=0)
    ease_factor = Column(Float, nullable=False, default=2.5)
    repetitions = Column(Integer, nullable=False, default=0)
    lapses = Column(Integer, nullable=False, default=0)
    review_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    reviews = relationship("FlashcardReview", back_populates="flashcard", cascade="all, delete-orphan")


class FlashcardReview(Base):
    """Historial inmutable de calificaciones de repaso."""
    __tablename__ = "flashcard_reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    flashcard_id = Column(UUID(as_uuid=True), ForeignKey("flashcard_records.id", ondelete="CASCADE"), nullable=False)
    rating = Column(Integer, nullable=False)
    previous_state = Column(String(16), nullable=False)
    new_state = Column(String(16), nullable=False)
    previous_interval_days = Column(Integer, nullable=False, default=0)
    scheduled_interval_days = Column(Integer, nullable=False, default=0)
    reviewed_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    flashcard = relationship("FlashcardRecord", back_populates="reviews")


class GenerationArtifact(Base):
    """Componentes y métricas del pipeline; el Markdown canónico sigue en processed_notes."""
    __tablename__ = "generation_artifacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    processed_note_id = Column(UUID(as_uuid=True), ForeignKey("processed_notes.id", ondelete="CASCADE"), nullable=False, unique=True)
    pipeline_version = Column(String(32), nullable=False)
    body_markdown = Column(Text, default="", nullable=False)
    glossary_markdown = Column(Text, default="", nullable=False)
    flashcards_markdown = Column(Text, default="", nullable=False)
    evidence_manifest = Column(JSON, default=dict)
    metrics = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class KnowledgeIndexState(Base):
    """Checkpoint reanudable del índice derivado por nota."""
    __tablename__ = "knowledge_index_states"

    raw_note_id = Column(UUID(as_uuid=True), ForeignKey("raw_notes.id", ondelete="CASCADE"), primary_key=True)
    index_version = Column(String(32), nullable=False)
    status = Column(String(16), nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class SourceDocument(Base):
    """Original PDF/EPUB and its locally discovered structure."""
    __tablename__ = "source_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255), nullable=False)
    media_type = Column(String(100), nullable=False)
    format = Column(String(8), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False, index=True)
    storage_key = Column(String(700), nullable=False, unique=True)
    page_count = Column(Integer, nullable=True)
    title = Column(String(500), nullable=False, default="")
    author = Column(String(500), nullable=False, default="")
    language = Column(String(32), nullable=False, default="")
    parser_name = Column(String(100), nullable=False, default="")
    parser_version = Column(String(50), nullable=False, default="")
    status = Column(String(32), nullable=False, default="uploaded")
    capabilities = Column(JSON, default=dict, nullable=False)
    warnings = Column(JSON, default=list, nullable=False)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class DocumentSection(Base):
    __tablename__ = "document_sections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("document_sections.id", ondelete="CASCADE"), nullable=True)
    order_index = Column(Integer, nullable=False)
    level = Column(Integer, nullable=False, default=1)
    title = Column(String(1000), nullable=False)
    source_kind = Column(String(32), nullable=False)
    page_start = Column(Integer, nullable=True)
    page_end = Column(Integer, nullable=True)
    epub_href = Column(String(1000), nullable=True)
    fragment_id = Column(String(500), nullable=True)
    confidence = Column(Float, nullable=False, default=1.0)


class DocumentElement(Base):
    __tablename__ = "document_elements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False)
    section_id = Column(UUID(as_uuid=True), ForeignKey("document_sections.id", ondelete="SET NULL"), nullable=True)
    order_index = Column(Integer, nullable=False)
    page_number = Column(Integer, nullable=True)
    element_type = Column(String(32), nullable=False)
    bbox_json = Column(JSON, nullable=True)
    text = Column(Text, nullable=False, default="")
    caption = Column(Text, nullable=False, default="")
    visual_description = Column(Text, nullable=False, default="")
    structured_data = Column(JSON, default=dict, nullable=False)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("document_assets.id", ondelete="SET NULL"), nullable=True)
    content_hash = Column(String(64), nullable=False)
    parser = Column(String(100), nullable=False)
    model = Column(String(255), nullable=False, default="")
    status = Column(String(32), nullable=False, default="extracted")
    status_reason = Column(Text, nullable=False, default="")


class DocumentAsset(Base):
    __tablename__ = "document_assets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False)
    storage_key = Column(String(700), nullable=False, unique=True)
    media_type = Column(String(100), nullable=False)
    kind = Column(String(32), nullable=False)
    page_number = Column(Integer, nullable=True)
    content_hash = Column(String(64), nullable=False)
    perceptual_hash = Column(String(64), nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    description = Column(Text, nullable=False, default="")
    analysis_model = Column(String(255), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class DocumentJob(Base):
    __tablename__ = "document_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False, default="pending")
    stage = Column(String(64), nullable=False, default="queued")
    progress = Column(Integer, nullable=False, default=0)
    message = Column(Text, nullable=False, default="Pendiente")
    error = Column(Text, nullable=True)
    profile = Column(String(16), nullable=False, default="balanced")
    selection_json = Column(JSON, default=dict, nullable=False)
    options_json = Column(JSON, default=dict, nullable=False)
    warnings = Column(JSON, default=list, nullable=False)
    heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    attempt = Column(Integer, nullable=False, default=0)
    cancel_requested = Column(Boolean, nullable=False, default=False)
    idempotency_key = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class DocumentRun(Base):
    __tablename__ = "document_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(UUID(as_uuid=True), ForeignKey("document_jobs.id", ondelete="SET NULL"), nullable=True)
    selection_json = Column(JSON, default=dict, nullable=False)
    profile = Column(String(16), nullable=False)
    model_snapshot = Column(JSON, default=dict, nullable=False)
    parser_version = Column(String(50), nullable=False, default="1")
    estimated_cost_usd = Column(Float, nullable=False, default=0.0)
    approved_cost_usd = Column(Float, nullable=False, default=1.0)
    actual_cost_usd = Column(Float, nullable=False, default=0.0)
    status = Column(String(32), nullable=False, default="processing")
    warnings = Column(JSON, default=list, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    finished_at = Column(DateTime(timezone=True), nullable=True)


class DocumentDraft(Base):
    __tablename__ = "document_drafts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("document_runs.id", ondelete="CASCADE"), nullable=False)
    order_index = Column(Integer, nullable=False)
    title = Column(String(1000), nullable=False)
    heading_path = Column(JSON, default=list, nullable=False)
    page_ranges = Column(JSON, default=list, nullable=False)
    source_markdown = Column(Text, nullable=False)
    course_name = Column(String(255), nullable=False, default="")
    course_module = Column(String(255), nullable=False, default="")
    class_title = Column(String(255), nullable=False, default="")
    asset_ids = Column(JSON, default=list, nullable=False)
    raw_note_id = Column(UUID(as_uuid=True), ForeignKey("raw_notes.id", ondelete="SET NULL"), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)


# ============================================================================
# DOCUMENTO CORNELL ESTRUCTURADO
# ============================================================================

class Workspace(Base):
    """Ámbito personal implícito; prepara aislamiento futuro sin añadir login."""
    __tablename__ = "workspaces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug = Column(String(100), nullable=False, unique=True, default="default")
    name = Column(String(255), nullable=False, default="Mi espacio")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class NoteCollection(Base):
    __tablename__ = "note_collections"
    __table_args__ = (UniqueConstraint("workspace_id", "name", name="uq_note_collection_workspace_name"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False, default="")
    order_index = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class StructuredNoteDocument(Base):
    """Fuente de verdad editable para contenido, relaciones y layout Cornell."""
    __tablename__ = "structured_note_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    raw_note_id = Column(UUID(as_uuid=True), ForeignKey("raw_notes.id", ondelete="SET NULL"), nullable=True, index=True)
    collection_id = Column(UUID(as_uuid=True), ForeignKey("note_collections.id", ondelete="SET NULL"), nullable=True)
    origin_kind = Column(String(32), nullable=False)
    schema_version = Column(String(16), nullable=False, default="1.0")
    migration_status = Column(String(24), nullable=False, default="native")
    current_revision_id = Column(UUID(as_uuid=True), nullable=True)
    revision_number = Column(Integer, nullable=False, default=0)
    document_json = Column(JSONB, nullable=False, default=dict)
    rendered_markdown = Column(Text, nullable=False, default="")
    sync_enabled = Column(Boolean, nullable=False, default=False)
    sync_status = Column(String(24), nullable=False, default="disabled")
    sync_filename = Column(String(255), nullable=False, default="")
    last_sync_hash = Column(String(64), nullable=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class NoteRevision(Base):
    __tablename__ = "note_revisions"
    __table_args__ = (UniqueConstraint("document_id", "revision_number", name="uq_note_revision_number"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("structured_note_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_revision_id = Column(UUID(as_uuid=True), ForeignKey("note_revisions.id", ondelete="SET NULL"), nullable=True)
    revision_number = Column(Integer, nullable=False)
    change_kind = Column(String(32), nullable=False)
    change_summary = Column(Text, nullable=False, default="")
    actor = Column(String(24), nullable=False, default="user")
    document_json = Column(JSONB, nullable=False)
    rendered_markdown = Column(Text, nullable=False)
    provenance = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class NoteEditSession(Base):
    __tablename__ = "note_edit_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("structured_note_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False, default="Edición con IA")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class NoteEditMessage(Base):
    __tablename__ = "note_edit_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("note_edit_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    scope_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class NotePatchProposal(Base):
    __tablename__ = "note_patch_proposals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("note_edit_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    base_revision_id = Column(UUID(as_uuid=True), ForeignKey("note_revisions.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(16), nullable=False, default="validated")
    intent = Column(Text, nullable=False, default="")
    summary = Column(Text, nullable=False, default="")
    operations = Column(JSONB, nullable=False, default=list)
    validation = Column(JSONB, nullable=False, default=dict)
    model_snapshot = Column(JSONB, nullable=False, default=dict)
    applied_revision_id = Column(UUID(as_uuid=True), ForeignKey("note_revisions.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class NoteStyleProfile(Base):
    __tablename__ = "note_style_profiles"
    __table_args__ = (UniqueConstraint("workspace_id", "slug", name="uq_note_style_workspace_slug"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    slug = Column(String(100), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False, default="")
    rules_json = Column(JSONB, nullable=False, default=dict)
    version = Column(Integer, nullable=False, default=1)
    is_builtin = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class NoteStyleExample(Base):
    __tablename__ = "note_style_examples"
    __table_args__ = (UniqueConstraint("profile_id", "document_id", name="uq_note_style_example"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id = Column(UUID(as_uuid=True), ForeignKey("note_style_profiles.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(UUID(as_uuid=True), ForeignKey("structured_note_documents.id", ondelete="CASCADE"), nullable=False)
    methodology_summary = Column(Text, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class FlashcardSource(Base):
    """Vínculo derivado; no controla el progreso ni la identidad de la tarjeta."""
    __tablename__ = "flashcard_sources"
    __table_args__ = (UniqueConstraint("flashcard_id", "document_id", "block_id", name="uq_flashcard_source_block"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    flashcard_id = Column(UUID(as_uuid=True), ForeignKey("flashcard_records.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("structured_note_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    block_id = Column(UUID(as_uuid=True), nullable=False)
    source_revision_id = Column(UUID(as_uuid=True), ForeignKey("note_revisions.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
