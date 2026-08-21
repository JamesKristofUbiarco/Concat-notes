# Handoff: procesamiento estructurado de PDF y EPUB

> Documento de arquitectura para el agente que implemente esta función en **Concat Notes**.
> Se redactó desde `/home/dirac/Documents/Proyecto-slm`; no se modificó código de Concat Notes.

## Objetivo del usuario

Concat Notes debe aceptar PDF y EPUB y permitir procesar:

1. el documento completo;
2. uno o varios capítulos/subcapítulos cuando el archivo declare esa estructura;
3. un intervalo de páginas elegido por el usuario (principalmente PDF; en EPUB conviene mostrar ubicaciones/secciones, no inventar páginas físicas).

El procesamiento debe ser rápido y preciso. Los parsers, OCR, detección de layout, hashing, crops y reconstrucción pueden ejecutarse localmente; los LLM se consumen mediante **OpenRouter**. Por coste, privacidad y latencia, un LLM remoto no debe recibir todas las páginas ni decidir mirando páginas completas qué debe analizar.

---

## Qué se implementó en Proyecto SLM

La referencia principal es el commit `54b9125` (`feat(documents): add structured vision-on-demand pipeline`) de la rama `feature/document-processing-pipeline`. La mejora de observabilidad está en `eb8b4c4`.

Archivos de referencia:

- `/home/dirac/Documents/Proyecto-slm/backend/document_pipeline.py`
- `/home/dirac/Documents/Proyecto-slm/backend/document_parser.py`
- `/home/dirac/Documents/Proyecto-slm/backend/job_service.py`
- `/home/dirac/Documents/Proyecto-slm/backend/rag_service.py`
- `/home/dirac/Documents/Proyecto-slm/backend/database.py`
- `/home/dirac/Documents/Proyecto-slm/backend/main.py`
- `/home/dirac/Documents/Proyecto-slm/frontend/src/components/FilesTab.tsx`
- `/home/dirac/Documents/Proyecto-slm/frontend/src/components/SourcesTab.tsx`

### Pipeline implementado

Proyecto SLM dejó de pensar en un PDF como una lista de imágenes y adoptó un pipeline `layout-first, vision-on-demand`:

```text
archivo
  -> preflight barato
  -> parser estructurado
  -> elementos ordenados con página y coordenadas
  -> clasificación/routing determinista
  -> análisis local o visión sólo para crops relevantes
  -> documento estructurado canónico
  -> proyección Markdown + chunks con procedencia
```

El resultado canónico conserva elementos como texto, heading, tabla, fórmula y figura, junto con:

- número de página;
- bounding box;
- orden de lectura;
- caption y contexto cercano;
- asset visual;
- parser/modelo utilizado;
- estado de enriquecimiento;
- hash de contenido;
- relación entre chunk, elemento, página y jerarquía de headings.

Docling se usa por su representación estructurada, no sólo por el Markdown. Las imágenes detectadas se guardan como crops WebP. Un router barato descarta **del análisis semántico**, pero no de la representación, logos, adornos, miniaturas y recursos repetidos. Las figuras informativas se analizan por crop. Sólo una página esencialmente escaneada o visual puede enviarse como página completa.

Se agregaron tres perfiles:

- `fast`: extrae y conserva estructura/assets sin inferencia visual costosa;
- `balanced`: enriquece sólo visuales informativos con el motor documental preferido;
- `accurate`: añade un VLM general como fallback selectivo.

También se implementaron jobs persistentes con porcentaje, etapa, mensaje, heartbeat, recuperación tras reinicio y detección visual de falta de avances. El usuario ve la etapa concreta (`Analizando visual 9 de 21`), tiempo transcurrido y degradaciones como “Paddle no disponible; se usa Gemma”.

### Resultado medido

En un PDF digital académico de 15 páginas, el perfil rápido tardó aproximadamente 12.1 segundos y produjo 162 elementos, 6 figuras, 4 tablas y 72 chunks, sin placeholders `<!-- image -->`. En un PDF con 21 visuales, el perfil preciso sin Paddle fue mucho más lento porque cada crop cayó al VLM general. Esta diferencia es la razón para hacer explícitos motor, coste y progreso.

### Qué no debe copiarse literalmente

