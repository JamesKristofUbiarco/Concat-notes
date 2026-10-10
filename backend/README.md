# Backend

API FastAPI que mantiene los contratos de Concat Notes, persiste el estado, orquesta los pipelines LangGraph y ejecuta el worker automático de notas. El parsing pesado de PDF/EPUB está aislado en `document-worker`.

Estado verificado: 10 de octubre de 2026. Python 3.13+; dependencias bloqueadas en `uv.lock`.

## Componentes

| Archivo | Responsabilidad |
|---|---|
| `app/main.py` | Aplicación, lifespan, endpoints y CORS |
| `app/models.py` / `app/schemas.py` | Persistencia SQLAlchemy y contratos Pydantic |
| `app/crud.py` | CRUD, cursos, ajustes y persistencia |
| `app/worker.py` | Procesamiento automático de pendientes |
| `app/regeneration.py` / `app/maintenance_routes.py` | Jobs selectivos y mantenimiento RAG |
| `app/generation_runtime.py` / `app/evidence_inputs.py` | Streaming, presupuestos, métricas y referencias literales |
| `app/reference_checks.py` | Referencias temáticas limitadas, no verificador universal |
| `app/agent.py` / `app/v2_agent.py` | Grafos legacy y v2 |
| `app/knowledge.py` | Chunks, claims, embeddings y recuperación v2 |
| `app/llm_models.py` | Catálogo y resolución de modelos por rol |
| `app/storage.py` | RustFS y análisis de imágenes ordinarias |
| `app/documents.py` | Upload, selección, jobs, costes, borradores y confirmación documental |
| `app/local_sync.py` | Exportación/reconciliación local |
| `app/flashcards.py` | Índice, scheduler y exportaciones |
| `app/structured_notes.py` | Contrato Cornell, renderer, revisiones y patches |
| `app/structured_routes.py` | API del workspace, colecciones, chat y candidatas |
| `app/global_agent.py` / `app/global_agent_routes.py` / `app/agent_workspace.py` | Chat global, herramientas acotadas y propuestas transaccionales |
| `app/reading_order.py` / `app/note_sections.py` | Orden Cornell→Markdown y separación segura de suplementos |
| `app/backup.py` | Backup/restauración de PostgreSQL y RustFS |
| `app/table_ocr.py` | OCR local de tablas manuales |

## Dominios de API

La referencia exacta está en `/docs`.

- `/api/notes*`: ciclo de vida, imágenes y procesamiento.
- `/api/note-documents*`, `/api/note-edit-sessions*` y `/api/note-patch-proposals*`: editor Cornell versionado.
- `/api/courses*`: listado, orden, renombrado, borrado, Markdown y glosario.
- `/api/flashcards*`: biblioteca, estudio, reindexado y exportación.
- `/api/documents*` y `/api/document-jobs*`: PDF/EPUB.
- `/api/local-sync*`: configuración, directorios, cursos y conflictos.
- `/api/settings*`: estudio, densidad, modelos y pipeline.
- `/api/knowledge/status`, `/api/embeddings*`: memoria.
- `/api/rag*`, `/api/regeneration/jobs`: índices derivados y regeneraciones.
- `/api/agent*`: conversaciones, mensajes, cancelación y propuestas.
- `/api/db/backup`, `/api/db/restore`: administración.

## Procesamiento de notas

`user_settings.generation_pipeline_version` selecciona `legacy` o `v2`. El worker y el endpoint manual comparten `generate_note_state`. Un fallo v2 se propaga: no dispara legacy automáticamente ni guarda una nota de simulación. La regeneración selectiva usa v2.

El worker consulta cada 30 segundos y procesa con tres pendientes o cuando la más antigua alcanza diez minutos. Un lock compartido evita ejecución duplicada. La evidencia vive en `raw_notes`. Para notas Cornell, `structured_note_documents.document_json` es la fuente editable y `processed_notes.structured_markdown` queda como proyección compatible; memoria e índices son derivados reconstruibles.

V2 construye evidencia/novedad, Class Knowledge Model y cobertura, redacta Markdown clásico, valida presentación, repara Mermaid y genera suplementos en paralelo. No tiene un nodo Critic separado ni usa la antigua Metodología de composición. El documento/revisión compatible se obtiene al persistir. Véase [arquitectura](../docs/agent-architecture.md).

