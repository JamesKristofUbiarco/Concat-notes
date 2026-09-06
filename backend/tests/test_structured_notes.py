import os
import sys
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


BACKEND_ROOT = os.path.dirname(os.path.dirname(__file__))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.structured_notes import apply_operations, clean_generated_heading, render_markdown, validate_document
from app.structured_notes import propose_ai_patch, _editor_images
from app import models


class StructuredNotesTests(unittest.TestCase):
    def test_editor_attachment_is_sent_as_image_content(self):
        db = MagicMock()
        db.get.return_value = SimpleNamespace(filename="example.png")
        with patch("app.storage.download_file_from_rustfs", return_value=b"image-bytes"):
            parts = _editor_images(db, [uuid.uuid4()])
        self.assertEqual(parts[0]["type"], "image_url")
        self.assertEqual(parts[0]["image_url"]["url"], "data:image/png;base64,aW1hZ2UtYnl0ZXM=")

    def test_editor_accepts_conversation_and_sends_history(self):
        db = MagicMock()
        revision = uuid.uuid4()
        db.get.return_value = SimpleNamespace(document_json=self.document(), current_revision_id=revision)
        previous = SimpleNamespace(role="assistant", content="Podemos revisar los índices.")
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [previous]
        def flush():
            for call in db.add.call_args_list:
                if isinstance(call.args[0], models.NotePatchProposal):
                    call.args[0].id = uuid.uuid4()
        db.flush.side_effect = flush
        llm = MagicMock()
        llm.invoke.return_value = SimpleNamespace(content='{"intent":"saludo","summary":"Hola, ¿en qué te ayudo?","operations":[]}')
        resolved = SimpleNamespace(requested_model="test", model_id="test")
        with patch("app.structured_notes.llm_models.resolve_selected_model", return_value=resolved), patch("app.structured_notes.llm_models.create_chat_model", return_value=llm):
            proposal = propose_ai_patch(db, SimpleNamespace(id=uuid.uuid4(), document_id=uuid.uuid4()), SimpleNamespace(content="Hola", scope="whole_note", block_ids=[], image_ids=[], model_id=None))
        self.assertEqual(proposal.operations, [])
        self.assertEqual(proposal.base_revision_id, revision)
        self.assertEqual(llm.invoke.call_args.args[0][1]["content"], previous.content)
        assistant = db.add.call_args_list[-1].args[0]
        self.assertEqual(assistant.scope_json["proposal_id"], str(proposal.id))
        self.assertNotEqual(assistant.scope_json["proposal_id"], "None")

    def document(self):
        section_id = str(uuid.uuid4())
        question_id = str(uuid.uuid4())
        answer_id = str(uuid.uuid4())
        return {
            "schema_version": "1.0",
            "document_id": str(uuid.uuid4()),
            "origin": {"kind": "manual_independent", "raw_note_id": None},
            "metadata": {"title": "Índices", "course_name": "Bases de Datos", "tags": []},
            "composition": {"profile_slug": "cornell-conceptual"},
            "sections": [{"id": section_id, "title": "B-tree", "order": 10}],
            "blocks": [
                {"id": question_id, "section_id": section_id, "type": "question", "lane": "left", "reading_order": 10, "content": "¿Qué acelera un B-tree?", "layout": {"gap_before": 0}, "sources": []},
                {"id": answer_id, "section_id": section_id, "type": "paragraph", "lane": "right", "reading_order": 20, "content": "Reduce las páginas inspeccionadas.", "layout": {"gap_before": 0}, "sources": []},
            ],
            "relations": [{"id": str(uuid.uuid4()), "from_block_id": question_id, "to_block_id": answer_id, "type": "answers", "order": 10}],
        }

    def test_renderer_emits_each_related_block_once(self):
        document = self.document()
        markdown = render_markdown(document)
        self.assertEqual(markdown.count("¿Qué acelera un B-tree?"), 1)
        self.assertEqual(markdown.count("Reduce las páginas inspeccionadas."), 1)
        self.assertNotIn("concat-notes", markdown)
        self.assertIn("\n# B-tree\n", markdown)
        self.assertLess(markdown.index("Reduce las páginas"), markdown.index("\n---\n"))
        self.assertLess(markdown.index("\n---\n"), markdown.index("¿Qué acelera"))

    def test_markdown_h1_splits_sections_but_fenced_code_does_not(self):
        document = self.document()
        block = document["blocks"][1]
        block["type"] = "markdown"
        updated = apply_operations(document, [{"op": "replace_text", "target_id": block["id"], "value": "Antes\n# Nuevo\nDespués\n```python\n# comentario\n```\n# Final\nFin"}])
        self.assertEqual([s["title"] for s in updated["sections"]], ["B-tree", "Nuevo", "Final"])
        self.assertEqual(updated["blocks"][1]["content"], "Antes")
        self.assertIn("# comentario", updated["blocks"][2]["content"])
        self.assertEqual(updated["blocks"][3]["content"], "Fin")

    def test_replace_text_is_atomic(self):
        document = self.document()
        target = document["blocks"][1]["id"]
        updated = apply_operations(document, [{"op": "replace_text", "target_id": target, "value": {"old": "páginas", "new": "páginas de disco"}}])
        self.assertEqual(updated["blocks"][0]["content"], document["blocks"][0]["content"])
        self.assertIn("páginas de disco", updated["blocks"][1]["content"])

    def test_replace_block_accepts_content_shorthand_without_losing_structure(self):
        document = self.document()
        target = document["blocks"][1]["id"]
        updated = apply_operations(document, [{"op": "replace_block", "target_id": target, "value": "Nueva explicación."}])
        self.assertEqual(updated["blocks"][1]["content"], "Nueva explicación.")
        self.assertEqual(updated["blocks"][1]["section_id"], document["blocks"][1]["section_id"])
        self.assertEqual(updated["blocks"][1]["sources"], document["blocks"][1]["sources"])

    def test_delete_block_removes_dangling_relations(self):
        document = self.document()
        target = document["blocks"][1]["id"]
        updated = apply_operations(document, [{"op": "delete_block", "target_id": target}])
        self.assertEqual(updated["relations"], [])

    def test_invalid_relation_is_rejected(self):
        document = self.document()
        document["relations"][0]["to_block_id"] = str(uuid.uuid4())
        with self.assertRaisesRegex(ValueError, "inexistente"):
            validate_document(document)

    def test_connector_style_survives_validation(self):
        document = self.document()
        document["relations"][0]["style"] = {"connector": True, "color": "#22d3ee"}
        validated = validate_document(document)
        self.assertEqual(validated["relations"][0]["style"], {"connector": True, "color": "#22d3ee"})

    def test_generated_heading_emoji_is_removed(self):
        self.assertEqual(clean_generated_heading("📚  Índices B-tree"), "Índices B-tree")


if __name__ == "__main__":
    unittest.main()
