"""Biblioteca, programación y exportación autónoma de flashcards."""

from __future__ import annotations

import csv
import hashlib
import html
import io
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import genanki
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app import models
from app.deck_names import canonical_deck_tag
from app.knowledge import ZERO_VECTOR, parse_flashcards


def _normalized_question(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())


def fingerprint(question: str) -> str:
    return hashlib.sha256(_normalized_question(question).encode("utf-8")).hexdigest()


def refresh_note(db: Session, note: models.RawNote) -> dict[str, int]:
    parsed = parse_flashcards(note.processed_note.structured_markdown)
    existing = db.query(models.FlashcardRecord).filter(models.FlashcardRecord.raw_note_id == note.id).all()
    by_question = {_normalized_question(card.question): card for card in existing}
    retained: set[UUID] = set()
    created = updated = deleted = 0
    for item in parsed:
        key = _normalized_question(item["question"])
        card = by_question.get(key)
        if card is None:
            card = models.FlashcardRecord(
                raw_note_id=note.id,
                question=item["question"],
                answer=item["answer"],
                fingerprint=fingerprint(item["question"]),
                embedding=ZERO_VECTOR,
                is_dummy_embedding=True,
            )
            db.add(card)
            db.flush()
            created += 1
        elif card.answer != item["answer"]:
            card.answer = item["answer"]
            card.embedding = ZERO_VECTOR
            card.is_dummy_embedding = True
            updated += 1
        retained.add(card.id)
    for card in existing:
        if card.id not in retained:
            db.delete(card)
            deleted += 1
    return {"created": created, "updated": updated, "deleted": deleted}


def refresh_index(db: Session) -> dict[str, int]:
    """Reconcilia Markdown → índice preservando progreso cuando la pregunta no cambió."""
    inspected = created = updated = deleted = 0
    notes = db.query(models.RawNote).join(models.ProcessedNote, models.ProcessedNote.raw_note_id == models.RawNote.id).all()
    try:
        for note in notes:
            inspected += 1
            result = refresh_note(db, note)
            created += result["created"]
            updated += result["updated"]
            deleted += result["deleted"]
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"notes": inspected, "created": created, "updated": updated, "deleted": deleted}


def _base_query(db: Session):
    return db.query(models.FlashcardRecord, models.RawNote).join(
        models.RawNote, models.RawNote.id == models.FlashcardRecord.raw_note_id
    )


def filtered_query(
    db: Session,
    *,
    course: str | None = None,
    module: str | None = None,
    class_title: str | None = None,
    learning_state: str | None = None,
    search: str | None = None,
    active_only: bool = True,
    activity: str | None = None,
    due_only: bool = False,
):
    query = _base_query(db)
    if activity == "inactive":
        query = query.filter(models.FlashcardRecord.is_active.is_(False))
    elif activity != "all" and active_only:
        query = query.filter(models.FlashcardRecord.is_active.is_(True))
    if course:
        query = query.filter(models.RawNote.course_name == course)
    if module:
        if module == "General":
            query = query.filter(or_(models.RawNote.course_module == "", models.RawNote.course_module.is_(None)))
        else:
            query = query.filter(models.RawNote.course_module == module)
    if class_title:
        query = query.filter(models.RawNote.class_title == class_title)
    if learning_state:
        query = query.filter(models.FlashcardRecord.learning_state == learning_state)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.filter(or_(
            models.FlashcardRecord.question.ilike(pattern),
            models.FlashcardRecord.answer.ilike(pattern),
        ))
    if due_only:
        now = datetime.now(timezone.utc)
        query = query.filter(or_(
            models.FlashcardRecord.learning_state == "new",
            models.FlashcardRecord.due_at.is_(None),
            models.FlashcardRecord.due_at <= now,
        ))
    return query


