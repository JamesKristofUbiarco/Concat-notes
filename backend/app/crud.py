import calendar
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo
from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session

from app import models, schemas
from app.storage import delete_file_from_rustfs

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
        class_minutes=note_in.class_minutes,
        order_index=note_in.order_index,
        code_snippets=code_snippets,
        command_snippets=command_snippets,
        status=models.QueueStatus.PENDING
    )
    db.add(db_raw_note)
    db.commit()
    
    # Asociar imágenes subidas temporalmente
    if note_in.image_snippets:
        img_ids = [img.id for img in note_in.image_snippets]
        db_images = db.query(models.RawNoteImage).filter(models.RawNoteImage.id.in_(img_ids)).all()
        for db_img in db_images:
            db_img.raw_note_id = db_raw_note.id
        db.commit()

    db.refresh(db_raw_note)
    
    # Sincronizar automáticamente minutos de estudio (usando fecha LOCAL del usuario)
    if db_raw_note.class_minutes > 0:
        adjust_study_minutes(db, local_today(), db_raw_note.class_minutes)
        
    return db_raw_note

# 4. Actualizar una nota existente en la cola
def update_raw_note(db: Session, note_id: UUID, note_in: schemas.NoteUpdate) -> Optional[models.RawNote]:
    db_raw_note = get_note_by_id(db, note_id)
    if not db_raw_note:
        return None
        
    code_snippets = [s.model_dump() for s in note_in.code_snippets]
    command_snippets = [c.model_dump() for c in note_in.command_snippets]
    
    # Calcular diferencia de minutos de estudio
    old_minutes = db_raw_note.class_minutes or 0
    new_minutes = note_in.class_minutes
    diff = new_minutes - old_minutes
    
    db_raw_note.writing_mode = note_in.writing_mode
    db_raw_note.platform = note_in.platform
    db_raw_note.course_name = note_in.course_name
    db_raw_note.teacher = note_in.teacher
    db_raw_note.course_module = note_in.course_module
    db_raw_note.class_title = note_in.class_title
    db_raw_note.transcription = note_in.transcription
    db_raw_note.class_summary = note_in.class_summary
    db_raw_note.my_notes = note_in.my_notes
    db_raw_note.class_minutes = new_minutes
    db_raw_note.order_index = note_in.order_index
    db_raw_note.code_snippets = code_snippets
    db_raw_note.command_snippets = command_snippets
    
    # Sincronizar imágenes entrantes y eliminar huérfanas
    incoming_ids = {img.id for img in note_in.image_snippets}
    orphans = [img for img in db_raw_note.images if img.id not in incoming_ids]
    for img in orphans:
        delete_file_from_rustfs(img.filename)
        db.delete(img)
        
    new_img_ids = [img.id for img in note_in.image_snippets if img.id not in {existing_img.id for existing_img in db_raw_note.images}]
    if new_img_ids:
        db_images = db.query(models.RawNoteImage).filter(models.RawNoteImage.id.in_(new_img_ids)).all()
        for db_img in db_images:
            db_img.raw_note_id = db_raw_note.id
            
    db.commit()
    db.refresh(db_raw_note)
    
    # Sincronizar la diferencia con el día de creación de la nota
    if diff != 0:
        note_date = db_raw_note.created_at.date() if db_raw_note.created_at else local_today()
        adjust_study_minutes(db, note_date, diff)
        
    return db_raw_note

# 5. Eliminar una nota físicamente (el borrado en cascada limpia processed_notes y note_chunks)
def delete_note(db: Session, note_id: UUID) -> bool:
    db_raw_note = get_note_by_id(db, note_id)
    if not db_raw_note:
        return False
        
    # Guardar minutos y fecha para restar antes de eliminar
    note_minutes = db_raw_note.class_minutes or 0
    note_date = db_raw_note.created_at.date() if db_raw_note.created_at else local_today()
    
    # Eliminar físicamente todas las imágenes asociadas de RustFS
    for img in db_raw_note.images:
        delete_file_from_rustfs(img.filename)
        
    db.delete(db_raw_note)
    db.commit()
    
    # Restar automáticamente los minutos al día en que se tomó la clase
    if note_minutes > 0:
        adjust_study_minutes(db, note_date, -note_minutes)
        
    return True

# 6. Archivar nota: Crea la nota procesada (Markdown) y marca la nota cruda como procesada
def archive_note(db: Session, raw_note_id: UUID, structured_markdown: str, ai_comments: str = "") -> Optional[models.ProcessedNote]:
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
        db_processed.ai_comments = ai_comments
    else:
        db_processed = models.ProcessedNote(
            raw_note_id=raw_note_id,
            structured_markdown=structured_markdown,
            ai_comments=ai_comments
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
        .order_by(models.RawNote.order_index.asc(), models.RawNote.created_at.asc())
        .all()
    )

