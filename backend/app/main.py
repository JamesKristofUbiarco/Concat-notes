import os
import re
import asyncio
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app import models, schemas, crud, llm_models
from app.database import get_db
from app.worker import processing_lock, _store_embedding, worker_loop, generate_note_state, persist_generated_result
from app import local_sync, flashcards


# ============================================================================
# LIFESPAN — Registrar el worker automático
# ============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicia el worker automático al arrancar el servidor y lo cancela al detenerlo."""
    from app.storage import init_storage
    init_storage()
    task = asyncio.create_task(worker_loop())
    sync_task = asyncio.create_task(local_sync.local_sync_loop())
    yield
    task.cancel()
    sync_task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    try:
        await sync_task
    except asyncio.CancelledError:
        pass


# Inicializar la aplicación FastAPI
app = FastAPI(
    title="Next.js Notes Concatenator API",
    description="Backend en FastAPI para gestionar la cola de apuntes de cursos e integración de pgvector/PostgreSQL.",
    version="2.0.0",
    lifespan=lifespan
)

# Configurar middleware de CORS (Cross-Origin Resource Sharing)
# Permite peticiones de nuestro frontend Next.js en puerto 3000
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# --- Endpoints de la API ---

@app.get("/api/health")
def health_check():
    return {"status": "healthy", "service": "notes-concatenator-backend", "version": "2.0.0"}


# --- Endpoints del Study Tracker ---

@app.post("/api/study/log", response_model=schemas.StudyLogResponse)
def log_study_minutes(log_in: schemas.StudyLogCreate, db: Session = Depends(get_db)):
    """
    Registra minutos estudiados en el día actual.
    Los minutos se suman al total acumulado del día.
    Si se alcanza la meta diaria, goal_met se marca TRUE (inmutable).
    """
    log = crud.log_study_minutes(db=db, minutes=log_in.minutes)
    return log


@app.get("/api/study/today")
def get_study_today(db: Session = Depends(get_db)):
    """
    Retorna el progreso de estudio del día actual.
    Si no hay registro, retorna valores por defecto con la meta actual.
    """
    log = crud.get_study_log_today(db)
    daily_goal = crud.get_daily_goal(db)
    if log:
        return {
            "study_date": log.study_date.isoformat(),
            "total_minutes": log.total_minutes,
            "daily_goal": daily_goal,
            "goal_percentage": log.goal_percentage,
            "goal_met": log.goal_met
        }
    return {
        "study_date": None,
        "total_minutes": 0,
        "daily_goal": daily_goal,
        "goal_percentage": 0.0,
        "goal_met": False
    }


@app.get("/api/study/calendar/{year}/{month}", response_model=schemas.MonthCalendarResponse)
def get_study_calendar(year: int, month: int, db: Session = Depends(get_db)):
    """
    Retorna los datos de estudio de un mes completo para el calendario.
    Incluye solo los días con actividad registrada y la lista de clases de cada día.
    """
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="Mes inválido (1-12)")
    if year < 2000 or year > 2100:
        raise HTTPException(status_code=400, detail="Año inválido (2000-2100)")
    
    logs = crud.get_study_logs_for_month(db, year, month)
    daily_goal = crud.get_daily_goal(db)
    
    # Obtener todas las notas creadas en el año y mes especificados para poblar los tooltips
    from sqlalchemy import extract
    notes = (
        db.query(models.RawNote)
        .filter(
            extract('year', models.RawNote.created_at) == year,
            extract('month', models.RawNote.created_at) == month
        )
        .all()
    )
    
    notes_by_date = {}
    for n in notes:
        if n.created_at:
            date_str = n.created_at.date().isoformat()
            if date_str not in notes_by_date:
                notes_by_date[date_str] = []
            notes_by_date[date_str].append(
                schemas.ClassInfoResponse(
                    class_title=n.class_title,
                    course_name=n.course_name,
                    class_minutes=n.class_minutes
                )
            )
            
    days = [
        schemas.CalendarDayResponse(
            date=log.study_date.isoformat(),
            total_minutes=log.total_minutes,
            goal_percentage=log.goal_percentage,
            goal_met=log.goal_met,
            classes=notes_by_date.get(log.study_date.isoformat(), [])
        )
        for log in logs
    ]
    
    return schemas.MonthCalendarResponse(
        year=year,
        month=month,
        daily_goal=daily_goal,
        days=days
    )


