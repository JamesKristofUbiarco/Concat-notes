import os
import sys
import unittest
from types import SimpleNamespace


BACKEND_ROOT = os.path.dirname(os.path.dirname(__file__))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.knowledge import build_source_chunks, parse_flashcards


class KnowledgeMemoryTests(unittest.TestCase):
    def note(self, **overrides):
        values = {
            "transcription": "Una frase. " * 300,
            "my_notes": "detalle propio",
            "class_summary": "resumen",
            "code_snippets": [{"lang": "python", "code": "print('ok')"}],
            "command_snippets": [{"lang": "bash", "cmd": "echo ok"}],
            "images": [SimpleNamespace(descripcion_llm="diagrama de flujo")],
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_source_chunks_cover_original_sources_and_are_bounded(self):
        chunks = build_source_chunks(self.note())
        source_types = {item["source_type"] for item in chunks}
        self.assertTrue({"transcription", "my_notes", "summary", "code", "command", "image"} <= source_types)
        self.assertTrue(all(len(item["content"]) <= 1600 for item in chunks if item["source_type"] == "transcription"))
        self.assertEqual(len({item["content_hash"] for item in chunks}), len(chunks))

    def test_flashcards_parse_single_multiline_and_cloze(self):
        markdown = """# Nota
## 🗃️ Flashcards
#flashcards/Curso/Modulo

Pregunta uno::Respuesta uno

Pregunta dos
?
Respuesta dos

La ==respuesta tres== está oculta.

## 🧠 Zona
Fuera::No cuenta
"""
        cards = parse_flashcards(markdown)
        self.assertEqual(len(cards), 3)
        self.assertEqual(cards[0]["question"], "Pregunta uno")
        self.assertEqual(cards[1]["answer"], "Respuesta dos")
        self.assertEqual(cards[2]["answer"], "respuesta tres")


if __name__ == "__main__":
    unittest.main()