- El almacenamiento SQLite de Proyecto SLM: Concat Notes ya usa PostgreSQL y SQLAlchemy.
- El fallback Ollama/Gemma: Concat Notes debe utilizar su resolvedor existente de OpenRouter.
- Rutas de assets en disco: Concat Notes ya tiene RustFS/S3 y debe guardar allí originales y crops.
- El ejecutor de un solo hilo tal cual: Concat Notes ya tiene un worker asyncio; conviene integrar una cola documental separada y limitar concurrencia.
- PaddleOCR-VL como requisito obligatorio: debe ser un enriquecedor local opcional. En la máquina actual de Proyecto SLM aún requiere NVIDIA Container Toolkit para funcionar en Docker.

---

## Encaje con la arquitectura actual de Concat Notes

Concat Notes ya tiene casi todos los puntos de integración necesarios:

| Capacidad actual | Cómo reutilizarla |
|---|---|
| FastAPI en `backend/app/main.py` | Endpoints de upload, inspección, selección y jobs |
| PostgreSQL + SQLAlchemy | Documentos, secciones, elementos, selecciones y jobs persistentes |
| RustFS en `backend/app/storage.py` | Originales, crops, thumbnails y manifest JSON |
| Worker en `backend/app/worker.py` | Ejecución en segundo plano y concurrencia limitada |
| OpenRouter en `backend/app/llm_models.py` | Síntesis textual y VLM remoto selectivo |
| OCR local en `backend/app/table_ocr.py` | Fallback para tablas recortadas, no para páginas enteras por defecto |
| Voyage/pgvector en `backend/app/knowledge.py` | Indexación de chunks seleccionados con procedencia |
| `raw_notes` y pipeline v2 | Convertir una selección documental en evidencia canónica antes de sintetizarla |

No se recomienda meter el parser directamente dentro de `agent.py` o `v2_agent.py`. El parsing documental debe ser una capa anterior, determinista y reanudable. El agente recibe después una selección estructurada y acotada.

Módulos nuevos sugeridos:

```text
backend/app/documents/
  __init__.py
  contracts.py          # dataclasses/Pydantic: document, section, element, selection
  service.py            # orquestación de ingestión/reprocesamiento
  pdf_parser.py         # preflight, outline, páginas y Docling/PyMuPDF
  epub_parser.py        # OPF, spine, nav/NCX, XHTML y assets
  section_builder.py    # árbol jerárquico y rangos
  visual_router.py      # heurísticas locales, deduplicación, crops
  visual_analysis.py    # OCR local y adaptador OpenRouter multimodal
  renderer.py           # Markdown/manifest derivados
  chunker.py            # chunks con página/sección/elementos
  jobs.py               # estado, heartbeat, progreso, retry/cancel cooperativo
```

---

## Modelo canónico recomendado

No convertir prematuramente todo a Markdown. Markdown debe ser una proyección reconstruible del modelo estructurado.

### Tablas sugeridas

#### `source_documents`

- `id UUID PK`
- `filename`, `media_type`, `size_bytes`, `sha256`
- `storage_key` (objeto original en RustFS)
- `format` (`pdf` o `epub`)
- `page_count` nullable
- `title`, `author`, `language`
- `parser_name`, `parser_version`
- `status`, `error`
- `created_at`, `updated_at`

#### `document_sections`

- `id UUID PK`
- `document_id FK`
- `parent_id FK nullable`
- `order_index`
- `level`
- `title`
- `source_kind`: `pdf_outline`, `pdf_heading`, `epub_nav`, `epub_ncx`, `epub_spine`, `synthetic`
- `page_start`, `page_end` nullable
- `epub_href`, `fragment_id` nullable
- `confidence`

#### `document_elements`

- `id UUID PK`
- `document_id FK`
- `section_id FK nullable`
- `order_index`
- `page_number` nullable
- `element_type`: `heading`, `paragraph`, `list`, `table`, `formula`, `figure`, `page_image`
- `bbox_json` nullable
- `text`, `caption`, `visual_description`
- `structured_data JSONB`
- `asset_key` nullable
- `content_hash`, `perceptual_hash`
- `parser`, `model`, `status`, `status_reason`

#### `document_jobs`

- `id UUID PK`
- `document_id FK nullable`
- `kind`, `status`, `stage`, `progress`
- `message`, `error`
- `profile`, `selection_json JSONB`
- `heartbeat_at`, `started_at`, `finished_at`
- `attempt`, `cancel_requested`

#### Procedencia de chunks

