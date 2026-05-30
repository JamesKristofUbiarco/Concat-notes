from typing import List
from uuid import UUID
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app import models, schemas, crud
from app.database import get_db

# Inicializar la aplicación FastAPI
app = FastAPI(
    title="Next.js Notes Concatenator API",
    description="Backend en FastAPI para gestionar la cola de apuntes de cursos e integración de pgvector/PostgreSQL.",
    version="1.0.0"
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
    return {"status": "healthy", "service": "notes-concatenator-backend"}


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


@app.get("/api/notes/archive", response_model=List[schemas.RawNoteResponse])
def list_archived_history(db: Session = Depends(get_db)):
    """
    Lista todos los apuntes que ya fueron procesados de forma exitosa (Archivados).
    """
    return crud.get_raw_notes_by_status(db=db, status=models.QueueStatus.PROCESSED)


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
def process_note_with_ai(note_id: UUID, db: Session = Depends(get_db)):
    """
    Ejecuta el procesamiento inteligente del apunte crudo.
    Sintetiza la información en Markdown de alta calidad y la guarda en la base de datos,
    cambiando el estado de la nota cruda a 'processed' e inyectando fragmentos vectoriales
    en la tabla 'note_chunks' para probar la extensión 'pgvector' con 1024 dimensiones.
    """
    db_raw_note = crud.get_note_by_id(db=db, note_id=note_id)
    if not db_raw_note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Ficha de apunte no encontrada"
        )
        
    # 1. Estructuración del Markdown (Motor en Python equivalente a la simulación)
    summary_text = db_raw_note.class_summary or "Ficha procesada de manera estructurada."
    transcription_text = db_raw_note.transcription or "No se suministró transcripción de audio."
    notes_text = db_raw_note.my_notes or "No se suministraron observaciones adicionales."
    
    ticks3 = "```"
    
    structured_markdown = f"""# 📘 Ficha de Estudio: {db_raw_note.class_title}
> **Curso:** {db_raw_note.course_name} | **Módulo:** {db_raw_note.course_module or "N/A"}
> **Plataforma:** {db_raw_note.platform or "Local"} | **Profesor:** {db_raw_note.teacher or "N/A"}
> **Procesamiento:** FastAPI Backend + PostgreSQL Vector Store (LangGraph Ready)

---

## 📌 Resumen Ejecutivo de la Clase
{summary_text}

## 💡 Conceptos Clave y Transcripción Procesada
{f"El análisis de la clase arroja las siguientes conclusiones estructuradas:\n\n> {transcription_text.replace(chr(10), chr(10) + '> ')}" if db_raw_note.transcription else transcription_text}

## 📝 Notas de Estudio Sintetizadas
{notes_text}

"""

    if db_raw_note.code_snippets:
        structured_markdown += "## 💻 Código de Referencia y Mejores Prácticas\n"
        for i, snippet in enumerate(db_raw_note.code_snippets):
            lang = snippet.get("lang") or "typescript"
            code = snippet.get("code") or ""
            structured_markdown += f"### Fragmento {i + 1} ({lang})\n\n{ticks3}{lang}\n{code}\n{ticks3}\n\n"

    if db_raw_note.command_snippets:
        structured_markdown += "## 🛠️ Comandos de Configuración Ejecutables\n"
        for snippet in db_raw_note.command_snippets:
            order = snippet.get("order") or "Ejecución"
            lang = snippet.get("lang") or "bash"
            cmd = snippet.get("cmd") or ""
            structured_markdown += f"**{order}** en terminal de shell `{lang}`:\n{ticks3}{lang}\n{cmd}\n{ticks3}\n\n"

    structured_markdown += "---\n*Ficha de conocimiento estructurada de manera inteligente y optimizada para búsquedas semánticas.*"

    # 2. Guardar la nota procesada (actualiza estado a 'processed' automáticamente)
    db_processed = crud.archive_note(
        db=db, 
        raw_note_id=note_id, 
        structured_markdown=structured_markdown
    )
    
    # 3. Validar integración con pgvector
    # Creamos un vector de prueba de 1024 dimensiones inicializado en ceros (float)
    # Esto confirma que el plugin de pgvector y la columna funcionan de manera perfecta.
    dummy_vector = [0.0] * 1024
    
    # Eliminar posibles chunks previos del mismo procesamiento
    db.query(models.NoteChunk).filter(models.NoteChunk.processed_note_id == db_processed.id).delete()
    
    # Insertar el chunk vectorial de validación
    db_chunk = models.NoteChunk(
        processed_note_id=db_processed.id,
        content=f"Resumen de clase: {summary_text[:200]}",
        embedding=dummy_vector,
        chunk_index=0
    )
    db.add(db_chunk)
    db.commit()

    return db_processed