El lifespan inicia cuatro tareas: cola automática, sincronización, regeneraciones y agente global. La extracción documental corre en otro contenedor. Los locks y tareas activas son locales al proceso; no ejecutar varias réplicas suponiendo coordinación distribuida. Los jobs/conversaciones sí son persistentes; regeneraciones interrumpidas no se repiten automáticamente con coste remoto.

El editor Cornell valida/repara internamente operaciones sobre una revisión base; el agente global usa herramientas acotadas y confirmación de propuestas. Son agentes distintos. Los presupuestos de generación no son un timeout universal de todos los chats.

## Modelos externos

Roles: `synthesis`, `query_expansion`, `image_analysis` y `document_vision`. OpenRouter transporta generación/visión; VoyageAI es independiente para embeddings. `GET /api/settings/models` muestra selección, disponibilidad y modelo efectivo.

Sin credenciales suficientes se usan rutas degradadas cuando existen. No debe presentarse el fallback local como equivalente a una síntesis LLM real.

## Flashcards y madurez

`flashcard_records` indexa preguntas/respuestas de clases y candidatos de documentos Cornell; `flashcard_reviews` guarda repasos. El scheduler es propio, inspirado en intervalos Anki, no una implementación de FSRS ni una copia exacta de todos los estados de Anki. En aprendizaje: Otra vez programa 10 minutos, Difícil 30 minutos, Bien 1 día y Fácil 4 días. En repaso, los intervalos crecen según intervalo previo y facilidad; los fallos reducen facilidad y pasan a reaprendizaje. Se considera madura una tarjeta en repaso con intervalo de al menos 21 días. La UI muestra el intervalo calculado para cada tarjeta.

Editar sólo la respuesta conserva la pregunta/identidad; cambiar o retirar preguntas puede afectar progreso. La reconciliación de regeneraciones conserva historial cuando la pregunta permanece. CSV y `.apkg` usan el nombre normalizado del curso seleccionado (o el conjunto completo); exportar no traslada automáticamente el scheduler nativo a un scheduler externo idéntico. Los decks se normalizan de forma determinista, no a criterio del modelo.

## Documentos

`app/documents.py` valida y hashea el archivo, reutiliza duplicados, sube el original a RustFS, crea jobs, valida selección/presupuesto y confirma borradores como `raw_notes`. El backend no realiza el parsing pesado.

Límites: 100 MB, 1000 páginas PDF, rangos físicos sólo para PDF y autorización si la estimación remota supera USD 1. Los assets confirmados se enlazan sin duplicar el objeto RustFS.

## Variables de entorno

| Variable | Uso |
|---|---|
| `DATABASE_URL` | PostgreSQL |
| `OPENROUTER_API_KEY` | Generación y visión |
| `GOOGLE_API_KEY` | Configuración heredada; no activa transporte directo en el catálogo actual |
| `VOYAGE_API_KEY` | Embeddings reales |
| `GEMINI_MODEL` | Compatibilidad heredada; preferencias efectivas por rol en PostgreSQL |
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

uv run python scripts/manage_db.py import -d /ruta/a/notas --dry-run
uv run python scripts/manage_db.py backfill-knowledge --all --resume --defer-embeddings --embedding-batch-size 64
```

Antes de restaurar o migrar datos existentes, crear un backup. Los scripts de `/docker-entrypoint-initdb.d` sólo corren cuando el volumen nace vacío.

`uv run python scripts/manage_db.py backup` se ejecuta en el host con Docker: usa `docker exec/cp` y guarda sólo PostgreSQL. No recomendarlo dentro del backend sin cliente/socket Docker. El backup completo PostgreSQL + RustFS está en `/api/db/backup`. [Migraciones](../db/README.md) detalla qué aplica Compose sobre bases existentes.

Pruebas de DB: `RUN_DB_TESTS=1 uv run python -m unittest discover -s tests -q` requieren una base configurada y usan rollback. El benchmark `scripts/benchmark_generation.py --live` hace llamadas facturables; `--live --class-id UUID` evalúa sin sustituir la nota. No ejecutarlo durante una actualización documental ordinaria.

Uso privado, CORS localhost y sin autenticación general de API. CORS no es autorización. [RAG](../docs/rag-maintenance.md), [chat global](../docs/global-agent.md) y [presupuestos](../docs/generation-efficiency.md) describen los límites actuales.