Puede extenderse `source_chunks` o crear `document_chunks`. Cada chunk debería guardar:

- `document_id`, `section_id`;
- `page_start`, `page_end`;
- `element_ids UUID[]` o tabla de unión;
- `heading_path JSONB`;
- `content_type`;
- `text` y embedding;
- versión de parser/chunker.

Usar migraciones aditivas y derivados reconstruibles. El original en RustFS y el manifiesto estructurado son la fuente canónica; embeddings, Markdown y thumbnails pueden regenerarse.

---

## Semántica de selección: completo, capítulos o páginas

Separar dos operaciones:

1. **inspeccionar** el archivo y descubrir su estructura;
2. **procesar** una selección confirmada por el usuario.

Esto evita procesar todo antes de que el usuario elija.

### Documento completo

```json
{"mode": "full"}
```

Incluye todos los elementos en orden documental. Aun así, visión remota sólo debe aplicarse a crops enrutados.

### Capítulos y subcapítulos

```json
{
  "mode": "sections",
  "section_ids": ["uuid-capitulo-2", "uuid-seccion-2-3"],
  "include_descendants": true
}
```

Reglas:

- seleccionar un capítulo incluye subcapítulos por defecto;
- seleccionar sólo un subcapítulo no incluye hermanos;
- deduplicar rangos cuando padre e hijo estén seleccionados;
- conservar el `heading_path` completo como contexto aunque el padre no forme parte del texto;
- mostrar origen y confianza de la estructura.

### Páginas PDF

```json
{
  "mode": "pages",
  "ranges": [{"start": 10, "end": 18}, {"start": 25, "end": 25}]
}
```

Validar números uno-basados, límites, rangos invertidos y solapamientos. Normalizar a intervalos ordenados no solapados. Definir claramente que “página” significa página física del PDF, no el número impreso dentro del documento.

Cuando una sección cruza el límite, incluir sólo los elementos cuyas páginas estén dentro del rango, pero conservar el heading padre como metadato contextual.

### EPUB y el problema de las páginas

EPUB es refluible: normalmente no tiene páginas estables. No ofrecer “página 20” salvo que el EPUB contenga `page-list`/pagebreaks explícitos. La UI debería ofrecer:

- capítulos/subcapítulos del `nav.xhtml` o `toc.ncx`;
- elementos del spine como fallback;
- “ubicaciones” o pagebreaks declarados si existen.

Si el usuario pide páginas para EPUB, explicar esta limitación y mostrar secciones/ubicaciones disponibles; no simular páginas basadas en longitud.

---

## Descubrimiento de estructura

### PDF

Orden de preferencia:

1. outline/bookmarks nativos con PyMuPDF;
2. headings tipados por Docling/layout;
3. heurística tipográfica local (tamaño, negrita, numeración, espacio, repetición);
4. estructura sintética por páginas si no hay capítulos confiables.

El outline nativo debe mapearse a páginas y cerrarse usando el inicio de la siguiente sección del mismo nivel o nivel superior. No confiar ciegamente en headings: eliminar encabezados/pies repetidos y exigir consistencia tipográfica.

Preflight local recomendado:

- número de páginas;
- texto nativo por página;
- proporción de páginas con texto suficiente;
- outline disponible;
- densidad de imágenes/dibujos;
- páginas probablemente escaneadas.

Para PDF digital, desactivar OCR global. Para páginas sin texto, aplicar OCR sólo a esas páginas.

### EPUB

Usar `ebooklib` o lectura ZIP segura más BeautifulSoup/lxml:

1. validar ZIP y rechazar path traversal/zip bombs;
2. leer `META-INF/container.xml` y OPF;
3. obtener metadata, manifest y spine;
4. preferir EPUB 3 `nav.xhtml` y caer a EPUB 2 `toc.ncx`;
5. parsear cada XHTML conservando headings, párrafos, listas, tablas, notas y orden;
6. resolver enlaces y fragmentos relativos;
7. extraer imágenes/CSS relevantes a RustFS;
8. generar el árbol de secciones sin perder el orden del spine.

El HTML del EPUB debe sanearse. Scripts, iframes, recursos remotos y CSS peligroso no deben ejecutarse en el frontend.

---

## Estrategia local + OpenRouter

La regla central es: **OpenRouter no decide si OpenRouter es necesario mirando el documento completo**.

### Trabajo local barato

