# 🖥️ Frontend — Gestor Inteligente de Apuntes

Dashboard interactivo construido con **Next.js 16** y **React 19** para capturar, gestionar y visualizar apuntes de cursos procesados por el agente de IA.

---

## Stack Tecnológico

| Tecnología | Versión | Propósito |
|-----------|---------|-----------|
| **Next.js** | 16.2.6 | Framework React con App Router |
| **React** | 19.2.4 | Biblioteca UI |
| **Tailwind CSS** | 4.x | Sistema de estilos utility-first |
| **Zod** | 4.4.3 | Validación de formularios en runtime |
| **@dnd-kit** | core 6.3 + sortable 10.0 | Drag-and-drop para reordenar notas por curso |
| **marked** | 18.0.5 | Parser de Markdown a HTML del lado del cliente |
| **mermaid** | 11.15.0 | Renderizado reactivo de diagramas en navegador |
| **katex** | 0.17.0 | Renderizado rápido de fórmulas matemáticas TeX/LaTeX |
| **lucide-react** | 1.17.0 | Iconografía SVG |
| **TypeScript** | 5.x | Tipado estático |

---

## Estructura de Archivos

```
frontend/app/
├── page.tsx                      # Página principal (orquesta sidebar, formulario y resultados)
├── layout.tsx                    # Layout global con fuentes (Geist)
├── globals.css                   # Estilos globales Tailwind CSS 4
├── components/
│   ├── Sidebar.tsx               # Sidebar con cola activa, archivo e historial por curso
│   ├── NoteForm.tsx              # Formulario de captura de apuntes (snippets dinámicos)
│   ├── ResultPanel.tsx           # Panel de resultado con Markdown renderizado
│   ├── ConfirmModal.tsx          # Modal de confirmación genérico (eliminar, limpiar)
│   ├── CourseReorderModal.tsx    # Modal de reordenación de notas con drag-and-drop
│   ├── ProcessedNotesModal.tsx   # Modal de notificación de notas procesadas en segundo plano
│   └── TemplateModal.tsx         # Modal de selección de plantillas predefinidas
├── hooks/
│   ├── useNotesApi.ts            # Orquestación de requests HTTP y procesamiento IA
│   ├── useNoteForm.ts            # Estado del formulario y validación Zod
│   └── useModals.ts              # Estado de modales de confirmación
├── schemas/
│   └── noteSchema.ts             # Schema Zod del formulario de notas
└── types/
    └── index.ts                  # Tipos TypeScript compartidos
```

---

## Componentes Principales

### `Sidebar.tsx`
Panel lateral que muestra tres secciones:
- **Cola Activa**: Notas pendientes de procesamiento con opción de editar o eliminar.
- **Archivo**: Notas ya procesadas exitosamente.
- **Historial por Curso**: Agrupación de notas procesadas por nombre de curso con opción de ver el Markdown concatenado y reordenar notas.

### `NoteForm.tsx`
Formulario extenso para captura de apuntes con campos para:
- Metadatos (curso, módulo, profesor, plataforma, modo de escritura)
- Transcripción y resumen de clase (con soporte y ayuda contextual para placeholders de inyección inline)
- Notas personales del alumno
- **Snippets dinámicos** de código (con selector de lenguaje y copiado rápido de placeholder `&"codigo:X"`)
- **Snippets dinámicos** de comandos CLI (con campo de orden de ejecución y copiado rápido de placeholder `&"comando:X"`)
- **Imágenes de apoyo**: Panel interactivo con carga de archivos (JPG, PNG, GIF, WebP), previsualización reactiva, copiado rápido de placeholder `&"imagen:X"` y visualización en tiempo real de la descripción de Gemini.

### `ResultPanel.tsx`
Renderiza el Markdown estructurado generado por el agente, incluyendo los comentarios interactivos (`ai_comments`). Incorpora un botón de previsualización (o ícono de maximizar en móviles) para abrir un modal a pantalla completa con soporte para:
- Renderizado de Markdown vía `marked`.
- Ecuaciones matemáticas en línea (`$`) y en bloque (`$$`) formateadas de forma nativa vía `katex` (con expresiones protegidas para prevenir interferencia de formato).
- Diagramas de flujo y arquitectura generados en caliente del lado del cliente con `mermaid`.

### `CourseReorderModal.tsx`
Modal con drag-and-drop (usando `@dnd-kit/sortable`) para reorganizar el orden de las notas procesadas dentro de un curso. Persiste el orden en el backend via `PUT /api/courses/{name}/reorder`.

### `ProcessedNotesModal.tsx`
Modal que notifica al usuario cuando el worker automático ha terminado de procesar notas en segundo plano. Consulta el endpoint `GET /api/notes/processed-since`.

---

## Hooks Personalizados

### `useNotesApi.ts`
Orquesta toda la comunicación HTTP con el backend:
- CRUD de notas (crear, leer, actualizar, eliminar)
- Subida de archivos de imagen a RustFS (`POST /api/notes/images/upload`)
- Procesamiento con el agente IA (`POST /api/notes/{id}/process`)
- Carga de la cola activa y el archivo
- Detección de notas procesadas en segundo plano

### `useNoteForm.ts`
Gestiona el estado reactivo del formulario y la validación con Zod:
- Estado de todos los campos del formulario (incluyendo la lista de snippets de imágenes de apoyo)
- Manejo de snippets dinámicos de código, comandos e imágenes (agregar, editar, eliminar, actualizar descripción)
- Validación en tiempo real con el schema Zod
- Carga de datos desde una nota existente para edición

### `useModals.ts`
Controla el estado de apertura/cierre de los modales de confirmación y sus callbacks.

---

## Inicio Rápido

```bash
cd frontend
npm install
npm run dev
```

Abre [http://localhost:3000](http://localhost:3000) en tu navegador. El frontend espera el backend corriendo en `http://localhost:8000`.
