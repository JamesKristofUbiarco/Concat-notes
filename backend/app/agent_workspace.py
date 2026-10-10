"""Herramientas del agente global y propuestas verificables sobre el espacio de notas."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from difflib import SequenceMatcher, unified_diff
import hashlib
import json
import re
from uuid import UUID

from sqlalchemy import or_
from app import models, crud, flashcards
from app.knowledge import ZERO_VECTOR, embed_texts, _hash, _normalise
from app.maintenance_routes import rag_index, KINDS, row_content
from app.note_sections import split_note_markdown, supplement_section, supplement_span
from app.structured_notes import apply_operations, _create_revision, render_markdown
from app.regeneration import persist_selection


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def replace_occurrence(text, old, new, occurrence=0):
    if not isinstance(old, str) or not old or not isinstance(new, str):
        raise ValueError("El cambio debe indicar texto anterior y texto nuevo.")
    indexes = [match.start() for match in re.finditer(re.escape(old), text)]
    if not isinstance(occurrence, int) or occurrence < 0 or occurrence >= len(indexes):
        raise ValueError("No se encontró la coincidencia exacta solicitada.")
    position = indexes[occurrence]
    return text[:position] + new + text[position + len(old):]


def remove_card(markdown, card):
    marker = f"REMOVE_CARD_{card.id.hex}"
    candidate = flashcards._replace_in_markdown(markdown, card.question, card.answer, marker, "REMOVE_ANSWER")
    return re.sub(rf"^.*{re.escape(marker)}.*(?:\n|$)", "", candidate, count=1, flags=re.MULTILINE)


def update_card_source(markdown, card, question=None, answer=None, *, delete=False):
    start, end = supplement_span(markdown, "flashcards")
    section = markdown[start:end]
    changed = remove_card(section, card) if delete else flashcards._replace_in_markdown(section, card.question, card.answer, question, answer)
    return markdown[:start] + changed + markdown[end:]


class WorkspaceTools:
    """Sólo lecturas durante el chat; los cambios se preparan en memoria."""
    def __init__(self, db, scope):
        self.db, self.scope = db, scope
        self.seen = {}
        self.duplicate_targets = set()

    def within_course(self, course):
        if self.scope.get("course") and course != self.scope["course"]:
            raise ValueError("Ese elemento está fuera del curso seleccionado.")

    def note(self, note_id):
        note = self.db.get(models.RawNote, UUID(str(note_id)))
        if not note or not note.processed_note:
            raise ValueError("No existe una nota procesada para esta clase.")
        self.within_course(note.course_name)
        self.seen[f"note:{note.id}"] = {"kind": "note", "id": str(note.id), "label": f"{note.course_name} · {note.class_title}", "before": note.processed_note.structured_markdown}
        return note

    def document(self, document_id):
        record = self.db.get(models.StructuredNoteDocument, UUID(str(document_id)))
        if not record or record.origin_kind == "generated_class":
            raise ValueError("Para las clases usa get_note y replace_note_text. get_document edita notas propias.")
        metadata = (record.document_json or {}).get("metadata", {})
        self.within_course(metadata.get("course_name") or "Mis notas")
        self.seen[f"document:{record.id}"] = {"kind": "document", "id": str(record.id), "label": metadata.get("title") or metadata.get("class_title") or "Nota propia", "before": deepcopy(record.document_json), "revision": str(record.current_revision_id)}
        return record

    def chunk(self, kind, row_id):
        if kind not in {"note", "source", "claim"}:
            raise ValueError("Para las tarjetas usa get_flashcard.")
        row = self.db.get(KINDS[kind], UUID(str(row_id)))
        if not row:
            raise ValueError("El fragmento no existe.")
        note = self.db.get(models.RawNote, row.processed_note.raw_note_id if kind == "note" else row.raw_note_id)
        self.within_course(note.course_name)
        self.seen[f"chunk:{kind}:{row.id}"] = {"kind": "chunk", "chunk_kind": kind, "id": str(row.id), "label": f"Fragmento · {note.class_title}", "before": {"content": row_content(row, kind), "has_embedding": not row.is_dummy_embedding}}
        return row

    def card(self, card_id):
        card = self.db.get(models.FlashcardRecord, UUID(str(card_id)))
        if not card:
            raise ValueError("La tarjeta no existe.")
        if not card.raw_note_id:
            raise ValueError("Esta tarjeta procede de Mis notas. Edita sus bloques y relaciones mediante get_document.")
        note = self.note(card.raw_note_id)
        self.seen[f"card_guard:{card.id}"] = {"kind": "card_guard", "id": str(card.id), "label": card.question, "before": card_snapshot(card)}
        return card, note

    def call(self, name, args):
        args = args or {}
        if name == "search_notes":
            query = self.db.query(models.RawNote).join(models.ProcessedNote)
            if self.scope.get("course"):
                query = query.filter(models.RawNote.course_name == self.scope["course"])
            search = str(args.get("query", ""))[:300]
            if search:
                query = query.filter(or_(models.RawNote.class_title.ilike(f"%{search}%"), models.ProcessedNote.structured_markdown.ilike(f"%{search}%")))
            total = query.count()
            notes = query.order_by(models.RawNote.course_name, models.RawNote.order_index, models.RawNote.id).offset(max(0, int(args.get("offset", 0)))).limit(25).all()
            docs = self.db.query(models.StructuredNoteDocument).filter(models.StructuredNoteDocument.origin_kind != "generated_class").all()
            own = [{"document_id": str(doc.id), "title": (doc.document_json or {}).get("metadata", {}).get("title", "Nota propia")} for doc in docs if (not search or search.casefold() in doc.rendered_markdown.casefold()) and (not self.scope.get("course") or (doc.document_json or {}).get("metadata", {}).get("course_name") == self.scope["course"])]
            return {"total_classes": total, "classes": [{"note_id": str(note.id), "course": note.course_name, "title": note.class_title, "module": note.course_module} for note in notes], "own_notes": own[:25]}
        if name == "get_note":
            note = self.note(args["note_id"])
            text = note.processed_note.structured_markdown
            if args.get("component"):
                text = split_note_markdown(text).get(args["component"], "")
            offset = max(0, int(args.get("offset", 0)))
            return {"note_id": str(note.id), "title": note.class_title, "markdown": text[offset:offset + 45000], "remaining": max(0, len(text) - offset - 45000)}
        if name == "get_sources":
            note = self.note(args["note_id"])
            return {"transcription": (note.transcription or "")[:25000], "user_notes": note.my_notes, "summary": note.class_summary, "code": note.code_snippets, "commands": note.command_snippets, "images": [{"description": image.descripcion_llm} for image in note.images]}
        if name == "get_document":
            return self.document(args["document_id"]).document_json
        if name == "search_chunks":
            index = rag_index()
            query = self.db.query(index.c.kind, index.c.id, index.c.content, models.RawNote.class_title).join(models.RawNote, index.c.note_id == models.RawNote.id)
            if self.scope.get("course"):
                query = query.filter(models.RawNote.course_name == self.scope["course"])
            query = query.filter(index.c.content.ilike(f"%{str(args.get('query', ''))[:300]}%"))
            return [{"kind": kind, "id": str(row_id), "preview": text[:450], "class": title} for kind, row_id, text, title in query.order_by(index.c.id).limit(25).all()]
        if name == "get_chunk":
            row = self.chunk(args["kind"], args["id"])
            return {"kind": args["kind"], "id": str(row.id), "content": row_content(row, args["kind"]), "has_embedding": not row.is_dummy_embedding}
        if name == "search_flashcards":
            rows = flashcards.filtered_query(self.db, course=self.scope.get("course"), search=args.get("query"), activity="all").limit(30).all()
            return [{"id": str(card.id), "question": card.question, "answer": card.answer, "reviews": card.review_count, "document_id": str(card.structured_document_id) if card.structured_document_id else None} for card, _, _ in rows]
        if name == "get_flashcard":
            card, note = self.card(args["id"])
            return {"id": str(card.id), "note_id": str(note.id), **card_snapshot(card)}
        if name == "get_glossary":
            course = args.get("course") or self.scope.get("course")
            if not course:
                raise ValueError("Indica un curso para consultar su glosario.")
            self.within_course(course)
            query = self.db.query(models.RawNote).filter(models.RawNote.course_name == course).order_by(models.RawNote.order_index, models.RawNote.id)
            definitions = []
            glossary_notes = query.all()
            offset = max(0, int(args.get("offset", 0)))
            for note in glossary_notes[offset:offset + 20]:
                if note.processed_note:
                    text = supplement_section(note.processed_note.structured_markdown, "glossary")
                    if text:
                        self.note(note.id)
                        definitions.append({"note_id": str(note.id), "class": note.class_title, "markdown": text})
            return {"course": course, "definitions": definitions, "next_offset": offset + 20 if offset + 20 < len(glossary_notes) else None, "instructions": "Edita las definiciones en sus notas fuente con replace_note_text; el glosario compilado se actualizará al aplicar."}
        if name == "study_progress":
            rows = flashcards.filtered_query(self.db, course=self.scope.get("course")).all()
            today = crud.get_study_log_today(self.db)
            return {"today_minutes": today.total_minutes if today else 0, "daily_goal": crud.get_daily_goal(self.db), "cards": len(rows), "new": sum(card.learning_state == "new" for card, _, _ in rows), "reviews": sum(card.review_count for card, _, _ in rows), "now": datetime.now(timezone.utc).isoformat()}
        if name == "find_duplicates":
            return self.find_duplicates()
        raise ValueError(f"Herramienta no permitida: {name}")

    def find_duplicates(self):
        components = self.scope.get("components") or ["content", "glossary", "flashcards"]
        query = self.db.query(models.RawNote).join(models.ProcessedNote)
        if self.scope.get("course"):
            query = query.filter(models.RawNote.course_name == self.scope["course"])
        notes = query.order_by(models.RawNote.course_name, models.RawNote.order_index, models.RawNote.id).all()
        candidates, kept, buckets, scanned = [], {}, {}, 0
        for note in notes:
            scanned += 1
            parts = split_note_markdown(note.processed_note.structured_markdown)
            for component in ("content", "glossary"):
                if component not in components:
                    continue
                text = parts[component]
                # El código y los metadatos no son prosa repetitiva.
                text = re.sub(r"(?ms)^```.*?^```\s*$|^~~~.*?^~~~\s*$", "", text)
                blocks = re.split(r"\n\s*\n", text) if component == "content" else re.findall(r"(?ms)^\*\*[^\n]+\*\*\s+#[^\n]+\n.*?(?=^\*\*[^\n]+\*\*\s+#|\Z)", text)
                occurrences = {}
                for block in blocks:
                    block = block.strip()
                    if len(block) < 90 or (component == "content" and (block.startswith(("#", "---", "**Curso:", "**Instructor:", "**Módulo:")) or "::" in block)):
                        continue
                    if block not in note.processed_note.structured_markdown:
                        continue
                    ordinal = occurrences.get(block, 0)
                    occurrences[block] = ordinal + 1
                    original = note.processed_note.structured_markdown
                    all_positions = [match.start() for match in re.finditer(re.escape(block), original)]
                    component_start = original.find(parts[component])
                    positions = [position for position in all_positions if component_start <= position < component_start + len(parts[component])]
                    if ordinal >= len(positions):
                        continue
                    occurrence = all_positions.index(positions[ordinal])
                    normalized = _normalise(block)
                    group = (note.course_name, component, normalized)
                    current = {"note_id": str(note.id), "title": note.class_title, "text": block, "occurrence": occurrence}
                    if group in kept:
                        self.note(note.id)
                        self.note(kept[group]["note_id"])
                        self.duplicate_targets.add((str(note.id), block))
                        candidates.append({"component": component, "similarity": 1.0, "keep": kept[group], "duplicate": current})
                    else:
                        # Busca variantes muy próximas dentro del mismo curso y componente.
                        bucket = len(normalized) // 120
                        tokens = set(normalized.split())
                        neighbors = [value for number in (bucket - 1, bucket, bucket + 1) for value in buckets.get((note.course_name, component, number), [])[-6:]]
                        near = next((other for key, other, previous_tokens in neighbors if abs(len(key) - len(normalized)) < max(20, len(normalized) * .12) and len(tokens & previous_tokens) / max(1, len(tokens | previous_tokens)) >= .90 and SequenceMatcher(None, key, normalized, autojunk=False).ratio() >= .94), None)
                        if near:
                            self.note(note.id)
                            self.note(near["note_id"])
                            self.duplicate_targets.add((str(note.id), block))
                            candidates.append({"component": component, "similarity": .94, "keep": near, "duplicate": current})
                        else:
                            kept[group] = current
                            buckets.setdefault((note.course_name, component, bucket), []).append((normalized, current, tokens))
            if len(candidates) >= 35:
                break
        if "flashcards" in components:
            rows = flashcards.filtered_query(self.db, course=self.scope.get("course")).order_by(models.FlashcardRecord.review_count.desc(), models.FlashcardRecord.created_at).all()
            retained, retained_cards = {}, {}
            for card, note, _ in rows:
                if not note:
                    continue
                group = (note.course_name, _normalise(card.question))
                previous = retained.get(group)
                if previous is None:
                    question_words = set(group[1].split())
                    previous = next((other for other in retained_cards.get(note.course_name, [])[-35:] if len(question_words & set(_normalise(other.question).split())) / max(1, len(question_words | set(_normalise(other.question).split()))) >= .55 and SequenceMatcher(None, _normalise(other.question), group[1]).ratio() >= .78 and SequenceMatcher(None, _normalise(other.answer), _normalise(card.answer)).ratio() >= .90), None)
                if previous and SequenceMatcher(None, _normalise(previous.answer), _normalise(card.answer)).ratio() >= .90:
                    self.card(card.id)
                    self.card(previous.id)
                    self.duplicate_targets.add(("card", str(card.id)))
                    candidates.append({"component": "flashcards", "keep": {"id": str(previous.id), "question": previous.question, "answer": previous.answer, "reviews": previous.review_count}, "duplicate": {"id": str(card.id), "question": card.question, "answer": card.answer, "reviews": card.review_count}})
                else:
                    retained[group] = card
                    retained_cards.setdefault(note.course_name, []).append(card)
                if len(candidates) >= 50:
                    break
        return {"candidates": candidates[:50], "scanned_classes": scanned, "remaining_classes": len(notes) - scanned, "limited": len(candidates) >= 35, "rule": "La similitud no demuestra redundancia. Comprueba si hay un matiz o contexto distinto. Conserva ejemplos, extensiones y la tarjeta con más progreso. Las coincidencias se buscan dentro de cada curso."}

    def prepare(self, actions):
        if not isinstance(actions, list) or len(actions) > 50:
            raise ValueError("La propuesta debe contener hasta 50 operaciones.")
        frames = {}
        def frame(key):
            if key not in self.seen:
                raise ValueError("El agente debe consultar un elemento antes de proponer modificarlo.")
            if key not in frames:
                frames[key] = {**deepcopy(self.seen[key]), "after": deepcopy(self.seen[key]["before"])}
            return frames[key]
        for action in actions:
            op = action.get("op")
            if self.scope.get("preset") == "duplicates":
                permitted = op == "replace_note_text" and (str(action.get("note_id")), action.get("old")) in self.duplicate_targets or op == "delete_flashcard" and ("card", str(action.get("id"))) in self.duplicate_targets
                if not permitted:
                    raise ValueError("La herramienta de duplicados sólo puede modificar los candidatos detectados.")
            if op == "replace_note_text":
                target = frame(f"note:{action['note_id']}")
                target["after"] = replace_occurrence(target["after"], action.get("old"), action.get("new"), action.get("occurrence", 0))
            elif op == "edit_document":
                target = frame(f"document:{action['document_id']}")
                target["after"] = apply_operations(target["after"], action.get("operations", []))
            elif op in {"edit_chunk", "delete_chunk", "delete_embedding", "regenerate_embedding"}:
                target = frame(f"chunk:{action['kind']}:{action['id']}")
                if op == "delete_chunk":
                    target["after"] = None
                else:
                    content = action.get("content", target["after"]["content"])
                    if not isinstance(content, str) or not content.strip():
                        raise ValueError("El contenido del fragmento no puede quedar vacío.")
                    target["after"] = {"content": content, "has_embedding": op != "delete_embedding"}
                    target["embedding_action"] = op
            elif op in {"update_flashcard", "delete_flashcard"}:
                guard = frame(f"card_guard:{action['id']}")
                # La lectura explícita ya verificó la tarjeta y su nota fuente.
                card = self.db.get(models.FlashcardRecord, UUID(action["id"]))
                target = frame(f"note:{card.raw_note_id}")
                if op == "delete_flashcard":
                    target["after"] = update_card_source(target["after"], card, delete=True)
                else:
                    question = action.get("question", card.question)
                    answer = action.get("answer", card.answer)
                    if not isinstance(question, str) or not question.strip() or not isinstance(answer, str) or not answer.strip():
                        raise ValueError("Una tarjeta necesita pregunta y respuesta.")
                    target["after"] = update_card_source(target["after"], card, question, answer)
                guard["after"] = guard["before"]
            else:
                raise ValueError(f"Operación no permitida: {op}")
        results = []
        changed_notes = {frame["id"] for frame in frames.values() if frame["kind"] == "note" and frame["before"] != frame["after"]}
        for target in frames.values():
            if target["kind"] == "chunk" and target["chunk_kind"] == "note":
                row = self.db.get(models.NoteChunk, UUID(target["id"]))
                if str(row.processed_note.raw_note_id) in changed_notes:
                    raise ValueError("Edita la nota o sus chunks en propuestas separadas: cambiar la nota reconstruye sus chunks.")
        for target in frames.values():
            if target["kind"] != "card_guard" and target["before"] == target["after"] and not target.get("embedding_action"):
                continue
            target["expected"] = fingerprint(target["before"])
            before = render_markdown(target["before"]) if target["kind"] == "document" else display_value(target["before"])
            after = render_markdown(target["after"]) if target["kind"] == "document" else display_value(target["after"])
            target["diff"] = "\n".join(unified_diff(before.splitlines(), after.splitlines(), fromfile="Antes", tofile="Después", lineterm="", n=3))
            results.append(target)
        if len(json.dumps(results, ensure_ascii=False)) > 2_000_000:
            raise ValueError("La propuesta es demasiado grande. Divide la petición en grupos de notas.")
        return results if any(frame["kind"] != "card_guard" for frame in results) else []


def display_value(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) if value is not None else "[Elemento eliminado]"


def card_snapshot(card):
    return {"question": card.question, "answer": card.answer, "reviews": card.review_count, "interval_days": card.interval_days, "active": card.is_active}


def apply_frames(db, frames):
    """Verifica todos los snapshots antes de modificar nada; el llamador confirma la transacción."""
    loaded = {}
    for frame in sorted(frames, key=lambda item: (item["kind"], item["id"])):
        kind, row_id = frame["kind"], UUID(frame["id"])
        if kind == "note":
            row = db.query(models.RawNote).filter_by(id=row_id).with_for_update().one_or_none()
            processed = db.query(models.ProcessedNote).filter_by(raw_note_id=row_id).with_for_update().one_or_none()
            current = processed.structured_markdown if processed else None
        elif kind == "document":
            row = db.query(models.StructuredNoteDocument).filter_by(id=row_id).with_for_update().one_or_none()
            current = row.document_json if row else None
            if row and str(row.current_revision_id) != frame["revision"]:
                raise ValueError("La nota propia cambió. Solicita una propuesta nueva.")
        elif kind == "card_guard":
            row = db.query(models.FlashcardRecord).filter_by(id=row_id).with_for_update().one_or_none()
            current = card_snapshot(row) if row else None
        else:
            row = db.query(KINDS[frame["chunk_kind"]]).filter_by(id=row_id).with_for_update().one_or_none()
            current = {"content": row_content(row, frame["chunk_kind"]), "has_embedding": not row.is_dummy_embedding} if row else None
        if not row or fingerprint(current) != frame["expected"]:
            raise ValueError(f"{frame['label']} cambió desde la propuesta. Pide al agente que vuelva a revisarlo.")
        loaded[(kind, frame["id"])] = row
    for frame in frames:
        kind, after = frame["kind"], frame["after"]
        row = loaded[(kind, frame["id"])]
        if kind == "card_guard":
            continue
        if kind == "note":
            parts = split_note_markdown(after)
            state = {"structured_markdown": after, "glossary_markdown": parts["glossary"], "flashcards_markdown": parts["flashcards"]}
            persist_selection(db, row, state, ["glossary", "flashcards"])
            artifact = db.query(models.GenerationArtifact).filter_by(processed_note_id=row.processed_note.id).first()
            if artifact:
                artifact.body_markdown = parts["content"]
        elif kind == "document":
            _create_revision(db, row, after, change_kind="agent_edit", summary="Edición desde el agente global", actor="agent")
        elif after is None:
            db.delete(row)
        else:
            content = after["content"]
            if frame["chunk_kind"] == "claim":
                row.statement, row.claim_hash = content, _hash(_normalise(content))
            else:
                row.content = content
            if frame["chunk_kind"] == "source":
                row.content_hash = _hash(f"{row.source_type}\0edited\0{content}")
                row.char_start = row.char_end = None
            if frame.get("embedding_action") == "delete_embedding":
                row.embedding, row.is_dummy_embedding = ZERO_VECTOR[:], True
            else:
                vectors, dummies = embed_texts([content])
                if frame.get("embedding_action") == "regenerate_embedding" and any(dummies):
                    raise ValueError("VoyageAI no produjo un vector real. No se aplicó la propuesta.")
                row.embedding, row.is_dummy_embedding = vectors[0], dummies[0]
