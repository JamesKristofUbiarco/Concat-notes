# Document worker

Servicio Python 3.12 aislado que inspecciona y extrae PDF/EPUB fuera de FastAPI. Comparte PostgreSQL y RustFS con el backend y trabaja con concurrencia uno.

## Herramientas locales

| Herramienta | Función |
|---|---|
| PyMuPDF | PDF: metadata, outline, texto, tablas, imágenes y thumbnails |
| Tesseract + pytesseract | OCR `spa+eng` cuando una página no tiene texto |
| EbookLib | EPUB: metadata, TOC, spine, XHTML y recursos |
| BeautifulSoup | Saneamiento y recorrido ordenado del XHTML |
| Pillow | Validación, dimensiones y conversión WebP |
| SHA-256 | Deduplicación de documentos y recursos |
| psycopg | Jobs y representación en PostgreSQL |
| boto3 | Originales y assets en RustFS |

La imagen contiene las dependencias; el host no necesita parsers ni OCR.

## Ciclo

1. Reclama un job pendiente con bloqueo SQL.
2. Descarga temporalmente el original desde RustFS.
3. Inspecciona estructura y crea secciones/thumbnails.
4. Procesa documento, secciones o páginas PDF seleccionadas.
5. Persiste elementos, assets y borradores.
6. Actualiza progreso, heartbeat, coste y advertencias.
7. Borra el temporal; los datos persistentes permanecen.

Los jobs sin heartbeat se recuperan al iniciar. La cancelación es cooperativa entre unidades de trabajo.

## PDF

- Bookmarks nativos; heurísticas de encabezados y secciones sintéticas como fallback.
- Texto ordenado con PyMuPDF.
- OCR sólo para páginas sin texto.
- Tablas convertidas a Markdown.
- Imágenes mayores de 120 × 120 convertidas a WebP y deduplicadas.
- Las figuras se colocan al final del bloque de su página; no se conserva aún su posición exacta entre párrafos.

## EPUB

- Validación ZIP contra path traversal.
- Navegación declarada y spine como fallback.
- Omisión de documentos de navegación.
- Eliminación de `script`, `iframe` y `style`.
- Recorrido ordenado de headings, párrafos, listas, tablas e imágenes.
- Sin páginas físicas ficticias: EPUB es refluible.

## Visión remota

| Perfil | Comportamiento |
|---|---|
| `local` | Cero llamadas visuales remotas |
| `balanced` | Candidatas de al menos 80 000 píxeles |
| `accurate` | Umbral ampliado a 20 000 píxeles |

Los umbrales son heurísticas de área, no clasificación semántica local. La candidata se envía en Base64 a OpenRouter con contexto acotado; nunca se envía el documento completo. Si se agota el presupuesto, continúa la extracción local.

## Límites

- 100 MB por archivo.
- 1000 páginas PDF.
- Grupos PDF de hasta 20 páginas.
- Miniaturas iniciales de hasta 30 páginas.
- No se usa Docling ni PaddleOCR actualmente.

## Desarrollo

```bash
cd document-worker
uv sync --frozen
uv run python -m unittest -q test_worker.py
uv run python -m py_compile worker.py

docker compose build document-worker
docker compose up -d --no-deps --force-recreate document-worker
docker compose logs -f document-worker
```
