# Reglas para agentes en el frontend

Este proyecto usa Next.js 16 con App Router, React 19, TypeScript y Tailwind CSS 4. Estas versiones pueden diferir de conocimiento previo.

Antes de cambiar APIs, convenciones o configuración de Next.js, consulta la guía pertinente en `node_modules/next/dist/docs/` y atiende sus avisos de deprecación.

## Arquitectura que debe preservarse

- El dock inferior separa Notas, Flashcards y Sincronización.
- La barra lateral es contextual y reutilizable.
- En Notas, Entrada manual e Importar documento son modos alternativos, no formularios simultáneos.
- Los trabajos largos muestran estado persistente y errores accionables.
- No deben exponerse comentarios internos, IDs técnicos evitables ni secretos.
- Los cambios destructivos, restauraciones, conflictos y costes altos exigen confirmación.

## Verificación mínima

```bash
pnpm build
```

Conservar tipado estricto, labels accesibles, foco visible y diseño responsive.