@app.get("/api/study/settings", response_model=schemas.StudySettingsResponse)
def get_study_settings(db: Session = Depends(get_db)):
    """Obtener la configuración actual del Study Tracker."""
    daily_goal = crud.get_daily_goal(db)
    return {"daily_goal": daily_goal}


@app.put("/api/study/settings", response_model=schemas.StudySettingsResponse)
def update_study_settings(settings_in: schemas.StudySettingsUpdate, db: Session = Depends(get_db)):
    """
    Actualizar la meta diaria de estudio.
    NO recalcula el historial — los días cumplidos son victorias permanentes.
    """
    daily_goal = crud.set_daily_goal(db, settings_in.daily_goal)
    return {"daily_goal": daily_goal}


@app.get("/api/settings/models", response_model=schemas.ModelSettingsResponse)
def get_model_settings(db: Session = Depends(get_db)):
    """Obtiene la configuración actual de modelos activos y las opciones del catálogo."""
    return llm_models.model_settings_payload(db)


@app.put("/api/settings/models", response_model=schemas.ModelSettingsResponse)
def update_model_settings(update_in: schemas.ModelSettingUpdate, db: Session = Depends(get_db)):
    """Actualiza el modelo de IA seleccionado para un rol en particular."""
    role = update_in.role
    model_id = update_in.model_id
    
    if role not in llm_models.MODEL_CATALOG:
        raise HTTPException(status_code=400, detail=f"Rol '{role}' inválido. Debe ser uno de: {list(llm_models.MODEL_CATALOG.keys())}")
        
    allowed_ids = [m["id"] for m in llm_models.MODEL_CATALOG[role]]
    if model_id not in allowed_ids:
        raise HTTPException(status_code=400, detail=f"Modelo '{model_id}' no permitido para el rol '{role}'. Permitidos: {allowed_ids}")

    try:
        llm_models.resolve_model(role, model_id, allow_fallback=False)
    except llm_models.ModelResolutionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
        
    crud.set_model_setting(db, role, model_id)
    return llm_models.model_settings_payload(db)


@app.get("/api/settings/generation-pipeline")
def get_generation_pipeline(db: Session = Depends(get_db)):
    return {"version": crud.get_generation_pipeline_version(db)}


@app.put("/api/settings/generation-pipeline")
def update_generation_pipeline(update_in: schemas.GenerationPipelineUpdate, db: Session = Depends(get_db)):
    return {"version": crud.set_generation_pipeline_version(db, update_in.version)}


@app.get("/api/knowledge/status")
def get_knowledge_status(db: Session = Depends(get_db)):
    from app.knowledge import knowledge_status
    return knowledge_status(db)


from fastapi import File, UploadFile
from fastapi.responses import StreamingResponse
from app import backup

ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def read_image_upload(file: UploadFile) -> tuple[bytes, str]:
    """Lee una imagen con límites explícitos y deriva la extensión del MIME."""
    max_bytes = int(os.getenv("MAX_IMAGE_UPLOAD_MB", "20")) * 1024 * 1024
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="Formato no permitido. Usa PNG, JPEG, GIF o WebP.")

    contents = file.file.read(max_bytes + 1)
    if not contents:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"La imagen supera el límite de {max_bytes // (1024 * 1024)} MB.",
        )
    return contents, ALLOWED_IMAGE_CONTENT_TYPES[content_type]

@app.get("/api/db/backup")
def download_backup():
    """Genera y descarga un archivo ZIP con el dump de base de datos e imágenes."""
    try:
        zip_buffer = backup.create_full_backup()
        # Generar nombre con timestamp
        filename = f"backup_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.zip"
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al generar el respaldo de datos: {e}"
        )

@app.post("/api/db/restore")
def upload_restore(file: UploadFile = File(...)):
    """Recibe un archivo ZIP de respaldo y restaura el estado completo de la app."""
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="El archivo debe ser un .zip válido")
        
    try:
        max_bytes = int(os.getenv("MAX_BACKUP_UPLOAD_MB", "2048")) * 1024 * 1024
        contents = file.file.read(max_bytes + 1)
        if len(contents) > max_bytes:
            raise HTTPException(status_code=413, detail="El respaldo supera el límite configurado.")
        res = backup.restore_full_backup(contents)
        return res
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error durante la restauración del respaldo: {e}"
        )

