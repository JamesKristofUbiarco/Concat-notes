from datetime import datetime
from typing import List, Optional
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
    code_snippets: List[CodeSnippetBase] = []
    command_snippets: List[CommandSnippetBase] = []

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

