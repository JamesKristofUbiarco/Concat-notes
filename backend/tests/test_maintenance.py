import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app.regeneration import markdown_parts, generate_selection, content_digest


ORIGINAL = """---
tipo: fuente
---
# 📚 Clase
## 🗺️ Contexto Inicial (Fase 1)
Contexto original.
## 📝 Apuntes de Clase (Captura Híbrida)
### 📌 Código
```markdown
## 🗃️ Flashcards
Esta línea pertenece a código.
```

## 📖 Conceptos Clave (Glosario)
**Algorithm** #definicion
Definición original.

## 🗃️ Flashcards
#flashcards/curso/modulo
Pregunta::Respuesta

## 🧠 Zona de Procesamiento (Fase 2: Deconstrucción)
* [[Algorithm]]
"""


class SelectiveRegenerationTests(unittest.TestCase):
    def test_markdown_boundaries_ignore_code_fences_and_reassemble_losslessly(self):
        parts = markdown_parts(ORIGINAL)
        self.assertIn("Esta línea pertenece a código.", parts["content"])
        self.assertNotIn("Esta línea pertenece a código.", parts["flashcards"])
        self.assertEqual("".join(parts.values()), ORIGINAL)

    def test_only_cards_are_generated_and_other_sections_are_preserved(self):
        note = SimpleNamespace(id="note-id", processed_note=SimpleNamespace(structured_markdown=ORIGINAL))
        with patch("app.regeneration.agent.context_node"), patch("app.regeneration.agent.evidence_node"), patch("app.regeneration.agent.knowledge_model_node"), patch("app.regeneration.llm_models.resolve_selected_model"), patch("app.regeneration.llm_models.create_chat_model"), patch("app.regeneration.agent.body_node") as body, patch("app.regeneration.agent._glossary_call") as glossary, patch("app.regeneration.agent._flashcard_call", return_value="## 🗃️ Flashcards\nNueva::Respuesta nueva") as cards:
            state = generate_selection(MagicMock(), note, ["flashcards"], "Preguntas más específicas")
        parts = markdown_parts(state["structured_markdown"])
        original = markdown_parts(ORIGINAL)
        for component in ("content", "glossary", "processing"):
            self.assertEqual(parts[component], original[component])
        body.assert_not_called()
        glossary.assert_not_called()
        cards.assert_called_once()
        self.assertEqual(state["additional_instructions"], "Preguntas más específicas")

    def test_snapshot_detects_changes_to_sources_and_output(self):
        note = SimpleNamespace(**{key: "" for key in ("course_name", "class_title", "course_module", "teacher", "platform", "writing_mode", "transcription", "my_notes", "class_summary")}, code_snippets=[], command_snippets=[], flashcard_target=None, images=[], processed_note=SimpleNamespace(structured_markdown=ORIGINAL))
        before = content_digest(note)
        note.transcription = "Cambio del usuario"
        self.assertNotEqual(content_digest(note), before)
        before = content_digest(note)
        note.processed_note.structured_markdown += "\nEdición"
        self.assertNotEqual(content_digest(note), before)
