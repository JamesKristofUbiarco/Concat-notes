# ⚙️ Backend — Gestor Inteligente de Apuntes

API REST construida con **FastAPI** que orquesta el agente de IA (LangGraph), gestiona la persistencia en PostgreSQL con pgvector, y ejecuta un worker automático para procesamiento en segundo plano.

---

## Stack Tecnológico

| Tecnología | Versión | Propósito |
|-----------|---------|-----------|
| **FastAPI** | ≥0.136.3 | Framework web async con validación automática |
| **SQLAlchemy** | ≥2.0.50 | ORM para PostgreSQL |
| **Pydantic** | ≥2.13.4 | Validación de datos y schemas de entrada/salida |
| **LangGraph** | ≥1.2.2 | Orquestación del agente como grafo de estados |
| **LangChain** | ≥1.3.2 | Abstracciones para LLMs y mensajes |
| **langchain-google-genai** | ≥4.2.4 | Integración con Google Gemini (sintetizador) |
| **google-genai** | ≥0.1.1 | SDK oficial de Google para Gemini 3.6 Flash (análisis de imágenes) |
| **boto3** | ≥1.34.84 | SDK de AWS para Python (interacción con S3/RustFS) |
| **python-multipart** | ≥0.0.32 | Soporte de parsing de formularios multipart para FastAPI |
| **pgvector** | ≥0.4.2 | Extensión de SQLAlchemy para vectores |
| **psycopg[binary]** | ≥3.3.4 | Driver PostgreSQL (psycopg3) |
| **VoyageAI** | ≥0.3.7 | Generación de embeddings vectoriales (voyage-4) |
| **uvicorn** | ≥0.48.0 | Servidor ASGI |
| **python-dotenv** | ≥1.2.2 | Carga de variables de entorno |
| **Python** | ≥3.13 | Runtime |

---

## Estructura de Archivos

```
backend/
├── main.py                  # Punto de entrada: `uv run uvicorn app.main:app`
├── pyproject.toml           # Dependencias Python (gestionadas con uv)
├── .env.template            # Plantilla de variables de entorno
├── .env                     # Variables de entorno (no versionado)
├── scripts/
│   └── manage_db.py         # CLI de mantenimiento: backup, restore, import
├── backups/                 # Directorio de backups de DB (no versionado)
└── app/
    ├── __init__.py          # Inicialización del paquete
    ├── main.py              # FastAPI app, CORS, endpoints, lifespan del worker y settings de modelos
    ├── agent.py             # Grafo LangGraph, preprocesador de placeholders y Synapse Scholar
    ├── llm_models.py        # Catálogo, disponibilidad y resolución explícita Google/OpenRouter
    ├── table_ocr.py         # Módulo de extracción local de tablas por OCR y fusión de filas multilinea
    ├── worker.py            # Worker automático con disparador híbrido y análisis de imágenes
    ├── storage.py           # Cliente S3 (RustFS) e integrador dinámico de visión (Gemini/OpenRouter)
    ├── backup.py            # Funciones de respaldo y restauración en vivo (S3 y DB PostgreSQL)
    ├── glossary.py          # Lógica para la compilación de glosarios y flashcards
    ├── clean_glossaries.py  # Script de limpieza y unificación de términos de glosarios
    ├── models.py            # Modelos SQLAlchemy, incluido UserSetting
    ├── schemas.py           # Schemas Pydantic:NoteCreate, NoteUpdate, ModelOption, ModelSettingsResponse, etc.
    ├── crud.py              # Operaciones CRUD, reordenación y settings de persistencia de modelos de IA
    └── database.py          # Configuración SQLAlchemy + psycopg3
```

---

## Endpoints de la API

### Notas e Imágenes

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check del servicio |
| `POST` | `/api/notes` | Añadir nota cruda a la cola (`pending`) |
| `POST` | `/api/notes/images/upload` | Subir imagen de apoyo a RustFS |
| `POST` | `/api/notes/images/upload-table` | Subir imagen de tabla, ejecuta OCR local y genera Markdown |
| `GET` | `/api/notes/queue` | Listar notas pendientes |
| `GET` | `/api/notes/archive` | Listar notas procesadas |
| `GET` | `/api/notes/processed-since?since=ISO` | Notas procesadas después de un timestamp |
| `GET` | `/api/notes/{id}` | Detalle completo de una nota |
| `PUT` | `/api/notes/{id}` | Actualizar contenido de una nota |
| `DELETE` | `/api/notes/{id}` | Eliminar nota y relaciones en cascada |
| `POST` | `/api/notes/{id}/process` | Ejecutar procesamiento con agente IA (realiza análisis de imágenes con Gemini o MiniMax antes del agente) |

