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

logger = logging.getLogger("worker")

# ============================================================================
# CONFIGURACIÓN DEL DISPARADOR HÍBRIDO
# ============================================================================
PENDING_THRESHOLD = 3           # Procesar si hay >= 3 notas pendientes
MAX_WAIT_MINUTES = 10           # O si la nota más antigua tiene > 10 min
CHECK_INTERVAL_SECONDS = 30     # Frecuencia de chequeo del loop

# Lock compartido con el endpoint manual para evitar procesamiento duplicado
processing_lock = asyncio.Lock()


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

        agent = compile_agent()

        for note in pending:
            async with processing_lock:
                # Re-verificar estado por si el botón manual procesó la nota mientras esperábamos el lock
                db.refresh(note)
                if note.status != models.QueueStatus.PENDING:
                    logger.info(f"[WORKER] Nota '{note.class_title}' ya fue procesada. Saltando.")
                    continue
                try:
                    await process_single_note(note, agent, db)
                except Exception as e:
                    logger.error(f"[WORKER] Error procesando nota '{note.class_title}': {e}", exc_info=True)
    finally:
        db.close()


async def process_single_note(note: models.RawNote, agent, db) -> None:
    """
    Procesa una nota individual usando el agente LangGraph.
    Reutiliza la misma lógica que el endpoint manual: invocar el agente,
    archivar, y generar embeddings reales con VoyageAI.
    """
    logger.info(f"[WORKER] Procesando: '{note.class_title}' (curso: {note.course_name})")

    config = {
        "configurable": {
            "thread_id": f"worker-thread-{note.id}",
            "db": db
        }
    }

    initial_state = {
        "raw_note_id": str(note.id),
        "raw_note_data": {
            "writing_mode": note.writing_mode,
            "platform": note.platform,
            "course_name": note.course_name,
            "teacher": note.teacher,
            "course_module": note.course_module,
            "class_title": note.class_title,
            "transcription": note.transcription,
            "class_summary": note.class_summary,
            "my_notes": note.my_notes,
            "code_snippets": note.code_snippets or [],
            "command_snippets": note.command_snippets or []
        },
        "notes_context": [],
        "structured_markdown": "",
        "ai_comments": "",
        "mermaid_validation_errors": "",
        "mermaid_retries": 0
    }

    # Ejecutar el agente en un thread executor para no bloquear el event loop
    loop = asyncio.get_event_loop()
    final_state = await loop.run_in_executor(None, lambda: agent.invoke(initial_state, config))

    structured_markdown = final_state.get("structured_markdown", "")
    if not structured_markdown:
        logger.warning(f"[WORKER] El agente no generó contenido para '{note.class_title}'")
        return

    # Archivar la nota (marca como 'processed')
    ai_comments = final_state.get("ai_comments", "")
    db_processed = crud.archive_note(
        db=db,
        raw_note_id=note.id,
        structured_markdown=structured_markdown,
        ai_comments=ai_comments
    )

    # Generar embeddings reales con VoyageAI si está disponible
    _store_embedding(db, db_processed, note)

    logger.info(f"[WORKER] ✓ Nota procesada exitosamente: '{note.class_title}'")


def _store_embedding(db, db_processed: models.ProcessedNote, raw_note: models.RawNote) -> None:
    """
    Genera y almacena el embedding vectorial de la nota procesada.
    Usa VoyageAI si está configurado, o un vector dummy como fallback.
    """
    chunk_text = (
        f"Resumen de clase: "
        f"{raw_note.class_summary[:500] if raw_note.class_summary else raw_note.class_title}"
    )

    voyage_api_key = os.getenv("VOYAGE_API_KEY")
    if voyage_api_key:
        try:
            import voyageai
            vo = voyageai.Client(api_key=voyage_api_key)
            result = vo.embed([chunk_text], model="voyage-4")
            embedding_vector = result.embeddings[0]
            logger.info("[WORKER] Embedding real generado con VoyageAI (voyage-4)")
        except Exception as e:
            logger.error(f"[WORKER] Error generando embedding real: {e}. Usando vector dummy.")
            embedding_vector = [0.0] * 1024
    else:
        embedding_vector = [0.0] * 1024

    # Eliminar chunks previos del mismo procesamiento
    db.query(models.NoteChunk).filter(
        models.NoteChunk.processed_note_id == db_processed.id
    ).delete()

    db_chunk = models.NoteChunk(
        processed_note_id=db_processed.id,
        content=chunk_text,
        embedding=embedding_vector,
        chunk_index=0
    )
    db.add(db_chunk)
    db.commit()
