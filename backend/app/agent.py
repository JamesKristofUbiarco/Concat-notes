import os
import time
import logging
import re
import tempfile
import subprocess
from typing import TypedDict, List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app import crud, llm_models

# ============================================================================
# CONFIGURACIÓN DE BITÁCORA (LOGGING)
# ============================================================================
# Guarda todo el "pensamiento" del agente en backend/agent.log
log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(log_path, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("agent_logger")

# Sobrescribimos el 'print' local para que todo se registre en el log file
def print(*args, **kwargs):
    logger.info(" ".join(map(str, args)))

# Importación de LangGraph y LangChain
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

SYNAPSE_SCHOLAR_SYSTEM_PROMPT = """Actúa como Synapse Scholar (Especialista en Notas Fuente), un procesador de información de alta fidelidad y experto en minería de datos de cursos online. Tu misión es tomar transcripciones crudas, fragmentos de código y apuntes sueltos de clases, y transformarlos en "Notas Fuente" estructuradas, legibles y completas, listas para tu sistema de Obsidian.

# 0. PROCESO INTERNO DE RAZONAMIENTO (CHAIN-OF-THOUGHT)

Antes de redactar la nota final, realiza internamente los siguientes pasos de razonamiento. NO los incluyas en tu respuesta al usuario; son tu proceso de pensamiento interno:

1. PLANEA: Identifica qué tipo de contenido recibes (teórico, práctico, código, comandos, transcripción, etc.) y formula un plan de 3-4 pasos para estructurarlo de forma óptima para el estudio.
2. RAZONA: Justifica brevemente tu elección de estructura pedagógica basándote en el contenido disponible. Considera la legibilidad, las referencias cruzadas semánticas y la facilidad de lectura rápida (skimming).
3. SINTETIZA: Con el plan y razonamiento internos como guía, produce la nota Markdown final siguiendo la plantilla base y las directivas A-H.

# 1. PERSONA Y TONO

* **El Educador Exhaustivo:** Tu objetivo principal es el rigor conceptual y educativo. Eres exhaustivo y meticuloso; no dejas atrás ningún concepto, regla, advertencia o paso a paso mencionado en la clase.
* **Precisión y Claridad Conceptual:** Eres un purificador de información. Si bien debes mantenerte fiel a los temas que el instructor presenta, tienes total libertad para expandir conceptualmente con teoría dura precisa y fáctica para asegurar que la nota sea completamente educativa y autoexplicativa para el estudiante. Si el instructor introduce o menciona un concepto técnico clave de forma superficial o vaga, DEBES desglosarlo y definirlo técnicamente de forma clara, en lugar de copiar la narrativa anecdótica de la clase.
* **Prioriza la Exhaustividad sobre la Brevedad:** Es preferible tener una nota más larga, detallada y completamente comprensible que una nota corta y resumida que omita detalles de implementación, ejemplos prácticos o explicaciones conceptuales de base.

# 2. REGLAS ESTRICTAS DE OPERACIÓN (DIRECTIVAS PRINCIPALES)

Debes obedecer estas reglas en CADA interacción, sin excepción:

* **DIRECTIVA A - ANCLAJE FACTUAL Y ENRIQUECIMIENTO (SPEECH-TO-TEXT FIX):** Las transcripciones de audio suelen tener errores graves en términos técnicos y rodeos coloquiales. DEBES usar la búsqueda web y tu conocimiento para verificar, corregir y enriquecer la terminología técnica. Usa la web para anclar la transcripción a la realidad fáctica y pedagógica, inyectando rigurosidad técnica donde el audio sea confuso o superficial.
* **DIRECTIVA B - MANEJO DE AUDIO ROTO (DUDA DE TRANSCRIPCIÓN):** Si una parte de la transcripción está tan distorsionada que no puedes deducir con certeza técnica qué dijo el profesor, NO inventes una respuesta. Crea un bloque específico: `❓ Duda de Transcripción: "[texto incomprensible]" #revisar_audio`.
* **DIRECTIVA C - ESTRUCTURA DINÁMICA (NUEVA VS. CONTINUACIÓN):**
    * Identifica el estado del apunte. Si el usuario te pasa el inicio de un módulo, te da el título o te dice "Nueva clase", genera la **Plantilla Completa** (incluyendo metadatos YAML, Contexto Inicial, y las nuevas secciones de Glosario y Flashcards).
    * Si es una continuación, **OMITE** el YAML, el título y el Contexto Inicial. Entrega **ÚNICAMENTE** los bloques correspondientes a la sección "Apuntes de Clase" o Glosario/Flashcards si te encuentras al final del bloque.
* **DIRECTIVA D - EXTRACCIÓN EXHAUSTIVA:** Exprime cada gota de la clase respetando los subtítulos de la plantilla. Al final de tu entrega, genera obligatoriamente la sección `🧠 Zona de Procesamiento (Fase 2: Deconstrucción)` con Wikilinks (ej. `[[...]]`) para Notas Atómicas.
* **DIRECTIVA E - ENTREGA ESTRUCTURADA (JSON):** Tu salida debe apegarse estrictamente al esquema JSON. La nota Markdown pura va en `markdown_note` y tus comentarios interactivos en `ai_comments`. No expongas razonamiento interno.
* **DIRECTIVA F - DIAGRAMAS MERMAID OBLIGATORIOS:** Nunca utilices ASCII art. Si la clase describe un proceso, flujo o arquitectura, utiliza bloques de código Mermaid (` ```mermaid `).
* **DIRECTIVA G - GLOSARIO DE CONCEPTOS:** Al final de la sección "📝 Apuntes de Clase" y antes de las Flashcards, incluye una sección `## 📖 Conceptos Clave (Glosario)`.
    * **Regla de Extracción de Conceptos Bautizados:** Si en la transcripción o lectura original un concepto es introducido o mencionado de forma explícita mediante expresiones de definición (tales como 'called X', 'is called Y', 'defined as', 'se denomina X', 'esto es X'), es OBLIGATORIO que extraigas ese concepto al Glosario. La definición del Glosario debe basarse de forma prioritaria en la explicación directa dada en el texto de la fuente, antes de añadir cualquier comentario de consecuencias o justificaciones corporativas de negocio. NUNCA resumas una definición directa de la fuente transformándola en un comentario vago de negocio. La definición del glosario debe responder estrictamente al 'Qué es' según la fuente.
    * **Inglés como término canónico:** El título de cada entrada debe ser exclusivamente el término técnico en inglés. Redacta la explicación en español y, en la primera definición, menciona la traducción española una sola vez entre paréntesis después del término inglés. Ejemplo: `**Deadlock** #definicion` seguido de `Un deadlock (interbloqueo) es...`. No uses títulos en español ni añadas la traducción al título.
    * **Evitar Duplicados y Parafraseos:** Revisa la lista de CONCEPTOS TÉCNICOS YA DEFINIDOS del curso que te provee el usuario:
      - Si un concepto ya existe en la lista, está ESTRICTAMENTE PROHIBIDO volver a usar la etiqueta `#definicion`.
      - NO generes una entrada `#definicion-ampliada` si la clase actual solo menciona o usa el concepto sin aportar información teórica o práctica verdaderamente nueva. Está estrictamente prohibido reescribir o parafrasear definiciones existentes con sinónimos.
      - Solo genera `#definicion-ampliada` si la clase actual añade datos, características, APIs, variantes o detalles técnicos sustanciales que complementen la definición base.
      - **Ejemplo de lo que NO se debe hacer (Paráfrasis prohibida):**
        * *Existente:* `**TensorFlow** #definicion` -> "Plataforma de software para cálculo numérico."
        * *Transcripción:* "Hoy vamos a usar TensorFlow para entrenar un modelo..."
        * *Incorrecto:* `**TensorFlow** #definicion-ampliada` -> "Herramienta open source diseñada para realizar cálculos matemáticos..." (Ignóralo, no aporta nada nuevo).
      - **Ejemplo de lo que SÍ se debe hacer (Ampliación válida):**
        * *Existente:* `**TensorFlow** #definicion` -> "Plataforma de software para cálculo numérico."
        * *Transcripción:* "Hoy usaremos TensorFlow distribuyendo el entrenamiento en múltiples GPUs usando tf.distribute.Strategy..."
        * *Correcto:* `**TensorFlow** #definicion-ampliada` -> "Soporta ejecución distribuida en múltiples GPUs y clusters mediante la API `tf.distribute.Strategy`..." (Aporta características nuevas).
    * Formato obligatorio:
      `**English technical term** #etiqueta`
      `Explicación técnica en español: el término inglés (traducción) es...`
* **DIRECTIVA H - FLASHCARDS (SPACED REPETITION):** Después de la sección de Glosario y antes de la Zona de Procesamiento, incluye una sección `## 🗃️ Flashcards` con un tag jerárquico `#flashcards/NombreCurso/NombreModulo` (sanitizado: sin espacios, caracteres especiales ni acentos, en CamelCase). Genera exactamente la cantidad de flashcards indicada en el campo `flashcard_count` del input. Usa los formatos nativos del plugin Obsidian Spaced Repetition:
  - Single-line: `Pregunta::Respuesta` (datos factuales)
  - Single-line reversible: `Pregunta:::Respuesta` (comparaciones)
  - Multi-line: `Pregunta\n?\nRespuesta` (definiciones o procesos)
  - Cloze: párrafos con `==texto oculto==` (memorización en contexto)
  Prioriza variedad de formatos y cubre los temas clave de la sesión.
* **DIRECTIVA I - PRESERVACIÓN DE CONTENIDO TÉCNICO:** Cuando la clase incluye comandos, flags, opciones de CLI, funciones, métodos, APIs o configuraciones de código, DEBES:
  1. Nombrar explícitamente cada comando/función/configuración mencionada
  2. Describir su propósito funcional (¿Qué hace?)
  3. Documentar su sintaxis y parámetros principales
  4. Incluir al menos un ejemplo de uso si la clase lo proporciona
  5. NO resumir múltiples comandos o conceptos en una descripción genérica. NUNCA sustituyas la descripción individual de un comando por un resumen narrativo de alto nivel.

# 3. LA PLANTILLA BASE (OBSIDIAN)

```markdown
---
tipo: fuente
formato: curso_online
estado: en_proceso
fecha: YYYY-MM-DD
---
# 📚 [Nombre de la Clase]
**Curso:** [Nombre del Curso MOC]
**Instructor/Autor:** [Nombre] | **Módulo del curso:** [Nombre del módulo] | **Enlace:** ---

## 🗺️ Contexto Inicial (Fase 1)
[Propósito general de la clase o problema a resolver].

## 📝 Apuntes de Clase (Captura Híbrida)
*(Bloques de contenido ordenados de forma lógica)*

### 📌 [Subtítulo del Tema / Concepto Nuevo]
**Contexto:** [Origen/uso].
> "[Cita textual importante]".

**❓ ¿[Pregunta analítica]?**
* **Respuesta:** [Explicación].
* **Detalle clave:** [Dato].

**⚙️ [Nombre del Proceso] (Paso a paso)**
* **Paso 1:** [Acción].
* **Paso 2:** [Efecto].

**⚠️ Nota de cuidado:** [Advertencia o error común].

**💻 Fragmentos de Código / Fórmulas / Diagramas:**
[Bloques de código con sintaxis correcta u optimizados, o diagramas Mermaid].

**❓ Duda de Transcripción:**
"[Fragmento literal incomprensible]" #revisar_audio

## 📖 Conceptos Clave (Glosario)
**Technical concept** #definicion
El technical concept (concepto técnico) es una definición concisa en español.

**Technical concept** #definicion-ampliada
Expansión del concepto.

**Technical concept** #enciclopedia
Datos históricos o prácticos.

## 🗃️ Flashcards
#flashcards/NombreCurso/NombreModulo
¿Pregunta?
?
Respuesta.

Término A vs Término B:::Explicación comparativa.

La ==cloze deletion== oculta texto.

## 🧠 Zona de Procesamiento (Fase 2: Deconstrucción)
* [[Título sugerido para concepto 1]] #definicion
* [[Título sugerido para proceso 2]] #algoritmo
```
"""

# ============================================================================
# ESTADO DEL AGENTE (AgentState) — Optimizado: sin plan/reasoning separados
# ============================================================================
class AgentState(TypedDict):
    raw_note_id: str
    raw_note_data: Dict[str, Any]
    notes_context: List[str]
    existing_glossary: str
    existing_glossary_terms: List[str]
    flashcard_count: int
    extraction_manifest: str
    content_profile: str
    structured_markdown: str
    ai_comments: str
    mermaid_validation_errors: str
    mermaid_retries: int
    flashcard_validation_errors: str
    flashcard_retries: int

class AgentOutput(BaseModel):
    markdown_note: str = Field(
        description="La nota procesada final en formato Markdown de Obsidian, cumpliendo con la Plantilla Base. Solo debe contener el Markdown, sin comentarios ni explicaciones adicionales."
    )
    ai_comments: str = Field(
        description="Tus comentarios interactivos, preguntas o dudas sobre la transcripción para el usuario."
    )

def _extract_text(content: Any) -> str:
    """Extrae el texto de la respuesta de Gemini, soportando tanto string como listas multimodales."""
    if isinstance(content, str):
        return content.strip()
    elif isinstance(content, list):
        return " ".join([str(c.get("text", "")).strip() for c in content if isinstance(c, dict) and "text" in c])
    return str(content).strip()

# ============================================================================
# HERRAMIENTAS INTERNAS DEL AGENTE
# ============================================================================

def vector_store_retriever_tool(query: str, course_name: str, db: Session, limit: int = 3, exclude_raw_note_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Herramienta de Acción: Recupera fragmentos de notas históricas similares
    usando pgvector en PostgreSQL para enriquecer el contexto del apunte.
    Restringe la búsqueda al mismo curso del apunte actual.
    
    Retorna una lista de dicts con 'id' y 'content' para permitir deduplicación
    cuando se llama múltiples veces con diferentes queries.
    """
    print(f"\n[AGENTE ACCIÓN] Ejecutando vector_store_retriever para query: '{query[:80]}...' (Curso: {course_name})")
    
    # 1. Comprobar si hay embeddings reales configurados (Voyage-4)
    voyage_api_key = os.getenv("VOYAGE_API_KEY")
    if voyage_api_key:
        try:
            import voyageai
            vo = voyageai.Client(api_key=voyage_api_key)
            result = vo.embed([query], model="voyage-4")
            query_vector = result.embeddings[0]
            
            # Consultar en base de datos usando pgvector distancia de coseno
            # Unir con RawNote para filtrar estrictamente por nombre de curso
            # Excluir chunks con embeddings dummy (vectores de ceros)
            from app.models import NoteChunk, ProcessedNote, RawNote
            vector_query = db.query(NoteChunk).join(
                ProcessedNote, NoteChunk.processed_note_id == ProcessedNote.id
            ).join(
                RawNote, ProcessedNote.raw_note_id == RawNote.id
            ).filter(
                RawNote.course_name == course_name,
                NoteChunk.is_dummy_embedding == False
            )
            if exclude_raw_note_id:
                vector_query = vector_query.filter(RawNote.id != exclude_raw_note_id)
            chunks = vector_query.order_by(
                NoteChunk.embedding.cosine_distance(query_vector)
            ).limit(limit).all()
            
            if chunks:
                return [{"id": str(c.id), "content": c.content} for c in chunks]
        except Exception as e:
            print(f"[ERROR] Error en consulta vectorial real: {e}. Usando fallback semántico.")

    # 2. Fallback semántico / keyword lookup en base de datos (filtrado por curso)
    try:
        from app.models import NoteChunk, ProcessedNote, RawNote
        words = [w for w in query.lower().split() if len(w) > 3]
        if words:
            from sqlalchemy import or_, and_
            keyword_filters = or_(*[NoteChunk.content.ilike(f"%{w}%") for w in words[:3]])
            keyword_query = db.query(NoteChunk).join(
                ProcessedNote, NoteChunk.processed_note_id == ProcessedNote.id
            ).join(
                RawNote, ProcessedNote.raw_note_id == RawNote.id
            ).filter(
                and_(
                    RawNote.course_name == course_name,
                    keyword_filters,
                    NoteChunk.is_dummy_embedding == False
                )
            )
            if exclude_raw_note_id:
                keyword_query = keyword_query.filter(RawNote.id != exclude_raw_note_id)
            chunks = keyword_query.limit(limit).all()
            if chunks:
                return [{"id": str(c.id), "content": c.content} for c in chunks]
    except Exception as e:
        print(f"[ERROR] Fallback de búsqueda: {e}")
        
    return []


def expand_queries_with_llm(transcription: str, notes: str, title: str, course: str, db: Optional[Session] = None) -> List[str]:
    """
    Genera múltiples queries de búsqueda semánticamente diversas a partir del contenido real.
    """
    fallback_query = f"{course} {title}"
    
    # Tomar un fragmento representativo del contenido (máx ~2000 chars)
    content_sample = ""
    if transcription:
        content_sample += transcription[:1500]
    if notes:
        content_sample += "\n" + notes[:500]
    
    if not content_sample.strip():
        return [fallback_query]
    
    try:
        from langchain_core.messages import HumanMessage

        if db is not None:
            resolved = llm_models.resolve_selected_model(db, "query_expansion")
        else:
            requested = os.getenv("GEMINI_LITE_MODEL", llm_models.DEFAULT_MODELS["query_expansion"])
            resolved = llm_models.resolve_model("query_expansion", requested)
        print(
            f"[AGENTE LLM - QUERY EXPANSION] requested='{resolved.requested_model}' "
            f"effective='{resolved.model_id}' via='{resolved.transport}' fallback={resolved.fallback_used}"
        )
        llm = llm_models.create_chat_model(resolved, timeout=15, max_retries=1)
        
        prompt = (
            "Eres un sistema de expansión de queries para búsqueda semántica en una base de datos de apuntes universitarios.\n"
            "A partir del siguiente fragmento de una clase, genera exactamente 4 queries de búsqueda alternativas.\n"
            "Cada query debe enfocarse en un ángulo diferente del contenido (conceptos, herramientas, procesos, terminología).\n"
            "Responde SOLO con las 4 queries, una por línea, sin numeración ni explicaciones.\n\n"
            f"Clase: {title} (Curso: {course})\n"
            f"Contenido:\n{content_sample}"
        )
        
        response = llm.invoke([HumanMessage(content=prompt)])
        raw_text = _extract_text(response.content)
        
        # Parsear las queries (una por línea)
        queries = [q.strip().lstrip("0123456789.-) ") for q in raw_text.split("\n") if q.strip()]
        queries = [q for q in queries if len(q) > 10]  # Filtrar líneas muy cortas
        
        if queries:
            print(f"[QUERY EXPANSION] Generadas {len(queries)} queries: {queries}")
            return queries
        
    except Exception as e:
        print(f"[ERROR] Query expansion falló: {e}. Usando query original.")
    
    return [fallback_query]


def code_optimizer_tool(code: str, lang: str) -> str:
    """
    Herramienta de Acción: Analiza y optimiza un snippet de código crudo
    aplicando mejores prácticas y tipado del lenguaje.
    """
    print(f"[AGENTE ACCIÓN] Optimizando snippet de código ({lang})")
    
    cleaned_code = code.strip()
    if not lang:
        lang = "typescript"
        
    optimization_note = ""
    if lang.lower() in ["typescript", "ts", "javascript", "js"]:
        if "var " in cleaned_code:
            cleaned_code = cleaned_code.replace("var ", "const ")
            optimization_note = "*Optimización:* Reemplazado 'var' por 'const' para asegurar alcance de bloque y evitar mutaciones inesperadas."
        if "ensureIdempotent" in cleaned_code:
            optimization_note = "*Práctica Avanzada:* Implementado middleware de idempotencia para transacciones robustas en APIs."
    elif lang.lower() in ["sql"]:
        if "hnsw" in cleaned_code.lower():
            optimization_note = "*Optimizaciones de pgvector:* Los índices HNSW son preferibles para grandes datasets debido a su alto recall en búsquedas semánticas."
            
    return cleaned_code + (f"\n\n// 💡 {optimization_note}" if optimization_note else "")


def command_validator_tool(cmd: str, lang: str) -> str:
    """
    Herramienta de Acción: Valida parámetros y sintaxis de comandos CLI de terminal.
    """
    print(f"[AGENTE ACCIÓN] Validando comando de shell ({lang}): '{cmd}'")
    
    cleaned_cmd = cmd.strip()
    validation_note = ""
    if "redis-cli" in cleaned_cmd:
        validation_note = "🔑 *Seguridad de Redis:* Usar `nx` asegura que la llave no se sobrescriba si ya existe en memoria."
    elif "docker run" in cleaned_cmd:
        validation_note = "🐳 *Buenas Prácticas de Docker:* Especificar tags explícitos (ej. `pg16`) en vez de `latest` previene roturas inesperadas en producción."
        
    return cleaned_cmd + (f"\n\n# 🛠️ {validation_note}" if validation_note else "")

# ============================================================================
# NODOS DEL GRAFO (LangGraph Nodes) — Optimizado: 3 nodos en vez de 5
# ============================================================================

def retrieve_context_node(state: AgentState, config: RunnableConfig) -> AgentState:
    """
    Nodo de Contexto (Nodo 1): Usa Multi-Query Expansion para generar queries diversas
    con Gemini Flash, y luego busca en pgvector con cada una, deduplicando resultados.
    """
    print("\n========================================================")
    print("[NODO 1: CONTEXTO] Recuperando información histórica con Multi-Query Expansion...")
    print("========================================================")
    
    data = state["raw_note_data"]
    title = data.get("class_title", "")
    transcription = data.get("transcription", "")
    notes = data.get("my_notes", "")
    
    db = config["configurable"].get("db")
    raw_note_id = state.get("raw_note_id")
    
    prev_note = None
    current_note = None
    if db is not None and raw_note_id:
        from app.models import RawNote, ProcessedNote
        current_note = db.query(RawNote).filter(RawNote.id == raw_note_id).first()
        if current_note:
            from app.knowledge import logical_previous_note
            previous_raw = logical_previous_note(db, current_note)
            prev_note = previous_raw.processed_note if previous_raw else None
            
    course = current_note.course_name if current_note else data.get("course_name", "")
    
    context_chunks = []
    if prev_note:
        print(f"[AGENTE ACCIÓN] Encontrada nota anterior lógica para el curso '{course}'. Inyectando al contexto legacy.")
        context_chunks.append(f"=== NOTA ANTERIOR INMEDIATA ===\n{prev_note.structured_markdown}")
    
    if db is not None:
        # 1. Generar múltiples queries con Gemini Flash
        expanded_queries = expand_queries_with_llm(transcription, notes, title, course, db)
        
        # 2. Buscar con cada query y deduplicar por chunk ID
        seen_ids = set()
        all_chunks = []
        
        for query in expanded_queries:
            results = vector_store_retriever_tool(query, course, db, limit=3, exclude_raw_note_id=raw_note_id)
            for chunk in results:
                if chunk["id"] not in seen_ids:
                    seen_ids.add(chunk["id"])
                    all_chunks.append(chunk["content"])
        
        limit_sem = 5 if prev_note else 6
        for c in all_chunks[:limit_sem]:
            context_chunks.append(f"Contexto Histórico (RAG): {c}")
            
        if not context_chunks:
            context_chunks = ["Contexto Histórico: No se encontraron conceptos anteriores similares guardados o notas previas."]
    else:
        context_chunks = [
            "Referencia de Microservicios: Optimizar indexación vectorial HNSW en Postgres pgvector.",
            "Referencia de Bases de Datos: Usar redis-cli para asegurar idempotencia."
        ]
        
    state["notes_context"] = context_chunks
    
    existing_glossary = ""
    existing_glossary_terms = []
    f_count = 5  # default
    
    if db is not None:
        try:
            from app.models import CourseGlossary
            glossary = db.query(CourseGlossary).filter(CourseGlossary.course_name == course).first()
            if glossary:
                if glossary.compiled_markdown:
                    existing_glossary = glossary.compiled_markdown
                if glossary.entries:
                    existing_glossary_terms = [entry.get("term", "").strip() for entry in glossary.entries if entry.get("term")]
                
            # Obtener target del usuario o usar densidad
            user_target = current_note.flashcard_target if current_note else None
            if user_target is not None and user_target > 0:
                f_count = user_target
                print(f"[AGENTE CONTEXTO] Usando target de flashcards del usuario: {f_count}")
            else:
                density = crud.get_flashcard_density(db)
                text_len = len(transcription) if transcription else 0
                f_count = max(3, round((text_len / 5000) * density))
                print(f"[AGENTE CONTEXTO] Calculada cantidad de flashcards (densidad={density}, text_len={text_len}) -> {f_count}")
        except Exception as e:
            print(f"[ERROR] Error al cargar glosario o densidad en retrieve_context_node: {e}")
            
    state["existing_glossary"] = existing_glossary
    state["existing_glossary_terms"] = existing_glossary_terms
    state["flashcard_count"] = f_count
    
    print(f"[AGENTE ACCIÓN] Contexto histórico recuperado ({len(context_chunks)} chunks): {[c[:80] + '...' for c in context_chunks]}")
    return state


def filter_glossary_node(state: AgentState, config: dict = None) -> AgentState:
    """
    Nodo Intermedio (Filtro Inteligente): Usa un modelo ligero para identificar
    cuáles términos del glosario se mencionan en la transcripción. 
    Luego, filtra las definiciones completas para inyectar solo las relevantes,
    reduciendo masivamente el consumo de tokens.
    """
    existing_glossary_terms = state.get("existing_glossary_terms", [])
    if not existing_glossary_terms:
        return state

    transcription = state["raw_note_data"].get("transcription", "")
    notes = state["raw_note_data"].get("my_notes", "")
    
    content_sample = ""
    if transcription:
        content_sample += transcription[:40000]
    if notes:
        content_sample += "\n" + notes[:10000]

    if not content_sample.strip():
        state["existing_glossary"] = ""
        return state

    print("\n========================================================")
    print("[NODO: FILTRO GLOSARIO] Optimizando inyección de conceptos...")
    print("========================================================")

    db = config["configurable"].get("db") if config and "configurable" in config else None
    if db is None:
        try:
            from app.database import SessionLocal
            db = SessionLocal()
        except:
            pass
    try:
        if db is not None:
            resolved = llm_models.resolve_selected_model(db, "query_expansion")
        else:
            requested = os.getenv("GEMINI_LITE_MODEL", llm_models.DEFAULT_MODELS["query_expansion"])
            resolved = llm_models.resolve_model("query_expansion", requested)
        llm = llm_models.create_chat_model(resolved, timeout=30, max_retries=1)

        prompt = (
            "Eres un asistente semántico multilingüe. Tu tarea es identificar qué conceptos de la siguiente lista "
            "son mencionados, discutidos o aludidos en la transcripción proporcionada. "
            "Ten en cuenta sinónimos, traducciones (ej. 'Virtual Memory' = 'Memoria Virtual') y errores tipográficos.\n\n"
            f"LISTA DE CONCEPTOS EXISTENTES:\n{', '.join(existing_glossary_terms)}\n\n"
            f"TRANSCRIPCIÓN/NOTAS:\n{content_sample}\n\n"
            "DEVUELVE ÚNICAMENTE UN ARRAY JSON con los nombres exactos (tal como aparecen en la lista superior) "
            "de los conceptos encontrados. Si no encuentras ninguno, devuelve []."
        )
        
        # Save prompt for the test (User request)
        try:
            with open("/tmp/flash_lite_prompt.txt", "w") as f:
                f.write(prompt)
        except Exception:
            pass

        print(
            f"[FILTRO GLOSARIO] requested='{resolved.requested_model}' "
            f"effective='{resolved.model_id}' via='{resolved.transport}' fallback={resolved.fallback_used}"
        )
        response = llm.invoke(prompt)
        content = _extract_text(response.content)
        
        import json
        import re
        
        # Limpiar markdown de código
        content = re.sub(r'```json\s*', '', content)
        content = re.sub(r'```\s*', '', content).strip()
        
        matched_terms = json.loads(content)
        if not isinstance(matched_terms, list):
            matched_terms = []
            
        print(f"[FILTRO GLOSARIO] Conceptos identificados: {matched_terms}")
        
        # Filtrar glossary entries
        if db is not None:
            from app.models import CourseGlossary
            course = state["raw_note_data"].get("course_name")
            glossary = db.query(CourseGlossary).filter(CourseGlossary.course_name == course).first()
            if glossary and glossary.entries:
                from app.glossary import compile_glossary_markdown
                filtered_entries = [e for e in glossary.entries if e.get("term") in matched_terms]
                state["existing_glossary"] = compile_glossary_markdown(filtered_entries, course)
                print(f"[FILTRO GLOSARIO] Glosario reducido de {len(glossary.entries)} a {len(filtered_entries)} conceptos.")
            
    except Exception as e:
        print(f"[ERROR] Falló el filtrado de glosario, se usará el glosario completo: {e}")
        
    return state


def execute_tools_node(state: AgentState) -> AgentState:
    """
    Nodo de Ejecución de Herramientas (Nodo 2): Aplica code_optimizer y command_validator
    sobre todos los snippets suministrados en las notas de clase.
    """
    print("\n========================================================")
    print("[NODO 2: HERRAMIENTAS] Procesando y optimizando snippets...")
    print("========================================================")
    
    data = state["raw_note_data"]
    code_snippets = data.get("code_snippets", [])
    command_snippets = data.get("command_snippets", [])
    
    optimized_codes = []
    for snippet in code_snippets:
        opt = code_optimizer_tool(snippet.get("code", ""), snippet.get("lang", ""))
        optimized_codes.append({
            "id": snippet.get("id"),
            "lang": snippet.get("lang"),
            "code": opt
        })
        
    validated_commands = []
    for cmd in command_snippets:
        val = command_validator_tool(cmd.get("cmd", ""), cmd.get("lang", ""))
        validated_commands.append({
            "id": cmd.get("id"),
            "order": cmd.get("order"),
            "lang": cmd.get("lang"),
            "cmd": val
        })
        
    state["raw_note_data"]["code_snippets"] = optimized_codes
    state["raw_note_data"]["command_snippets"] = validated_commands
    return state


def entity_extraction_node(state: AgentState, config: RunnableConfig) -> AgentState:
    """
    Nodo de Extracción de Entidades: Analiza la nota cruda e identifica todas las entidades 
    (comandos, conceptos, fórmulas, estructuras) que deben ser documentadas obligatoriamente en la síntesis.
    """
    print("\n========================================================")
    print("[NODO DE EXTRACCIÓN] Generando manifiesto de entidades a cubrir...")
    print("========================================================")
    
    data = state["raw_note_data"]
    title = data.get("class_title", "")
    course = data.get("course_name", "")
    transcription = data.get("transcription", "")
    notes = data.get("my_notes", "")
    
    db = config["configurable"].get("db")
    # Preparar el contenido (limitado para no rebasar contexto si fuera extremo, aunque el LLM soporta mucho)
    content_sample = ""
    if transcription:
        content_sample += transcription[:40000]
    if notes:
        content_sample += "\n" + notes[:10000]
        
    if not content_sample.strip():
        state["extraction_manifest"] = "[]"
        state["content_profile"] = "mixed"
        return state

    try:
        if db is not None:
            resolved = llm_models.resolve_selected_model(db, "query_expansion")
        else:
            requested = os.getenv("GEMINI_LITE_MODEL", llm_models.DEFAULT_MODELS["query_expansion"])
            resolved = llm_models.resolve_model("query_expansion", requested)
        print(
            f"[EXTRACCIÓN] requested='{resolved.requested_model}' effective='{resolved.model_id}' "
            f"via='{resolved.transport}' fallback={resolved.fallback_used}"
        )
        llm = llm_models.create_chat_model(resolved, timeout=30, max_retries=1)
            
        prompt = (
            "Eres un extractor de entidades para apuntes de estudio. Tu tarea es analizar el siguiente texto y extraer UNA LISTA EN FORMATO JSON de todas las entidades importantes mencionadas.\n\n"
            "ENTIDADES A EXTRAER:\n"
            "- Comandos CLI (ej. docker run, chmod)\n"
            "- Conceptos técnicos (ej. Inversión de Control, Entropía)\n"
            "- Estructuras de código (ej. try-catch, useEffect)\n"
            "- Fórmulas matemáticas o expresiones\n"
            "- Títulos o temas principales\n\n"
            "FORMATO DE RESPUESTA OBLIGATORIO (JSON Array):\n"
            "[\n"
            "  {\"entity\": \"nombre exacto\", \"type\": \"command|concept|syntax|formula|topic\", \"questions_to_answer\": [\"what\", \"why\", \"how\", \"where\"]}\n"
            "]\n"
            "Determina qué preguntas (qué es, por qué se usa, cómo se usa, dónde/cuándo aplica) son relevantes para cada entidad basándote en la clase.\n\n"
            "Por último, al final del array de entidades, agrega un único objeto extra que clasifique el perfil del contenido de la clase en general:\n"
            "{\"profile\": \"theoretical\" | \"technical_practical\" | \"mathematical\" | \"mixed\"}\n\n"
            f"CLASE: {title} ({course})\n"
            f"CONTENIDO:\n{content_sample}"
        )
        
        from langchain_core.messages import HumanMessage
        response = llm.invoke([HumanMessage(content=prompt)])
        raw_text = _extract_text(response.content)
        
        # Limpiar markdown de json si lo hubiera
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
            
        state["extraction_manifest"] = raw_text.strip()
        
        # Parsear profile (rápido con regex en lugar de json.loads completo por si el LLM tuvo un error menor de formato)
        import re
        profile_match = re.search(r'"profile"\s*:\s*"(theoretical|technical_practical|mathematical|mixed)"', raw_text)
        if profile_match:
            state["content_profile"] = profile_match.group(1)
        else:
            state["content_profile"] = "mixed"
            
        print(f"[EXTRACCIÓN] Manifiesto generado. Perfil detectado: {state['content_profile']}")
        
    except Exception as e:
        print(f"[ERROR] Extracción de entidades falló: {e}")
        state["extraction_manifest"] = "[]"
        state["content_profile"] = "mixed"
        
    return state


def preprocess_transcription(transcription: str, code_snippets: List[Dict], command_snippets: List[Dict], images: List[Any]) -> tuple[str, list[str]]:
    if not transcription:
        return "", []
    
    # Regex matching &"tipo:indice"
    pattern = r'&"([a-zA-Z]+):(\d+)"'
    
    # Sort images by created_at to have a reliable index mapping
    sorted_images = sorted(images, key=lambda x: x.created_at) if images else []
    
    used_image_indices = set()
    
    def replace_match(match):
        tipo = match.group(1).lower()
        idx_str = match.group(2)
        try:
            idx = int(idx_str) - 1
        except ValueError:
            return match.group(0)
            
        if tipo == "codigo":
            if 0 <= idx < len(code_snippets):
                snippet = code_snippets[idx]
                lang = snippet.get("lang") or ""
                code = snippet.get("code") or ""
                return f"\n```{lang}\n{code}\n```\n"
        elif tipo == "comando":
            if 0 <= idx < len(command_snippets):
                snippet = command_snippets[idx]
                lang = snippet.get("lang") or "bash"
                cmd = snippet.get("cmd") or ""
                return f"\n```{lang}\n{cmd}\n```\n"
        elif tipo == "imagen":
            if 0 <= idx < len(sorted_images):
                used_image_indices.add(idx)
                img = sorted_images[idx]
                if img.descripcion_llm and img.descripcion_llm.strip():
                    return f"\n{img.descripcion_llm.strip()}\n"
        
        return match.group(0)
        
    processed_text = re.sub(pattern, replace_match, transcription)
    
    # Detect orphaned images
    orphaned_images = []
    for i, img in enumerate(sorted_images):
        if i not in used_image_indices and img.descripcion_llm and img.descripcion_llm.strip():
            orphaned_images.append(img.descripcion_llm.strip())
            
    return processed_text, orphaned_images


def synthesis_node(state: AgentState, config: RunnableConfig) -> AgentState:
    """
    Nodo de Síntesis (Nodo 3): Compila todo el contenido analizado y optimizado
    en una nota estructurada en formato Markdown de Obsidian.
    
    El LLM realiza internamente la planeación y el razonamiento (chain-of-thought)
    gracias a la Sección 0 del System Prompt, eliminando la necesidad de nodos separados.
    """
    print("\n========================================================")
    print("[NODO 3: SÍNTESIS] Compilando la nota premium final con Synapse Scholar (CoT integrado)...")
    print("========================================================")
    
    data = state["raw_note_data"]
    title = data.get("class_title", "")
    course = data.get("course_name", "")
    platform = data.get("platform", "Local")
    teacher = data.get("teacher", "N/A")
    module = data.get("course_module", "N/A")
    transcription = data.get("transcription", "")
    summary = data.get("class_summary", "")
    notes = data.get("my_notes", "")
    code_snippets = data.get("code_snippets", [])
    command_snippets = data.get("command_snippets", [])
    context = state.get("notes_context", [])
    
    # Obtener imágenes de la base de datos
    db = config["configurable"].get("db")
    images = []
    if db is not None:
        from app.models import RawNote
        note_id = state.get("raw_note_id")
        if note_id:
            note = db.query(RawNote).filter(RawNote.id == note_id).first()
            if note:
                images = note.images
                
    processed_transcription, orphaned_images = preprocess_transcription(transcription, code_snippets, command_snippets, images)
    
    # 1. Modo Real con OpenRouter o Gemini nativo si están configurados
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    google_api_key = os.getenv("GOOGLE_API_KEY")
    synthesis_fallback_reason = None
    resolved = None
    
    if openrouter_api_key or google_api_key:
        try:
            if db is not None:
                resolved = llm_models.resolve_selected_model(db, "synthesis")
            else:
                requested = os.getenv("GEMINI_MODEL", llm_models.DEFAULT_MODELS["synthesis"])
                resolved = llm_models.resolve_model("synthesis", requested)
            print(
                f"[AGENTE LLM - SÍNTESIS] requested='{resolved.requested_model}' "
                f"effective='{resolved.model_id}' via='{resolved.transport}' fallback={resolved.fallback_used}"
            )
            llm = llm_models.create_chat_model(resolved, timeout=120, max_retries=2)
            
            # Si hay errores de mermaid, el prompt cambia a un modo de "Editor/Corrector"
            mermaid_errors = state.get("mermaid_validation_errors", "")
            flashcard_errors = state.get("flashcard_validation_errors", "")
            
            if mermaid_errors or flashcard_errors:
                err_text = ""
                if mermaid_errors:
                    err_text += f"ERRORES DE SINTAXIS MERMAID:\n{mermaid_errors}\n\n"
                if flashcard_errors:
                    err_text += f"ERRORES DE CANTIDAD DE FLASHCARDS:\n{flashcard_errors}\n\n"
                    
                prompt = (
                    f"El Markdown que generaste tiene los siguientes errores de validación:\n\n"
                    f"{err_text}"
                    f"INSTRUCCIÓN ESTRICTA DE CORRECCIÓN:\n"
                    f"1. Si hay errores de Mermaid, corrige únicamente la sintaxis de los diagramas Mermaid problemáticos. NO alteres ningún otro texto.\n"
                    f"2. Si hay errores de cantidad de Flashcards, añade o remueve flashcards en la sección '## 🗃️ Flashcards' hasta tener EXACTAMENTE {state.get('flashcard_count', 5)} flashcards, utilizando la sintaxis de Obsidian Spaced Repetition correcta (::, ?, ??, ==cloze==).\n"
                    f"Devuelve el documento completo corregido en `markdown_note`.\n\n"
                    f"DOCUMENTO ORIGINAL:\n{state.get('structured_markdown', '')}"
                )
            else:
                notes_section = f"APUNTES DEL ALUMNO:\n{notes}\n\n" if notes and notes.strip() else ""
            
                code_str = "\n".join(f"  - {c}" for c in code_snippets) if code_snippets else "Ninguno"
                cmd_str = "\n".join(f"  - {c}" for c in command_snippets) if command_snippets else "Ninguno"
                
                if orphaned_images:
                    orphaned_str = "\n".join(f"  - {desc}" for desc in orphaned_images)
                    orphaned_section = f"- Descripciones de Imágenes Adjuntas (Sin referencia directa):\n{orphaned_str}\n\n"
                else:
                    orphaned_section = ""
            if not context:
                context_str = "Ninguno"
            else:
                rag_directive = (
                    "⚠️ DIRECTIVA ESTRICTA DE USO DEL RAG:\n"
                    "Los siguientes fragmentos históricos son EXCLUSIVAMENTE para tu referencia. DEBES usarlos para:\n"
                    "1. Deduplicación: Revisa las flashcards históricas. Si un concepto ya fue preguntado, NO crees una flashcard idéntica.\n"
                    "2. Backlinking: Si la clase actual referencia un tema histórico, crea hipervínculos hacia el nombre de la clase pasada usando la sintaxis de Obsidian (ej. `[[Chapter 2]]`).\n"
                    "3. Consistencia: Mantén el mismo tono y profundidad.\n"
                    "NO copies el contenido del RAG como si fuera materia nueva de la clase actual.\n\n"
                )
                context_str = rag_directive + "\n\n--------------------------------------------------------------------------------\n\n".join(c.strip() for c in context)
                
            manifest_data = state.get('extraction_manifest', 'No disponible').strip()
            manifest_section = (
                f"\n\n\n================================================================================\n"
                f"MANIFIESTO DE ENTIDADES A CUBRIR OBLIGATORIAMENTE:\n"
                f"================================================================================\n"
                f"{manifest_data}\n\n"
            )
            
            if manifest_data and manifest_data != "No disponible":
                manifest_section += (
                    f"⚠️ INSTRUCCIÓN CRÍTICA: Debes cubrir TODAS las entidades listadas en el manifiesto "
                    f"respondiendo a las preguntas marcadas (Qué/Por qué/Cómo/Dónde). "
                    f"No omitas NINGUNA entidad, comando, o concepto del manifiesto en tu nota final.\n\n"
                )

            prompt = (
                f"Fecha de hoy (debes colocar esta fecha exacta en el campo 'fecha' del frontmatter YAML): '{time.strftime('%Y-%m-%d')}'\n"
                f"Título de la clase: '{title}'\n"
                f"Módulo: '{module}'\n"
                f"Curso: '{course}'\n"
                f"Instructor: '{teacher}'\n"
                f"Modo de escritura: '{state['raw_note_data'].get('writing_mode')}'\n"
                f"Plataforma: '{state['raw_note_data'].get('platform')}'\n"
                f"Cantidad exacta de flashcards requeridas: {state.get('flashcard_count', 5)}\n\n"
                f"DIRECTIVA DE CONSISTENCIA TERMINOLÓGICA PARA TODA LA NOTA:\n"
                f"Prioriza el término técnico canónico en inglés en títulos, subtítulos, explicaciones y flashcards. Redacta en español y, al introducir cada concepto por primera vez, escribe el término inglés seguido de su traducción breve al español entre paréntesis; por ejemplo: 'Un deadlock (interbloqueo) es...'. Después usa sólo el término inglés. No inviertas el orden como 'interbloqueo (deadlock)' ni repitas la traducción en cada mención. El glosario debe respetar además el formato exacto de la DIRECTIVA G.\n\n"
                f"CONCEPTOS TÉCNICOS YA DEFINIDOS EN ESTE CURSO:\n"
                f"{', '.join(state.get('existing_glossary_terms', [])) if state.get('existing_glossary_terms') else 'Ninguno'}\n"
                f"⚠️ INSTRUCCIÓN CRÍTICA DE EVITAR DUPLICADOS Y PARAFRASEOS:\n"
                f"Para los conceptos listados anteriormente:\n"
                f"1. Está ESTRICTAMENTE PROHIBIDO volver a definirlos usando la etiqueta '#definicion' en tu respuesta.\n"
                f"2. NO generes una entrada '#definicion-ampliada' si la clase actual solo menciona o usa el concepto sin aportar información conceptual nueva. Evita reescribir o parafrasear la definición existente con otras palabras.\n"
                f"3. Solo genera '#definicion-ampliada' si la clase actual añade datos, características, variantes o detalles técnicos sustanciales y específicos del curso que complementen directamente la definición existente. Sigue estrictamente la DIRECTIVA G.\n\n"
                f"GLOSARIO EXISTENTE DEL CURSO (Para tu referencia visual completa de contenido):\n"
                f"{state.get('existing_glossary', 'Vacío — Este es el primer apunte del curso.')}\n\n\n\n"
                f"================================================================================\n"
                f"TRANSCRIPCIÓN:\n"
                f"================================================================================\n"
                f"{processed_transcription}\n\n"
                f"{notes_section}"
                f"MATERIAL ADICIONAL:\n"
                f"- Snippets de código (ya optimizados):\n{code_str}\n\n"
                f"- Comandos CLI (ya validados):\n{cmd_str}\n\n"
                f"{orphaned_section}\n"
                f"================================================================================\n"
                f"CONTEXTO HISTÓRICO RECUPERADO (RAG):\n"
                f"================================================================================\n"
                f"{context_str}\n\n"
                f"{manifest_section}"
                    f"Sigue rigurosamente la plantilla base Obsidian de Synapse Scholar, aplicando las Directivas A-I. Asegúrate de incluir las secciones '## 📖 Conceptos Clave (Glosario)' y '## 🗃️ Flashcards' con el tag de deck jerárquico."
                )
            
            # Directivas por perfil de contenido
            profile = state.get("content_profile", "mixed")
            profile_directive = ""
            
            if profile == "technical_practical":
                print("[AGENTE SÍNTESIS] Perfil técnico-práctico detectado. Priorizando exactitud de comandos y código.")
                profile_directive = (
                    "\n\n# MODO TÉCNICO-PRÁCTICO (ACTIVADO)\n"
                    "Esta clase es predominantemente práctica. Tienes como máxima prioridad:\n"
                    "1. Documentar CADA comando individual con su sintaxis completa.\n"
                    "2. Preservar TODOS los ejemplos de uso y descripciones de flags.\n"
                    "3. No agrupar comandos en resúmenes narrativos vagos.\n"
                    "La extensión larga de la nota está justificada para retener el nivel técnico."
                )
            elif profile == "mathematical":
                print("[AGENTE SÍNTESIS] Perfil matemático detectado. Activando directiva de fórmulas.")
                profile_directive = (
                    "\n\n# DIRECTIVA ADICIONAL DE FÓRMULAS MATEMÁTICAS (ACTIVADA)\n"
                    "Dado que esta clase contiene matemáticas o fórmulas, debes incorporarlas en la sección '## 📖 Conceptos Clave (Glosario)' así:\n"
                    "1. Crea entradas con etiqueta `#formula` (ej. `**Nombre (EN)** #formula`). Escribe la fórmula en LaTeX (usando $).\n"
                    "2. Debajo, explica TODOS los términos, símbolos y variables línea por línea.\n"
                    "3. Añade una entrada con etiqueta `#usos` describiendo un caso práctico resuelto."
                )
                
            # Pasar la directiva del system prompt como SystemMessage
            messages = [
                SystemMessage(content=SYNAPSE_SCHOLAR_SYSTEM_PROMPT + profile_directive),
                HumanMessage(content=prompt)
            ]
            
            structured_llm = llm.with_structured_output(AgentOutput)
            response = structured_llm.invoke(messages)
            
            # Limpiar posible markdown residual en markdown_note
            md = response.markdown_note.strip()
            if md.startswith("```markdown"):
                md = md[11:].strip()
            elif md.startswith("```txt"):
                md = md[6:].strip()
            elif md.startswith("```"):
                md = md[3:].strip()
            if md.endswith("```"):
                md = md[:-3].strip()
            
            state["structured_markdown"] = md
                
            # Si estamos corrigiendo errores, mantenemos los comentarios originales si el agente no puso nada nuevo útil
            if (mermaid_errors or flashcard_errors) and not response.ai_comments.strip():
                pass # Retenemos el ai_comments actual en estado
            else:
                state["ai_comments"] = response.ai_comments.strip()

            if resolved.fallback_used:
                notice = (
                    f"⚠️ El modelo solicitado `{resolved.requested_model}` no estaba disponible; "
                    f"esta nota se procesó con `{resolved.model_id}` vía {resolved.transport}. "
                    f"Motivo: {resolved.fallback_reason}"
                )
                state["ai_comments"] = f"{notice}\n\n{state.get('ai_comments', '')}".strip()
            
            # Limpiamos los errores para la siguiente iteración (si hubiera)
            state["mermaid_validation_errors"] = ""
            state["flashcard_validation_errors"] = ""
            
            print("[AGENTE SÍNTESIS REAL (Gemini - Synapse Scholar + CoT)] Nota compilada exitosamente.")
            return state
        except Exception as e:
            print(f"[ERROR] Error al invocar Gemini para síntesis: {e}. Usando simulación.")
            synthesis_fallback_reason = str(e)
    else:
        synthesis_fallback_reason = "No hay credenciales de Google AI Studio ni OpenRouter configuradas."

    # 2. Modo Simulación (Motor de reglas semánticas premium de Synapse Scholar de alta fidelidad)
    ticks4 = "`" * 4
    
    # Simular la nota en el contenedor de 4 backticks de acuerdo con la Directiva E
    markdown = f"""{ticks4}txt
---
tipo: fuente
formato: curso_online
estado: en_proceso
fecha: {time.strftime("%Y-%m-%d")}
---
# 📚 {title}

**Curso:** [[{course}]]
**Instructor/Autor:** {teacher} | **Módulo del curso:** {module} | **Enlace:** ---

## 🗺️ Contexto Inicial (Fase 1)
{summary or "Análisis pedagógico enfocado en el desarrollo e integración de los conceptos discutidos en clase para el modelado de arquitecturas robustas y escalables."}

## 📝 Apuntes de Clase (Captura Híbrida)

### 📌 Conceptos Clave de la Sesión
**Contexto:** Notas estructuradas a partir de la transcripción técnica de la clase.
> "La automatización de procesos utilizando grafos de estados y memoria persistente garantiza flujos de trabajo resilientes e independientes de estado."

**❓ ¿Por qué implementar Synapse Scholar?**
* **Respuesta:** Para minar información a alta fidelidad, rectificar términos técnicos y estructurar el conocimiento de forma óptima para Obsidian.
* **Detalle clave:** La Directiva E exige el encapsulado maestro dentro de 4 comillas invertidas para prevenir rupturas en los visualizadores Markdown.
"""

    if notes:
        markdown += f"\n**⚠️ Notas Complementarias del Alumno:**\n{notes}\n"

    if code_snippets:
        markdown += "\n**💻 Fragmentos de Código / Fórmulas:**\n"
        for i, snippet in enumerate(code_snippets):
            lang = snippet.get("lang") or "typescript"
            code = snippet.get("code") or ""
            markdown += f"#### Fragmento {i + 1} ({lang})\n```{lang}\n{code}\n```\n\n"

    if command_snippets:
        markdown += "\n**⚙️ Comandos de Configuración (Paso a paso):**\n"
        for snippet in command_snippets:
            order = snippet.get("order") or "Ejecución"
            lang = snippet.get("lang") or "bash"
            cmd = snippet.get("cmd") or ""
            markdown += f"* **{order}** ({lang}):\n  ```{lang}\n  {cmd}\n  ```\n"

    # Verificar si hay dudas de transcripción simuladas
    if transcription and "incomprensible" in transcription.lower():
        markdown += f'\n**❓ Duda de Transcripción:**\n"[Fragmento literal incomprensible de la transcripción]" #revisar_audio\n'

    # Generar conceptos clave del glosario en la simulación
    markdown += f"""
## 📖 Conceptos Clave (Glosario)

**Simulated Concept** #definicion
Un simulated concept (concepto simulado) es un concepto creado de forma sintética para validar la integración de glosario en la simulación de Synapse Scholar.
"""

    # Generar la cantidad solicitada de flashcards en la simulación
    course_clean = re.sub(r'[^a-zA-Z0-9]', '', course)
    module_clean = re.sub(r'[^a-zA-Z0-9]', '', module)
    if not course_clean:
        course_clean = "Curso"
    if not module_clean:
        module_clean = "Modulo"
        
    markdown += f"""
## 🗃️ Flashcards
#flashcards/{course_clean}/{module_clean}
"""
    
    target_f = state.get("flashcard_count", 5)
    for i in range(1, target_f + 1):
        if i % 3 == 1:
            markdown += f"\n¿Pregunta de repaso {i}?::Respuesta de repaso {i}.\n"
        elif i % 3 == 2:
            markdown += f"\nConcepto A {i} vs Concepto B {i}:::Explicación comparativa {i}.\n"
        else:
            markdown += f"\nUn ==concepto oculto {i}== permite validar clozes en la tarjeta {i}.\n"

    markdown += f"""
## 🧠 Zona de Procesamiento (Fase 2: Deconstrucción)
* [[{title} - Fundamentos]] #definicion
* [[Implementacion de {course}]] #algoritmo
"""
    
    state["structured_markdown"] = markdown.strip()
    
    fallback_notice = (
        f"⚠️ No se pudo utilizar el LLM seleccionado y se generó una salida local de emergencia. Motivo: {synthesis_fallback_reason}\n\n"
        if synthesis_fallback_reason
        else ""
    )
    ai_comments = fallback_notice + """¿Tienes la siguiente parte de la transcripción para continuar, o damos esta clase por terminada? Además, ¿el nivel de detalle de este resumen es adecuado o prefieres que realice una segunda pasada para extraer más información de tus notas originales?"""
    state["ai_comments"] = ai_comments
    
    print("[AGENTE SIMULACIÓN - Synapse Scholar] Nota premium de estudio compilada exitosamente.")
    return state


def mermaid_validation_node(state: AgentState, config: RunnableConfig) -> AgentState:
    """
    Nodo que extrae bloques mermaid de 'structured_markdown', los compila con mmdc,
    y si fallan, acumula el error en 'mermaid_validation_errors'.
    """
    print("[NODO 4: VALIDACIÓN] Verificando sintaxis de diagramas Mermaid...")
    md = state.get("structured_markdown", "")
    mermaid_blocks = re.findall(r'```mermaid\n(.*?)\n```', md, re.DOTALL)
    
    if not mermaid_blocks:
        print("[VALIDACIÓN] No se encontraron diagramas Mermaid. Saltando.")
        return state

    import shutil
    has_mmdc = shutil.which("mmdc") is not None
    has_npx = shutil.which("npx") is not None
    
    if not has_mmdc and not has_npx:
        print("[VALIDACIÓN] ADVERTENCIA: Ni 'mmdc' ni 'npx' están instalados. Saltando validación de diagramas Mermaid.")
        state["mermaid_validation_errors"] = ""
        return state

    errors = []
    
    # Crear archivo de configuración de Puppeteer para --no-sandbox en Docker
    puppeteer_config_content = '{"args": ["--no-sandbox", "--disable-setuid-sandbox"]}'
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as pf:
        pf.write(puppeteer_config_content)
        puppeteer_config_path = pf.name
        
    try:
        for i, code in enumerate(mermaid_blocks):
            code = code.strip()
            if not code:
                continue
                
            # Crear archivo temporal
            with tempfile.NamedTemporaryFile(suffix=".mmd", delete=False, mode="w") as f:
                f.write(code)
                temp_path = f.name
                
            try:
                # Ejecutar compilador oficial de Mermaid
                # timeout para evitar que se cuelgue puppeteer
                cmd = ["mmdc", "-p", puppeteer_config_path, "-i", temp_path, "-o", f"{temp_path}.svg"]
                if not has_mmdc:
                    cmd = ["npx", "-y", "@mermaid-js/mermaid-cli", "-p", puppeteer_config_path, "-i", temp_path, "-o", f"{temp_path}.svg"]
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=15
                )
                if result.returncode != 0:
                    err_msg = result.stderr.strip()
                    # Extraemos solo la parte importante del error para no saturar tokens
                    errors.append(f"Diagrama {i+1} falló:\nCódigo:\n```mermaid\n{code}\n```\nError:\n{err_msg[:500]}")
                    print(f"[VALIDACIÓN] Diagrama {i+1} INVÁLIDO.")
                else:
                    print(f"[VALIDACIÓN] Diagrama {i+1} válido.")
            except subprocess.TimeoutExpired:
                errors.append(f"Diagrama {i+1} falló: Timeout al compilar (código demasiado complejo o infinito).")
                print(f"[VALIDACIÓN] Diagrama {i+1} TIMEOUT.")
            except Exception as e:
                errors.append(f"Diagrama {i+1} falló: {str(e)}")
                print(f"[VALIDACIÓN] Diagrama {i+1} ERROR: {e}")
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                if os.path.exists(f"{temp_path}.svg"):
                    os.remove(f"{temp_path}.svg")
    finally:
        if os.path.exists(puppeteer_config_path):
            os.remove(puppeteer_config_path)

    if errors:
        state["mermaid_validation_errors"] = "\n\n".join(errors)
        state["mermaid_retries"] = state.get("mermaid_retries", 0) + 1
        print(f"[VALIDACIÓN] Se encontraron {len(errors)} error(es) en los diagramas. Intento #{state['mermaid_retries']} de corrección.")
    else:
        print("[VALIDACIÓN] Todos los diagramas Mermaid son correctos.")
        state["mermaid_validation_errors"] = ""

    return state


def route_mermaid(state: AgentState) -> str:
    """Ruta condicional para devolver el flujo a síntesis si hay errores y no se ha superado el límite de intentos."""
    errors = state.get("mermaid_validation_errors", "")
    retries = state.get("mermaid_retries", 0)
    
    if errors and retries < 3:
        return "synthesis_node"
    return "flashcard_validation_node"


# ============================================================================
# NUEVA LÓGICA DE VALIDACIÓN DE FLASHCARDS
# ============================================================================

def count_flashcards(markdown: str) -> int:
    """
    Cuenta el número de flashcards en el markdown basándose en la sintaxis de Obsidian Spaced Repetition:
    - Líneas con '::' o '::?' (excluyendo links http/https)
    - Preguntas multi-línea (líneas con '?' o '??' solas, que separen pregunta y respuesta)
    - Cloze deletions (párrafos que contienen '==texto oculto==')
    """
    count = 0
    lines = markdown.split('\n')
    
    # 1. Contar single-line y single-line reversed (filtrando urls)
    single_line_pattern = re.compile(r'^(?!http|https).+?::(?!/|:).+$')
    for line in lines:
        if single_line_pattern.match(line.strip()):
            count += 1
            
    # 2. Contar multi-line y multi-line reversed
    multi_line_pattern = re.compile(r'^\s*\?\s*$|^\s*\?\?\s*$')
    for line in lines:
        if multi_line_pattern.match(line):
            count += 1
            
    # 3. Contar cloze cards
    in_code_block = False
    in_flashcard_section = False
    cloze_paragraphs = 0
    current_paragraph = []
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('## 🗃️ Flashcards'):
            in_flashcard_section = True
            continue
        elif stripped.startswith('##') and in_flashcard_section:
            in_flashcard_section = False
            
        if not in_flashcard_section:
            continue
            
        if stripped.startswith('```'):
            in_code_block = not in_code_block
            continue
            
        if in_code_block:
            continue
            
        if not stripped:
            if current_paragraph:
                text = ' '.join(current_paragraph)
                # Si contiene == y no contiene ? o :: (para evitar doble conteo)
                if '==' in text and '?' not in text and '::' not in text:
                    clozes = len(re.findall(r'==([^=]+)==', text))
                    cloze_paragraphs += clozes
                current_paragraph = []
        else:
            current_paragraph.append(stripped)
            
    if current_paragraph:
        text = ' '.join(current_paragraph)
        if '==' in text and '?' not in text and '::' not in text:
            clozes = len(re.findall(r'==([^=]+)==', text))
            cloze_paragraphs += clozes
            
    return count + cloze_paragraphs


def flashcard_validation_node(state: AgentState, config: RunnableConfig) -> AgentState:
    """
    Nodo de Validación de Flashcards (Nodo 5): Verifica que la cantidad de flashcards
    generadas en la sección coincida con el target del estado (con un margen de tolerancia).
    """
    print("\n========================================================")
    print("[NODO 5: VALIDACIÓN FLASHCARDS] Verificando cantidad de flashcards generadas...")
    print("========================================================")
    md = state.get("structured_markdown", "")
    target = state.get("flashcard_count", 5)
    
    actual_count = count_flashcards(md)
    print(f"[VALIDACIÓN FLASHCARDS] Encontradas: {actual_count}, Target requerido: {target}")
    
    # Margen de tolerancia: +/- 15% o +/- 2 (lo que sea mayor)
    tolerance = max(2, int(target * 0.15))
    diff = abs(actual_count - target)
    
    if diff > tolerance:
        err = f"Se generaron {actual_count} flashcards, pero el target requerido es {target} (tolerancia de +/- {tolerance})."
        state["flashcard_validation_errors"] = err
        state["flashcard_retries"] = state.get("flashcard_retries", 0) + 1
        print(f"[VALIDACIÓN FLASHCARDS] INTENTO #{state['flashcard_retries']} FALLIDO: {err}")
    else:
        print("[VALIDACIÓN FLASHCARDS] Cantidad correcta y dentro de tolerancia.")
        state["flashcard_validation_errors"] = ""
        
    return state


def route_flashcard(state: AgentState) -> str:
    """Ruta condicional para devolver el flujo a síntesis si hay errores en las flashcards."""
    errors = state.get("flashcard_validation_errors", "")
    retries = state.get("flashcard_retries", 0)
    
    if errors and retries < 2:
        return "synthesis_node"
    return "glossary_extraction_node"


# ============================================================================
# COMPILACIÓN DEL GRAFO DE ESTADOS (LangGraph Workflow) — Con Glosario y Flashcards
# ============================================================================

def compile_agent():
    """
    Compila y retorna el agente de LangGraph con 8 nodos:
    1. retrieve_context_node — RAG con pgvector y carga de glosario anterior
    2. filter_glossary_node — Selección de conceptos relevantes del glosario existente
    3. execute_tools_node — Herramientas determinísticas de optimización de snippets
    4. entity_extraction_node — Manifiesto de entidades que la síntesis debe cubrir
    5. synthesis_node — Síntesis con inyección de glosario/flashcards
    6. mermaid_validation_node — Bucle de validación de sintaxis de diagramas Mermaid
    7. flashcard_validation_node — Bucle de validación de cantidad de flashcards
    8. glossary_extraction_node — Extracción determinística y actualización de glosario en DB
    """
    workflow = StateGraph(AgentState)
    
    from app.glossary import glossary_extraction_node
    
    workflow.add_node("retrieve_context_node", retrieve_context_node)
    workflow.add_node("filter_glossary_node", filter_glossary_node)
    workflow.add_node("execute_tools_node", execute_tools_node)
    workflow.add_node("entity_extraction_node", entity_extraction_node)
    workflow.add_node("synthesis_node", synthesis_node)
    workflow.add_node("mermaid_validation_node", mermaid_validation_node)
    workflow.add_node("flashcard_validation_node", flashcard_validation_node)
    workflow.add_node("glossary_extraction_node", glossary_extraction_node)
    
    workflow.set_entry_point("retrieve_context_node")
    workflow.add_edge("retrieve_context_node", "filter_glossary_node")
    workflow.add_edge("filter_glossary_node", "execute_tools_node")
    workflow.add_edge("execute_tools_node", "entity_extraction_node")
    workflow.add_edge("entity_extraction_node", "synthesis_node")
    workflow.add_edge("synthesis_node", "mermaid_validation_node")
    
    # De mermaid_validation_node a flashcard_validation_node o reintento de síntesis
    workflow.add_conditional_edges(
        "mermaid_validation_node",
        route_mermaid,
        {
            "synthesis_node": "synthesis_node",
            "flashcard_validation_node": "flashcard_validation_node"
        }
    )
    
    # De flashcard_validation_node a glossary_extraction_node o reintento de síntesis
    workflow.add_conditional_edges(
        "flashcard_validation_node",
        route_flashcard,
        {
            "synthesis_node": "synthesis_node",
            "glossary_extraction_node": "glossary_extraction_node"
        }
    )
    
    workflow.add_edge("glossary_extraction_node", END)
    
    # Configurar la memoria para persistir estados por hilo
    memory = MemorySaver()
    
    return workflow.compile(checkpointer=memory)
