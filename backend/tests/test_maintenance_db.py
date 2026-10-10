"""Pruebas PostgreSQL optativas; toda modificación queda dentro de un rollback."""
import os
import sys
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app import models
from app.database import engine, get_db
from app.main import app
from app.regeneration import persist_selection, markdown_parts, process_item
from test_maintenance import ORIGINAL


@unittest.skipUnless(os.getenv("RUN_DB_TESTS") == "1", "Requiere PostgreSQL y RUN_DB_TESTS=1")
class MaintenanceDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.connection = engine.connect()
        self.transaction = self.connection.begin()
        self.db = Session(bind=self.connection, join_transaction_mode="create_savepoint")
        self.note = models.RawNote(course_name=f"maintenance-test-{uuid.uuid4()}", class_title="Clase de prueba", transcription="Un algoritmo resuelve un problema.", status=models.QueueStatus.PROCESSED)
        self.db.add(self.note)
        self.db.flush()
        self.processed = models.ProcessedNote(raw_note_id=self.note.id, structured_markdown=ORIGINAL)
        self.db.add(self.processed)
        self.db.flush()
        self.note.processed_note = self.processed
        vector = [0.1] * 1024
        self.source = models.SourceChunk(raw_note_id=self.note.id, source_type="transcription", content="Fuente original", content_hash="source-test", chunk_index=0, embedding=vector, is_dummy_embedding=False)
        self.chunk = models.NoteChunk(processed_note_id=self.processed.id, content="Fragmento de nota", chunk_index=0, embedding=vector, is_dummy_embedding=False)
        self.claim = models.NoteClaim(raw_note_id=self.note.id, concept="Algorithm", statement="Afirmación", claim_hash="claim-test", embedding=vector, is_dummy_embedding=False)
        self.card = models.FlashcardRecord(raw_note_id=self.note.id, question="Pregunta", answer="Respuesta", fingerprint="test-card", embedding=vector, is_dummy_embedding=False, repetitions=7, interval_days=40, review_count=8)
        self.db.add_all([self.source, self.chunk, self.claim, self.card])
        self.db.flush()
        self.review = models.FlashcardReview(flashcard_id=self.card.id, rating=3, previous_state="review", new_state="review", previous_interval_days=20, scheduled_interval_days=40)
        self.db.add(self.review)
        self.db.flush()
        self.client = TestClient(app)
        app.dependency_overrides[get_db] = lambda: self.db

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()
        self.db.close()
        self.transaction.rollback()
        self.connection.close()

    def test_retrieval_excludes_future_classes_and_other_courses(self):
        from app.knowledge import retrieve_prior_knowledge
        self.note.order_index = 10
        self.note.transcription = "ls -a muestra archivos ocultos"
        past = models.RawNote(course_name=self.note.course_name, class_title="Anterior", order_index=5)
        future = models.RawNote(course_name=self.note.course_name, class_title="Futura", order_index=20)
        other = models.RawNote(course_name="other-course-test", class_title="Otro curso")
        self.db.add_all([past, future, other])
        self.db.flush()
        for row in (past, future, other):
            self.db.add(models.NoteClaim(raw_note_id=row.id, concept="ls", statement="ls -a muestra archivos ocultos", claim_hash="same-" + str(row.id), embedding=[0.0] * 1024, is_dummy_embedding=True))
        self.db.flush()
        with patch("app.knowledge.embed_texts", return_value=([[0.0] * 1024], [True])):
            result = retrieve_prior_knowledge(self.db, self.note)
        self.assertEqual({item["raw_note_id"] for item in result["claims"]}, {str(past.id)})
        self.assertEqual(result["claims"][0]["title"], "Anterior")

    def test_unchanged_claim_identity_survives_regeneration(self):
        from app.knowledge import persist_v2_derivatives
        claim_id = self.claim.id
        state = {"structured_markdown": ORIGINAL, "evidence_manifest": [{"concept": "Algorithm", "statement": self.claim.statement, "claim_hash": self.claim.claim_hash, "novelty_relation": "NEW"}], "metrics": {}}
        with patch("app.knowledge.embed_texts", side_effect=lambda texts: ([[0.1] * 1024 for _ in texts], [False] * len(texts))):
            persist_v2_derivatives(self.db, self.note, self.processed, state, update_glossary=False)
        self.db.flush()
        claims = self.db.query(models.NoteClaim).filter_by(raw_note_id=self.note.id).all()
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].id, claim_id)
        self.assertGreaterEqual(state["metrics"]["embeddings_reused"], 1)

    def test_pagination_lists_all_four_indexes_with_class_filter(self):
        response = self.client.get("/api/rag/chunks", params={"note_id": str(self.note.id)})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["total"], 4)
        self.assertEqual({item["kind"] for item in response.json()["items"]}, {"source", "note", "claim", "flashcard"})
        response = self.client.get("/api/rag/chunks", params={"note_id": str(self.note.id), "kind": "claim"})
        self.assertEqual(response.json()["total"], 1)

    def test_edit_invalidates_old_vector_and_rejects_stale_edit(self):
        path = f"/api/rag/chunks/source/{self.source.id}"
        old = self.client.get(path).json()
        with patch("app.maintenance_routes.embed_texts", return_value=([[0.0] * 1024], [True])):
            response = self.client.put(path, json={"content": "Fuente corregida", "digest": old["digest"]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["has_embedding"])
        self.assertEqual(self.source.content, "Fuente corregida")
        self.assertEqual(self.processed.structured_markdown, ORIGINAL)
        self.assertEqual(self.client.put(path, json={"content": "Edición obsoleta", "digest": old["digest"]}).status_code, 409)

    def test_failed_vector_generation_preserves_previous_vector(self):
        before = list(self.source.embedding)
        with patch("app.maintenance_routes.embed_texts", return_value=([[0.0] * 1024], [True])):
            response = self.client.post("/api/rag/actions", json={"action": "reembed", "targets": [{"kind": "source", "id": str(self.source.id)}]})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(list(self.source.embedding), before)
        self.assertFalse(self.source.is_dummy_embedding)

    def test_embedding_deletion_preserves_card_progress(self):
        payload = {"action": "delete_embeddings", "targets": [{"kind": "flashcard", "id": str(self.card.id)}]}
        response = self.client.post("/api/rag/actions", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(self.card.is_dummy_embedding)
        self.assertEqual(self.card.repetitions, 7)
        payload["action"] = "delete_chunks"
        self.assertEqual(self.client.post("/api/rag/actions", json=payload).status_code, 400)

    def test_job_persists_selection_and_prevents_duplicate_work(self):
        payload = {"note_ids": [str(self.note.id)], "components": ["glossary"], "instructions": "Explica mejor cada concepto."}
        response = self.client.post("/api/regeneration/jobs", json=payload)
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(response.json()["components"], ["glossary"])
        self.assertEqual(response.json()["items"][0]["status"], "pending")
        self.assertEqual(self.client.post("/api/regeneration/jobs", json=payload).status_code, 409)
        self.assertTrue(any(job["id"] == response.json()["id"] for job in self.client.get("/api/regeneration/jobs").json()))

    def test_glossary_regeneration_preserves_body_cards_and_previous_revision(self):
        parts = markdown_parts(ORIGINAL)
        parts["glossary"] = "## 📖 Conceptos Clave (Glosario)\n**Algorithm** #definicion\nNueva definición.\n\n"
        state = {"structured_markdown": "".join(parts.values()), "glossary_markdown": parts["glossary"]}
        with patch("app.regeneration._store_embedding"):
            persist_selection(self.db, self.note, state, ["glossary"])
        self.db.flush()
        self.assertEqual(markdown_parts(self.processed.structured_markdown)["content"], markdown_parts(ORIGINAL)["content"])
        self.assertEqual(self.card.repetitions, 7)
        self.assertEqual(self.card.interval_days, 40)
        glossary = self.db.query(models.CourseGlossary).filter_by(course_name=self.note.course_name).one()
        self.assertIn("Nueva definición.", glossary.compiled_markdown)
        self.assertNotIn("Definición original.", glossary.compiled_markdown)
        record = self.db.query(models.StructuredNoteDocument).filter_by(raw_note_id=self.note.id).one()
        self.assertEqual(record.revision_number, 2)

    def test_content_regeneration_retains_flashcard_id_maturity_and_reviews(self):
        parts = markdown_parts(ORIGINAL)
        state = {"structured_markdown": ORIGINAL, "body_markdown": parts["content"], "glossary_markdown": parts["glossary"], "flashcards_markdown": parts["flashcards"], "evidence_manifest": []}
        card_id, review_id = self.card.id, self.review.id
        def vectors(texts):
            return [[0.0] * 1024 for _ in texts], [True] * len(texts)
        with patch("app.regeneration._store_embedding"), patch("app.knowledge.embed_texts", side_effect=vectors):
            persist_selection(self.db, self.note, state, ["content"])
        self.db.flush()
        self.assertEqual(self.db.get(models.FlashcardRecord, card_id).interval_days, 40)
        self.assertEqual(self.db.get(models.FlashcardRecord, card_id).repetitions, 7)
        self.assertFalse(self.db.get(models.FlashcardRecord, card_id).is_dummy_embedding)
        self.assertIsNotNone(self.db.get(models.FlashcardReview, review_id))

    def test_failed_save_rolls_back_note_and_marks_job_failed(self):
        response = self.client.post("/api/regeneration/jobs", json={"note_ids": [str(self.note.id)], "components": ["glossary"]})
        self.assertEqual(response.status_code, 202, response.text)
        job_id = uuid.UUID(response.json()["id"])
        note_id = self.note.id
        self.db.commit()
        parts = markdown_parts(ORIGINAL)
        parts["glossary"] = "## 📖 Conceptos Clave (Glosario)\n**Algorithm** #definicion\nCambio que debe revertirse.\n\n"
        state = {"structured_markdown": "".join(parts.values()), "glossary_markdown": parts["glossary"]}
        def new_session():
            return Session(bind=self.connection, join_transaction_mode="create_savepoint")
        with patch("app.regeneration.SessionLocal", side_effect=new_session), patch("app.regeneration.generate_selection", return_value=state), patch("app.regeneration._store_embedding"), patch("app.structured_notes._create_revision", side_effect=RuntimeError("Fallo de guardado simulado")):
            process_item(job_id, 0)
        self.db.expire_all()
        self.assertEqual(self.db.query(models.ProcessedNote).filter_by(raw_note_id=note_id).one().structured_markdown, ORIGINAL)
        job = self.db.get(models.RegenerationJob, job_id)
        self.assertEqual(job.items[0]["status"], "failed")
        self.assertIn("Fallo de guardado simulado", job.items[0]["error"])
