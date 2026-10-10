# Gestión del RAG y regeneración de clases

Estado contrastado: 10 de octubre de 2026. Implementación: `maintenance_routes.py`, `regeneration.py`, `knowledge.py`, `/rag` y `ClassRegenerationPanel.tsx`. Son operaciones sobre datos existentes, no un pipeline documental nuevo.

## Memoria RAG

La sección **RAG**, junto a Sincronización en el dock, permite filtrar por curso,
clase, texto, tipo de fragmento y disponibilidad del vector. Lista 25 registros
por página y permite seleccionar la página completa o registros individuales.

Los índices gestionados son `note_chunks` (notas procesadas), `source_chunks`
(fuentes originales), `note_claims` (afirmaciones) y los embeddings de
`flashcard_records` asociados a clases. Las tarjetas de Mis notas siguen bajo
la gestión de su editor y de Flashcards.

El detalle muestra el texto completo, la evidencia cuando existe y el vector
de 1024 dimensiones. Editar un fragmento cambia sólo el índice derivado; la nota
original permanece en Clases. El guardado solicita un nuevo vector a VoyageAI.
Si no está disponible, el texto queda guardado con embedding pendiente y nunca
conserva un vector del texto anterior. Las tarjetas se editan en Flashcards.

Las operaciones por selección son:

- Regenerar embeddings: sólo sustituye vectores si la API devuelve resultados
  reales para toda la selección.
- Borrar embeddings: elimina su disponibilidad semántica poniendo un vector
  cero y marcando el registro como pendiente. El texto permanece disponible
  para los mecanismos de recuperación por palabras que lo utilicen.
- Borrar fragmentos: elimina los registros derivados seleccionados. Las
  tarjetas no se borran desde esta acción, para proteger su historial.

Las ediciones detectan cambios concurrentes mediante una huella del contenido.
Las operaciones destructivas requieren confirmación. Regenerar o reindexar una
clase puede reconstruir sus fragmentos; esta gestión no constituye una lista
permanente de exclusiones del índice.

## Cursos y clases

En Clases, la pestaña **Cursos y clases** muestra los cursos con sus clases y
permite seleccionar varias notas ya procesadas. **Regenerar completo ahora**
solicita contenido, glosario y flashcards. **Regenerar con instrucciones
adicionales** abre un campo de instrucciones y casillas para elegir cualquier
combinación de esos tres componentes.

La regeneración usa el pipeline v2 y los modelos elegidos en la configuración.
Las instrucciones se pasan a los generadores de cada componente solicitado.
La separación de Markdown respeta las cercas de código: un heading de ejemplo
dentro de un snippet no se confunde con una sección de la nota.

El backend guarda los trabajos en `regeneration_jobs`; un worker los procesa en
orden de curso y clase, compartiendo el lock del procesamiento habitual.
Cada clase se confirma en una transacción con sus derivados, una revisión del
documento y el resultado del trabajo. Los componentes no seleccionados se
conservan. El glosario del curso se recompila cuando se regeneran definiciones,
para que las antiguas no permanezcan en la compilación.

Las tarjetas se reconcilian por pregunta: si la pregunta se conserva, también
su historial y madurez; una pregunta nueva crea una tarjeta nueva y una retirada
elimina su registro. Regenerar contenido sin seleccionar flashcards mantiene
las preguntas y respuestas existentes.

Una huella de fuentes, imágenes y Markdown evita sobrescribir una clase que
cambió durante la espera o la generación. Los fallos de una clase quedan en el
historial y no interrumpen las siguientes. Los trabajos pendientes sobreviven
a reinicios; los que estaban en ejecución se marcan como interrumpidos para
evitar repetir automáticamente llamadas facturables.

## API y despliegue

Rutas principales: `GET /api/rag/classes`, `GET /api/rag/stats`,
`GET /api/rag/chunks`, `GET|PUT /api/rag/chunks/{kind}/{id}`,
`POST /api/rag/actions` y `GET|POST /api/regeneration/jobs`.

La migración aditiva `db/migrate_regeneration_jobs.sql` crea únicamente la tabla
de trabajos y un índice de estado. Docker Compose la aplica tanto en bases
nuevas como mediante el servicio `db-migrate` para instalaciones existentes.
## Extracción de evidencia: eficiencia y seguimiento

La regeneración conserva la comparación con clases anteriores: distingue información nueva, ampliaciones, aplicaciones, aclaraciones, contradicciones y teoría repetida. Reutilizar evidencia no significa saltarse esta comparación.

La extracción individual utiliza las fuentes originales sin concatenar ventanas solapadas del índice RAG. Divide material largo en páginas de aproximadamente 8000 caracteres, cubriendo todas las fuentes, sin el antiguo corte de 60 000 caracteres. Cada página recibe historial acotado y las afirmaciones relacionadas ya extraídas para evitar duplicarlas dentro de la clase. El modelo referencia fragmentos numerados y el backend conserva las citas literalmente, sin pedir que las genere. Los fragmentos usados para búsqueda y embeddings conservan su configuración independiente.

Una extracción guardada puede reutilizarse únicamente si coincide su huella: fuentes actuales, curso y título, clases precedentes en orden, sus afirmaciones, historial recuperado, modelo auxiliar y versión de extracción. Cambios en cualquiera de estos elementos invalidan la caché. Los artefactos anteriores sin huella se comparan de nuevo; una generación exitosa prepara la reutilización posterior. Regenerar con nuevas instrucciones editoriales puede aprovechar la misma evidencia, pero sigue generando los componentes solicitados.

El historial de regeneraciones muestra fase actual, tiempo transcurrido, tiempos por fase, páginas de evidencia, llamadas y ajustes de formato; indica cuándo se reutilizó evidencia. Estos datos se guardan durante el trabajo mediante transacciones breves independientes. Las notas y sus derivados siguen guardándose atómicamente al terminar cada clase. Los registros incluyen tiempos de llamadas; las métricas del artefacto incluyen tokens cuando el proveedor los facilita. Los límites de tiempo y reintentos no garantizan una duración total fija: depende también del proveedor y del resto del pipeline.

El extractor de lotes también usa llamadas limitadas. Los lotes grandes se derivan a extracción individual en orden, en lugar de truncar clases. No se eliminan automáticamente conceptos compartidos: una aplicación o ampliación relevante debe conservarse, aunque utilice teoría conocida. Glosario y flashcards se generan en paralelo; no se inventan tarjetas para alcanzar una cantidad obligatoria. Véase [validación de eficiencia](generation-efficiency.md).

Las solicitudes nuevas muestran modelo efectivo, espera del primer texto, actividad, caracteres recibidos, tope y tipo de timeout. El backend publica avances cada cinco segundos; trabajos antiguos sin estas métricas siguen legibles. La ausencia de texto no identifica por sí sola si el proveedor está en cola o razonando. Un fallo no autoriza reintentos ilimitados ni la sustitución de todo el curso. Véase [generación](agent-architecture.md).