### Modelos de IA e Historial

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `GET` | `/api/settings/models` | Obtener selección, catálogo, disponibilidad y modelo/transporte efectivo por rol |
| `PUT` | `/api/settings/models` | Actualizar un rol; rechaza modelos cuyo proveedor no tenga credenciales |
| `GET` | `/api/courses` | Listar cursos con notas procesadas |
| `GET` | `/api/courses/{name}/notes` | Notas procesadas de un curso |
| `GET` | `/api/courses/{name}/markdown` | Markdown concatenado de un curso |
| `PUT` | `/api/courses/{name}/reorder` | Reordenar notas de un curso |
| `DELETE` | `/api/courses/{name}` | Eliminar el curso completo: notas, procesados, chunks/embeddings, glosario e imágenes |
| `GET` | `/api/courses/{name}/glossary` | Obtener el glosario generado del curso |
| `POST` | `/api/courses/{name}/glossary/compile` | Compilar/actualizar el markdown del glosario |
| `GET` | `/api/settings/flashcard-density` | Obtener la densidad objetivo de flashcards por clase |
| `GET` | `/api/flashcards` | Consultar la biblioteca con filtros y tarjetas pendientes |
| `GET` | `/api/flashcards/tree` | Jerarquía indexada de cursos y módulos |
| `PUT` | `/api/flashcards/{id}` | Editar o activar/desactivar una tarjeta conservando el Markdown |
| `POST` | `/api/flashcards/{id}/review` | Calificar un repaso y programar el siguiente |
| `POST` | `/api/flashcards/reindex` | Reconciliar el índice desde el Markdown preservando progreso |
| `GET` | `/api/flashcards/export/{csv|anki}` | Exportar CSV o paquete `.apkg` |
| `GET/PUT` | `/api/local-sync/config` | Configurar y verificar la raíz montada de Markdown |
| `GET/PUT` | `/api/local-sync/courses[/{name}]` | Consultar y activar cursos sincronizados |
| `POST` | `/api/local-sync/run` | Ejecutar reconciliación inmediata |
| `GET` | `/api/local-sync/courses/{name}/conflict` | Revisar cambios externos y su diferencia |
| `POST` | `/api/local-sync/courses/{name}/resolve` | Integrar o descartar cambios externos |
| `POST` | `/api/settings/flashcard-density` | Establecer la densidad de flashcards (ej. 5 por cada 10k chars) |

### Backup y Restauración

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `GET` | `/api/db/backup` | Iniciar copia de seguridad de la base de datos y RustFS |
| `POST` | `/api/db/restore` | Restaurar el sistema a partir de un archivo `.zip` de backup |

### Embeddings

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `GET` | `/api/embeddings/status` | Estado de embeddings (real vs. dummy) |
| `POST` | `/api/embeddings/reprocess-dummies` | Re-generar embeddings para chunks dummy |
| `GET` | `/api/knowledge/status` | Cobertura y errores de la memoria de conocimiento v2 |
| `GET/PUT` | `/api/settings/generation-pipeline` | Consultar o cambiar entre `legacy` y `v2` |

---

## Worker Automático

El backend incluye un worker asyncio (`worker.py`) registrado en el lifespan de FastAPI que procesa notas pendientes automáticamente:

- **Intervalo de chequeo**: cada 30 segundos
- **Umbral de volumen**: se activa con ≥3 notas pendientes
- **Timeout**: se activa si la nota más antigua tiene ≥10 minutos
- **Lock compartido**: `asyncio.Lock()` compartido con el endpoint manual

---

## Configuración

### Variables de Entorno

Copia `.env.template` a `.env` y configura:

| Variable | Requerida | Descripción |
|----------|-----------|-------------|
| `DATABASE_URL` | Sí | URL de conexión PostgreSQL |
| `PORT` | No | Puerto del servidor (default: 8000) |
| `GOOGLE_API_KEY` | No | API key de Google Gemini para procesamiento real y análisis de imágenes |
| `OPENROUTER_API_KEY` | No | API key de OpenRouter para Qwen, MiniMax y DeepSeek |
| `GEMINI_MODEL` | No | Modelo a usar para la nota sintetizada mediante OpenRouter (default: `google/gemini-3.6-flash`) |
| `VOYAGE_API_KEY` | No | API key de VoyageAI para embeddings reales |
| `RUSTFS_ENDPOINT_INTERNAL` | No | Endpoint S3 interno para conexión backend (default: `http://rustfs:9000` en Docker, `http://localhost:9000` en local) |
| `RUSTFS_ENDPOINT_EXTERNAL` | No | Endpoint S3 externo para que el navegador resuelva imágenes (default: `http://localhost:9000`) |
| `RUSTFS_ACCESS_KEY` | No | Nombre de usuario / access key de RustFS (default: `rustfs_admin`) |
| `RUSTFS_SECRET_KEY` | No | Contraseña / secret key de RustFS (default: `rustfs_password`) |
| `RUSTFS_BUCKET_NAME` | No | Nombre del bucket público (default: `notes-images`) |

### Selección de modelos

Las preferencias se guardan en `user_settings` y sobreviven a reconstrucciones de los contenedores mientras se conserve PostgreSQL. El resolvedor de `llm_models.py` usa OpenRouter como transporte para Gemini, Qwen, MiniMax y DeepSeek; las claves de Google pueden llegar a OpenRouter mediante BYOK. Si una credencial desaparece durante la ejecución, se registra el fallback efectivo; si no existe ningún proveedor disponible, los nodos conservan sus salidas locales de emergencia.

El rol `query_expansion`, presentado como **Modelo auxiliar** en la interfaz, genera las queries del RAG y también filtra el glosario y extrae entidades. No controla los embeddings: estos continúan usando VoyageAI `voyage-4`.

### Inicio Rápido

```bash
cd backend
cp .env.template .env
# Editar .env con tus API keys

# Iniciar servidor (instala dependencias automáticamente)
uv run uvicorn app.main:app --port 8000 --reload
```

La documentación interactiva Swagger estará disponible en [http://localhost:8000/docs](http://localhost:8000/docs).

---

## Script de Administración

`scripts/manage_db.py` proporciona tres comandos CLI:

```bash
# Backup de la base de datos
uv run python scripts/manage_db.py backup [-f ruta/custom.dump]

# Restaurar desde backup
uv run python scripts/manage_db.py restore -f backups/backup.dump

# Crear/reanudar la memoria v2 sin reescribir notas históricas
uv run python scripts/manage_db.py backfill-knowledge --all --resume --defer-embeddings --embedding-batch-size 64

# Importar notas Markdown desde un directorio
uv run python scripts/manage_db.py import -d /ruta/a/notas [--dry-run]
```
