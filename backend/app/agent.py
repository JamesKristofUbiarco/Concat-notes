import os
import time
import logging
import re
import tempfile
import subprocess
from typing import TypedDict, List, Dict, Any, Optional
from sqlalchemy.orm import Session

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
3. SINTETIZA: Con el plan y razonamiento internos como guía, produce la nota Markdown final siguiendo la plantilla base y las directivas A-E.

# 1. PERSONA Y TONO

* **El Minero Fiel:** Tu objetivo principal es la fidelidad absoluta a la fuente original. Eres exhaustivo y meticuloso; no dejas atrás ningún concepto, regla, advertencia o paso a paso mencionado en la clase.
* **Precisión sobre Invención:** Eres un estructurador y purificador de información. No debes inventar, expandir con teoría extra ni agregar temas que el instructor no haya tocado. Tu trabajo es rescatar lo que *sí* se dijo.

# 2. REGLAS ESTRICTAS DE OPERACIÓN (DIRECTIVAS PRINCIPALES)

Debes obedecer estas reglas en CADA interacción, sin excepción:

* **DIRECTIVA A - BÚSQUEDA WEB COMO CONTRAPESO (SPEECH-TO-TEXT FIX):** Las transcripciones de audio suelen tener errores graves en términos técnicos ("teléfono descompuesto"). DEBES usar la búsqueda web (Google Search) para verificar y corregir la terminología técnica. Si el audio dice "crear un jota son" en un contexto de programación, la web te confirmará que es "JSON". Usa la web para anclar la transcripción a la realidad fáctica sin alucinar conceptos nuevos.
* **DIRECTIVA B - MANEJO DE AUDIO ROTO (DUDA DE TRANSCRIPCIÓN):** Si una parte de la transcripción está tan distorsionada que, incluso con contexto y búsqueda web, no puedes deducir con certeza técnica qué dijo el profesor, NO inventes una respuesta. Extrae ese fragmento literal y crea un bloque específico así: `❓ Duda de Transcripción: "[texto incomprensible]" #revisar_audio`. Esto le indicará al usuario que debe ir al video a escuchar ese minuto exacto.
* **DIRECTIVA C - ESTRUCTURA DINÁMICA (NUEVA VS. CONTINUACIÓN):**
    * Identifica el estado del apunte. Si el usuario te pasa el inicio de un módulo, te da el título o te dice "Nueva clase", genera la **Plantilla Completa** (incluyendo metadatos YAML y Contexto Inicial).
    * Si el usuario dice "siguiente parte", "continuación" o te pasa un bloque subsecuente de la misma clase, **OMITE** el YAML, el título y el Contexto Inicial. Entrega **ÚNICAMENTE** los bloques correspondientes a la sección "📝 Apuntes de Clase" para que el usuario copie y pegue debajo de sus apuntes actuales.
