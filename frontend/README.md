# Frontend

Interfaz de Concat Notes construida con Next.js 16.2.6, React 19.2.4, TypeScript y Tailwind CSS 4. Estado contrastado con el código el 10 de octubre de 2026.

## Navegación

El dock inferior separa seis funciones, en este orden:

- `/notes`: Clases, entrada de fuentes, importación documental, cola y archivo.
- `/my-notes`: colecciones, etiquetas y escritura propia.
- `/flashcards`: biblioteca, filtros, estudio y exportación.
- `/agent`: chat global, alcance por curso y propuestas revisables.
- `/sync`: carpeta montada, cursos y conflictos.
- `/rag`: fragmentos, vectores y mantenimiento del índice.

La barra lateral se reutiliza con herramientas contextuales según la sección.

`/editor/[id]` es el workspace compartido por Clases y Mis notas. Ofrece vista Cornell 1/3–2/3, Markdown derivado, relaciones, revisiones y chat atómico.

### Acomodo de Mis notas

Los **separadores de alineación** dividen cada sección en grupos compartidos por ambas columnas. La columna más larga determina la altura del grupo y ambas empiezan el siguiente a la misma altura. «Añadir separador de alineación» crea un grupo nuevo; para partir celdas existentes, selecciona la primera celda de cada columna que deba bajar y pulsa «Separador antes». Puedes seleccionar una sola columna si sólo quieres bajar sus celdas. El botón de eliminar separador une ambos grupos sin borrar contenido ni relaciones.

Cada grupo tiene sus botones de añadir bloque. El arrastre reordena dentro de una columna y permite trasladar celdas entre grupos de la misma sección, incluso a grupos vacíos; estos muestran «Arrastra una celda aquí». Los separadores se guardan en las revisiones (`composition.grid_rows` y `layout.grid_row`), sin migrar tablas ni exportar líneas adicionales en Markdown. Los resúmenes permanecen al final de la sección.

La vista Cornell usa un grid de dos columnas, con listas de bloques en flujo normal. Los bloques no tienen coordenadas libres ni necesitan alineación manual: al crecer un bloque, los siguientes bajan sin superponerse. El tirador permite reordenar dentro de su columna y sección (ratón, toque o teclado). Resúmenes y secciones conservan sus espacios propios.

Los marcos y encabezados de bloque se sustituyen por controles contextuales al pasar el cursor o enfocar; en móvil permanecen visibles. El menú `…` permite añadir un bloque debajo, adjuntar una imagen o eliminar. El botón de vínculo selecciona bloques para conectar/desconectar y configurar lazos, independientemente del orden.

Las notas antiguas se muestran siguiendo su orden visual guardado, sin migración destructiva. `layout.position_y` se reutiliza como clave ordinal al reordenar; ya no se interpreta como distancia en píxeles. Los IDs, relaciones, contenido e historial se conservan. Markdown, TeX y Mermaid siguen disponibles.

Pruebas del orden: `node --test tests/blockGrid.test.mjs` (Node 22.18+). La prueba de navegador `tests/cornellGrid.browser.mjs` requiere Playwright y permite `MOCK_API=1` para trabajar sin base de datos. Sin ese modo crea y elimina únicamente una nota temporal de prueba.

## Notas

`app/notes/page.tsx` ofrece tres pestañas:

- **Entrada manual:** metadatos, transcripción, resumen, notas propias, código, comandos e imágenes.
- **Importar documento:** PDF/EPUB, notas propias opcionales, alcance completo/capítulos/páginas PDF, perfil y revisión de borradores.
- **Cursos y clases:** selección múltiple y regeneración completa o por componentes con instrucciones adicionales; historial y progreso persistente.

`DocumentImportPanel.tsx` envía las notas propias al confirmar; se guardan en `raw_notes.my_notes`. La extracción nunca crea notas silenciosamente: curso, módulo, clase y Markdown se revisan antes.

Clases genera Markdown clásico con emojis y suplementos; Mis notas usa Cornell. La antigua Metodología de composición no forma parte del generador. Markdown tiene copia y alternancia entre formato renderizado y fuente. El renderer ordena Desarrollo por posición, coloca cada pista relacionada una vez antes del primer desarrollo asociado y deja las pistas sin relación al final de la sección tras un divider, sin etiquetas de columna ni IDs visibles.

El Editor con IA conserva sesiones/mensajes al cerrar la barra, acepta imágenes y ofrece los cuatro modelos de visión. Las propuestas se revisan por operaciones; no equivale al botón de procesar la nota completa. Esquema y editor tienen scroll independiente. Los bloques admiten Markdown, TeX, Mermaid e indentación con tabulador; no incorporan subrayado HTML como sintaxis propia.

## Componentes

| Componente | Función |
|---|---|
| `Sidebar.tsx` | Cola, archivo y navegación por cursos |
| `NoteForm.tsx` | Captura manual y placeholders |
| `DocumentImportPanel.tsx` | Flujo PDF/EPUB y borradores |
| `ClassRegenerationPanel.tsx` | Cursos/clases, trabajos, solicitudes, métricas y fallbacks |
| `ResultPanel.tsx` | Markdown, KaTeX y Mermaid |
| `StudySettingsModal.tsx` | Metas, modelos, densidad, embeddings y backups |
| `CourseReorderModal.tsx` | Orden drag-and-drop |
| `ProcessedNotesModal.tsx` | Avisos del worker automático |
| `NavigationDock.tsx` | Navegación de la suite |
| `CornellBoard.tsx` | Bloques, carriles, selección, arrastre y relaciones |
| `AgentEditorPanel.tsx` | Chat, alcance y aprobación por operación |
| `MarkdownPreview.tsx` | Proyección Markdown reutilizable |
| `SmartMarkdownEditor.tsx` | Edición y previsualización Markdown/TeX/Mermaid |
| `lib/blockGrid.ts` | Orden ordinal y traslado entre grupos de alineación |
| `lib/maintenanceApi.ts` | Cliente de RAG y regeneración |

La comunicación general está en `hooks/useNotesApi.ts`; algunos flujos especializados mantienen un cliente junto al componente. `NEXT_PUBLIC_API_URL` es la URL del backend accesible desde el navegador y queda incorporada durante el build.

## Renderizado y portabilidad

- `marked` renderiza Markdown.
- DOMPurify sanea el HTML producido por el renderizado.
- KaTeX procesa matemáticas.
- Mermaid renderiza diagramas en el cliente.
- Las flashcards preservan sintaxis Markdown portable.
- La interfaz no debe mostrar comentarios internos de persistencia o concatenación.
- Las relaciones se muestran bajo demanda; el lienzo usa flujo vertical sin solapamientos.
- En móvil se alternan los carriles Pistas y Desarrollo.

## Desarrollo

```bash
cd frontend
corepack enable
pnpm install --frozen-lockfile
pnpm dev
pnpm build
```

El build usa modo `standalone`. Antes de modificar APIs de Next.js, consulta `node_modules/next/dist/docs/`, como exige `AGENTS.md`.

El build no verifica disponibilidad de servicios remotos ni corrección semántica de notas. Para acceso remoto privado, véase [Inicio rápido](../README.md#inicio-rápido): abrir sólo el puerto 3000 no resuelve las llamadas client-side al backend ni las imágenes de RustFS.

## Criterios de interfaz

- Explicar decisiones con lenguaje del usuario, no nombres internos.
- Mantener Entrada manual e Importar documento como alternativas claras.
- Mostrar progreso persistente y errores accionables.
- Confirmar borrados, restauraciones, conflictos y costes altos.
- Conservar labels, foco, estados disabled y navegación por teclado.