@app.post("/api/notes/images/upload", response_model=schemas.ImageSnippetBase)
def upload_image(file: UploadFile = File(...), db: Session = Depends(get_db)):
    from app.storage import upload_file_to_rustfs
    import uuid
    
    contents, ext = read_image_upload(file)
            
    unique_filename = f"{uuid.uuid4().hex}{ext}"
    try:
        image_url = upload_file_to_rustfs(unique_filename, contents, file.content_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo guardar la imagen en RustFS: {e}")
        
    db_image = models.RawNoteImage(
        image_url=image_url,
        filename=unique_filename,
        raw_note_id=None
    )
    db.add(db_image)
    db.commit()
    db.refresh(db_image)
    return db_image


@app.post("/api/notes/images/upload-table", response_model=schemas.ImageSnippetBase)
def upload_table(file: UploadFile = File(...), db: Session = Depends(get_db)):
    from app.storage import upload_file_to_rustfs
    from app.table_ocr import extract_table_from_image
    import uuid
    
    contents, ext = read_image_upload(file)
            
    unique_filename = f"{uuid.uuid4().hex}{ext}"
    try:
        image_url = upload_file_to_rustfs(unique_filename, contents, file.content_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo guardar la imagen en RustFS: {e}")
        
    # Extraer tabla usando OCR local
    ocr_result = extract_table_from_image(contents)
    
    db_image = models.RawNoteImage(
        image_url=image_url,
        filename=unique_filename,
        raw_note_id=None,
        descripcion_llm=ocr_result,
        image_type="table"
    )
    db.add(db_image)
    db.commit()
    db.refresh(db_image)
    return db_image


@app.post("/api/notes", response_model=schemas.RawNoteResponse, status_code=status.HTTP_201_CREATED)
def add_note_to_queue(note_in: schemas.NoteCreate, db: Session = Depends(get_db)):
    """
    Añade un apunte crudo a la cola activa con estado 'pending'.
    """
    return crud.create_raw_note(db=db, note_in=note_in)


@app.get("/api/notes/queue", response_model=List[schemas.RawNoteResponse])
def list_active_queue(db: Session = Depends(get_db)):
    """
    Lista todos los apuntes pendientes en la cola activa.
    """
    return crud.get_raw_notes_by_status(db=db, status=models.QueueStatus.PENDING)


@app.get("/api/notes/archive", response_model=List[schemas.FullNoteResponse])
def list_archived_history(db: Session = Depends(get_db)):
    """
    Lista todos los apuntes que ya fueron procesados de forma exitosa (Archivados).
    """
    return crud.get_raw_notes_by_status(db=db, status=models.QueueStatus.PROCESSED)


@app.get("/api/notes/processed-since")
def get_notes_processed_since(since: str = Query(..., description="Timestamp ISO 8601"), db: Session = Depends(get_db)):
    """
    Retorna notas procesadas después de un timestamp ISO dado.
    Usado por el frontend para mostrar notificaciones de notas procesadas en segundo plano.
    """
    try:
        since_dt = datetime.fromisoformat(since)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato de timestamp inválido. Usa ISO 8601 (ej: 2026-06-03T10:00:00Z)"
        )

    # Asegurar timezone-awareness para la comparación
    if since_dt.tzinfo is None:
        since_dt = since_dt.replace(tzinfo=timezone.utc)

    notes = (
        db.query(models.RawNote)
        .filter(
            models.RawNote.status == models.QueueStatus.PROCESSED,
            models.RawNote.processed_at.isnot(None),
            models.RawNote.processed_at > since_dt
        )
        .order_by(models.RawNote.processed_at.desc())
        .all()
    )

    return [
        {
            "id": str(n.id),
            "class_title": n.class_title,
            "course_name": n.course_name,
            "processed_at": n.processed_at.isoformat() if n.processed_at else None
        }
        for n in notes
    ]


@app.get("/api/courses", response_model=List[str])
def list_courses(db: Session = Depends(get_db)):
    """
    Lista todos los nombres de cursos que tienen apuntes procesados.
    """
    return crud.get_courses_with_processed_notes(db=db)


@app.get("/api/courses/{course_name}/markdown")
def get_course_markdown(course_name: str, db: Session = Depends(get_db)):
    """
    Recupera todas las notas procesadas de un curso y las concatena.
    Mantiene el frontmatter YAML de la primera nota, pero purga
    el frontmatter redundante de las notas subsecuentes.
    """
    try:
        return {"structured_markdown": local_sync.build_course_markdown(db, course_name)}
    except local_sync.LocalSyncError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/courses/{course_name}/notes", response_model=List[schemas.RawNoteResponse])
def read_processed_notes_by_course(course_name: str, db: Session = Depends(get_db)):
    notes = crud.get_processed_notes_by_course(db, course_name)
    return notes

@app.put("/api/courses/{course_name}/reorder")
def reorder_course_notes(course_name: str, request: schemas.ReorderRequest, db: Session = Depends(get_db)):
    success = crud.update_course_order(db, course_name, request.note_ids)
    if not success:
        raise HTTPException(status_code=404, detail="No se pudieron actualizar las notas de este curso")
    return {"status": "success", "message": "Orden actualizado"}


@app.put("/api/courses/{course_name}/rename")
def rename_course(course_name: str, new_name: str, db: Session = Depends(get_db)):
    # 1. Buscar todas las raw_notes
    notes = db.query(models.RawNote).filter(models.RawNote.course_name == course_name).all()
    for note in notes:
        note.course_name = new_name
    
    # 2. Buscar el glosario si existe y actualizarlo
    glossary = db.query(models.CourseGlossary).filter(models.CourseGlossary.course_name == course_name).first()
    if glossary:
        glossary.course_name = new_name
        from app.glossary import compile_glossary_markdown
        glossary.compiled_markdown = compile_glossary_markdown(glossary.entries, new_name)

    local_sync.rename_course_state(db, course_name, new_name)
        
    db.commit()
    return {
        "status": "success",
        "message": f"Curso renombrado de '{course_name}' a '{new_name}'",
        "notes_updated": len(notes),
        "glossary_updated": glossary is not None
    }


@app.delete("/api/courses/{course_name}")
async def delete_course(course_name: str, db: Session = Depends(get_db)):
    """Elimina definitivamente clases, glosario, chunks, embeddings e imágenes de un curso."""
    async with processing_lock:
        try:
            local_sync.archive_course_file(db, course_name)
        except local_sync.LocalSyncError as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        result = crud.delete_course(db, course_name)
    if result is None:
        raise HTTPException(status_code=404, detail="Curso no encontrado")
    return {
        "status": "success",
        "message": f"El curso '{course_name}' y todo su contenido fueron eliminados.",
        **result,
    }


# --- Endpoints de Diagnóstico y Mantenimiento de Embeddings ---

@app.get("/api/embeddings/status")
def embeddings_status(db: Session = Depends(get_db)):
    """
    Muestra cuántos chunks tienen embeddings reales vs. dummy.
    Útil para diagnosticar si el sistema RAG está funcionando correctamente.
    """
    total = db.query(models.NoteChunk).count()
    dummies = db.query(models.NoteChunk).filter(models.NoteChunk.is_dummy_embedding == True).count()
    real = total - dummies
    voyage_configured = bool(os.getenv("VOYAGE_API_KEY"))
    return {
        "total_chunks": total,
        "real_embeddings": real,
        "dummy_embeddings": dummies,
        "voyage_api_configured": voyage_configured,
        "rag_operational": voyage_configured and dummies == 0,
    }


@app.post("/api/embeddings/reprocess-dummies")
def reprocess_dummy_embeddings(request: schemas.ReprocessEmbeddingsRequest, db: Session = Depends(get_db)):
    """
    Re-genera embeddings reales para los chunks marcados como dummy según el target especificado.
    """
    voyage_api_key = os.getenv("VOYAGE_API_KEY")
    if not voyage_api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="VOYAGE_API_KEY no está configurada. Agrégala al .env primero."
        )

    query = db.query(models.NoteChunk).filter(
        models.NoteChunk.is_dummy_embedding == True
    )

    if request.target == "course":
        if not request.course_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Se requiere course_name para el target 'course'."
            )
        query = query.join(models.ProcessedNote).join(models.RawNote).filter(
            models.RawNote.course_name == request.course_name
        )
    elif request.target == "individual":
        if not request.note_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Se requiere note_id para el target 'individual'."
            )
        query = query.join(models.ProcessedNote).filter(
            models.ProcessedNote.raw_note_id == request.note_id
        )
    elif request.target != "all_dummies":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Target '{request.target}' inválido."
        )

    dummy_chunks = query.all()

    if not dummy_chunks:
        return {"status": "success", "message": "No hay chunks dummy que coincidan con la selección para reprocesar.", "reprocessed": 0}

    try:
        import voyageai
        vo = voyageai.Client(api_key=voyage_api_key)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al inicializar cliente de VoyageAI: {e}"
        )

    reprocessed = 0
    errors = 0
    for chunk in dummy_chunks:
        try:
            result = vo.embed([chunk.content[:2000]], model="voyage-4")
            chunk.embedding = result.embeddings[0]
            chunk.is_dummy_embedding = False
            reprocessed += 1
        except Exception as e:
            errors += 1

    db.commit()
    return {
        "status": "success",
        "message": f"Reprocesados {reprocessed} chunks. Errores: {errors}.",
        "reprocessed": reprocessed,
        "errors": errors,
    }


