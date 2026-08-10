"""
Worker automático para procesamiento de notas en segundo plano.

Implementa un disparador híbrido (B3) que procesa notas pendientes cuando:
- Se acumulan >= PENDING_THRESHOLD notas pendientes, o
- La nota pendiente más antigua tiene > MAX_WAIT_MINUTES sin procesar

El worker corre como tarea asyncio dentro del proceso de FastAPI,
registrada en el lifespan de la aplicación.
"""

import os
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.database import SessionLocal
from app.agent import compile_agent
from app import models, crud
from app.v2_agent import compile_agent_v2
from app.knowledge import persist_v2_derivatives

logger = logging.getLogger("worker")

# ============================================================================
# CONFIGURACIÓN DEL DISPARADOR HÍBRIDO
# ============================================================================
PENDING_THRESHOLD = 3           # Procesar si hay >= 3 notas pendientes
MAX_WAIT_MINUTES = 10           # O si la nota más antigua tiene > 10 min
CHECK_INTERVAL_SECONDS = 30     # Frecuencia de chequeo del loop

# Lock compartido con el endpoint manual para evitar procesamiento duplicado
processing_lock = asyncio.Lock()


async def invoke_agent_in_thread(agent, initial_state: dict, thread_id: str):
    """Ejecuta LangGraph fuera del event loop con una sesión propia del hilo."""
    def run_agent():
        agent_db = SessionLocal()
        try:
            config = {
                "configurable": {
                    "thread_id": thread_id,
                    "db": agent_db,
                }
            }
            return agent.invoke(initial_state, config)
        finally:
            agent_db.close()

    return await asyncio.to_thread(run_agent)


async def worker_loop():
    """
    Loop principal del worker. Revisa periódicamente si hay notas pendientes
    que cumplan las condiciones del disparador híbrido.
    """
    logger.info("[WORKER] Iniciado — Disparador híbrido activo "
                f"(threshold={PENDING_THRESHOLD}, timeout={MAX_WAIT_MINUTES}min, "
                f"check_interval={CHECK_INTERVAL_SECONDS}s)")

    while True:
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
        try:
            await check_and_process()
        except Exception as e:
            logger.error(f"[WORKER] Error en ciclo de verificación: {e}", exc_info=True)


async def check_and_process():
    """
    Evalúa las condiciones del disparador híbrido y procesa las notas
    pendientes si se cumplen.
    """
    db = SessionLocal()
    try:
        pending = crud.get_raw_notes_by_status(db, models.QueueStatus.PENDING)
        if not pending:
            return

        # Calcular la antigüedad de la nota pendiente más antigua
        oldest_created = min(n.created_at for n in pending)
        # Manejar timezone-awareness de forma segura
        now = datetime.now(timezone.utc)
        oldest_aware = oldest_created if oldest_created.tzinfo else oldest_created.replace(tzinfo=timezone.utc)
        age_minutes = (now - oldest_aware).total_seconds() / 60

        should_process = (
            len(pending) >= PENDING_THRESHOLD or
            age_minutes >= MAX_WAIT_MINUTES
        )

        if not should_process:
            return

        trigger_reason = (
            f"threshold alcanzado ({len(pending)} >= {PENDING_THRESHOLD})"
            if len(pending) >= PENDING_THRESHOLD
            else f"timeout alcanzado ({age_minutes:.1f} min >= {MAX_WAIT_MINUTES} min)"
        )
        logger.info(f"[WORKER] Disparado por {trigger_reason}. "
                     f"Procesando {len(pending)} nota(s) pendiente(s)...")

        for note in pending:
            async with processing_lock:
                # Re-verificar estado por si el botón manual procesó la nota mientras esperábamos el lock
                db.refresh(note)
                if note.status != models.QueueStatus.PENDING:
                    logger.info(f"[WORKER] Nota '{note.class_title}' ya fue procesada. Saltando.")
                    continue
                try:
                    await process_single_note(note, db)
                except Exception as e:
                    logger.error(f"[WORKER] Error procesando nota '{note.class_title}': {e}", exc_info=True)
    finally:
        db.close()


def build_initial_state(note: models.RawNote) -> dict:
    return {
        "raw_note_id": str(note.id),
        "raw_note_data": {
            "writing_mode": note.writing_mode, "platform": note.platform,
            "course_name": note.course_name, "teacher": note.teacher,
            "course_module": note.course_module, "class_title": note.class_title,
            "transcription": note.transcription, "class_summary": note.class_summary,
            "my_notes": note.my_notes, "code_snippets": note.code_snippets or [],
            "command_snippets": note.command_snippets or [],
        },
        "notes_context": [], "existing_glossary": "", "existing_glossary_terms": [],
        "flashcard_count": 5, "extraction_manifest": "", "content_profile": "mixed",
        "structured_markdown": "", "ai_comments": "",
        "mermaid_validation_errors": "", "mermaid_retries": 0,
        "flashcard_validation_errors": "", "flashcard_retries": 0,
    }


async def generate_note_state(note: models.RawNote, preferred_pipeline: str) -> tuple[dict, str]:
    initial_state = build_initial_state(note)
    if preferred_pipeline == "v2":
        try:
            result = await invoke_agent_in_thread(compile_agent_v2(), initial_state, thread_id=f"v2-{note.id}")
            if result.get("structured_markdown"):
                return result, "v2"
            raise RuntimeError("El pipeline v2 no produjo Markdown")
        except Exception as exc:
            logger.error("[PIPELINE V2] Falló para '%s'; usando legacy: %s", note.class_title, exc, exc_info=True)
    result = await invoke_agent_in_thread(compile_agent(), initial_state, thread_id=f"legacy-{note.id}")
    return result, "legacy"


