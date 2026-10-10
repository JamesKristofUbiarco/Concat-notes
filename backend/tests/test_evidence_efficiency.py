import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.evidence_inputs import source_parts, evidence_pages, evidence_key
from app.knowledge import extract_claims


class EvidenceEfficiencyTests(unittest.TestCase):
    def note(self, **changes):
        fields = dict(id="note", course_name="Curso", class_title="Clase", transcription="Nueva aplicación", processed_note=None)
        fields.update(changes)
        return SimpleNamespace(**fields)

    def test_pages_cover_long_source_once_without_truncation(self):
        text = "a" * 65000 + "FINAL ÚNICO"
        pages = evidence_pages(source_parts(self.note(transcription=text)))
        recovered = "".join(page.split("\n", 1)[1] for page in pages)
        self.assertEqual(recovered, text)
        self.assertGreater(len(pages), 1)

    def test_cache_identity_tracks_sources_history_scope_and_model(self):
        note = self.note()
        parts = source_parts(note)
        base = evidence_key(note, parts, [], {"notes": []}, "model")
        variants = [
            evidence_key(note, [("transcription", "Cambio")], [], {"notes": []}, "model"),
            evidence_key(note, parts, [{"id": "prior", "statement": "Cambio"}], {"notes": []}, "model"),
            evidence_key(note, parts, [], {"notes": ["prior"]}, "model"),
            evidence_key(note, parts, [], {"notes": []}, "other-model"),
        ]
        self.assertTrue(all(key != base for key in variants))

    @patch("app.knowledge.prior_note_ids", return_value=[])
    @patch("app.knowledge.llm_models.resolve_selected_model", return_value=SimpleNamespace(model_id="model"))
    @patch("app.knowledge.GenerationClient")
    def test_preserves_novelty_categories_and_repairs_format(self, create, resolve, prior):
        history = [SimpleNamespace(id="prior", concept="Teoría", statement="Explicada")]
        claims = [{"statement": category, "relation": category, "prior_claim_id": "prior", "evidence_text": "Nueva aplicación"} for category in ["NEW", "REPEATS", "APPLIES", "EXTENDS", "CLARIFIES", "CONTRADICTS"]]
        create.return_value.invoke.side_effect = [SimpleNamespace(content="malformed"), SimpleNamespace(content=json.dumps(claims))]
        metrics, updates = {}, []
        output = extract_claims(self.note(), MagicMock(), history, metrics=metrics, progress=updates.append)
        self.assertEqual([item["novelty_relation"] for item in output], [item["relation"] for item in claims])
        self.assertEqual(metrics["evidence_calls"], 2)
        self.assertEqual(metrics["evidence_format_retries"], 1)
        self.assertGreater(len(updates), 2)

    @patch("app.knowledge.prior_note_ids", return_value=[])
    @patch("app.knowledge.llm_models.resolve_selected_model", return_value=SimpleNamespace(model_id="model"))
    @patch("app.knowledge.GenerationClient")
    def test_cache_reuse_avoids_llm_and_source_change_invalidates(self, create, resolve, prior):
        note = self.note(processed_note=SimpleNamespace(id="processed"))
        key = evidence_key(note, source_parts(note), [], {"notes": [], "claims": []}, "model")
        cached = [{"statement": "Nueva aplicación", "novelty_relation": "APPLIES", "prior_claim_id": None}]
        artifact = SimpleNamespace(metrics={"evidence_cache_key": key}, evidence_manifest={"claims": cached})
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = artifact
        metrics = {}
        output = extract_claims(note, db, [], metrics=metrics)
        create.assert_not_called()
        self.assertTrue(metrics["evidence_cache_hit"])
        output[0]["statement"] = "Mutación"
        self.assertEqual(cached[0]["statement"], "Nueva aplicación")
        note.transcription = "Información distinta"
        create.return_value.invoke.return_value = SimpleNamespace(content='[{"statement":"Información distinta","evidence_text":"Información distinta"}]')
        extract_claims(note, db, [], metrics=metrics)
        create.assert_called_once()
        self.assertFalse(metrics["evidence_cache_hit"])

    @patch("app.knowledge.prior_note_ids", return_value=["prior-note"])
    @patch("app.knowledge.llm_models.resolve_selected_model", return_value=SimpleNamespace(model_id="model"))
    @patch("app.knowledge.GenerationClient")
    def test_change_in_preceding_knowledge_invalidates_cached_novelty(self, create, resolve, prior):
        note = self.note(processed_note=SimpleNamespace(id="processed"))
        key = evidence_key(note, source_parts(note), [], {"notes": ["prior-note"], "claims": [("prior", "Concept", "Old", "NEW")]}, "model")
        artifact = SimpleNamespace(metrics={"evidence_cache_key": key}, evidence_manifest={"claims": [{"statement": "Current", "prior_claim_id": None}]})
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = artifact
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [("prior", "Concept", "Changed", "NEW")]
        create.return_value.invoke.return_value = SimpleNamespace(content='[{"statement":"Current","relation":"REPEATS","evidence_text":"Nueva aplicación"}]')
        metrics = {}
        output = extract_claims(note, db, [], metrics=metrics)
        create.assert_called_once()
        self.assertFalse(metrics["evidence_cache_hit"])
        # A model cannot assert repetition without identifying a valid antecedent.
        self.assertEqual(output[0]["novelty_relation"], "NEW")

    @patch("app.knowledge.prior_note_ids", return_value=[])
    @patch("app.knowledge.llm_models.resolve_selected_model", return_value=SimpleNamespace(model_id="model"))
    @patch("app.knowledge.GenerationClient")
    def test_quotes_are_copied_by_backend_not_generated_by_model(self, create, resolve, prior):
        note = self.note(transcription="El kernel administra recursos. ls -a muestra archivos ocultos.")
        first = [{"statement": "Conservada", "evidence_ref": 0, "evidence_text": "Invented quote"},
                 {"statement": "ls -a muestra archivos ocultos", "evidence_ref": 0}]
        create.return_value.invoke.return_value = SimpleNamespace(content=json.dumps(first))
        metrics = {}
        result = extract_claims(note, MagicMock(), [], metrics=metrics)
        self.assertEqual([item["statement"] for item in result], [item["statement"] for item in first])
        self.assertTrue(all(item["evidence_text"] == note.transcription for item in result))
        self.assertEqual(create.return_value.invoke.call_count, 1)


if __name__ == "__main__":
    unittest.main()