- PyMuPDF: metadata, outline, texto, coordenadas y crops PDF;
- Docling: layout y tablas cuando compense su coste;
- ebooklib + BeautifulSoup/lxml: estructura EPUB;
- Tesseract/img2table existente: tablas o regiones escaneadas;
- Pillow/imagehash: dimensiones, área, conversión WebP y deduplicación;
- reglas geométricas: logos, márgenes, iconos y repetidos;
- captions/contexto: decidir relevancia antes de visión;
- hashing/caché: no pagar dos veces por la misma imagen.

### Routing visual sugerido

```text
logo, fondo, icono pequeño, recurso repetido -> conservar asset, no analizar
tabla -> parser local existente; remoto sólo si falla integridad
texto escaneado -> OCR local
gráfico/diagrama informativo -> VLM OpenRouter con crop + caption + contexto
fotografía -> analizar sólo si caption/curso indica relevancia
```

Nunca enviar una página completa salvo que el preflight determine que la página es esencialmente una imagen: escaneo, infografía o diapositiva completa.

### Adaptador OpenRouter

Reutilizar `llm_models.resolve_selected_model` y el transporte existente. Añadir un rol configurable, por ejemplo `document_vision`, separado del modelo de síntesis. El adaptador debe aceptar:

- bytes/crop o URL firmada de RustFS;
- caption;
- párrafo anterior y posterior con límite estricto;
- tipo esperado (`chart`, `diagram`, `photo`, `table_fallback`);
- respuesta estructurada validada.

Prompt base:

```text
Analiza únicamente este recorte documental. Extrae texto visible y describe
datos, relaciones, ejes, leyendas y estructura que no estén ya expresados en
el contexto. No inventes información. Devuelve JSON/Markdown conciso.
```

Aplicar timeout, retries con backoff, límites de tamaño, presupuesto máximo por job y caché por:

```text
sha256(crop + model_id + prompt_version + context_hash)
```

Registrar llamadas, tokens/coste si OpenRouter los devuelve, modelo efectivo y fallback. Mostrar una estimación previa: cantidad de visuales locales, cantidad enviada a API y coste aproximado.

Perfiles adaptados a Concat Notes:

- `fast/local`: estructura, texto, tablas/OCR local y assets; cero visión remota;
- `balanced`: VLM remoto sólo para gráficos/diagramas claramente informativos;
- `accurate`: amplía candidatos y permite fallback remoto para tablas/OCR difíciles.

El modelo de síntesis textual de notas puede seguir siendo remoto, pero debe recibir chunks/secciones seleccionados, no el binario ni todo el documento en un único prompt.

---

## Flujo API propuesto

### 1. Subida e inspección

`POST /api/documents`

- multipart con PDF/EPUB;
- streaming hacia RustFS, sin cargar el archivo completo en RAM;
- límites por tamaño, MIME real, extensión y hash;
- crea documento y job `inspect`;
- responde `202` con `document_id` y `job_id`.

### 2. Estado

- `GET /api/document-jobs/{job_id}`
- `GET /api/documents/{document_id}/status`

Respuesta mínima:

```json
{
  "status": "running",
  "stage": "detecting_structure",
  "progress": 36,
  "message": "Construyendo índice de 14 capítulos",
  "heartbeat_at": "...",
  "warnings": []
}
```

### 3. Inspección

- `GET /api/documents/{id}`: metadata y capacidades;
- `GET /api/documents/{id}/sections`: árbol seleccionable;
- `GET /api/documents/{id}/pages?from=1&to=20`: thumbnails/preview PDF;
- `GET /api/documents/{id}/elements?...`: inspección avanzada.

### 4. Procesamiento de selección

`POST /api/documents/{id}/process`

```json
{
  "selection": {"mode": "sections", "section_ids": ["..."]},
  "profile": "balanced",
  "target": {
    "course_name": "...",
    "one_note_per_top_level_section": true
  }
}
```

Responder `202`. No mantener la conexión HTTP abierta durante parsing/LLM.

### 5. Resultado y reprocesamiento

- `GET /api/documents/{id}/runs/{run_id}`;
- `POST /api/documents/{id}/runs/{run_id}/retry`;
- `POST /api/document-jobs/{job_id}/cancel` con cancelación cooperativa entre etapas;
- endpoint para convertir una o varias secciones en `raw_notes`.

Guardar la selección y versión del parser para reproducibilidad.

---

