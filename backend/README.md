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
| **google-genai** | ≥0.1.1 | SDK oficial de Google para Gemini 3.5 Flash (análisis de imágenes) |
| **boto3** | ≥1.34.84 | SDK de AWS para Python (interacción con S3/MinIO) |
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
    ├── main.py              # FastAPI app, CORS, endpoints (incluye upload de imagen), lifespan del worker
    ├── agent.py             # Grafo LangGraph: 4 nodos, preprocesador de placeholders, tools, Synapse Scholar
    ├── worker.py            # Worker automático con disparador híbrido y análisis de imágenes
    ├── storage.py           # Cliente S3 (MinIO) e integrador con Gemini 3.5 Flash (Base64)
    ├── models.py            # Modelos SQLAlchemy: RawNote, ProcessedNote, NoteChunk, RawNoteImage, StudyLog, UserSetting
    ├── schemas.py           # Schemas Pydantic: NoteCreate, NoteUpdate, ImageSnippetBase, responses
    ├── crud.py              # Operaciones CRUD + asociación y cascada de imágenes + reorder
    └── database.py          # Configuración SQLAlchemy + psycopg3
```

---

## Endpoints de la API

### Notas e Imágenes

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check del servicio |
| `POST` | `/api/notes` | Añadir nota cruda a la cola (`pending`) |
| `POST` | `/api/notes/images/upload` | Subir imagen de apoyo a MinIO (retorna URL y metadatos) |
| `GET` | `/api/notes/queue` | Listar notas pendientes |
| `GET` | `/api/notes/archive` | Listar notas procesadas |
| `GET` | `/api/notes/processed-since?since=ISO` | Notas procesadas después de un timestamp |
| `GET` | `/api/notes/{id}` | Detalle completo de una nota (incluye processed_note e imágenes) |
| `PUT` | `/api/notes/{id}` | Actualizar contenido de una nota y sincronizar imágenes |
| `DELETE` | `/api/notes/{id}` | Eliminar nota y relaciones en cascada (incluyendo imágenes físicas de MinIO) |
| `POST` | `/api/notes/{id}/process` | Ejecutar procesamiento con agente IA (realiza análisis de imágenes con Gemini 3.5 Flash antes del agente) |

### Cursos

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `GET` | `/api/courses` | Listar cursos con notas procesadas |
| `GET` | `/api/courses/{name}/notes` | Notas procesadas de un curso |
| `GET` | `/api/courses/{name}/markdown` | Markdown concatenado de un curso |
| `PUT` | `/api/courses/{name}/reorder` | Reordenar notas de un curso |

### Embeddings

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `GET` | `/api/embeddings/status` | Estado de embeddings (real vs. dummy) |
| `POST` | `/api/embeddings/reprocess-dummies` | Re-generar embeddings para chunks dummy |

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
| `GEMINI_MODEL` | No | Modelo a usar para la nota sintetizada (default: `gemini-3.5-flash`) |
| `VOYAGE_API_KEY` | No | API key de VoyageAI para embeddings reales |
| `MINIO_ENDPOINT_INTERNAL` | No | Endpoint S3 interno para conexión backend (default: `http://minio:9000` en Docker, `http://localhost:9000` en local) |
| `MINIO_ENDPOINT_EXTERNAL` | No | Endpoint S3 externo para que el navegador resuelva imágenes (default: `http://localhost:9000`) |
| `MINIO_ACCESS_KEY` | No | Nombre de usuario / access key de MinIO (default: `minio_admin`) |
| `MINIO_SECRET_KEY` | No | Contraseña / secret key de MinIO (default: `minio_password`) |
| `MINIO_BUCKET_NAME` | No | Nombre del bucket público (default: `notes-images`) |

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

# Importar notas Markdown desde Obsidian
uv run python scripts/manage_db.py import -d /ruta/a/notas [--dry-run]
```
