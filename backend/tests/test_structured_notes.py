import os
import sys
import unittest
import uuid


BACKEND_ROOT = os.path.dirname(os.path.dirname(__file__))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.structured_notes import apply_operations, clean_generated_heading, render_markdown, validate_document


class StructuredNotesTests(unittest.TestCase):
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

    def test_generated_heading_emoji_is_removed(self):
        self.assertEqual(clean_generated_heading("📚  Índices B-tree"), "Índices B-tree")


if __name__ == "__main__":
    unittest.main()