@app.get("/api/notes/{note_id}", response_model=schemas.FullNoteResponse)
def get_note_details(note_id: UUID, db: Session = Depends(get_db)):
    """
    Recupera los detalles de una nota específica por su ID.
    Si ya fue procesada, incluye la nota estructurada en Markdown.
    """
    db_note = crud.get_note_by_id(db=db, note_id=note_id)
    if not db_note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Ficha de apunte no encontrada"
        )
    return db_note


@app.put("/api/notes/{note_id}", response_model=schemas.RawNoteResponse)
def update_note_in_queue(note_id: UUID, note_in: schemas.NoteUpdate, db: Session = Depends(get_db)):
    """
    Actualiza el contenido crudo de una nota en la cola.
    """
    db_note = crud.update_raw_note(db=db, note_id=note_id, note_in=note_in)
    if not db_note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Ficha de apunte no encontrada"
        )
    return db_note


@app.delete("/api/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note_from_db(note_id: UUID, db: Session = Depends(get_db)):
    """
    Elimina una nota y todas sus relaciones (en cascada) de la base de datos.
    """
    note = crud.get_note_by_id(db=db, note_id=note_id)
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ficha de apunte no encontrada"
        )
    sync_state = db.query(models.CourseSyncState).filter(
        models.CourseSyncState.course_name == note.course_name,
        models.CourseSyncState.status == "conflict",
    ).first()
    if sync_state:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Resuelve el conflicto de sincronización del curso antes de eliminar clases."
        )
    success = crud.delete_note(db=db, note_id=note_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Ficha de apunte no encontrada"
        )
    return