# 9. Actualizar el orden de las notas crudas para un curso
def update_course_order(db: Session, course_name: str, note_ids: List[UUID]) -> bool:
    # Verificamos que las notas pertenezcan al curso y existan
    notes = db.query(models.RawNote).filter(models.RawNote.id.in_(note_ids), models.RawNote.course_name == course_name).all()
    if not notes:
        return False
        
    notes_dict = {str(n.id): n for n in notes}
    
    for idx, note_id in enumerate(note_ids):
        note = notes_dict.get(str(note_id))
        if note:
            note.order_index = idx
            
    db.commit()
    return True


# ============================================================================
# STUDY TRACKER — CRUD
# ============================================================================

# Zona horaria local del usuario (CST = UTC-6)
_USER_TIMEZONE = ZoneInfo("America/Mexico_City")


def local_today() -> date:
    """Retorna la fecha LOCAL del usuario (America/Mexico_City),
    independientemente de que el servidor corra en UTC."""
    return datetime.now(tz=_USER_TIMEZONE).date()


# 10. Obtener la meta diaria actual del usuario
def get_daily_goal(db: Session) -> int:
    setting = db.query(models.UserSetting).filter(models.UserSetting.key == "daily_study_goal").first()
    if setting:
        return int(setting.value)
    return 60  # Valor por defecto

# 11. Actualizar la meta diaria (NO recalcula historial)
def set_daily_goal(db: Session, minutes: int) -> int:
    setting = db.query(models.UserSetting).filter(models.UserSetting.key == "daily_study_goal").first()
    if setting:
        setting.value = str(minutes)
    else:
        setting = models.UserSetting(key="daily_study_goal", value=str(minutes))
        db.add(setting)
    db.commit()
    return minutes

# Helper: Ajustar minutos de estudio de un día específico
def adjust_study_minutes(db: Session, study_date: date, minutes_diff: int) -> Optional[models.StudyLog]:
    if minutes_diff == 0:
        return None
        
    daily_goal = get_daily_goal(db)
    log = db.query(models.StudyLog).filter(models.StudyLog.study_date == study_date).first()
    
    if log:
        log.total_minutes = max(0, log.total_minutes + minutes_diff)
        log.daily_goal_at_time = daily_goal
        log.goal_percentage = (log.total_minutes / daily_goal) * 100.0 if daily_goal > 0 else 0.0
        # Al eliminar o modificar notas, el estado de la meta SÍ puede cambiar a incompleto (False)
        log.goal_met = log.total_minutes >= daily_goal
    else:
        # Solo crear log si estamos añadiendo minutos
        if minutes_diff > 0:
            percentage = (minutes_diff / daily_goal) * 100.0 if daily_goal > 0 else 0.0
            met = minutes_diff >= daily_goal
            log = models.StudyLog(
                study_date=study_date,
                total_minutes=minutes_diff,
                daily_goal_at_time=daily_goal,
                goal_percentage=percentage,
                goal_met=met
            )
            db.add(log)
            
    db.commit()
    if log:
        db.refresh(log)
    return log

# 12. Registrar minutos estudiados en el día actual (manual/directo)
def log_study_minutes(db: Session, minutes: int) -> models.StudyLog:
    return adjust_study_minutes(db, local_today(), minutes)

# 13. Obtener el log de estudio del día actual
def get_study_log_today(db: Session) -> Optional[models.StudyLog]:
    today = local_today()  # Fecha local del usuario (CST)
    return db.query(models.StudyLog).filter(models.StudyLog.study_date == today).first()

# 14. Obtener los logs de un mes completo para el calendario
def get_study_logs_for_month(db: Session, year: int, month: int) -> List[models.StudyLog]:
    # Calcular rango de fechas del mes
    first_day = date(year, month, 1)
    last_day_num = calendar.monthrange(year, month)[1]
    last_day = date(year, month, last_day_num)
    
    return (
        db.query(models.StudyLog)
        .filter(
            models.StudyLog.study_date >= first_day,
            models.StudyLog.study_date <= last_day
        )
        .order_by(models.StudyLog.study_date.asc())
        .all()
    )


def get_model_setting(db: Session, role: str) -> str:
    import os
    key = f"model_{role}"
    setting = db.query(models.UserSetting).filter(models.UserSetting.key == key).first()
    if setting:
        return setting.value
    # Fallbacks based on env variables or defaults
    if role == "synthesis":
        return os.getenv("GEMINI_MODEL", "google/gemini-3.5-flash")
    elif role == "query_expansion":
        return os.getenv("GEMINI_LITE_MODEL", "google/gemini-3.1-flash-lite")
    elif role == "image_analysis":
        return "gemini-3.5-flash"
    return ""


def set_model_setting(db: Session, role: str, model_id: str) -> str:
    key = f"model_{role}"
    setting = db.query(models.UserSetting).filter(models.UserSetting.key == key).first()
    if setting:
        setting.value = model_id
    else:
        setting = models.UserSetting(key=key, value=model_id)
        db.add(setting)
    db.commit()
    return model_id
