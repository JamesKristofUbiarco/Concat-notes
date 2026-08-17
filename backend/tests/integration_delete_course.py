"""Prueba manual contra PostgreSQL/RustFS activos usando un curso temporal aislado."""

from __future__ import annotations

import base64
import os
import sys
import uuid

BACKEND_ROOT = os.path.dirname(os.path.dirname(__file__))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app import crud, models
from app.database import SessionLocal
from app.storage import RUSTFS_BUCKET_NAME, get_s3_client, upload_file_to_rustfs


TABLES = (
    models.RawNote,
    models.ProcessedNote,
    models.NoteChunk,
    models.RawNoteImage,
    models.CourseGlossary,
    models.SourceChunk,
    models.NoteClaim,
    models.FlashcardRecord,
    models.GenerationArtifact,
    models.KnowledgeIndexState,
)


def counts(db) -> tuple[int, ...]:
    return tuple(db.query(table).count() for table in TABLES)


def main() -> None:
    db = SessionLocal()
    suffix = uuid.uuid4().hex
    course_name = f"__codex_delete_course_test__{suffix}"
    filename = f"{course_name}.png"
    baseline = counts(db)

    try:
        note = models.RawNote(course_name=course_name, class_title="Temporal", class_minutes=0)
        db.add(note)
        db.flush()

        processed = models.ProcessedNote(
            raw_note_id=note.id,
            structured_markdown="# Temporal",
        )
        db.add(processed)
        db.flush()
        db.add(models.NoteChunk(
            processed_note_id=processed.id,
            content="chunk temporal",
            embedding=[0.0] * 1024,
            is_dummy_embedding=False,
            chunk_index=0,
        ))
        db.add(models.SourceChunk(
            raw_note_id=note.id, source_type="transcription", content="evidencia temporal",
            content_hash=uuid.uuid4().hex, embedding=[0.0] * 1024,
            is_dummy_embedding=True, chunk_index=0,
        ))
        db.add(models.NoteClaim(
            raw_note_id=note.id, concept="Temporal", statement="Afirmación temporal",
            claim_hash=uuid.uuid4().hex, embedding=[0.0] * 1024,
            is_dummy_embedding=True,
        ))
        db.add(models.FlashcardRecord(
            raw_note_id=note.id, question="¿Temporal?", answer="Sí",
            fingerprint=uuid.uuid4().hex, embedding=[0.0] * 1024,
            is_dummy_embedding=True,
        ))
        db.add(models.GenerationArtifact(
            processed_note_id=processed.id, pipeline_version="v2",
        ))
        db.add(models.KnowledgeIndexState(
            raw_note_id=note.id, index_version="knowledge-v2.1", status="complete",
        ))
        db.add(models.RawNoteImage(
            raw_note_id=note.id,
            image_url=f"http://localhost:9000/{RUSTFS_BUCKET_NAME}/{filename}",
            filename=filename,
        ))
        db.add(models.CourseGlossary(
            course_name=course_name,
            entries=[{"term": "Temporal", "definition": "Temporal"}],
            compiled_markdown="# Temporal",
        ))
        db.commit()

        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        upload_file_to_rustfs(filename, png, "image/png")

        result = crud.delete_course(db, course_name)
        assert result is not None
        assert result["raw_notes_deleted"] == 1
        assert result["processed_notes_deleted"] == 1
        assert result["chunks_deleted"] == 1
        assert result["glossary_deleted"] is True
        assert result["images_deleted"] == 1
        assert result["image_delete_errors"] == 0
        assert counts(db) == baseline

        try:
            get_s3_client().head_object(Bucket=RUSTFS_BUCKET_NAME, Key=filename)
        except Exception:
            pass
        else:
            raise AssertionError("La imagen temporal continúa en RustFS")

        print(result)
        print("Integración de borrado de curso: OK")
    finally:
        db.rollback()
        orphan_notes = db.query(models.RawNote).filter(models.RawNote.course_name == course_name).all()
        for note in orphan_notes:
            db.delete(note)
        orphan_glossary = db.query(models.CourseGlossary).filter(
            models.CourseGlossary.course_name == course_name
        ).first()
        if orphan_glossary:
            db.delete(orphan_glossary)
        db.commit()
        try:
            get_s3_client().delete_object(Bucket=RUSTFS_BUCKET_NAME, Key=filename)
        except Exception:
            pass
        db.close()


if __name__ == "__main__":
    main()