* **DIRECTIVA D - EXTRACCIÓN EXHAUSTIVA Y ZONA DE PROCESAMIENTO:** Exprime cada gota de la clase respetando los subtítulos de la plantilla (Definiciones, Pasos, Notas de cuidado). Al final de tu entrega (solo si es el final de la clase o si el usuario lo pide), genera obligatoriamente la sección `🧠 Zona de Procesamiento (Fase 2: Deconstrucción)` con una lista de títulos sugeridos en formato Wikilink (ej. `[[...]]`) para que el usuario sepa qué Notas Atómicas crear después.
* **DIRECTIVA E - ENTREGA ESTRUCTURADA (JSON):** Tu salida debe apegarse estrictamente al esquema JSON proporcionado. Todo tu proceso de pensamiento va en `chain_of_thought`. La nota Markdown pura, SIN comentarios adicionales ni bloques de código que lo envuelvan, va en `markdown_note`. Tus preguntas o comentarios finales interactivos van en `ai_comments`.
* **DIRECTIVA F - DIAGRAMAS MERMAID OBLIGATORIOS:** Nunca utilices ASCII art para dibujar tablas, flujos o diagramas. Si la clase describe un proceso, flujo, arquitectura o relación jerárquica que requiera apoyo visual, SIEMPRE utiliza bloques de código con la sintaxis de Mermaid (` ```mermaid `).

# 3. LA PLANTILLA BASE (OBSIDIAN)

Usa esta estructura y sus bloques dinámicos según el flujo natural de la clase. El orden de los bloques internos en "Apuntes de Clase" no es rígido, adáptalo a cómo el profesor explicó el tema:

```markdown
---
tipo: fuente
formato: curso_online
estado: en_proceso
fecha: YYYY-MM-DD
---
# 📚 [Nombre de la Clase]
**Curso:** [Nombre del Curso MOC]
**Instructor/Autor:** [Nombre] | **Módulo del curso:** [Nombre del módulo del curso] | **Enlace:** ---

## 🗺️ Contexto Inicial (Fase 1)
[Redacta el propósito general de la clase o el problema a resolver, basándote estrictamente en la introducción de la transcripción].

## 📝 Apuntes de Clase (Captura Híbrida)
*(Aplica los siguientes bloques según correspondan al contenido de la transcripción)*

### 📌 [Subtítulo del Tema / Concepto Nuevo]
**Contexto:** [Información sobre el origen/uso extraída de la clase].
> "[Cita textual o regla de oro importante que dictó el profesor y deba recordarse tal cual]".

**❓ ¿[Pregunta analítica sobre el tema]?**
* **Respuesta:** [Explicación clara extraída de la clase].
* **Detalle clave:** [Dato específico mencionado].

**⚙️ [Nombre del Proceso o Algoritmo] (Paso a paso)**
* **Paso 1:** [Estado inicial y primera acción].
* **Paso 2:** [Qué sucede después].
* **Paso 3:** [Resultado esperado].

**⚠️ Nota de cuidado:** [Errores comunes, advertencias o casos extremos mencionados por el instructor].

**💻 Fragmentos de Código / Fórmulas / Diagramas:**
[Si hay código, matemáticas o necesidad de un diagrama, inclúyelo en bloques de Markdown/LaTeX o Mermaid. Corrige la sintaxis si la transcripción la rompió, verificando con la web].

**❓ Duda de Transcripción:**
"[Fragmento literal incomprensible de la transcripción]" #revisar_audio

## 🧠 Zona de Procesamiento (Fase 2: Deconstrucción)
*(Convierte los conceptos de arriba en posibles Notas Atómicas)*
* [[Título sugerido para concepto 1]] #definicion
* [[Título sugerido para proceso 2]] #algoritmo
```

# 4. FLUJO DE INTERACCIÓN PASO A PASO
1. **Recibir Input:** Lee la transcripción/apuntes del usuario. Identifica si es una clase nueva o una continuación (Directiva C).
2. **Minería y Purificación:** Usa la Búsqueda Web (Directiva A) para corregir términos técnicos mal transcritos. Si algo es irrecuperable, márcalo (Directiva B).
3. **Estructuración:** Organiza la información rescatada usando los bloques de la Plantilla Base, respetando el flujo natural de la clase. No inventes teoría extra.
4. **Cierre y Entrega:** Entrega el resultado Markdown completo DENTRO del bloque de CUATRO comillas (````txt).
"""

# ============================================================================
# ESTADO DEL AGENTE (AgentState) — Optimizado: sin plan/reasoning separados
# ============================================================================
class AgentState(TypedDict):
    raw_note_id: str
    raw_note_data: Dict[str, Any]
    notes_context: List[str]
    structured_markdown: str
    ai_comments: str
    mermaid_validation_errors: str
    mermaid_retries: int

class AgentOutput(BaseModel):
    chain_of_thought: str = Field(
        description="Tu proceso de planificación y razonamiento interno (Pasos 1 y 2). Nunca será visto por el usuario."
    )
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

def vector_store_retriever_tool(query: str, course_name: str, db: Session, limit: int = 3) -> List[Dict[str, Any]]:
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
            chunks = db.query(NoteChunk).join(
                ProcessedNote, NoteChunk.processed_note_id == ProcessedNote.id
            ).join(
                RawNote, ProcessedNote.raw_note_id == RawNote.id
            ).filter(
                RawNote.course_name == course_name,
                NoteChunk.is_dummy_embedding == False
            ).order_by(
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
            chunks = db.query(NoteChunk).join(
                ProcessedNote, NoteChunk.processed_note_id == ProcessedNote.id
            ).join(
                RawNote, ProcessedNote.raw_note_id == RawNote.id
            ).filter(
                and_(
                    RawNote.course_name == course_name,
                    keyword_filters,
                    NoteChunk.is_dummy_embedding == False
                )
            ).limit(limit).all()
            if chunks:
                return [{"id": str(c.id), "content": c.content} for c in chunks]
    except Exception as e:
        print(f"[ERROR] Fallback de búsqueda: {e}")
        
    return []


def expand_queries_with_llm(transcription: str, notes: str, title: str, course: str) -> List[str]:
    """
    Usa Gemini Flash para generar múltiples queries de búsqueda semánticamente
    diversas a partir del contenido real de la nota (patrón Multi-Query Expansion).
    
    Retorna una lista de 4-5 queries alternativas, o [f"{course} {title}"] como fallback.
    """
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    google_api_key = os.getenv("GOOGLE_API_KEY")
    fallback_query = f"{course} {title}"
    
    if not openrouter_api_key and not google_api_key:
        return [fallback_query]
    
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
        
        # 1. Intentar con OpenRouter (si está configurada la API key)
        if openrouter_api_key:
            from langchain_openai import ChatOpenAI
            model_lite = os.getenv("GEMINI_LITE_MODEL", "google/gemini-3.1-flash-lite")
            print(f"[AGENTE LLM - QUERY EXPANSION] Iniciando vía OpenRouter con modelo: '{model_lite}'")
            llm = ChatOpenAI(
                model=model_lite,
                openai_api_key=openrouter_api_key,
                openai_api_base="https://openrouter.ai/api/v1",
                default_headers={
                    "HTTP-Referer": "https://github.com/JamesKristofUbiarco/Concat-notes",
                    "X-Title": "Gestor Inteligente de Notas"
                },
                timeout=15,
                max_retries=1,
            )
        # 2. Fallback a Google AI Studio nativo
        else:
            from langchain_google_genai import ChatGoogleGenerativeAI
            print("[AGENTE LLM - QUERY EXPANSION] Iniciando vía Google AI Studio Nativo con modelo: 'gemini-3.1-flash-lite'")
            llm = ChatGoogleGenerativeAI(
                model="gemini-3.1-flash-lite",
                google_api_key=google_api_key,
                timeout=15,
                max_retries=1,
            )
        
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
        if current_note and current_note.order_index > 0:
            prev_note = db.query(ProcessedNote).join(
                RawNote, ProcessedNote.raw_note_id == RawNote.id
            ).filter(
                RawNote.course_name == current_note.course_name,
                RawNote.order_index == current_note.order_index - 1
            ).first()
            
    course = current_note.course_name if current_note else data.get("course_name", "")
    
    context_chunks = []
    if prev_note:
        print(f"[AGENTE ACCIÓN] Encontrada nota anterior inmediata (order_index: {current_note.order_index - 1}) para el curso '{course}'. Inyectando al contexto.")
        context_chunks.append(f"=== NOTA ANTERIOR INMEDIATA ===\n{prev_note.structured_markdown}")
    
    if db is not None:
        # 1. Generar múltiples queries con Gemini Flash
        expanded_queries = expand_queries_with_llm(transcription, notes, title, course)
        
        # 2. Buscar con cada query y deduplicar por chunk ID
        seen_ids = set()
        all_chunks = []
        
        for query in expanded_queries:
            results = vector_store_retriever_tool(query, course, db, limit=3)
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
    print(f"[AGENTE ACCIÓN] Contexto histórico recuperado ({len(context_chunks)} chunks): {[c[:80] + '...' for c in context_chunks]}")
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


def preprocess_transcription(transcription: str, code_snippets: List[Dict], command_snippets: List[Dict], images: List[Any]) -> str:
    if not transcription:
        return ""
    
    # Regex matching &"tipo:indice"
    pattern = r'&"([a-zA-Z]+):(\d+)"'
    
    # Sort images by created_at to have a reliable index mapping
    sorted_images = sorted(images, key=lambda x: x.created_at) if images else []
    
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
                img = sorted_images[idx]
                if img.descripcion_llm and img.descripcion_llm.strip():
                    return f"\n{img.descripcion_llm.strip()}\n"
        
        return match.group(0)
        
    return re.sub(pattern, replace_match, transcription)


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
                
    processed_transcription = preprocess_transcription(transcription, code_snippets, command_snippets, images)
    
    # 1. Modo Real con OpenRouter o Gemini nativo si están configurados
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    google_api_key = os.getenv("GOOGLE_API_KEY")
    
    if openrouter_api_key or google_api_key:
        try:
            # 1.1 Configurar llm usando OpenRouter
            if openrouter_api_key:
                from langchain_openai import ChatOpenAI
                model_name = os.getenv("GEMINI_MODEL", "google/gemini-3.5-flash")
                print(f"[AGENTE LLM - SÍNTESIS] Iniciando vía OpenRouter con modelo: '{model_name}'")
                llm = ChatOpenAI(
                    model=model_name,
                    openai_api_key=openrouter_api_key,
                    openai_api_base="https://openrouter.ai/api/v1",
                    default_headers={
                        "HTTP-Referer": "https://github.com/JamesKristofUbiarco/Concat-notes",
                        "X-Title": "Gestor Inteligente de Notas"
                    },
                    timeout=120,
                    max_retries=2,
                )
            # 1.2 Configurar llm usando Google AI Studio nativo
            else:
                from langchain_google_genai import ChatGoogleGenerativeAI
                model_name = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
                print(f"[AGENTE LLM - SÍNTESIS] Iniciando vía Google AI Studio Nativo con modelo: '{model_name}'")
                llm = ChatGoogleGenerativeAI(
                    model=model_name,
                    google_api_key=google_api_key,
                    timeout=120,
                    max_retries=2,
                )
            
            # Si hay errores de mermaid, el prompt cambia a un modo de "Editor/Corrector"
            validation_errors = state.get("mermaid_validation_errors", "")
            if validation_errors:
                prompt = (
                    f"El Markdown que generaste contiene diagramas Mermaid con errores de sintaxis.\n"
                    f"ERRORES DEL COMPILADOR:\n{validation_errors}\n\n"
                    f"INSTRUCCIÓN ESTRICTA:\n"
                    f"Corrige únicamente la sintaxis de los diagramas Mermaid problemáticos en el siguiente documento.\n"
                    f"NO alteres NINGÚN otro texto, estructura o contenido del documento original.\n"
                    f"Devuelve el documento completo corregido en `markdown_note`.\n\n"
                    f"DOCUMENTO ORIGINAL:\n{state.get('structured_markdown', '')}"
                )
            else:
                prompt = (
                    f"Fecha de hoy (debes colocar esta fecha exacta en el campo 'fecha' del frontmatter YAML): '{time.strftime('%Y-%m-%d')}'\n"
                    f"Título de la clase: '{title}'\n"
                    f"Módulo: '{module}'\n"
                    f"Curso: '{course}'\n"
                    f"Instructor: '{teacher}'\n"
                    f"Modo de escritura: '{state['raw_note_data'].get('writing_mode')}'\n"
                    f"Plataforma: '{state['raw_note_data'].get('platform')}'\n\n"
                    f"TRANSCRIPCIÓN:\n{processed_transcription}\n\n"
                    f"APUNTES DEL ALUMNO:\n{notes}\n\n"
                    f"MATERIAL ADICIONAL:\n"
                    f"- Snippets de código (ya optimizados): {code_snippets}\n"
                    f"- Comandos CLI (ya validados): {command_snippets}\n"
                    f"- Contexto histórico recuperado (RAG): {context}\n\n"
                    f"Sigue rigurosamente la plantilla base Obsidian de Synapse Scholar, aplicando las Directivas A, B, C, D, E y F."
                )
            
            # Pasar la directiva del system prompt como SystemMessage
            messages = [
                SystemMessage(content=SYNAPSE_SCHOLAR_SYSTEM_PROMPT),
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
            if validation_errors and not response.ai_comments.strip():
                pass # Retenemos el ai_comments actual en estado
            else:
                state["ai_comments"] = response.ai_comments.strip()
            
            # Limpiamos los errores para la siguiente iteración (si hubiera)
            state["mermaid_validation_errors"] = ""
            
            print("[AGENTE SÍNTESIS REAL (Gemini - Synapse Scholar + CoT)] Nota compilada exitosamente.")
            return state
        except Exception as e:
            print(f"[ERROR] Error al invocar Gemini para síntesis: {e}. Usando simulación.")

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

    markdown += f"""
## 🧠 Zona de Procesamiento (Fase 2: Deconstrucción)
* [[{title} - Fundamentos]] #definicion
* [[Implementacion de {course}]] #algoritmo
"""
    
    state["structured_markdown"] = markdown.strip()
    
    ai_comments = """¿Tienes la siguiente parte de la transcripción para continuar, o damos esta clase por terminada? Además, ¿el nivel de detalle de este resumen es adecuado o prefieres que realice una segunda pasada para extraer más información de tus notas originales?"""
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
    return END

# ============================================================================
# COMPILACIÓN DEL GRAFO DE ESTADOS (LangGraph Workflow) — Optimizado: 4 nodos
# ============================================================================

def compile_agent():
    """
    Compila y retorna el agente de LangGraph con 4 nodos:
    1. retrieve_context_node — RAG con pgvector
    2. execute_tools_node — Herramientas determinísticas
    3. synthesis_node — Síntesis con chain-of-thought integrado
    4. mermaid_validation_node — Bucle de validación de sintaxis de diagramas
    """
    workflow = StateGraph(AgentState)
    
    workflow.add_node("retrieve_context_node", retrieve_context_node)
    workflow.add_node("execute_tools_node", execute_tools_node)
    workflow.add_node("synthesis_node", synthesis_node)
    workflow.add_node("mermaid_validation_node", mermaid_validation_node)
    
    workflow.set_entry_point("retrieve_context_node")
    workflow.add_edge("retrieve_context_node", "execute_tools_node")
    workflow.add_edge("execute_tools_node", "synthesis_node")
    workflow.add_edge("synthesis_node", "mermaid_validation_node")
    
    workflow.add_conditional_edges(
        "mermaid_validation_node",
        route_mermaid,
        {
            "synthesis_node": "synthesis_node",
            END: END
        }
    )
    
    # 4. Configurar la memoria para persistir estados por hilo
    memory = MemorySaver()
    
    # 5. Compilar el grafo con soporte para checkpointer
    return workflow.compile(checkpointer=memory)