@app.post("/api/notes/{note_id}/process", response_model=schemas.ProcessedNoteResponse)
async def process_note_with_ai(note_id: UUID, db: Session = Depends(get_db)):
    """
    Ejecuta el procesamiento inmediato de un apunte crudo utilizando el Agente de LangGraph
    optimizado con chain-of-thought integrado (1 sola llamada al LLM).

    Usa un lock compartido con el worker automático para evitar procesamiento duplicado.
    """
    async with processing_lock:
        db_raw_note = crud.get_note_by_id(db=db, note_id=note_id)
        if not db_raw_note:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Ficha de apunte no encontrada"
            )
            
        # 1. Analizar imágenes asociadas con Gemini 3.6 Flash si hace falta
        from app.storage import analyze_note_images
        analyze_note_images(db, db_raw_note)
        
        # 2. Ejecutar el pipeline configurado; v2 cae al flujo clásico si falla.
        try:
            final_state, pipeline = await generate_note_state(
                db_raw_note, crud.get_generation_pipeline_version(db)
            )
            structured_markdown = final_state.get("structured_markdown", "")
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error en el procesamiento del agente de IA: {str(e)}"
            )

        if not structured_markdown:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="El agente de IA no pudo generar contenido estructurado."
            )

        # 3. Guardar la nota procesada (actualiza estado a 'processed' automáticamente)
        db_processed = persist_generated_result(db, db_raw_note, final_state, pipeline)
        
        # 4. Generar embeddings reales con VoyageAI (o dummy como fallback)
        _store_embedding(db, db_processed, db_raw_note)

        return db_processed


