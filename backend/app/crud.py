from datetime import datetime
from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session

from app import models, schemas

# 1. Recuperar notas por su estado en la cola (Ej: pending o processed)
def get_raw_notes_by_status(db: Session, status: models.QueueStatus) -> List[models.RawNote]:
    return (
        db.query(models.RawNote)
        .filter(models.RawNote.status == status)
        .order_by(models.RawNote.created_at.desc())
        .all()
    )

# 2. Recuperar una nota específica por su ID
def get_note_by_id(db: Session, note_id: UUID) -> Optional[models.RawNote]:
    return db.query(models.RawNote).filter(models.RawNote.id == note_id).first()

# 3. Crear una nueva nota en la cola (con estado 'pending')
def create_raw_note(db: Session, note_in: schemas.NoteCreate) -> models.RawNote:
    # Convertir snippets a formato JSON listable serializable
    code_snippets = [s.model_dump() for s in note_in.code_snippets]
    command_snippets = [c.model_dump() for c in note_in.command_snippets]
    
    db_raw_note = models.RawNote(
        writing_mode=note_in.writing_mode,
        platform=note_in.platform,
        course_name=note_in.course_name,
        teacher=note_in.teacher,
        course_module=note_in.course_module,
        class_title=note_in.class_title,
        transcription=note_in.transcription,
        class_summary=note_in.class_summary,
        my_notes=note_in.my_notes,
        code_snippets=code_snippets,
        command_snippets=command_snippets,
        status=models.QueueStatus.PENDING
    )
    db.add(db_raw_note)
    db.commit()
    db.refresh(db_raw_note)
    return db_raw_note

# 4. Actualizar una nota existente en la cola
def update_raw_note(db: Session, note_id: UUID, note_in: schemas.NoteUpdate) -> Optional[models.RawNote]:
    db_raw_note = get_note_by_id(db, note_id)
    if not db_raw_note:
        return None
        
    code_snippets = [s.model_dump() for s in note_in.code_snippets]
    command_snippets = [c.model_dump() for c in note_in.command_snippets]
    
    db_raw_note.writing_mode = note_in.writing_mode
    db_raw_note.platform = note_in.platform
    db_raw_note.course_name = note_in.course_name
    db_raw_note.teacher = note_in.teacher
    db_raw_note.course_module = note_in.course_module
    db_raw_note.class_title = note_in.class_title
    db_raw_note.transcription = note_in.transcription
    db_raw_note.class_summary = note_in.class_summary
    db_raw_note.my_notes = note_in.my_notes
    db_raw_note.code_snippets = code_snippets
    db_raw_note.command_snippets = command_snippets
    
    db.commit()
    db.refresh(db_raw_note)
    return db_raw_note

# 5. Eliminar una nota físicamente (el borrado en cascada limpia processed_notes y note_chunks)
def delete_note(db: Session, note_id: UUID) -> bool:
    db_raw_note = get_note_by_id(db, note_id)
    if not db_raw_note:
        return False
    db.delete(db_raw_note)
    db.commit()
    return True

# 6. Archivar nota: Crea la nota procesada (Markdown) y marca la nota cruda como procesada
def archive_note(db: Session, raw_note_id: UUID, structured_markdown: str) -> Optional[models.ProcessedNote]:
    db_raw_note = get_note_by_id(db, raw_note_id)
    if not db_raw_note:
        return None
        
    # Actualizar estado de la nota cruda a 'processed'
    db_raw_note.status = models.QueueStatus.PROCESSED
    db_raw_note.processed_at = datetime.utcnow()
    
    # Comprobar si ya existía una nota procesada previa para evitar duplicados
    db_processed = db.query(models.ProcessedNote).filter(models.ProcessedNote.raw_note_id == raw_note_id).first()
    if db_processed:
        db_processed.structured_markdown = structured_markdown
    else:
        db_processed = models.ProcessedNote(
            raw_note_id=raw_note_id,
            structured_markdown=structured_markdown
        )
        db.add(db_processed)
        
    db.commit()
    db.refresh(db_processed)
    return db_processed

# 7. Obtener lista de cursos únicos que tienen notas procesadas
def get_courses_with_processed_notes(db: Session) -> List[str]:
    courses = (
        db.query(models.RawNote.course_name)
        .join(models.ProcessedNote, models.RawNote.id == models.ProcessedNote.raw_note_id)
        .filter(models.RawNote.status == models.QueueStatus.PROCESSED)
        .distinct()
        .all()
    )
    return [c[0] for c in courses if c[0]]

# 8. Obtener todas las notas procesadas de un curso específico ordenadas cronológicamente
def get_processed_notes_by_course(db: Session, course_name: str) -> List[models.RawNote]:
    return (
        db.query(models.RawNote)
        .join(models.ProcessedNote, models.RawNote.id == models.ProcessedNote.raw_note_id)
        .filter(
            models.RawNote.course_name == course_name,
            models.RawNote.status == models.QueueStatus.PROCESSED
        )
        .order_by(models.RawNote.created_at.asc())
        .all()
    )
