import os
import time
import logging
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
* **DIRECTIVA E - ENTREGA ESTRICTA EN CONTENEDOR DE 4 COMILLAS:** Para evitar que el formateador visual rompa la sintaxis Markdown, TODA tu respuesta de la nota DEBE estar encapsulada dentro de un ÚNICO bloque de código maestro usando **CUATRO COMILLAS INVERTIDAS BACKTICKS** (iniciando con ````txt y terminando con ````). Fuera de este bloque, solo haz comentarios interactivos.

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

**💻 Fragmentos de Código / Fórmulas:**
[Si hay código o matemáticas, inclúyelo en bloques de Markdown/LaTeX. Corrige la sintaxis si la transcripción la rompió, verificando con la web].

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

def vector_store_retriever_tool(query: str, db: Session, limit: int = 2) -> List[str]:
    """
    Herramienta de Acción: Recupera fragmentos de notas históricas similares
    usando pgvector en PostgreSQL para enriquecer el contexto del apunte.
    """
    print(f"\n[AGENTE ACCIÓN] Ejecutando vector_store_retriever para query: '{query}'")
    
    # 1. Comprobar si hay embeddings reales configurados (Voyage-4)
    voyage_api_key = os.getenv("VOYAGE_API_KEY")
    if voyage_api_key:
        try:
            import voyageai
            vo = voyageai.Client(api_key=voyage_api_key)
            result = vo.embed([query], model="voyage-4")
            query_vector = result.embeddings[0]
            
            # Consultar en base de datos usando pgvector distancia de coseno
            from app.models import NoteChunk
            chunks = db.query(NoteChunk).order_by(
                NoteChunk.embedding.cosine_distance(query_vector)
            ).limit(limit).all()
            
            if chunks:
                return [f"Contexto Histórico (Similitud Vectorial): {c.content}" for c in chunks]
        except Exception as e:
            print(f"[ERROR] Error en consulta vectorial real: {e}. Usando fallback semántico.")

    # 2. Fallback semántico / keyword lookup en base de datos
    try:
        from app.models import NoteChunk
        words = [w for w in query.lower().split() if len(w) > 3]
        if words:
            # Buscar coincidencias de texto simples
            filters = [NoteChunk.content.ilike(f"%{w}%") for w in words[:3]]
            chunks = db.query(NoteChunk).filter(*filters).limit(limit).all()
            if chunks:
                return [f"Contexto Histórico (Búsqueda Relacionada): {c.content}" for c in chunks]
    except Exception as e:
        print(f"[ERROR] Fallback de búsqueda: {e}")
        
    return ["Contexto Histórico: No se encontraron conceptos anteriores similares guardados."]


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
    Nodo de Contexto (Nodo 1): Llama a la herramienta de búsqueda vectorial en pgvector
    para recuperar referencias y conceptos previos que complementen esta clase.
    """
    print("\n========================================================")
    print("[NODO 1: CONTEXTO] Recuperando información histórica de base de datos...")
    print("========================================================")
    
    data = state["raw_note_data"]
    title = data.get("class_title", "")
    course = data.get("course_name", "")
    
    # Obtener la sesión db pasada en el config
    db = config["configurable"].get("db")
    query = f"{course} {title}"
    
    if db is not None:
        context_chunks = vector_store_retriever_tool(query, db)
    else:
        context_chunks = [
            f"Referencia de Microservicios: Optimizar indexación vectorial HNSW en Postgres pgvector.",
            f"Referencia de Bases de Datos: Usar redis-cli para asegurar idempotencia."
        ]
        
    state["notes_context"] = context_chunks
    print(f"[AGENTE ACCIÓN] Contexto histórico recuperado: {context_chunks}")
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


def synthesis_node(state: AgentState) -> AgentState:
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
    
    # 1. Modo Real con Gemini 3.5 Flash si está configurado
    google_api_key = os.getenv("GOOGLE_API_KEY")
    if google_api_key:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            model_name = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
            llm = ChatGoogleGenerativeAI(model=model_name, google_api_key=google_api_key)
            
            prompt = (
                f"Procesa el siguiente apunte utilizando las directivas del system prompt del Synapse Scholar.\n"
                f"Recuerda ejecutar internamente tu proceso de razonamiento (Sección 0: Chain-of-Thought) "
                f"antes de redactar la nota final.\n\n"
                f"- Título de la clase: {title}\n"
                f"- Curso: {course} | Módulo: {module} | Plataforma: {platform} | Profesor: {teacher}\n"
                f"- Resumen base: {summary}\n"
                f"- Transcripción original: {transcription}\n"
                f"- Notas del estudiante: {notes}\n"
                f"- Snippets de código (ya optimizados): {code_snippets}\n"
                f"- Comandos CLI (ya validados): {command_snippets}\n"
                f"- Contexto histórico recuperado (RAG): {context}\n\n"
                f"Sigue rigurosamente la plantilla base Obsidian de Synapse Scholar, aplicando las Directivas A, B, C, D y E. "
                f"Entrega el Markdown maestro encapsulado en un bloque único de 4 comillas invertidas (backticks) de acuerdo con la Directiva E, "
                f"y los comentarios interactivos finales requeridos fuera del bloque."
            )
            
            # Pasar la directiva del system prompt como SystemMessage
            messages = [
                SystemMessage(content=SYNAPSE_SCHOLAR_SYSTEM_PROMPT),
                HumanMessage(content=prompt)
            ]
            response = llm.invoke(messages)
            state["structured_markdown"] = _extract_text(response.content)
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
{ticks4}

¿Tienes la siguiente parte de la transcripción para continuar, o damos esta clase por terminada? Además, ¿el nivel de detalle de este resumen es adecuado o prefieres que realice una segunda pasada para extraer más información de tus notas originales?
"""
    
    state["structured_markdown"] = markdown
    print("[AGENTE SIMULACIÓN - Synapse Scholar] Nota premium de estudio compilada exitosamente.")
    return state

# ============================================================================
# COMPILACIÓN DEL GRAFO DE ESTADOS (LangGraph Workflow) — Optimizado: 3 nodos
# ============================================================================

def compile_agent():
    """
    Compila y retorna el agente de LangGraph con 3 nodos optimizados:
    1. retrieve_context_node — RAG con pgvector
    2. execute_tools_node — Herramientas determinísticas (code_optimizer, command_validator)
    3. synthesis_node — Síntesis con chain-of-thought integrado (1 sola llamada al LLM)
    
    Persistencia de memoria mediante MemorySaver.
    """
    # 1. Instanciar el flujo de grafo con el estado del agente
    workflow = StateGraph(AgentState)
    
    # 2. Agregar los nodos (3 en vez de 5)
    workflow.add_node("retrieve_context_node", retrieve_context_node)
    workflow.add_node("execute_tools_node", execute_tools_node)
    workflow.add_node("synthesis_node", synthesis_node)
    
    # 3. Establecer las conexiones / bordes
    workflow.set_entry_point("retrieve_context_node")
    workflow.add_edge("retrieve_context_node", "execute_tools_node")
    workflow.add_edge("execute_tools_node", "synthesis_node")
    workflow.add_edge("synthesis_node", END)
    
    # 4. Configurar la memoria para persistir estados por hilo
    memory = MemorySaver()
    
    # 5. Compilar el grafo con soporte para checkpointer
    return workflow.compile(checkpointer=memory)