def serialize(card: models.FlashcardRecord, note: models.RawNote) -> dict[str, Any]:
    return {
        "id": str(card.id),
        "raw_note_id": str(card.raw_note_id),
        "course_name": note.course_name,
        "course_module": note.course_module or "General",
        "class_title": note.class_title,
        "deck_tag": canonical_deck_tag(note.course_name, note.course_module),
        "question": card.question,
        "answer": card.answer,
        "is_active": card.is_active,
        "learning_state": card.learning_state,
        "due_at": card.due_at.isoformat() if card.due_at else None,
        "last_reviewed_at": card.last_reviewed_at.isoformat() if card.last_reviewed_at else None,
        "interval_days": card.interval_days,
        "ease_factor": card.ease_factor,
        "repetitions": card.repetitions,
        "lapses": card.lapses,
        "review_count": card.review_count,
        "maturity": maturity(card),
        "review_options": review_options(card),
    }


def maturity(card: models.FlashcardRecord) -> str:
    if card.learning_state == "new":
        return "new"
    if card.learning_state == "learning":
        return "learning"
    return "mature" if (card.interval_days or 0) >= 21 else "young"


def _schedule_values(card: models.FlashcardRecord, rating: int, now: datetime) -> dict[str, Any]:
    previous_interval = card.interval_days or 0
    ease = card.ease_factor or 2.5
    repetitions = card.repetitions or 0
    lapses = card.lapses or 0
    is_review = card.learning_state == "review"
    is_relearning = card.learning_state == "learning" and lapses > 0 and previous_interval > 0
    if rating == 1:
        # Anki-style lapse: relearn soon, but retain part of a mature card's interval.
        interval = max(1, round(previous_interval * 0.2)) if is_review else previous_interval
        due_delta = timedelta(minutes=10)
        repetitions = 0
        lapses += 1
        ease = max(1.3, ease - 0.2)
        new_state = "learning"
    elif rating == 2:
        if is_review:
            interval = max(previous_interval + 1, round(max(1, previous_interval) * 1.2))
            due_delta = timedelta(days=interval)
            ease = max(1.3, ease - 0.15)
            repetitions += 1
            new_state = "review"
        else:
            interval = previous_interval
            due_delta = timedelta(minutes=30)
            new_state = "learning"
    elif rating == 3:
        repetitions += 1
        if is_review:
            interval = max(previous_interval + 1, round(max(1, previous_interval) * ease))
        elif is_relearning:
            interval = max(1, previous_interval)
        else:
            interval = 1
        due_delta = timedelta(days=interval)
        new_state = "review"
    else:
        repetitions += 1
        interval = max(previous_interval + 2, round(max(1, previous_interval) * ease * 1.3)) if is_review else 4
        due_delta = timedelta(days=interval)
        ease = min(3.0, ease + 0.15)
        new_state = "review"
    return {
        "interval": interval, "due_at": now + due_delta, "ease": ease,
        "repetitions": repetitions, "lapses": lapses, "new_state": new_state,
    }


def review_options(card: models.FlashcardRecord) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    labels = {
        1: ("Otra vez", "No la recordé"),
        2: ("Difícil", "La recordé con esfuerzo"),
        3: ("Bien", "La recordé correctamente"),
        4: ("Fácil", "La recordé de inmediato"),
    }
    result = []
    for rating in range(1, 5):
        schedule = _schedule_values(card, rating, now)
        seconds = round((schedule["due_at"] - now).total_seconds())
        if seconds < 3600:
            due_label = f"{max(1, round(seconds / 60))} min"
        else:
            days = max(1, round(seconds / 86400))
            due_label = f"{days} día" + ("s" if days != 1 else "")
        label, meaning = labels[rating]
        result.append({"rating": rating, "label": label, "meaning": meaning, "due_label": due_label})
    return result