# --- Endpoints de Glosario y Ajustes de Flashcards ---

@app.get("/api/courses/{course_name}/glossary", response_model=Optional[schemas.CourseGlossaryResponse])
def get_course_glossary(course_name: str, db: Session = Depends(get_db)):
    """Obtiene el glosario de un curso específico."""
    glossary = crud.get_course_glossary(db, course_name)
    return glossary


@app.post("/api/courses/{course_name}/glossary/compile")
def compile_course_glossary(course_name: str, db: Session = Depends(get_db)):
    """Recompila completamente el glosario de un curso a partir de todas sus notas procesadas."""
    from app.glossary import parse_glossary_entries, merge_entries, compile_glossary_markdown
    
    notes = crud.get_processed_notes_by_course(db, course_name)
    if not notes:
        raise HTTPException(status_code=404, detail="No se encontraron notas procesadas para este curso")
        
    all_entries = []
    for note in notes:
        if not note.processed_note:
            continue
        entries = parse_glossary_entries(note.processed_note.structured_markdown, note.class_title)
        all_entries.extend(entries)
        
    merged = merge_entries([], all_entries)
    compiled_md = compile_glossary_markdown(merged, course_name)
    
    glossary = crud.save_course_glossary(db, course_name, merged, compiled_md)
    return glossary


@app.get("/api/settings/flashcard-density")
def get_flashcard_density(db: Session = Depends(get_db)):
    """Obtiene la densidad de flashcards configurada."""
    density = crud.get_flashcard_density(db)
    return {"flashcard_density": density}


@app.post("/api/settings/flashcard-density")
def set_flashcard_density(density_in: schemas.FlashcardDensityUpdate, db: Session = Depends(get_db)):
    """Actualiza la densidad global de flashcards."""
    density = crud.set_flashcard_density(db, density_in.flashcard_density)
    return {"flashcard_density": density}


# --- Biblioteca y repaso autónomo de Flashcards ---

@app.get("/api/flashcards/tree")
def flashcard_tree(db: Session = Depends(get_db)):
    return flashcards.tree(db)


