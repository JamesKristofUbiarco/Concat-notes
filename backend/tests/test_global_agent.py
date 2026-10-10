import asyncio
import json
import os
import sys
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from sqlalchemy.orm import Session
from app import models
from app.agent_workspace import WorkspaceTools, replace_occurrence, update_card_source, apply_frames
from app.global_agent import run_agent
from test_maintenance import ORIGINAL
import test_maintenance_db as maintenance_tests


class AgentTextTests(unittest.TestCase):
    def test_replaces_only_the_requested_duplicate_occurrence(self):
        self.assertEqual(replace_occurrence("A B A", "A", "", 1), "A B ")
        with self.assertRaises(ValueError):
            replace_occurrence("A", "X", "Y")

    def test_card_change_leaves_matching_example_in_code_untouched(self):
        source = "# Nota\n```md\n## 🗃️ Flashcards\nPregunta::Respuesta\n```\n\n## 🗃️ Flashcards\nPregunta::Respuesta\n"
        card = SimpleNamespace(id=uuid.uuid4(), question="Pregunta", answer="Respuesta")
        edited = update_card_source(source, card, "Nueva pregunta", r"Ruta C:\new\test")
        self.assertIn("Pregunta::Respuesta\n```", edited)
        self.assertIn(r"Nueva pregunta::Ruta C:\new\test", edited)
        removed = update_card_source(source, card, delete=True)
        self.assertIn("Pregunta::Respuesta\n```", removed)
        self.assertNotIn("Pregunta::Respuesta", removed.split("```", 2)[-1])

    def test_cancelled_run_does_not_persist_a_late_model_response(self):
        run = SimpleNamespace(id=uuid.uuid4(), status="pending", progress="", user_message_id=uuid.uuid4(), conversation_id=uuid.uuid4(), model_id="google/gemini-3.8-flash", scope={})
        user = SimpleNamespace(id=run.user_message_id, content="Hola", attachments=[])
        conversation = SimpleNamespace(title="Mi conversación", title_is_manual=True)
        db = MagicMock()
        db.get.side_effect = lambda model, _id: {models.AgentRun: run, models.AgentMessage: user, models.AgentConversation: conversation}[model]
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        db.query.return_value.filter_by.return_value.with_for_update.return_value.one_or_none.return_value = run
        async def late_reply(_messages):
            run.status = "cancelled"
            return SimpleNamespace(content=json.dumps({"reply": "Respuesta que llegó tarde", "actions": []}))
        llm = SimpleNamespace(ainvoke=late_reply)
        with patch("app.global_agent.SessionLocal", return_value=db), patch("app.global_agent.llm_models.resolve_model"), patch("app.global_agent.llm_models.create_chat_model", return_value=llm):
            asyncio.run(run_agent(run.id))
        db.add.assert_not_called()
        self.assertEqual(run.status, "cancelled")


