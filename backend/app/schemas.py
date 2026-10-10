from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union
from uuid import UUID
from pydantic import BaseModel, Field

from app.models import QueueStatus

# --- Schemas para Snippets Dinámicos ---

class CodeSnippetBase(BaseModel):
    id: Optional[str] = None
    lang: str = ""
    code: str = ""

    class Config:
        from_attributes = True

class CommandSnippetBase(BaseModel):
    id: Optional[str] = None
    order: str = ""
    lang: str = "bash"
    cmd: str = ""

    class Config:
        from_attributes = True

class ImageSnippetBase(BaseModel):
    id: UUID
    image_url: str
    filename: str
    descripcion_llm: Optional[str] = None
    image_type: str = "image"

    class Config:
        from_attributes = True

# --- Schemas de Entrada (Peticiones) ---

class NoteDataBase(BaseModel):
    writing_mode: str = ""
    platform: str = ""
    course_name: str = Field(..., min_length=2, description="El nombre del curso es obligatorio (mínimo 2 caracteres)")
    teacher: str = ""
    course_module: str = ""
    class_title: str = Field(..., min_length=2, description="El título de la clase es obligatorio (mínimo 2 caracteres)")
    transcription: str = ""
    class_summary: str = ""
    my_notes: str = ""
    class_minutes: int = 0
    order_index: int = 0
    code_snippets: List[CodeSnippetBase] = []
    command_snippets: List[CommandSnippetBase] = []
    image_snippets: List[ImageSnippetBase] = []
    flashcard_target: Optional[int] = None

class NoteCreate(NoteDataBase):
    pass

class NoteUpdate(NoteDataBase):
    pass

class ReorderRequest(BaseModel):
    note_ids: List[UUID]

# --- Schemas de Salida (Respuestas) ---

class ProcessedNoteResponse(BaseModel):
    id: UUID
    raw_note_id: UUID
    structured_markdown: str
    ai_comments: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class RawNoteResponse(NoteDataBase):
    id: UUID
    status: QueueStatus
    order_index: int = 0
    created_at: datetime
    updated_at: datetime
    processed_at: Optional[datetime] = None
    images: List[ImageSnippetBase] = []

    class Config:
        from_attributes = True

class FullNoteResponse(RawNoteResponse):
    # Incluye la nota procesada si el estado es 'processed'
    processed_note: Optional[ProcessedNoteResponse] = None

    class Config:
        from_attributes = True


# --- Schemas para Study Tracker ---

class StudyLogCreate(BaseModel):
    """Input para registrar minutos estudiados. Se suman al total del día."""
    minutes: int = Field(..., ge=1, description="Minutos de la clase (mínimo 1)")

class StudyLogResponse(BaseModel):
    study_date: datetime
    total_minutes: int
    daily_goal_at_time: int
    goal_percentage: float
    goal_met: bool

    class Config:
        from_attributes = True

class ClassInfoResponse(BaseModel):
    class_title: str
    course_name: str
    class_minutes: int

class CalendarDayResponse(BaseModel):
    date: str  # formato YYYY-MM-DD
    total_minutes: int
    goal_percentage: float
    goal_met: bool
    classes: List[ClassInfoResponse] = []

class MonthCalendarResponse(BaseModel):
    year: int
    month: int
    daily_goal: int
    days: List[CalendarDayResponse]

class StudySettingsUpdate(BaseModel):
    daily_goal: int = Field(..., ge=1, description="Meta diaria en minutos (mínimo 1)")

class StudySettingsResponse(BaseModel):
    daily_goal: int


class ReprocessEmbeddingsRequest(BaseModel):
    target: str  # 'all_dummies', 'course', or 'individual'
    course_name: Optional[str] = None
    note_id: Optional[UUID] = None


class ModelOption(BaseModel):
    id: str
    name: str
    provider: str
    transport: str
    transport_label: str
    capabilities: List[str]
    configured: bool
    unavailable_reason: Optional[str] = None


class ModelSettingsResponse(BaseModel):
    synthesis: str
    query_expansion: str
    image_analysis: str
    document_vision: str
    available: dict
    effective: dict


class ModelSettingUpdate(BaseModel):
    role: str
    model_id: str


class GenerationPipelineUpdate(BaseModel):
    version: str = Field(..., pattern="^(legacy|v2)$")


# --- Schemas para Glosario y Flashcards ---

class GlossaryItem(BaseModel):
    content: str
    sources: List[str] = []

class GlossaryEntry(BaseModel):
    term: str
    term_es: Optional[str] = None
    definition: str
    definition_sources: List[str] = []
    expansions: List[Union[GlossaryItem, str]] = []
    encyclopedia: List[Union[GlossaryItem, str]] = []
    sources: List[str] = []

class CourseGlossaryResponse(BaseModel):
    id: UUID
    course_name: str
    entries: List[GlossaryEntry]
    compiled_markdown: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class FlashcardDensityUpdate(BaseModel):
    flashcard_density: int = Field(..., ge=1, le=100, description="Cantidad de flashcards por cada 10,000 caracteres")


