# Agente del espacio de notas

Estado contrastado: 10 de octubre de 2026. Implementación: `backend/app/global_agent.py`, `global_agent_routes.py`, `agent_workspace.py` y `frontend/app/agent/page.tsx`. No es el Editor con IA de un único documento Cornell ni el pipeline generador de clases.

La sección **Agente** está entre Flashcards y Sincronización en el dock. Ofrece
un chat con mensajes Markdown, imágenes adjuntas, selector de los cuatro modelos
con visión del catálogo, alcance por curso y un historial de conversaciones.
El campo de texto ajusta su altura hasta 200 px y luego tiene scroll vertical;
las líneas largas se ajustan al ancho. Enter envía y Shift + Enter añade una línea.

Las conversaciones pueden continuarse, renombrarse y borrarse. Su título inicial
lo propone el modelo auxiliar usando un fragmento de la primera petición y la
respuesta. Ese intercambio interno no aparece como un mensaje del chat. Un
nombre editado por el usuario nunca se sustituye por otro título automático.

## Herramientas y modificaciones

El agente consulta notas procesadas, notas propias Cornell, fuentes originales,
chunks, tarjetas, definiciones y progreso de estudio mediante herramientas de
lectura predefinidas. Puede proponer cambios de texto, operaciones sobre bloques
y relaciones, ediciones o eliminaciones de chunks, actualización de embeddings,
edición o retirada de tarjetas y cambios en definiciones del glosario.

Las modificaciones se preparan como propuestas con diferencias Antes/Después.
El usuario puede aplicarlas o descartarlas. El agente debe inspeccionar un
elemento antes de modificarlo; el servidor impide actuar sobre elementos no
consultados o fuera del curso seleccionado. Las tarjetas y definiciones de
clases se editan en el Markdown fuente y se reconcilian con sus índices y con el
glosario compilado. Las tarjetas de Mis notas se editan mediante sus bloques
fuente. La confirmación de una propuesta guarda todas sus modificaciones en una
transacción; si hay un fallo, ninguna se confirma. Las huellas del contenido y
las revisiones evitan sobrescribir ediciones realizadas después de la propuesta.

Las notas conservan revisiones. Las tarjetas que mantienen su pregunta conservan
su identidad y progreso; retirar una tarjeta o cambiar su pregunta puede retirar
su historial, y se advierte al confirmar. Los chunks editados nunca conservan un
vector del texto anterior. Las modificaciones confirmadas participan en la
sincronización habitual de la app.

## Eliminación de duplicados

Esta herramienta visible permite elegir contenido de notas generadas, glosario,
flashcards o cualquier combinación. Busca coincidencias exactas y variantes muy
parecidas dentro de cada curso. Las notas excluyen bloques de código y metadatos
de la comparación de prosa. Las tarjetas priorizan conservar la que tiene más
repasos. El agente revisa los candidatos y debe conservar aportes, ejemplos y
contextos distintos aunque los textos sean similares.

Se preparan hasta 50 candidatos por análisis y se informa cuántas clases se
revisaron y si quedaron clases pendientes. La herramienta no constituye una
garantía de detectar toda repetición semántica. No elimina contenido durante el
análisis: entrega una propuesta. Las restricciones de esta acción impiden
modificar elementos ajenos a los candidatos encontrados. El generador de notas
también compara las flashcards nuevas con las ya aceptadas de la misma clase,
además de con el historial, para prevenir reiteraciones desde el origen.

## Ejecuciones persistentes

Las tablas `agent_conversations`, `agent_messages` y `agent_runs` guardan historial,
adjuntos, ejecuciones y propuestas. La migración aditiva es
`db/migrate_global_agent.sql`. Docker Compose la aplica en instalaciones nuevas
y mediante `db-migrate` en instalaciones existentes.

El worker procesa hasta tres conversaciones simultáneas, con una ejecución
activa por conversación y hasta diez rondas de herramientas por petición. El
modelo de conversación y el título se llaman por API; búsquedas, preparación de
diferencias y aplicación de cambios se ejecutan en el backend local. Los
embeddings usan VoyageAI cuando corresponde. No se conceden herramientas para
ejecutar comandos o acceder a archivos arbitrarios.

Cancelar guarda el estado y cancela la llamada asíncrona activa. Una respuesta
tardía no se publica después de la cancelación. Cancelar no revierte cambios ya
confirmados ni garantiza que el proveedor anule el coste de una llamada recibida.
Las ejecuciones en curso se marcan como interrumpidas tras reiniciar el backend;
los mensajes y propuestas permanecen guardados y las pendientes pueden retomarse.

API principal: `/api/agent/models`, `/api/agent/conversations`,
`/api/agent/conversations/{id}/messages`, `/api/agent/runs/{id}/cancel`,
`/api/agent/runs/{id}/apply` y `/api/agent/runs/{id}/reject`.

## Límites operativos

El protocolo del agente global es JSON validado localmente, con una corrección de formato cuando el parsing inicial falla; no hereda los cinco intentos del editor Cornell. Usa su propio timeout de cliente y hasta diez rondas; tampoco hereda los presupuestos por tarea del generador. Las búsquedas acotan resultados y algunas lecturas requieren paginación: el agente no recibe toda la base de datos automáticamente. No garantiza detectar toda repetición ni resolver cualquier petición profunda.

Las tareas activas/cancelación son de proceso; el historial es persistente. La app no tiene autenticación general ni aislamiento multiusuario: usar en entorno privado. La selección de curso limita las herramientas, pero no sustituye un sistema de permisos. Véanse [arquitectura](agent-architecture.md) y [RAG](rag-maintenance.md).
