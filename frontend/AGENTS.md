# Reglas para agentes en el frontend

Este proyecto usa Next.js 16 con App Router, React 19, TypeScript y Tailwind CSS 4. Estas versiones pueden diferir de conocimiento previo.

Antes de cambiar APIs, convenciones o configuración de Next.js, consulta la guía pertinente en `node_modules/next/dist/docs/` y atiende sus avisos de deprecación.

## Arquitectura que debe preservarse

- El dock inferior separa Clases, Mis notas, Flashcards, Agente, Sincronización y RAG, en ese orden.
- La barra lateral es contextual y reutilizable.
- En Clases, Entrada manual e Importar documento son modos alternativos, no formularios simultáneos; Cursos y clases gestiona regeneraciones.
- Clases genera Markdown clásico; Mis notas conserva Cornell con grid, separadores y relaciones. No recuperar acomodo libre ni Metodología de composición.
- Editor atómico y agente global proponen cambios revisables; no describir una propuesta pendiente como aplicada.
- Los trabajos largos muestran estado persistente y errores accionables.
- No deben exponerse comentarios internos, IDs técnicos evitables ni secretos.
- Los cambios destructivos, restauraciones, conflictos y costes altos exigen confirmación.

## Verificación mínima

```bash
pnpm build
```

Conservar tipado estricto, labels accesibles, foco visible y diseño responsive.
