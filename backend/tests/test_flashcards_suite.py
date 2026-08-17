import csv
import io
import os
import sys
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4


BACKEND_ROOT = os.path.dirname(os.path.dirname(__file__))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.flashcards import _replace_in_markdown, _schedule_values, anki_export, csv_export, fingerprint, maturity, review_options


class FlashcardSuiteTests(unittest.TestCase):
    def row(self):
        card = SimpleNamespace(
            id=uuid4(), question="¿Qué es state?", answer="Datos internos.",
            learning_state="new", due_at=None,
        )
        note = SimpleNamespace(
            course_name="Aprende React desde cero", course_module="Módulo 1",
            class_title="Introducción al state",
        )
        return card, note

    def test_fingerprint_ignores_case_and_repeated_spaces(self):
        self.assertEqual(fingerprint("  Qué   ES State "), fingerprint("qué es state"))

    def test_edit_keeps_native_markdown_syntax(self):
        source = "## 🗃️ Flashcards\n#flashcards/Curso/Modulo\n\nPregunta::Respuesta\n"
        result = _replace_in_markdown(source, "Pregunta", "Respuesta", "Pregunta nueva", "Respuesta nueva")
        self.assertIn("Pregunta nueva::Respuesta nueva", result)
        self.assertIn("#flashcards/Curso/Modulo", result)

    def test_edit_preserves_reversible_syntax_from_either_side(self):
        source = "## 🗃️ Flashcards\nAnverso:::Reverso\n"
        forward = _replace_in_markdown(source, "Anverso", "Reverso", "Frente", "Atrás")
        reverse = _replace_in_markdown(source, "Reverso", "Anverso", "Atrás", "Frente")
        self.assertIn("Frente:::Atrás", forward)
        self.assertIn("Frente:::Atrás", reverse)

    def test_csv_export_contains_portable_metadata(self):
        payload = csv_export([self.row()]).decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(payload)))
        self.assertEqual(rows[0][0:3], ["course", "module", "class"])
        self.assertEqual(rows[1][3:5], ["¿Qué es state?", "Datos internos."])

    def test_anki_export_is_a_real_package(self):
        payload = anki_export([self.row()])
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            self.assertTrue(any(name.startswith("collection.anki2") for name in archive.namelist()))

    def test_again_schedules_relearning_in_ten_minutes(self):
        card = SimpleNamespace(learning_state="review", interval_days=30, ease_factor=2.5, repetitions=4, lapses=1)
        now = datetime.now(timezone.utc)
        schedule = _schedule_values(card, 1, now)
        self.assertEqual(schedule["interval"], 6)
        self.assertEqual(schedule["due_at"], now + timedelta(minutes=10))
        self.assertEqual(schedule["new_state"], "learning")

    def test_review_options_explain_meaning_and_real_interval(self):
        card = SimpleNamespace(learning_state="new", interval_days=0, ease_factor=2.5, repetitions=0, lapses=0)
        options = review_options(card)
        self.assertEqual([option["label"] for option in options], ["Otra vez", "Difícil", "Bien", "Fácil"])
        self.assertEqual(options[0]["due_label"], "10 min")
        self.assertEqual(options[1]["due_label"], "30 min")
        self.assertEqual(options[2]["due_label"], "1 día")
        self.assertEqual(options[3]["due_label"], "4 días")
        self.assertEqual(options[0]["meaning"], "No la recordé")

    def test_review_intervals_grow_with_card_maturity(self):
        card = SimpleNamespace(learning_state="review", interval_days=30, ease_factor=2.5, repetitions=5, lapses=0)
        now = datetime.now(timezone.utc)
        self.assertEqual(_schedule_values(card, 2, now)["interval"], 36)
        self.assertEqual(_schedule_values(card, 3, now)["interval"], 75)
        self.assertEqual(_schedule_values(card, 4, now)["interval"], 98)
        self.assertEqual(maturity(card), "mature")


if __name__ == "__main__":
    unittest.main()
