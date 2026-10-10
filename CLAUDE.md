## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

## Fuente de contexto

Seguir también [AGENTS.md](AGENTS.md). La arquitectura vigente está en [README.md](README.md) y [docs/agent-architecture.md](docs/agent-architecture.md), no en borradores privados ni informes históricos. Clases genera Markdown clásico; Mis notas usa un grid Cornell. No versionar secretos, respaldos o planes `.local.md`, ni eliminar volúmenes al actualizar.
