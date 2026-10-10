import os
import sys
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch


BACKEND_ROOT = os.path.dirname(os.path.dirname(__file__))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.v2_agent import BODY_SYSTEM, ensure_visible_class_header, invoke_synthesis, validate_body_markdown
from app import llm_models
from app.worker import generate_note_state


class VisibleClassHeaderTests(unittest.TestCase):
    def test_processed_note_prompt_uses_classic_markdown_not_cornell_json(self):
        self.assertIn("## 🗺️ Contexto Inicial (Fase 1)", BODY_SYSTEM)
        self.assertIn("## 📝 Apuntes de Clase (Captura Híbrida)", BODY_SYSTEM)
        self.assertIn("preserva", BODY_SYSTEM.lower())
        self.assertNotIn("Cornell", BODY_SYSTEM)
        self.assertNotIn('"sections"', BODY_SYSTEM)

    def note(self):
        return SimpleNamespace(
            class_title="7. Tipos de Datos",
            course_name="Máster Completo Python de cero a experto",
            teacher="Andrés Guzmán",
            course_module="Section 1: Introducción",
            platform="Udemy",
            created_at=datetime(2026, 7, 31, 6, 34, tzinfo=timezone.utc),
        )

    def test_header_is_inserted_after_frontmatter(self):
        result = ensure_visible_class_header("---\ncreated: 2026-07-31\n---\n\n## Contenido\nTexto", self.note())
        self.assertIn("---\n\n# 📚 7. Tipos de Datos", result)
        self.assertIn("**Curso:** [[Máster Completo Python de cero a experto]]", result)
        self.assertIn("**Módulo:** Section 1: Introducción", result)
        self.assertIn("**Instructor:** Andrés Guzmán | **Plataforma:** Udemy", result)
        self.assertLess(result.index("# 📚 7."), result.index("## Contenido"))

    def test_existing_visible_header_is_replaced_not_duplicated(self):
        source = """---
fecha: 2026-07-31
---
# Encabezado inventado
**Curso:** Otro
**Instructor/Autor:** Otro | **Módulo del curso:** Otro
**Fecha de clase:** 2000-01-01

## Contenido
Texto
"""
        result = ensure_visible_class_header(source, self.note())
        self.assertEqual(result.count("# 📚 7. Tipos de Datos"), 1)
        self.assertNotIn("# Encabezado inventado", result)
        self.assertNotIn("**Curso:** Otro", result)
        self.assertEqual(result.count("## Contenido"), 1)

    def test_generated_header_uses_benchmark_frontmatter(self):
        result = ensure_visible_class_header("## 🗺️ Contexto Inicial (Fase 1)\nContenido", self.note())
        self.assertTrue(result.startswith("---\ntipo: fuente\nformato: curso_online\nestado: en_proceso\nfecha: 2026-07-31\n---"))
        self.assertEqual(result.count("# 📚 7. Tipos de Datos"), 1)

    def test_body_validator_accepts_real_code_and_rejects_simulation(self):
        body = """## 🗺️ Contexto Inicial (Fase 1)
Se comparan cuatro maneras de crear una lista.
## 📝 Apuntes de Clase (Captura Híbrida)
### 📌 1. Construcción de listas
```python
values = [n for n in range(10)]
```
"""
        self.assertEqual(validate_body_markdown("````markdown\n" + body + "````"), body.strip())
        self.assertEqual(validate_body_markdown("---\nfecha: 2026-09-30\n---\n# Título extra\n**Curso:** Curso\n\n" + body), body.strip())
        with self.assertRaisesRegex(ValueError, "simulación"):
            validate_body_markdown(body + "\nLa Directiva E de Synapse Scholar exige una simulación.")
        with self.assertRaisesRegex(ValueError, "sin cerrar"):
            validate_body_markdown(body + "\n```python\nprint('incompleto')")


class PipelineFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_v2_failure_does_not_archive_legacy_simulation(self):
        note = SimpleNamespace(id="class-id", writing_mode="", platform="", course_name="Curso",
                               teacher="", course_module="", class_title="Clase", transcription="",
                               class_summary="", my_notes="", code_snippets=[], command_snippets=[])
        with patch("app.worker.invoke_agent_in_thread", side_effect=RuntimeError("OpenRouter 429")) as invoke:
            with self.assertRaisesRegex(RuntimeError, "429"):
                await generate_note_state(note, "v2")
        self.assertEqual(invoke.call_count, 1)


class SynthesisFallbackTests(unittest.TestCase):
    def test_rate_limit_uses_another_configured_synthesis_model(self):
        selected = llm_models.resolve_model("synthesis", "qwen/qwen3.8-flash",
                                             environ={"OPENROUTER_API_KEY": "test"}, allow_fallback=False)
        primary = SimpleNamespace(invoke=lambda _: (_ for _ in ()).throw(RuntimeError("Error code: 429")))
        alternate = SimpleNamespace(invoke=lambda _: SimpleNamespace(content="## 🗺️ Contexto Inicial (Fase 1)"))
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test"}), patch(
            "app.v2_agent.GenerationClient", side_effect=[primary, alternate]
        ):
            output, effective = invoke_synthesis(["prompt"], selected)
        self.assertEqual(output.content, "## 🗺️ Contexto Inicial (Fase 1)")
        self.assertEqual(effective.model_id, "google/gemini-3.8-flash")
        self.assertTrue(effective.fallback_used)
        self.assertEqual(effective.requested_model, "qwen/qwen3.8-flash")


if __name__ == "__main__":
    unittest.main()
