# Generación progresiva: presupuesto, precisión y evaluación

Estado contrastado: 10 de octubre de 2026. Alcance: generación/regeneración v2 y sus auxiliares. No atribuir estos límites automáticamente al chat global, al editor Cornell ni a la visión del document-worker, que tienen clientes y contratos propios. Fuentes: `generation_runtime.py`, `knowledge.py`, `v2_agent.py` y `regeneration.py`.

## Objetivo e invariantes

El objetivo es explicar información nueva relevante sin repetir teoría anterior. Una aplicación, una opción de comando, un caso práctico, una aclaración o una corrección pueden ser novedades aunque compartan el concepto base. La eliminación de repetición no debe convertirse en eliminación de estos matices.

Se conserva todo el material actual durante la extracción. El historial se recupera sólo de clases anteriores del mismo curso. Los hechos del cuerpo vienen de la clase actual; los antecedentes sirven para contraste y continuidad. Las citas del manifiesto las copia el backend a partir de las referencias elegidas por el modelo. El editor Cornell, el chat agéntico, los modelos disponibles y los formatos de exportación no se sustituyen.

## Presupuestos

| Operación | Presupuesto |
|---|---|
| Página de evidencia | Unos 8000 caracteres, con fragmentos numerados de hasta 500 |
| Historial de afirmaciones recuperado | Hasta 28 candidatos / 12000 caracteres de contenido |
| Tarjetas enviadas como antecedentes | Hasta 24 relevantes / 8000 caracteres |
| Definiciones anteriores enviadas | Hasta 60 términos relevantes / 4000 caracteres |
| Extracción por página | 6144 tokens de salida, 90–150 s por solicitud |
| Extracción por lote pequeño | 6144 tokens de salida, 120–180 s por solicitud |
| Glosario | 4096 tokens de salida, 150–180 s por solicitud |
| Flashcards | 4096 tokens de salida, 90–150 s por solicitud |
| Cuerpo | 10000 tokens de salida, 150–240 s por solicitud |
| Reparación de presentación del cuerpo | Un intento, 120–180 s |
| Reparación de diagramas | 4096 tokens de salida, 60–90 s por solicitud |

Son presupuestos iniciales, no garantías de latencia ni cifras ya calibradas estadísticamente. `request_budget` añade 15 s por cada 8000 caracteres de entrada que excedan los primeros 8000, y por cada 2048 tokens de capacidad de salida adicionales al límite habitual de la tarea, sin superar su tope. No recorta fuentes ni modifica los prompts para conseguir esos plazos. Una prueba optativa puede fijar un límite explícito más corto.

Hay tres límites distintos: tiempo total (aunque haya avance), espera del primer texto (80 % del total, acotada entre 90 y 180 s y nunca superior al total), e inactividad después del primer texto (60 s para cuerpo/reparación/glosario; 45 s para evidencia/flashcards/diagramas). El timeout HTTP de lectura se ajusta al margen del primer texto; ya no existe un corte fijo de 45 s que anule el presupuesto mayor. La conexión mantiene un límite independiente de 15 s.

Los SDK no reintentan internamente. El protocolo JSON admite dos intentos; puede haber una solicitud de fallback ante indisponibilidad temporal. Estos límites son por solicitud, no una promesa de duración total por clase. Un documento grande necesita varias páginas. Se rechaza una respuesta truncada por tokens; no se presenta como una nota completa.

La política de razonamiento depende del modelo efectivo, también después de un fallback: DeepSeek auxiliar permite desactivarlo; Gemini Flash Lite lo exige y usa `minimal`; la composición usa `low`. El catálogo registra los modelos que exigen razonamiento. Si un endpoint antes opcional rechaza explícitamente desactivarlo con un 400, se corrige esa opción y se reintenta una sola vez; el requisito se recuerda durante la vida del proceso. Otros errores 400 se propagan sin reintentos de compatibilidad. No se modifica la selección persistida del usuario.

Los presupuestos de historial no son recortes de la fuente actual. La lista completa de tarjetas anteriores se conserva para deduplicación local. La búsqueda de afirmaciones combina señales lexicales y semánticas. Los tokens registrados son los informados por el proveedor, no estimaciones de facturación.

Los suplementos reciben el cuerpo final y un mapa de conceptos/relaciones, sin repetir todas las afirmaciones ni las respuestas históricas en su prompt. El manifiesto íntegro y la lista completa de tarjetas siguen disponibles para validación y persistencia.

## Observabilidad de cada solicitud

Las llamadas reciben contenido en streaming internamente, pero el JSON y Markdown sólo se entregan a los nodos cuando terminan, y se validan antes de guardar. No se persiste ni muestra contenido parcial. Se exige confirmación de finalización: un EOF inesperado, un error en mitad de la respuesta o un límite de salida no se aceptan como nota completa.

