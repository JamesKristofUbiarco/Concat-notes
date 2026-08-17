import os
import sys
import unittest


BACKEND_ROOT = os.path.dirname(os.path.dirname(__file__))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.deck_names import canonical_deck_tag, has_canonical_deck, normalize_flashcard_deck


class CanonicalDeckTests(unittest.TestCase):
    course = "Introduction to TensorFlow for Artificial Intelligence, Machine Learning, and Deep Learning"
    module = "Week 1 - A new programming paradigm"

    def test_canonical_tag_comes_only_from_authoritative_metadata(self):
        self.assertEqual(
            canonical_deck_tag(self.course, self.module),
            "#flashcards/IntroductionToTensorFlowForArtificialIntelligenceMachineLearningAndDeepLearning/Week1ANewProgrammingParadigm",
        )

    def test_replaces_model_variant_without_touching_cards(self):
        source = """## 🗃️ Flashcards
#flashcards/IntroToTensorFlow/Week1NewProgrammingParadigm

Pregunta::Respuesta
"""
        result = normalize_flashcard_deck(source, self.course, self.module)
        self.assertIn(canonical_deck_tag(self.course, self.module), result)
        self.assertIn("Pregunta::Respuesta", result)
        self.assertNotIn("#flashcards/IntroToTensorFlow/", result)
        self.assertTrue(has_canonical_deck(result, self.course, self.module))

    def test_inserts_missing_tag_and_removes_duplicates(self):
        source = """## 🗃️ Flashcards
#flashcards/Uno/Uno
#flashcards/Dos/Dos
Pregunta::Respuesta
"""
        result = normalize_flashcard_deck(source, self.course, self.module)
        self.assertEqual(result.count("#flashcards/"), 1)
        self.assertTrue(has_canonical_deck(result, self.course, self.module))


if __name__ == "__main__":
    unittest.main()
