## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

## Arquitectura vigente

Consultar [README.md](README.md), [backend](backend/README.md), [frontend](frontend/README.md) y [arquitectura de agentes](docs/agent-architecture.md). Clases genera Markdown clásico; Mis notas mantiene Cornell con grid y relaciones. El agente global, editor atómico, regeneraciones y procesamiento documental tienen contratos distintos.

No versionar credenciales, backups, exportaciones ni `BIG_UPDATE_NOTE_EDITOR_PLAN*.local.md`. Los borradores originales deben permanecer intactos. Graphify es navegación generada, no la fuente de verdad arquitectónica. No borrar volúmenes ni regenerar clases automáticamente durante una actualización documental.
