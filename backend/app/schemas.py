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
    code_snippets: List[CodeSnippetBase] = []
    command_snippets: List[CommandSnippetBase] = []

class NoteCreate(NoteDataBase):
    pass

class NoteUpdate(NoteDataBase):
    pass

# --- Schemas de Salida (Respuestas) ---

class ProcessedNoteResponse(BaseModel):
    id: UUID
    raw_note_id: UUID
    structured_markdown: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class RawNoteResponse(NoteDataBase):
    id: UUID
    status: QueueStatus
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