## Integración con notas y cursos

No introducir silenciosamente un libro entero como una sola `raw_note` gigante. Dos estrategias explícitas:

1. una nota por capítulo superior seleccionado;
2. una nota única para un intervalo corto de páginas/secciones.

Para cada `raw_note` generada:

- `transcription` puede contener el texto documental estructurado seleccionado;
- `class_title` usa el título de la sección;
- `course_module` puede usar el heading padre;
- agregar `source_document_id`, `source_section_id` y páginas/locations mediante columnas nuevas o tabla de unión;
- assets visuales se enlazan como `ImageSnippet`, sin duplicar el objeto en RustFS;
- el pipeline v2 sintetiza después esta evidencia como ya lo hace con notas normales.

Mantener dos salidas:

- **extracción fiel**: texto/estructura y visuales recuperados, sin “mejorarlos” mediante síntesis;
- **nota procesada**: interpretación/síntesis de Concat Notes.

Esto evita confundir contenido fuente con contenido generado.

---

## Experiencia de usuario necesaria

Flujo recomendado:

```text
Subir -> Inspeccionando -> Elegir alcance -> Revisar coste -> Procesar -> Resultado
```

Selector de alcance:

- Todo el documento;
- Capítulos/subcapítulos (árbol con checkboxes y selección padre/hijos);
- Páginas PDF (campos desde/hasta, varios rangos y thumbnails).

Antes de procesar mostrar:

- páginas/secciones incluidas;
- cantidad estimada de texto, tablas y visuales;
- trabajo local vs llamadas OpenRouter;
- perfil y modelo;
- advertencias (“este EPUB no tiene TOC”, “12 páginas parecen escaneadas”).

Durante el job mostrar:

- barra basada en progreso real, no en cantidad de archivos terminados;
- etapa y contador (`Analizando visual 3 de 8`);
- motor actual (`OCR local`, `OpenRouter: modelo X`);
- tiempo transcurrido;
- “actividad confirmada hace N s”;
- warning después de 90 s sin heartbeat;
- estado persistente tras refrescar o navegar;
- error accionable y posibilidad de retry.

No mostrar ETA hasta tener suficiente historial por etapa. Una estimación falsa genera más ansiedad que no mostrarla.

---

## Seguridad y operación

- validar PDF/EPUB por contenido, no sólo extensión;
- limitar bytes, páginas, entradas ZIP, ratio de compresión y tamaño descomprimido;
- impedir Zip Slip en EPUB;
- sanear XHTML/Markdown antes de renderizar;
- rechazar URLs internas si se permiten recursos remotos;
- nunca incluir API keys en jobs, logs o manifests;
- usar URLs firmadas o base64 acotado para OpenRouter;
- borrar temporales en `finally`; el original y assets canónicos quedan en RustFS;
- transacciones para reemplazar elementos/chunks en reprocesamiento;
- idempotencia mediante hash del archivo + selección + perfil + versiones;
- límites de concurrencia independientes para CPU, OCR y OpenRouter;
- retry sólo en operaciones idempotentes;
- métricas de duración, errores, cache hit, tokens y coste.

Docling y OCR pueden consumir bastante RAM/CPU. No ejecutarlos dentro del event loop. El worker actual usa `asyncio.to_thread`; para múltiples documentos pesados conviene un pool de procesos o un worker separado, con concurrencia 1 inicialmente.

---

## Dependencias candidatas

Agregar sólo tras un spike/benchmark:

- `pymupdf`: preflight, outline, render y crops PDF;
- `docling`: layout PDF estructurado;
- `ebooklib`: EPUB/OPF/spine/navigation;
- `beautifulsoup4` o `lxml`: XHTML;
- `pillow` + `imagehash`: assets y deduplicación;
- `bleach`: saneamiento HTML;
- mantener `img2table` + Tesseract existentes;
- PaddleOCR/PP-Structure opcional como servicio local, no dependencia obligatoria del backend.

Python 3.13 puede ser un punto de compatibilidad para Docling/Paddle y algunas dependencias nativas. Antes de fijarlas, crear un spike dentro de la imagen Docker actual. Si Docling no soporta bien esa combinación, aislar el parser en un microservicio Python 3.11/3.12 en vez de degradar el backend principal.

---

## Plan de implementación recomendado

### Fase 0: benchmark y contratos