def tree(db: Session) -> list[dict[str, Any]]:
    rows = (
        db.query(models.RawNote.course_name, models.RawNote.course_module, models.RawNote.class_title, func.count(models.FlashcardRecord.id))
        .join(models.FlashcardRecord, models.FlashcardRecord.raw_note_id == models.RawNote.id)
        .filter(models.FlashcardRecord.is_active.is_(True))
        .group_by(models.RawNote.course_name, models.RawNote.course_module, models.RawNote.class_title)
        .order_by(models.RawNote.course_name, models.RawNote.course_module, models.RawNote.class_title)
        .all()
    )
    courses: dict[str, dict[str, Any]] = {}
    modules: dict[tuple[str, str], dict[str, Any]] = {}
    for course, module, class_title, count in rows:
        entry = courses.setdefault(course, {"course_name": course, "count": 0, "modules": []})
        entry["count"] += count
        module_name = module or "General"
        module_entry = modules.get((course, module_name))
        if module_entry is None:
            module_entry = {"module_name": module_name, "count": 0, "classes": []}
            modules[(course, module_name)] = module_entry
            entry["modules"].append(module_entry)
        module_entry["count"] += count
        module_entry["classes"].append({"class_title": class_title, "count": count})
    return list(courses.values())


def summary(db: Session, *, course: str | None = None, module: str | None = None, class_title: str | None = None) -> dict[str, int]:
    all_rows = filtered_query(db, course=course, module=module, class_title=class_title, active_only=False).all()
    now = datetime.now(timezone.utc)
    cards = [card for card, _ in all_rows if card.is_active]
    return {
        "total": len(cards),
        "new": sum(card.learning_state == "new" for card in cards),
        "learning": sum(card.learning_state == "learning" for card in cards),
        "review": sum(card.learning_state == "review" for card in cards),
        "due": sum(card.learning_state == "new" or card.due_at is None or card.due_at <= now for card in cards),
        "inactive": sum(not card.is_active for card, _ in all_rows),
    }


def review(db: Session, card_id: UUID, rating: int) -> dict[str, Any]:
    row = _base_query(db).filter(models.FlashcardRecord.id == card_id).first()
    if not row:
        raise KeyError("Flashcard no encontrada")
    card, note = row
    if not card.is_active:
        raise ValueError("La flashcard está desactivada")
    previous_state = card.learning_state
    previous_interval = card.interval_days or 0
    now = datetime.now(timezone.utc)
    schedule = _schedule_values(card, rating, now)
    card.learning_state = schedule["new_state"]
    card.interval_days = schedule["interval"]
    card.ease_factor = schedule["ease"]
    card.repetitions = schedule["repetitions"]
    card.lapses = schedule["lapses"]
    card.review_count = (card.review_count or 0) + 1
    card.last_reviewed_at = now
    card.due_at = schedule["due_at"]
    db.add(models.FlashcardReview(
        flashcard_id=card.id,
        rating=rating,
        previous_state=previous_state,
        new_state=schedule["new_state"],
        previous_interval_days=previous_interval,
        scheduled_interval_days=schedule["interval"],
        reviewed_at=now,
    ))
    db.commit()
    db.refresh(card)
    return serialize(card, note)


def _replace_in_markdown(markdown: str, old_question: str, old_answer: str, new_question: str, new_answer: str) -> str:
    reversible = re.compile(rf"^{re.escape(old_question)}\s*:::\s*{re.escape(old_answer)}\s*$", re.MULTILINE)
    if reversible.search(markdown):
        return reversible.sub(f"{new_question}:::{new_answer}", markdown, count=1)
    reverse_side = re.compile(rf"^{re.escape(old_answer)}\s*:::\s*{re.escape(old_question)}\s*$", re.MULTILINE)
    if reverse_side.search(markdown):
        return reverse_side.sub(f"{new_answer}:::{new_question}", markdown, count=1)
    single = re.compile(rf"^{re.escape(old_question)}\s*::(?!:)\s*\??{re.escape(old_answer)}\s*$", re.MULTILINE)
    if single.search(markdown):
        return single.sub(f"{new_question}::{new_answer}", markdown, count=1)
    cloze_line = old_question.replace("[…]", f"=={old_answer}==")
    if cloze_line in markdown:
        return markdown.replace(cloze_line, f"{new_question}::{new_answer}", 1)
    multiline = re.compile(rf"^{re.escape(old_question)}\s*\n\?\??\s*\n{re.escape(old_answer)}\s*$", re.MULTILINE)
    if multiline.search(markdown):
        return multiline.sub(f"{new_question}::{new_answer}", markdown, count=1)
    raise ValueError("No se encontró la representación original de la tarjeta en el Markdown")


