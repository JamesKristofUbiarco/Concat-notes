from datetime import datetime
from typing import List, Optional, Union
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


class CourseSyncUpdate(BaseModel):
    enabled: bool


class LocalSyncRunRequest(BaseModel):
    course_name: Optional[str] = None


class LocalSyncResolveRequest(BaseModel):
    action: str = Field(..., pattern="^(integrate_external|restore_database)$")


class LocalDirectoryCreate(BaseModel):
    parent: str = ""
    name: str = Field(..., min_length=1, max_length=120)
