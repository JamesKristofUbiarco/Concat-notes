import os
import re
import asyncio
from typing import List
from uuid import UUID
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app import models, schemas, crud
from app.database import get_db
from app.agent import compile_agent
from app.worker import processing_lock, _store_embedding, worker_loop


# ============================================================================
# LIFESPAN — Registrar el worker automático
# ============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicia el worker automático al arrancar el servidor y lo cancela al detenerlo."""
    from app.storage import init_storage
    init_storage()
    task = asyncio.create_task(worker_loop())
    yield
    task.cancel()
    try:
        await task
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


from fastapi import File, UploadFile

@app.post("/api/notes/images/upload", response_model=schemas.ImageSnippetBase)
def upload_image(file: UploadFile = File(...), db: Session = Depends(get_db)):
    from app.storage import upload_file_to_rustfs
    import uuid
    
    contents = file.file.read()
    ext = os.path.splitext(file.filename)[1].lower() if file.filename else ""
    if not ext:
        if file.content_type == "image/png":
            ext = ".png"
        elif file.content_type == "image/jpeg":
            ext = ".jpg"
        elif file.content_type == "image/gif":
            ext = ".gif"
        elif file.content_type == "image/webp":
            ext = ".webp"
        else:
            ext = ".jpg"
            
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
    notes = crud.get_processed_notes_by_course(db=db, course_name=course_name)
    if not notes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Curso no encontrado o sin apuntes"
        )
    
    concatenated = []
    yaml_regex = re.compile(r"^---\n.*?\n---\n", re.DOTALL)
    
    for i, note in enumerate(notes):
        if not note.processed_note:
            continue
        md = note.processed_note.structured_markdown
        if md.startswith("````txt\n"):
            md = md.replace("````txt\n", "", 1)
        if md.endswith("\n````"):
            md = md[:-5]
            
        if i > 0:
            md = yaml_regex.sub("", md).strip()
            
        concatenated.append(md)
        
    final_md = "\n\n".join(concatenated)
    return {"structured_markdown": final_md}


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
            
        # 1. Analizar imágenes asociadas con Gemini 3.5 Flash si hace falta
        from app.storage import analyze_note_images
        analyze_note_images(db, db_raw_note)
        
        # 2. Instanciar y configurar el Agente LangGraph
        agent = compile_agent()
        config = {
            "configurable": {
                "thread_id": f"thread-{note_id}",
                "db": db
            }
        }
        
        # Preparar el estado inicial para el grafo (optimizado: sin plan/reasoning)
        initial_state = {
            "raw_note_id": str(note_id),
            "raw_note_data": {
                "writing_mode": db_raw_note.writing_mode,
                "platform": db_raw_note.platform,
                "course_name": db_raw_note.course_name,
                "teacher": db_raw_note.teacher,
                "course_module": db_raw_note.course_module,
                "class_title": db_raw_note.class_title,
                "transcription": db_raw_note.transcription,
                "class_summary": db_raw_note.class_summary,
                "my_notes": db_raw_note.my_notes,
                "code_snippets": db_raw_note.code_snippets or [],
                "command_snippets": db_raw_note.command_snippets or []
            },
            "notes_context": [],
            "structured_markdown": "",
            "ai_comments": "",
            "mermaid_validation_errors": "",
            "mermaid_retries": 0
        }
        
        # 2. Ejecutar el grafo del agente en un thread executor
        try:
            loop = asyncio.get_event_loop()
            final_state = await loop.run_in_executor(
                None, lambda: agent.invoke(initial_state, config)
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
        ai_comments = final_state.get("ai_comments", "")
        db_processed = crud.archive_note(
            db=db, 
            raw_note_id=note_id, 
            structured_markdown=structured_markdown,
            ai_comments=ai_comments
        )
        
        # 4. Generar embeddings reales con VoyageAI (o dummy como fallback)
        _store_embedding(db, db_processed, db_raw_note)

        return db_processed
