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
| **langchain-google-genai** | ≥4.2.4 | Integración con Google Gemini |
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
    ├── main.py              # FastAPI app, CORS, endpoints, lifespan del worker
    ├── agent.py             # Grafo LangGraph: 4 nodos, Synapse Scholar, tools
    ├── worker.py            # Worker automático con disparador híbrido
    ├── models.py            # Modelos SQLAlchemy: RawNote, ProcessedNote, NoteChunk
    ├── schemas.py           # Schemas Pydantic: NoteCreate, NoteUpdate, responses
    ├── crud.py              # Operaciones CRUD + archive + reorder
    └── database.py          # Configuración SQLAlchemy + psycopg3
```

---

## Endpoints de la API

### Notas

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check del servicio |
| `POST` | `/api/notes` | Añadir nota cruda a la cola (`pending`) |
| `GET` | `/api/notes/queue` | Listar notas pendientes |
| `GET` | `/api/notes/archive` | Listar notas procesadas |
| `GET` | `/api/notes/processed-since?since=ISO` | Notas procesadas después de un timestamp |
| `GET` | `/api/notes/{id}` | Detalle completo de una nota (incluye processed_note) |
| `PUT` | `/api/notes/{id}` | Actualizar contenido de una nota |
| `DELETE` | `/api/notes/{id}` | Eliminar nota y relaciones en cascada |
| `POST` | `/api/notes/{id}/process` | Ejecutar procesamiento con agente IA |

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
| `GOOGLE_API_KEY` | No | API key de Google Gemini para procesamiento real |
| `GEMINI_MODEL` | No | Modelo a usar (default: `gemini-3.5-flash`) |
| `VOYAGE_API_KEY` | No | API key de VoyageAI para embeddings reales |

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