def update_card(db: Session, card_id: UUID, *, question: str | None, answer: str | None, is_active: bool | None) -> dict[str, Any]:
    row = _base_query(db).filter(models.FlashcardRecord.id == card_id).first()
    if not row:
        raise KeyError("Flashcard no encontrada")
    card, note = row
    if question is not None or answer is not None:
        new_question = (question or card.question).strip()
        new_answer = (answer or card.answer).strip()
        note.processed_note.structured_markdown = _replace_in_markdown(
            note.processed_note.structured_markdown, card.question, card.answer, new_question, new_answer
        )
        card.question = new_question
        card.answer = new_answer
        card.fingerprint = fingerprint(new_question)
        card.embedding = ZERO_VECTOR
        card.is_dummy_embedding = True
        card.learning_state = "new"
        card.due_at = None
        card.last_reviewed_at = None
        card.interval_days = 0
        card.repetitions = 0
        card.lapses = 0
        card.review_count = 0
    if is_active is not None:
        card.is_active = is_active
    if question is not None or answer is not None:
        # Mantiene sincronizada también la tarjeta inversa de una línea `:::`.
        db.flush()
        refresh_note(db, note)
    db.commit()
    db.refresh(card)
    return serialize(card, note)


def csv_export(rows: list[tuple[models.FlashcardRecord, models.RawNote]]) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["course", "module", "class", "question", "answer", "deck_tag", "state", "due_at"])
    for card, note in rows:
        writer.writerow([
            note.course_name, note.course_module or "General", note.class_title,
            card.question, card.answer, canonical_deck_tag(note.course_name, note.course_module),
            card.learning_state, card.due_at.isoformat() if card.due_at else "",
        ])
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def _stable_id(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:8], 16) & 0x7FFFFFFF


def anki_export(rows: list[tuple[models.FlashcardRecord, models.RawNote]]) -> bytes:
    model = genanki.Model(
        _stable_id("concat-notes-basic-v1"),
        "Concat Notes Basic",
        fields=[{"name": "Question"}, {"name": "Answer"}, {"name": "Source"}],
        templates=[{"name": "Card 1", "qfmt": "{{Question}}", "afmt": "{{FrontSide}}<hr id=answer>{{Answer}}<br><small>{{Source}}</small>"}],
        css=".card { font-family: sans-serif; font-size: 20px; text-align: left; color: #111; background: #fff; } small { color: #666; }",
    )
    decks: dict[str, genanki.Deck] = {}
    for card, note in rows:
        deck_name = f"{note.course_name}::{note.course_module or 'General'}"
        deck = decks.setdefault(deck_name, genanki.Deck(_stable_id(f"deck:{deck_name}"), deck_name))
        source = f"{note.course_name} · {note.course_module or 'General'} · {note.class_title}"
        deck.add_note(genanki.Note(
            model=model,
            fields=[html.escape(card.question).replace("\n", "<br>"), html.escape(card.answer).replace("\n", "<br>"), html.escape(source)],
            guid=genanki.guid_for(str(card.id)),
            tags=["concat-notes"],
        ))
    package = genanki.Package(list(decks.values()))
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "flashcards.apkg"
        package.write_to_file(str(path))
        return path.read_bytes()
