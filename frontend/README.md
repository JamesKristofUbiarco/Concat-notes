# Frontend

Interfaz de Concat Notes construida con Next.js 16, React 19, TypeScript y Tailwind CSS 4.

## Navegación

El dock inferior separa cuatro funciones:

- `/notes`: Clases, entrada de fuentes, importación documental, cola y archivo.
- `/my-notes`: colecciones, etiquetas y escritura propia.
- `/flashcards`: biblioteca, filtros, estudio y exportación.
- `/sync`: carpeta montada, cursos y conflictos.

La barra lateral se reutiliza con herramientas contextuales según la sección.

`/editor/[id]` es el workspace compartido por Clases y Mis notas. Ofrece vista Cornell 1/3–2/3, Markdown derivado, relaciones, revisiones y chat atómico.

## Notas

`app/notes/page.tsx` ofrece dos modos excluyentes:

- **Entrada manual:** metadatos, transcripción, resumen, notas propias, código, comandos e imágenes.
- **Importar documento:** PDF/EPUB, notas propias opcionales, alcance completo/capítulos/páginas PDF, perfil y revisión de borradores.

`DocumentImportPanel.tsx` envía las notas propias al confirmar; se guardan en `raw_notes.my_notes`. La extracción nunca crea notas silenciosamente: curso, módulo, clase y Markdown se revisan antes.

## Componentes

| Componente | Función |
|---|---|
| `Sidebar.tsx` | Cola, archivo y navegación por cursos |
| `NoteForm.tsx` | Captura manual y placeholders |
| `DocumentImportPanel.tsx` | Flujo PDF/EPUB y borradores |
| `ResultPanel.tsx` | Markdown, KaTeX y Mermaid |
| `StudySettingsModal.tsx` | Metas, modelos, densidad, embeddings y backups |
| `CourseReorderModal.tsx` | Orden drag-and-drop |
| `ProcessedNotesModal.tsx` | Avisos del worker automático |
| `NavigationDock.tsx` | Navegación de la suite |
| `CornellBoard.tsx` | Bloques, carriles, selección, arrastre y relaciones |
| `AgentEditorPanel.tsx` | Chat, alcance y aprobación por operación |
| `MarkdownPreview.tsx` | Proyección Markdown reutilizable |

La comunicación general está en `hooks/useNotesApi.ts`; algunos flujos especializados mantienen un cliente junto al componente. `NEXT_PUBLIC_API_URL` es la URL del backend accesible desde el navegador y queda incorporada durante el build.

## Renderizado y portabilidad

- `marked` renderiza Markdown.
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

## Criterios de interfaz

- Explicar decisiones con lenguaje del usuario, no nombres internos.
- Mantener Entrada manual e Importar documento como alternativas claras.
- Mostrar progreso persistente y errores accionables.
- Confirmar borrados, restauraciones, conflictos y costes altos.
- Conservar labels, foco, estados disabled y navegación por teclado.
