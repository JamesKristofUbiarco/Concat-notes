# Planes a futuro

Iniciativas no implementadas o incompletas. Las funciones ya entregadas deben documentarse en los README correspondientes, no mantenerse como planes.

Revisado el 10 de octubre de 2026. Clases, Mis notas, Flashcards, Agente, Sincronización y RAG ya existen; la lista siguiente describe trabajo pendiente, no promesas de disponibilidad.

## Sincronización local

- Mejorar la integración con carpetas del sistema para seleccionar cualquier carpeta con un botón y sincronizar con otro, sin editar manualmente `.env` ni montajes.
- Permitir cambiar el destino de forma segura desde aplicaciones empaquetadas para cada sistema operativo.
- Añadir historial visible de sincronizaciones y recuperación de versiones.

## Procesamiento documental

- Reconstruir la posición de figuras PDF con bloques y coordenadas, no sólo por página.
- Sustituir el filtro por área por routing visual local que distinga diagramas, tablas, fotografías, logos y decoración.
- Evaluar Docling/PaddleOCR como enriquecedores opcionales mediante benchmark reproducible.
- Añadir caché multimodal por asset, modelo, prompt y contexto.
- Mejorar OCR de fórmulas, documentos multicolumna y tablas complejas.

## Agente y conocimiento

- Ampliar la evaluación regresiva existente con más cursos/fixtures y medidas de fidelidad, cobertura, duplicación y calidad de flashcards.
- Hacer más visibles las citas internas entre afirmaciones y evidencia original.
- Añadir reparación independiente de diagramas; la regeneración selectiva de contenido/glosario/flashcards y el agente global ya permiten cambios parciales.
- Calibrar presupuestos de generación con latencias reales por modelo/proveedor; los márgenes actuales son deterministas por tarea y tamaño.

## Suite

- Diseñar nuevas secciones del dock manteniendo barras laterales contextuales.
- Mejorar importación/exportación interoperable y accesibilidad integral.
- Extender la observabilidad existente de generación a visión documental y chats, con panel de salud de workers y costes comparables.
- Diseñar autenticación, autorización y aislamiento multiusuario antes de publicar la suite en una red no confiable.