@unittest.skipUnless(os.getenv("RUN_DB_TESTS") == "1", "Requiere PostgreSQL y RUN_DB_TESTS=1")
class GlobalAgentDatabaseTests(unittest.TestCase):
    setUp = maintenance_tests.MaintenanceDatabaseTests.setUp
    tearDown = maintenance_tests.MaintenanceDatabaseTests.tearDown

    def send(self, conversation_id, content="Hola"):
        with patch("app.global_agent_routes.llm_models.resolve_model"):
            response = self.client.post(f"/api/agent/conversations/{conversation_id}/messages", json={"content": content, "model_id": "google/gemini-3.8-flash"})
        self.assertEqual(response.status_code, 202, response.text)
        return uuid.UUID(response.json()["id"])

    def test_persistent_history_manual_title_and_pending_cancel(self):
        created = self.client.post("/api/agent/conversations")
        self.assertEqual(created.status_code, 201)
        conversation_id = created.json()["id"]
        run_id = self.send(conversation_id)
        response = self.client.get(f"/api/agent/conversations/{conversation_id}")
        self.assertEqual(response.json()["messages"][0]["content"], "Hola")
        self.client.patch(f"/api/agent/conversations/{conversation_id}", json={"title": "Mi conversación"})
        self.assertTrue(self.db.get(models.AgentConversation, uuid.UUID(conversation_id)).title_is_manual)
        self.assertEqual(self.client.post(f"/api/agent/runs/{run_id}/cancel").json()["status"], "cancelled")
        self.assertEqual(self.client.delete(f"/api/agent/conversations/{conversation_id}").status_code, 204)
        self.assertIsNone(self.db.get(models.AgentRun, run_id))
        self.assertEqual(self.processed.structured_markdown, ORIGINAL)

    def test_proposals_require_inspection_and_detect_concurrent_edits(self):
        tools = WorkspaceTools(self.db, {"course": self.note.course_name})
        action = {"op": "replace_note_text", "note_id": str(self.note.id), "old": "Contexto original.", "new": "Contexto mejorado."}
        with self.assertRaises(ValueError):
            tools.prepare([action])
        tools.call("get_note", {"note_id": str(self.note.id)})
        frames = tools.prepare([action])
        self.assertEqual(self.processed.structured_markdown, ORIGINAL)
        self.processed.structured_markdown += "\nCambio posterior del usuario"
        self.db.flush()
        with self.assertRaises(ValueError):
            apply_frames(self.db, frames)
        self.assertNotIn("Contexto mejorado.", self.processed.structured_markdown)

    def test_approved_note_edit_updates_only_target_and_preserves_card_progress(self):
        tools = WorkspaceTools(self.db, {})
        tools.call("get_note", {"note_id": str(self.note.id)})
        frames = tools.prepare([{"op": "replace_note_text", "note_id": str(self.note.id), "old": "Contexto original.", "new": "Contexto mejorado."}])
        with patch("app.regeneration._store_embedding"):
            apply_frames(self.db, frames)
        self.db.flush()
        self.assertEqual(self.processed.structured_markdown, ORIGINAL.replace("Contexto original.", "Contexto mejorado."))
        self.assertEqual(self.card.interval_days, 40)
        self.assertEqual(self.card.review_count, 8)

    def test_duplicate_tool_restricts_deletions_to_detected_candidates(self):
        other = models.RawNote(course_name=self.note.course_name, class_title="Otra clase", status=models.QueueStatus.PROCESSED)
        self.db.add(other)
        self.db.flush()
        other.processed_note = models.ProcessedNote(raw_note_id=other.id, structured_markdown=ORIGINAL)
        duplicate = models.FlashcardRecord(raw_note_id=other.id, question="Pregunta", answer="Respuesta", fingerprint="duplicate-test", embedding=[0.0] * 1024, is_dummy_embedding=True, review_count=1)
        self.db.add_all([other.processed_note, duplicate])
        self.db.flush()
        tools = WorkspaceTools(self.db, {"course": self.note.course_name, "preset": "duplicates", "components": ["flashcards"]})
        result = tools.call("find_duplicates", {})
        self.assertEqual(result["candidates"][0]["keep"]["id"], str(self.card.id))
        frames = tools.prepare([{"op": "delete_flashcard", "id": str(duplicate.id)}])
        with patch("app.regeneration._store_embedding"):
            apply_frames(self.db, frames)
        self.db.flush()
        self.assertIsNone(self.db.get(models.FlashcardRecord, duplicate.id))
        self.assertEqual(self.card.review_count, 8)
        with self.assertRaises(ValueError):
            tools.prepare([{"op": "replace_note_text", "note_id": str(self.note.id), "old": "Contexto original.", "new": ""}])

    def test_real_agent_flow_persists_reply_and_model_title_with_mock_transport(self):
        created = self.client.post("/api/agent/conversations").json()
        run_id = self.send(created["id"])
        self.db.commit()
        chat = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content=json.dumps({"reply": "Hola. ¿Qué quieres estudiar?", "actions": []}))))
        title = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content="Mi plan de estudio")))
        def session():
            return Session(bind=self.connection, join_transaction_mode="create_savepoint")
        with patch("app.global_agent.SessionLocal", side_effect=session), patch("app.global_agent.llm_models.resolve_model"), patch("app.global_agent.llm_models.resolve_selected_model"), patch("app.global_agent.llm_models.create_chat_model", side_effect=[chat, title]):
            asyncio.run(run_agent(run_id))
        self.db.expire_all()
        response = self.client.get(f"/api/agent/conversations/{created['id']}").json()
        self.assertEqual([message["role"] for message in response["messages"]], ["user", "assistant"])
        self.assertEqual(response["title"], "Mi plan de estudio")
        self.assertEqual(response["runs"][0]["status"], "complete")
        self.assertEqual(self.processed.structured_markdown, ORIGINAL)

    def test_failed_approval_rolls_back_every_change(self):
        created = self.client.post("/api/agent/conversations").json()
        run_id = self.send(created["id"])
        tools = WorkspaceTools(self.db, {})
        tools.call("get_note", {"note_id": str(self.note.id)})
        frames = tools.prepare([{"op": "replace_note_text", "note_id": str(self.note.id), "old": "Contexto original.", "new": "Cambio temporal"}])
        run = self.db.get(models.AgentRun, run_id)
        run.status, run.proposal_status, run.proposal = "complete", "pending", {"frames": frames}
        note_id = self.note.id
        self.db.commit()
        def session():
            return Session(bind=self.connection, join_transaction_mode="create_savepoint")
        def fail_after_apply(db, proposed):
            apply_frames(db, proposed)
            raise RuntimeError("Fallo final simulado")
        with patch("app.global_agent.SessionLocal", side_effect=session), patch("app.global_agent.apply_frames", side_effect=fail_after_apply), patch("app.regeneration._store_embedding"):
            response = self.client.post(f"/api/agent/runs/{run_id}/apply")
        self.assertEqual(response.status_code, 500)
        self.db.expire_all()
        self.assertEqual(self.db.query(models.ProcessedNote).filter_by(raw_note_id=note_id).one().structured_markdown, ORIGINAL)
        self.assertEqual(self.db.get(models.AgentRun, run_id).proposal_status, "pending")
