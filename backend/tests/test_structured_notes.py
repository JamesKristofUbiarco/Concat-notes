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
from app.structured_notes import propose_ai_patch, _editor_images, reading_blocks, _recover_editor_response
from app import models


class StructuredNotesTests(unittest.TestCase):
    def test_add_blocks_to_only_empty_section(self):
        document = self.document()
        document["blocks"] = []
        document["relations"] = []
        section_id = document["sections"][0]["id"]
        for lane in ("left", "right"):
            document = apply_operations(document, [{"op": "insert_block", "target_id": section_id, "block": {"type": "markdown", "lane": lane, "content": ""}}])
        self.assertEqual(len(document["sections"]), 1)
        self.assertEqual([b["lane"] for b in document["blocks"]], ["left", "right"])
        self.assertTrue(all(b["section_id"] == section_id for b in document["blocks"]))

    def test_sections_can_be_inserted_explicitly_at_top_and_bottom(self):
        document = self.document()
        document = apply_operations(document, [{"op": "insert_section", "section": {"title": "Primera", "order": 0}}])
        document = apply_operations(document, [{"op": "insert_section", "section": {"title": "Última", "order": 20}}])
        titles = [section["title"] for section in sorted(document["sections"], key=lambda item: item["order"])]
        self.assertEqual(titles, ["Primera", "B-tree", "Última"])

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
        previous = SimpleNamespace(role="assistant", content="Podemos revisar los índices.", scope_json={})
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [previous]
        def flush():
            for call in db.add.call_args_list:
                if isinstance(call.args[0], models.NotePatchProposal):
                    call.args[0].id = uuid.uuid4()
        db.flush.side_effect = flush
        llm = MagicMock()
        llm.bind.return_value = llm
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

    def test_editor_repairs_invalid_json_privately(self):
        llm = MagicMock()
        llm.bind.return_value = llm
        llm.invoke.side_effect = [SimpleNamespace(content='{"summary": "truncado'), SimpleNamespace(content='{"intent":"saludo","summary":"Hola","operations":[]}')]
        document = self.document()
        payload, candidate, repairs, exhausted = _recover_editor_response(llm, [{"role": "user", "content": "Hola"}], document)
        self.assertEqual(payload["summary"], "Hola")
        self.assertEqual(repairs, 1)
        self.assertFalse(exhausted)
        self.assertEqual(len(candidate["blocks"]), len(document["blocks"]))
        correction = llm.invoke.call_args.args[0][-1]["content"]
        self.assertIn("CORRECCIÓN INTERNA", correction)
        self.assertIn("No se ha aplicado", correction)

    def test_editor_repairs_persist_only_one_user_message_and_one_proposal(self):
        db = MagicMock()
        db.get.return_value = SimpleNamespace(document_json=self.document(), current_revision_id=uuid.uuid4())
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        def flush():
            for call in db.add.call_args_list:
                if isinstance(call.args[0], models.NotePatchProposal):
                    call.args[0].id = uuid.uuid4()
        db.flush.side_effect = flush
        llm = MagicMock(); llm.bind.return_value = llm
        llm.invoke.side_effect = ['invalid JSON', '{"intent":"saludo","summary":"Hola","operations":[]}']
        resolved = SimpleNamespace(requested_model="test", model_id="test")
        with patch("app.structured_notes.llm_models.resolve_selected_model", return_value=resolved), patch("app.structured_notes.llm_models.create_chat_model", return_value=llm):
            propose_ai_patch(db, SimpleNamespace(id=uuid.uuid4(), document_id=uuid.uuid4()), SimpleNamespace(content="Hola", scope="whole_note", block_ids=[], image_ids=[], model_id=None))
        persisted = [call.args[0] for call in db.add.call_args_list]
        self.assertEqual(len([row for row in persisted if isinstance(row, models.NotePatchProposal)]), 1)
        self.assertEqual([row.role for row in persisted if isinstance(row, models.NoteEditMessage)], ["user", "assistant"])
        self.assertEqual(db.commit.call_count, 2)

    def test_editor_repairs_invalid_operations_without_applying_partial_changes(self):
        import json
        document = self.document()
        op = {"op": "insert_block", "target_id": document["sections"][0]["id"], "block": {"type": "markdown", "lane": "right", "content": "Fotosíntesis"}}
        llm = MagicMock(); llm.bind.return_value = llm
        llm.invoke.side_effect = [
            json.dumps({"intent": "añadir", "summary": "Propuesta", "operations": [op, {"op": "delete_block", "target_id": str(uuid.uuid4())}]}),
            json.dumps({"intent": "añadir", "summary": "Propongo añadir un bloque", "operations": [op]}),
        ]
        payload, candidate, repairs, exhausted = _recover_editor_response(llm, [], document)
        self.assertEqual(repairs, 1)
        self.assertFalse(exhausted)
        self.assertEqual(len(document["blocks"]), 2)
        self.assertEqual(len(candidate["blocks"]), 3)
        self.assertEqual(len(payload["operations"]), 1)

    def test_editor_recovers_schema_and_scope_violations(self):
        import json
        document = self.document(); target = document["blocks"][0]["id"]
        llm = MagicMock(); llm.bind.return_value = llm
        llm.invoke.side_effect = ['{"intent":"editar","summary":"Cambio","operations":"invalid"}',
            json.dumps({"intent": "editar", "summary": "Cambio", "operations": [{"op": "delete_block", "target_id": document["blocks"][1]["id"]}]}),
            '{"intent":"conversar","summary":"¿Qué quieres cambiar en este bloque?","operations":[]}']
        payload, _, repairs, exhausted = _recover_editor_response(llm, [], document, {target})
        self.assertEqual(repairs, 2)
        self.assertFalse(exhausted)
        self.assertEqual(payload["operations"], [])

    def test_editor_exhaustion_is_safe_and_never_exposes_parser_errors(self):
        llm = MagicMock(); llm.bind.return_value = llm
        llm.invoke.return_value = 'broken'
        document = self.document()
        payload, candidate, _, exhausted = _recover_editor_response(llm, [], document, max_attempts=3)
        self.assertEqual(llm.invoke.call_count, 3)
        self.assertTrue(exhausted)
        self.assertEqual(candidate, document)
        self.assertEqual(payload["operations"], [])
        self.assertNotIn("JSON", payload["summary"])
        self.assertNotIn("vuelve", payload["summary"])

    def test_editor_unsupported_structured_output_uses_same_model(self):
        class Unsupported(Exception):
            status_code = 400
        llm = MagicMock(); constrained = MagicMock(); llm.bind.return_value = constrained
        constrained.invoke.side_effect = Unsupported('unsupported response_format')
        llm.invoke.return_value = '{"intent":"saludo","summary":"Hola","operations":[]}'
        payload, _, _, exhausted = _recover_editor_response(llm, [], self.document())
        self.assertEqual(payload["summary"], "Hola")
        self.assertFalse(exhausted)
        self.assertEqual(llm.invoke.call_count, 1)

    def test_editor_does_not_hide_authentication_failure_as_format_error(self):
        class Unauthorized(Exception):
            status_code = 401
        llm = MagicMock(); llm.bind.return_value = llm
        llm.invoke.side_effect = Unauthorized('invalid credential')
        with self.assertRaises(Unauthorized):
            _recover_editor_response(llm, [], self.document())
        self.assertEqual(llm.invoke.call_count, 1)

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

    def test_development_order_cues_once_and_orphans_last(self):
        document = self.document()
        cue, development = document["blocks"]
        cue["layout"] = {"position_y": 900}
        development["layout"] = {"position_y": 300}
        from copy import deepcopy
        earlier = deepcopy(development)
        earlier.update(id=str(uuid.uuid4()), content="Primer desarrollo", layout={"position_y": 0})
        orphan = deepcopy(cue)
        orphan.update(id=str(uuid.uuid4()), content="Pista suelta", layout={"position_y": 0})
        upper = deepcopy(cue)
        upper.update(id=str(uuid.uuid4()), content="Pista superior", layout={"position_y": 100})
        document["blocks"].extend([earlier, orphan, upper])
        for source, target in [(cue, earlier), (upper, earlier), (upper, development)]:
            document["relations"].append({"id": str(uuid.uuid4()), "from_block_id": target["id"], "to_block_id": source["id"], "type": "explains", "order": 20})
        document["composition"]["reading_order_ids"] = [b["id"] for b in document["blocks"]]
        self.assertEqual([b["id"] for b in reading_blocks(document)], [upper["id"], cue["id"], earlier["id"], development["id"], orphan["id"]])
        markdown = render_markdown(document)
        self.assertEqual(markdown.count("¿Qué acelera un B-tree?"), 1)
        self.assertNotIn("#pistas-preguntas", markdown)
        self.assertNotIn("#desarrollo", markdown)
        self.assertLess(markdown.index("Reduce las páginas"), markdown.index("\n---\n"))
        self.assertGreater(markdown.index("Pista suelta"), markdown.index("\n---\n"))
        self.assertNotIn("Relacionado con:", markdown)
        self.assertNotIn(cue["id"], markdown)

    def test_summary_is_rendered_after_development_and_orphan_cues(self):
        document = self.document()
        section_id = document["sections"][0]["id"]
        document = apply_operations(document, [{"op": "insert_block", "target_id": section_id, "block": {
            "type": "summary", "lane": "right", "reading_order": 1,
            "content": "Resumen final", "layout": {"position_y": 0},
        }}])
        ordered = reading_blocks(document)
        self.assertEqual(ordered[-1]["type"], "summary")
        markdown = render_markdown(document)
        self.assertGreater(markdown.index("Resumen final"), markdown.index("Reduce las páginas"))

    def test_insert_after_does_not_inherit_relations_or_alignment(self):
        document = self.document()
        source = document["blocks"][1]
        source["layout"] = {"position_y": 30, "alignment_group": "group-a"}
        updated = apply_operations(document, [{"op": "insert_after", "target_id": source["id"], "block": {
            "type": "markdown", "lane": "right", "content": "", "layout": {"position_y": 180},
        }}])
        created = updated["blocks"][-1]
        self.assertNotIn("alignment_group", created["layout"])
        self.assertFalse(any(created["id"] in (r["from_block_id"], r["to_block_id"]) for r in updated["relations"]))

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

    def test_grid_reorder_preserves_links_and_development_led_markdown(self):
        document = self.document()
        document["relations"][0]["style"] = {"connector": True, "color": "#818cf8"}
        cue, first = document["blocks"]
        first["layout"]["position_y"] = 0
        second = {**first, "id": str(uuid.uuid4()), "content": "Segundo desarrollo.", "layout": {"position_y": 500}, "reading_order": 30}
        document["blocks"].append(second)
        result = apply_operations(document, [
            {"op": "move_block", "target_id": second["id"], "value": {"layout": {"position_y": 0, "alignment_group": None}}},
            {"op": "move_block", "target_id": first["id"], "value": {"layout": {"position_y": 10, "alignment_group": None}}},
        ])
        self.assertEqual(result["relations"], document["relations"])
        self.assertEqual({b["id"]: b["content"] for b in result["blocks"]}, {b["id"]: b["content"] for b in document["blocks"]})
        rendered = render_markdown(result)
        self.assertLess(rendered.index("Segundo desarrollo."), rendered.index(cue["content"]))
        self.assertLess(rendered.index(cue["content"]), rendered.index(first["content"]))

    def test_grid_separator_is_visual_only_and_revision_round_trips(self):
        document = self.document()
        section = document["sections"][0]["id"]
        row = str(uuid.uuid4())
        before = render_markdown(document)
        operations = [{"op": "set_grid_rows", "target_id": section, "value": [row]}]
        operations += [{"op": "move_block", "target_id": b["id"], "value": {"layout": {**b["layout"], "grid_row": row}}} for b in document["blocks"]]
        result = apply_operations(document, operations)
        self.assertEqual(render_markdown(result), before)
        self.assertEqual(result["composition"]["grid_rows"][section], [row])
        self.assertTrue(all(b["layout"]["grid_row"] == row for b in validate_document(result)["blocks"]))
        merged = apply_operations(result, [{"op": "set_grid_rows", "target_id": section, "value": []}])
        self.assertEqual(render_markdown(merged), before)
        self.assertEqual(len(merged["blocks"]), len(document["blocks"]))
        self.assertEqual(merged["relations"], result["relations"])

    def test_grid_insert_after_inherits_only_visual_group(self):
        document = self.document(); section = document["sections"][0]["id"]; row = str(uuid.uuid4())
        document["composition"]["grid_rows"] = {section: [row]}
        document["blocks"][1]["layout"]["grid_row"] = row
        result = apply_operations(document, [{"op": "insert_after", "target_id": document["blocks"][1]["id"], "block": {"type": "markdown", "lane": "right", "content": "Nueva celda"}}])
        new = next(b for b in result["blocks"] if b["content"] == "Nueva celda")
        self.assertEqual(new["layout"]["grid_row"], row)
        self.assertFalse(new["layout"].get("alignment_group"))
        self.assertEqual(len(result["relations"]), 1)

    def test_grid_rejects_invalid_separator_list(self):
        document = self.document(); section = document["sections"][0]["id"]
        for value in [["a", "a"], ["start"], [12], "not a list"]:
            with self.assertRaises(ValueError):
                apply_operations(document, [{"op": "set_grid_rows", "target_id": section, "value": value}])

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