def persist_generated_result(db, note: models.RawNote, final_state: dict, pipeline: str):
    structured_markdown = final_state.get("structured_markdown", "")
    if not structured_markdown:
        raise RuntimeError("El agente no generó contenido")
    if pipeline != "v2":
        return crud.archive_note(
            db=db, raw_note_id=note.id, structured_markdown=structured_markdown,
            ai_comments=final_state.get("ai_comments", ""),
        )
    try:
        processed = crud.archive_note(
            db=db, raw_note_id=note.id, structured_markdown=structured_markdown,
            ai_comments=final_state.get("ai_comments", ""), commit=False,
        )
        persist_v2_derivatives(db, note, processed, final_state)
        db.commit()
        db.refresh(processed)
        return processed
    except Exception:
        db.rollback()
        raise


async def process_single_note(note: models.RawNote, db) -> None:
    """
    Procesa una nota individual usando el agente LangGraph.
    Reutiliza la misma lógica que el endpoint manual: invocar el agente,
    archivar, y generar embeddings reales con VoyageAI.
    """
    logger.info(f"[WORKER] Procesando: '{note.class_title}' (curso: {note.course_name})")

    from app.storage import analyze_note_images
    analyze_note_images(db, note)

    final_state, pipeline = await generate_note_state(note, crud.get_generation_pipeline_version(db))

    structured_markdown = final_state.get("structured_markdown", "")
    if not structured_markdown:
        logger.warning(f"[WORKER] El agente no generó contenido para '{note.class_title}'")
        return

    # Archivar la nota (marca como 'processed')
    db_processed = persist_generated_result(db, note, final_state, pipeline)

    # Generar embeddings reales con VoyageAI si está disponible
    _store_embedding(db, db_processed, note)

    logger.info(f"[WORKER] ✓ Nota procesada exitosamente con {pipeline}: '{note.class_title}'")


def _store_embedding(db, db_processed: models.ProcessedNote, raw_note: models.RawNote) -> None:
    """
    Genera y almacena embeddings vectoriales de la nota procesada.
    
    En vez de crear un solo chunk genérico, divide el markdown en secciones
    lógicas (por headings ## y ###) y embeddea cada sección individualmente.
    Esto permite búsquedas RAG mucho más granulares y precisas.
    
    Los chunks con embeddings dummy (sin API de Voyage) se etiquetan con
    is_dummy_embedding=True para poder re-embeddearlos cuando la API esté disponible.
    """
    import re
    
    markdown = db_processed.structured_markdown or ""
    
    # Dividir el markdown en secciones por headings (## o ###)
    # Cada sección incluye su heading como contexto
    sections = re.split(r'(?=^#{2,3}\s)', markdown, flags=re.MULTILINE)
    
    # Filtrar secciones vacías y demasiado cortas (menos de 50 chars de contenido útil)
    sections = [s.strip() for s in sections if s.strip() and len(s.strip()) > 50]
    
    if not sections:
        # Fallback: si no hay secciones, usar el texto completo como un solo chunk
        sections = [f"Resumen de clase: {raw_note.class_summary[:500] if raw_note.class_summary else raw_note.class_title}"]
    
    # Prefijo de contexto para cada chunk (ayuda al embedding a entender de qué clase viene)
    context_prefix = f"Curso: {raw_note.course_name} | Clase: {raw_note.class_title}\n"
    
    voyage_api_key = os.getenv("VOYAGE_API_KEY")
    
    # Eliminar chunks previos del mismo procesamiento
    db.query(models.NoteChunk).filter(
        models.NoteChunk.processed_note_id == db_processed.id
    ).delete()
    
    # Inicializar cliente de Voyage una sola vez si está disponible
    vo_client = None
    if voyage_api_key:
        try:
            import voyageai
            vo_client = voyageai.Client(api_key=voyage_api_key)
        except Exception as e:
            logger.error(f"[WORKER] No se pudo inicializar el cliente de VoyageAI: {e}")
    
    dummy_count = 0
    real_count = 0
    
    # Embeddear cada sección
    for idx, section in enumerate(sections):
        chunk_text = context_prefix + section
        # Limitar el tamaño del chunk para no exceder límites del modelo de embedding
        chunk_text = chunk_text[:2000]
        
        is_dummy = True
        embedding_vector = [0.0] * 1024
        
        if vo_client:
            try:
                result = vo_client.embed([chunk_text], model="voyage-4")
                embedding_vector = result.embeddings[0]
                is_dummy = False
                real_count += 1
            except Exception as e:
                logger.error(f"[WORKER] Error generando embedding para chunk {idx}: {e}. Marcando como dummy.")
                dummy_count += 1
        else:
            dummy_count += 1
        
        db_chunk = models.NoteChunk(
            processed_note_id=db_processed.id,
            content=chunk_text,
            embedding=embedding_vector,
            is_dummy_embedding=is_dummy,
            chunk_index=idx
        )
        db.add(db_chunk)
    
    db.commit()
    
    if dummy_count > 0:
        logger.warning(
            f"[WORKER] ⚠️  {dummy_count} chunk(s) de '{raw_note.class_title}' tienen embeddings DUMMY. "
            f"Estos no servirán para búsqueda semántica. Configura VOYAGE_API_KEY y usa "
            f"el endpoint /api/embeddings/reprocess-dummies para regenerarlos."
        )
    if real_count > 0:
        logger.info(f"[WORKER] Almacenados {real_count} chunks con embeddings reales para '{raw_note.class_title}'")