- reunir 10–20 PDF/EPUB reales: digitales, escaneados, con TOC, sin TOC, tablas, diagramas;
- definir `Document`, `Section`, `Element`, `Selection` y `Job`;
- medir PyMuPDF, Docling y parser EPUB en la imagen real;
- congelar fixtures esperados de estructura.

### Fase 1: inspección sin LLM

- upload streaming a RustFS;
- preflight PDF/EPUB;
- outline/nav/spine;
- persistir árbol de secciones;
- endpoints y UI de selección;
- jobs, heartbeat y recuperación.

### Fase 2: extracción seleccionada local

- páginas/rangos y secciones;
- elementos estructurados;
- OCR sólo donde falta texto;
- crops y tablas locales;
- Markdown fiel y chunks con procedencia.

### Fase 3: visión OpenRouter selectiva

- router determinista;
- rol `document_vision`;
- caché, presupuesto y auditoría;
- perfiles y estimación de coste;
- degradación limpia si OpenRouter falla.

### Fase 4: integración con notas

- crear `raw_notes` por capítulo o selección;
- vínculos de procedencia;
- assets compartidos desde RustFS;
- síntesis v2 y pgvector;
- reprocesamiento idempotente.

### Fase 5: endurecimiento

- cancelación cooperativa;
- límites ZIP/PDF y saneamiento;
- métricas y benchmark regresivo;
- pruebas con reinicio del backend y fallos de OpenRouter/RustFS/OCR.

---

## Pruebas y criterios de aceptación

### Unitarias

- normalización de rangos `1-3, 3-5 -> 1-5`;
- árbol outline/nav con padres e hijos;
- cierre correcto de rangos por capítulo;
- selección de padre con/sin descendientes;
- EPUB sin TOC cae al spine;
- deduplicación de logos/crops;
- router no envía decoraciones a OpenRouter;
- caché evita llamadas duplicadas;
- heartbeat se actualiza en cada etapa;
- Markdown no contiene placeholders de imágenes.

### Integración

- PDF completo, por capítulo y por páginas;
- EPUB completo y por capítulo/subcapítulo;
- PDF digital no ejecuta OCR global;
- PDF parcialmente escaneado sólo procesa páginas necesarias;
- caída de OpenRouter conserva extracción local y marca degradación;
- reinicio recupera job sin duplicar notas/assets;
- selección genera notas con procedencia y chunks correctos.

### UX

- el usuario puede ver qué está ocurriendo en todo momento;
- una recarga no hace desaparecer el trabajo;
- el progreso global refleja porcentaje real;
- “Preciso” advierte coste/fallback antes de iniciar;
- EPUB no presenta páginas ficticias;
- errores indican acción posible.

### Rendimiento/coste

- cero llamadas multimodales en perfil local;
- ninguna página PDF completa enviada remotamente salvo clasificación explícita de página visual/escaneada;
- registrar llamadas por documento y cache hit rate;
- benchmark reproducible por formato/perfil con tiempo, RAM, visuales y coste.

---

## Decisiones que el agente debe confirmar con el usuario

Antes de integrar la salida con `raw_notes`, confirmar:

1. si “procesar capítulo” crea automáticamente una nota por capítulo o permite previsualizar/editar primero;
2. si seleccionar un capítulo incluye siempre todos sus subcapítulos por defecto;
3. si las imágenes originales deben aparecer embebidas en la nota final o sólo como evidencia/análisis;
4. presupuesto máximo de OpenRouter por documento y modelo visual preferido;
5. tamaño/páginas máximos aceptables para un archivo.

Estas decisiones no bloquean la Fase 1 de inspección, pero sí cambian persistencia, UI y costes de las fases posteriores.

## Resumen ejecutivo

La implementación adecuada para Concat Notes no es `PDF/EPUB -> LLM`. Debe ser:

```text
PDF/EPUB -> estructura local -> selección del usuario -> extracción local
         -> crops relevantes -> OpenRouter sólo bajo demanda
         -> evidencia fiel -> pipeline v2 de notas -> pgvector/RustFS
```

El mayor valor reutilizable de Proyecto SLM es la separación entre representación canónica, proyección Markdown, routing visual, procedencia y jobs observables. El mayor cambio respecto a Proyecto SLM es sustituir Ollama por un adaptador OpenRouter con control explícito de coste y aprovechar PostgreSQL, RustFS, el worker y el pipeline v2 que Concat Notes ya posee.