class FlashcardUpdate(BaseModel):
    question: Optional[str] = Field(None, min_length=1, max_length=4000)
    answer: Optional[str] = Field(None, min_length=1, max_length=12000)
    is_active: Optional[bool] = None


class FlashcardReviewCreate(BaseModel):
    rating: int = Field(..., ge=1, le=4)


# --- Sincronización local de Markdown ---

class LocalSyncConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    destination_subpath: Optional[str] = Field(None, min_length=1, max_length=500)
    assets_subdirectory: Optional[str] = Field(None, min_length=1, max_length=120)


class CourseSyncUpdate(BaseModel):
    enabled: bool


class DocumentSyncUpdate(BaseModel):
    enabled: bool


class LocalSyncRunRequest(BaseModel):
    course_name: Optional[str] = None


class LocalSyncResolveRequest(BaseModel):
    action: str = Field(..., pattern="^restore_database$")


class LocalDirectoryCreate(BaseModel):
    parent: str = ""
    name: str = Field(..., min_length=1, max_length=120)


# --- Procesamiento estructurado de documentos ---

class PageRange(BaseModel):
    start: int = Field(..., ge=1)
    end: int = Field(..., ge=1)


class DocumentSelection(BaseModel):
    mode: str = Field(..., pattern="^(full|sections|pages)$")
    section_ids: List[UUID] = []
    include_descendants: bool = True
    excluded_section_ids: List[UUID] = []
    ranges: List[PageRange] = []


class DocumentProcessRequest(BaseModel):
    selection: DocumentSelection
    profile: str = Field("balanced", pattern="^(local|balanced|accurate)$")
    approved_cost_usd: float = Field(1.0, ge=0, le=100)


class DocumentDraftUpdate(BaseModel):
    id: UUID
    course_name: str = Field(..., min_length=2, max_length=255)
    course_module: str = Field("", max_length=255)
    class_title: str = Field(..., min_length=2, max_length=255)
    source_markdown: Optional[str] = None


# --- Documento Cornell estructurado ---

BlockType = Literal[
    "question", "concept", "paragraph", "heading", "bullet_list", "numbered_list",
    "procedure", "code", "code_output", "command", "image", "table", "formula",
    "mermaid", "quote", "warning", "callout", "resource", "quiz", "project_goal",
    "summary", "markdown",
]
RelationType = Literal[
    "answers", "defines", "explains", "demonstrates", "produces", "warns_about",
    "references", "summarizes", "contrasts_with", "depends_on",
]


class NoteSectionData(BaseModel):
    id: UUID
    title: str = Field(..., min_length=1, max_length=500)
    order: int = 0


class NoteBlockData(BaseModel):
    id: UUID
    section_id: UUID
    type: BlockType
    lane: Literal["left", "right"]
    reading_order: int = 0
    content: Any = ""
    layout: Dict[str, Any] = {}
    sources: List[Dict[str, Any]] = []
    asset: Optional[Dict[str, Any]] = None


class NoteRelationData(BaseModel):
    id: UUID
    from_block_id: UUID
    to_block_id: UUID
    type: RelationType
    order: int = 0
    style: Dict[str, Any] = Field(default_factory=dict)


class NoteDocumentData(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    document_id: UUID
    origin: Dict[str, Any]
    metadata: Dict[str, Any]
    composition: Dict[str, Any] = {}
    sections: List[NoteSectionData]
    blocks: List[NoteBlockData]
    relations: List[NoteRelationData] = []


class StructuredNoteCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    course_name: str = Field("", max_length=255)
    course_module: str = Field("", max_length=255)
    class_title: str = Field("", max_length=255)
    collection_id: Optional[UUID] = None
    tags: List[str] = []
    linked_raw_note_id: Optional[UUID] = None
    origin_kind: Literal["manual_independent", "manual_class_companion"] = "manual_independent"


class NoteOperation(BaseModel):
    op: str
    target_id: Optional[UUID] = None
    value: Any = None
    block: Optional[Dict[str, Any]] = None
    section: Optional[Dict[str, Any]] = None
    relation: Optional[Dict[str, Any]] = None


class NoteOperationsRequest(BaseModel):
    base_revision_id: UUID
    operations: List[NoteOperation] = Field(..., min_length=1)
    summary: str = Field("Edición manual", max_length=500)


class NoteEditSessionCreate(BaseModel):
    title: str = Field("Edición con IA", min_length=1, max_length=255)


class NoteEditMessageCreate(BaseModel):
    model_id: Optional[str] = None
    image_ids: List[UUID] = Field(default_factory=list, max_length=4)
    content: str = Field(..., min_length=1, max_length=20000)
    scope: Literal["selected_blocks", "whole_note"] = "whole_note"
    block_ids: List[UUID] = []


class PatchApplyRequest(BaseModel):
    operation_indexes: List[int]


class CollectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field("", max_length=2000)


class DocumentConfirmRequest(BaseModel):
    drafts: List[DocumentDraftUpdate]
    my_notes: str = Field("", max_length=50000)
    writing_mode: str = "Resumir el contenido pero manteniendo toda la información importante"
    flashcard_target: Optional[int] = Field(None, ge=1, le=100)
