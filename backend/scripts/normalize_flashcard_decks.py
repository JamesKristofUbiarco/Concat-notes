"""Normaliza rutas de decks existentes. Sin --apply sólo informa cambios."""

import argparse
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import models
from app.database import SessionLocal
from app.deck_names import DECK_TAG_RE, canonical_deck_tag, normalize_flashcard_deck


def run(*, apply: bool) -> tuple[int, int]:
    db = SessionLocal()
    inspected = 0
    changed = 0
    try:
        notes = (
            db.query(models.RawNote)
            .join(models.ProcessedNote, models.ProcessedNote.raw_note_id == models.RawNote.id)
            .order_by(models.RawNote.course_name, models.RawNote.course_module, models.RawNote.order_index)
            .all()
        )
        for note in notes:
            inspected += 1
            current = note.processed_note.structured_markdown or ""
            normalized = normalize_flashcard_deck(current, note.course_name, note.course_module)
            if normalized == current:
                continue
            changed += 1
            old_tags = DECK_TAG_RE.findall(current)
            print(f"{note.id}\t{old_tags or ['sin tag']}\t→\t{canonical_deck_tag(note.course_name, note.course_module)}")
            if apply:
                note.processed_note.structured_markdown = normalized
        if apply:
            db.commit()
        else:
            db.rollback()
        return inspected, changed
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Confirma y guarda la migración")
    args = parser.parse_args()
    inspected_count, changed_count = run(apply=args.apply)
    mode = "aplicados" if args.apply else "detectados (dry-run)"
    print(f"Notas inspeccionadas: {inspected_count}; cambios {mode}: {changed_count}")
