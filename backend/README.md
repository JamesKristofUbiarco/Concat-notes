# Backend

API FastAPI que mantiene los contratos de Concat Notes, persiste el estado, orquesta los pipelines LangGraph y ejecuta el worker automático de notas. El parsing pesado de PDF/EPUB está aislado en `document-worker`.

## Componentes

| Archivo | Responsabilidad |
|---|---|
| `app/main.py` | Aplicación, lifespan, endpoints y CORS |
| `app/models.py` / `app/schemas.py` | Persistencia SQLAlchemy y contratos Pydantic |
| `app/crud.py` | CRUD, cursos, ajustes y persistencia |
| `app/worker.py` | Procesamiento automático de pendientes |
| `app/agent.py` / `app/v2_agent.py` | Grafos legacy y v2 |
| `app/knowledge.py` | Chunks, claims, embeddings y recuperación v2 |
| `app/llm_models.py` | Catálogo y resolución de modelos por rol |
| `app/storage.py` | RustFS y análisis de imágenes ordinarias |
| `app/documents.py` | Upload, selección, jobs, costes, borradores y confirmación documental |
| `app/local_sync.py` | Exportación/reconciliación local |
| `app/flashcards.py` | Índice, scheduler y exportaciones |
| `app/backup.py` | Backup/restauración de PostgreSQL y RustFS |
| `app/table_ocr.py` | OCR local de tablas manuales |

## Dominios de API

La referencia exacta está en `/docs`.

- `/api/notes*`: ciclo de vida, imágenes y procesamiento.
- `/api/courses*`: listado, orden, renombrado, borrado, Markdown y glosario.
- `/api/flashcards*`: biblioteca, estudio, reindexado y exportación.
- `/api/documents*` y `/api/document-jobs*`: PDF/EPUB.
- `/api/local-sync*`: configuración, directorios, cursos y conflictos.
- `/api/settings*`: estudio, densidad, modelos y pipeline.
- `/api/knowledge/status`, `/api/embeddings*`: memoria.
- `/api/db/backup`, `/api/db/restore`: administración.

## Procesamiento de notas

`user_settings.generation_pipeline_version` selecciona `legacy` o `v2`. El worker y el endpoint manual comparten el mecanismo de procesamiento. Si v2 falla antes de persistir, se usa legacy como fallback.

El worker consulta cada 30 segundos y procesa con tres pendientes o cuando la más antigua alcanza diez minutos. Un lock compartido evita ejecución duplicada. La evidencia vive en `raw_notes`; la salida pública queda en `processed_notes.structured_markdown`; memoria e índices son derivados reconstruibles.

## Modelos externos

Roles: `synthesis`, `query_expansion`, `image_analysis` y `document_vision`. OpenRouter transporta generación/visión; VoyageAI es independiente para embeddings. `GET /api/settings/models` muestra selección, disponibilidad y modelo efectivo.

Sin credenciales suficientes se usan rutas degradadas cuando existen. No debe presentarse el fallback local como equivalente a una síntesis LLM real.

## Documentos

`app/documents.py` valida y hashea el archivo, reutiliza duplicados, sube el original a RustFS, crea jobs, valida selección/presupuesto y confirma borradores como `raw_notes`. El backend no realiza el parsing pesado.

Límites: 100 MB, 1000 páginas PDF, rangos físicos sólo para PDF y autorización si la estimación remota supera USD 1. Los assets confirmados se enlazan sin duplicar el objeto RustFS.

## Variables de entorno

| Variable | Uso |
|---|---|
| `DATABASE_URL` | PostgreSQL |
| `OPENROUTER_API_KEY` | Generación y visión |
| `GOOGLE_API_KEY` | Disponibilidad/BYOK según modelos |
| `VOYAGE_API_KEY` | Embeddings reales |
| `GEMINI_MODEL` | Compatibilidad de selección inicial |
| `RUSTFS_ENDPOINT_INTERNAL`, `RUSTFS_ENDPOINT_EXTERNAL` | Acceso S3 interno y URL pública |
| `RUSTFS_ACCESS_KEY`, `RUSTFS_SECRET_KEY`, `RUSTFS_BUCKET_NAME` | RustFS |
| `LOCAL_SYNC_ROOT`, `LOCAL_SYNC_INTERVAL_SECONDS` | Sincronización |

No versionar `backend/.env` ni imprimir secretos.

## Desarrollo y administración

```bash
cd backend
uv sync --frozen
uv run uvicorn app.main:app --reload --port 8000
uv run python -m unittest discover -s tests -q

uv run python scripts/manage_db.py backup
uv run python scripts/manage_db.py import -d /ruta/a/notas --dry-run
uv run python scripts/manage_db.py backfill-knowledge --all --resume --defer-embeddings --embedding-batch-size 64
```

Antes de restaurar o migrar datos existentes, crear un backup. Los scripts de `/docker-entrypoint-initdb.d` sólo corren cuando el volumen nace vacío.