`metrics.llm_requests` conserva las últimas 64 solicitudes de la clase: tarea, modelo efectivo, tamaño de entrada, presupuesto, primer evento, primer texto, caracteres de salida, fragmentos recibidos, última actividad y duración. Los estados distinguen espera, generación, respuesta recibida, error y timeout; estos últimos distinguen falta de primer texto, falta de avance y límite total. No se guardan prompts, respuesta parcial ni razonamiento en estos registros. Los caracteres recibidos son progreso, no una estimación de tokens facturados.

Las regeneraciones publican un estado inicial, el primer texto, actualizaciones cada 5 s y el cierre de la llamada. El panel muestra las últimas llamadas por tarea, su modelo, el tope, el primer texto y el avance recibido; el historial de métricas permanece disponible por API. Los snapshots de glosario/flashcards en paralelo se serializan para no sobrescribir información más reciente. Un fallo de telemetría se registra, pero no descarta una respuesta válida.

Los eventos vacíos y comentarios de mantenimiento de conexión no reinician el temporizador de avance. La espera de contenido todavía no permite distinguir por sí sola cola del proveedor, preparación de contexto o razonamiento interno no expuesto. Los contadores de tokens sólo usan el consumo comunicado por el proveedor; las tramas finales repetidas no se suman dos veces. El esquema JSON viaja en el payload de OpenRouter sin activar el stream beta de parsing que puede perder sus tramas de uso. Véase [OpenRouter: Streaming](https://openrouter.ai/docs/api_reference/streaming).

## Reutilización y persistencia

La extracción se reutiliza sólo con una huella vigente de fuentes actuales, curso, título, clases precedentes, sus afirmaciones, historial, modelo configurado y versión. Los artefactos antiguos o entradas cambiadas requieren comparación nueva. Una regeneración sólo de suplementos puede guardar una extracción nueva sin sustituir la evidencia del cuerpo conservado.

La persistencia de cada clase es atómica. Las afirmaciones idénticas conservan IDs y los vectores reales de texto idéntico se reutilizan; el texto cambiado no hereda su vector anterior. El índice de Markdown divide secciones largas en ventanas con solapamiento, en vez de descartar todo después de sus primeros 2000 caracteres. No se reconstruyen automáticamente notas ni índices históricos durante el despliegue.

## Verificación reproducible

```bash
cd backend
uv run python -m unittest discover -s tests -q
RUN_DB_TESTS=1 uv run python -m unittest discover -s tests -q
# Prueba pequeña con API: hay coste, no guarda datos.
uv run python scripts/benchmark_generation.py --live
# Generación completa en lectura: no sustituye la nota ni sus índices.
uv run python scripts/benchmark_generation.py --live --class-id UUID_DE_CLASE
```

Las pruebas cubren separación entre cursos y clases futuras, extracción sin corte de material, invalidación de caché, cancelación real, referencias de fuente, cuotas flexibles, deduplicación, preservación de IDs y madurez, recuperación de formato, reutilización de vectores, presupuestos por tamaño, distinción entre espera/inactividad/límite total, cierre de streams y rechazo de respuestas parciales. La prueba pequeña con API comprueba que se registra teoría repetida, se conserva la aplicación nueva y las evidencias pertenecen literalmente a la fuente.

## Límites que deben permanecer visibles

`reference_checks.py` aporta un conjunto pequeño de referencias oficiales revisadas para errores observados en la evaluación: venta de copias GPL, reconocimiento de licencias permisivas por FSF y bytecode de CPython. Sólo se activa por tema, sin consultas remotas por clase. Se entrega al cuerpo y suplementos como conocimiento de contraste, no como palabras del instructor ni como sustituto de la evidencia original. Es una cobertura limitada de errores conocidos, no un verificador universal. Las referencias son la [FAQ GNU](https://www.gnu.org/licenses/gpl-faq.en.html#DoesTheGPLAllowMoney), la [lista FSF](https://www.gnu.org/licenses/license-list.en.html#ModifiedBSD) y el [glosario Python](https://docs.python.org/3/glossary.html#term-bytecode).

Ninguna validación sintáctica demuestra por sí misma que toda afirmación sea correcta, completa o semánticamente novedosa. Una referencia válida garantiza origen del fragmento, no que la interpretación sea infalible. La comparación depende de la calidad y cobertura del índice histórico; se advierte cuando hay clases anteriores sin afirmaciones. La similitud lexical local de flashcards es un filtro conservador, no una garantía de deduplicación semántica perfecta. No se fuerzan cantidades ni se generan sustitutos de simulación para ocultar fallos.

El soporte de esquemas depende del endpoint y debe validarse localmente, según [OpenRouter: Structured Outputs](https://openrouter.ai/docs/guides/features/structured-outputs). Ocultar razonamiento no reduce por sí solo su consumo: hay que desactivarlo o ajustar su esfuerzo, y algunos modelos lo requieren, como describe [OpenRouter: Reasoning Tokens](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens).