@app.get("/api/flashcards/summary")
def flashcard_summary(
    course: Optional[str] = None,
    module: Optional[str] = None,
    class_title: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return flashcards.summary(db, course=course, module=module, class_title=class_title)


@app.get("/api/flashcards")
def list_flashcards(
    course: Optional[str] = None,
    module: Optional[str] = None,
    class_title: Optional[str] = None,
    learning_state: Optional[str] = Query(None, pattern="^(new|learning|review)$"),
    search: Optional[str] = None,
    active_only: bool = True,
    activity: Optional[str] = Query(None, pattern="^(active|inactive|all)$"),
    due_only: bool = False,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = flashcards.filtered_query(
        db, course=course, module=module, class_title=class_title,
        learning_state=learning_state, search=search,
        active_only=active_only, activity=activity, due_only=due_only,
    )
    total = query.count()
    rows = query.order_by(
        models.FlashcardRecord.due_at.asc().nullsfirst(),
        models.RawNote.course_name,
        models.RawNote.course_module,
        models.RawNote.order_index,
    ).offset(offset).limit(limit).all()
    return {"total": total, "items": [flashcards.serialize(card, note) for card, note in rows]}


@app.put("/api/flashcards/{card_id}")
def update_flashcard(card_id: UUID, payload: schemas.FlashcardUpdate, db: Session = Depends(get_db)):
    try:
        return flashcards.update_card(
            db, card_id,
            question=payload.question, answer=payload.answer, is_active=payload.is_active,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/flashcards/{card_id}/review")
def review_flashcard(card_id: UUID, payload: schemas.FlashcardReviewCreate, db: Session = Depends(get_db)):
    try:
        return flashcards.review(db, card_id, payload.rating)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/flashcards/reindex")
def reindex_flashcards(db: Session = Depends(get_db)):
    return flashcards.refresh_index(db)


@app.get("/api/flashcards/export/{export_format}")
def export_flashcards(
    export_format: str,
    course: Optional[str] = None,
    module: Optional[str] = None,
    class_title: Optional[str] = None,
    db: Session = Depends(get_db),
):
    rows = flashcards.filtered_query(db, course=course, module=module, class_title=class_title).order_by(
        models.RawNote.course_name, models.RawNote.course_module, models.RawNote.order_index
    ).all()
    if not rows:
        raise HTTPException(status_code=404, detail="No hay flashcards para exportar con estos filtros.")
    label = local_sync.safe_filename(course or "Todas-las-flashcards")[:-3]
    if export_format == "csv":
        return Response(
            flashcards.csv_export(rows), media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{label}.csv"'},
        )
    if export_format == "anki":
        return Response(
            flashcards.anki_export(rows), media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{label}.apkg"'},
        )
    raise HTTPException(status_code=400, detail="Formato inválido. Usa csv o anki.")


# --- Sincronización local de Markdown ---

def _sync_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, local_sync.LocalSyncConflict):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@app.get("/api/local-sync/config")
def get_local_sync_config(db: Session = Depends(get_db)):
    config = local_sync.get_config(db)
    mount = local_sync.mount_status()
    return {
        "enabled": config.enabled,
        "destination_subpath": config.destination_subpath,
        **mount,
    }


@app.put("/api/local-sync/config")
def put_local_sync_config(payload: schemas.LocalSyncConfigUpdate, db: Session = Depends(get_db)):
    try:
        config = local_sync.update_config(
            db, enabled=payload.enabled, destination_subpath=payload.destination_subpath
        )
        if config.enabled:
            local_sync.reconcile_all(db)
        return {"enabled": config.enabled, "destination_subpath": config.destination_subpath, **local_sync.mount_status()}
    except local_sync.LocalSyncError as exc:
        raise _sync_http_error(exc) from exc


@app.get("/api/local-sync/directories")
def get_local_sync_directories(path: str = ""):
    try:
        return {"path": path, "directories": local_sync.list_directories(path)}
    except local_sync.LocalSyncError as exc:
        raise _sync_http_error(exc) from exc


@app.post("/api/local-sync/directories", status_code=status.HTTP_201_CREATED)
def post_local_sync_directory(payload: schemas.LocalDirectoryCreate):
    try:
        return local_sync.create_directory(payload.parent, payload.name)
    except local_sync.LocalSyncError as exc:
        raise _sync_http_error(exc) from exc


@app.get("/api/local-sync/courses")
def get_local_sync_courses(db: Session = Depends(get_db)):
    return local_sync.list_course_states(db)


@app.put("/api/local-sync/courses/{course_name}")
def put_local_sync_course(course_name: str, payload: schemas.CourseSyncUpdate, db: Session = Depends(get_db)):
    try:
        return local_sync.set_course_enabled(db, course_name, payload.enabled)
    except local_sync.LocalSyncError as exc:
        raise _sync_http_error(exc) from exc


@app.post("/api/local-sync/run")
async def run_local_sync(payload: schemas.LocalSyncRunRequest, db: Session = Depends(get_db)):
    async with local_sync.sync_lock:
        return {"courses": local_sync.reconcile_all(db, payload.course_name)}


@app.get("/api/local-sync/courses/{course_name}/conflict")
def get_local_sync_conflict(course_name: str, db: Session = Depends(get_db)):
    try:
        return local_sync.conflict_details(db, course_name)
    except local_sync.LocalSyncError as exc:
        raise _sync_http_error(exc) from exc


@app.post("/api/local-sync/courses/{course_name}/resolve")
async def resolve_local_sync_conflict(
    course_name: str, payload: schemas.LocalSyncResolveRequest, db: Session = Depends(get_db)
):
    async with processing_lock:
        try:
            if payload.action == "integrate_external":
                return local_sync.integrate_external(db, course_name)
            return local_sync.restore_database(db, course_name)
        except local_sync.LocalSyncError as exc:
            raise _sync_http_error(exc) from exc
