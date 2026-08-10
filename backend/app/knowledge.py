"""Memoria de conocimiento v2 basada en evidencia original.

Este módulo es deliberadamente aditivo: no modifica transcripciones, Markdown
procesado ni ``note_chunks``. Todos los derivados pueden reconstruirse.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import re
from typing import Any, Iterable, Optional
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import llm_models, models


INDEX_VERSION = "knowledge-v2.1"
ZERO_VECTOR = [0.0] * 1024
NOVELTY_RELATIONS = {"NEW", "EXTENDS", "REPEATS", "APPLIES", "CLARIFIES", "CONTRADICTS"}


def _hash(value: str) -> str:
    return hashlib.sha256(value.strip().encode("utf-8")).hexdigest()


def _normalise(value: str) -> str:
    value = re.sub(r"[`*_#=\[\]()]", " ", value.lower())
    return re.sub(r"\s+", " ", value).strip()


def logical_course_notes(db: Session, course_name: str) -> list[models.RawNote]:
    """Orden estable compatible con índices repetidos o con huecos."""
    return (
        db.query(models.RawNote)
        .filter(models.RawNote.course_name == course_name)
        .order_by(
            models.RawNote.order_index.asc(),
            models.RawNote.created_at.asc(),
            models.RawNote.id.asc(),
        )
        .all()
    )


def prior_note_ids(db: Session, note: models.RawNote) -> list[UUID]:
    ordered = logical_course_notes(db, note.course_name)
    ids = [item.id for item in ordered]
    try:
        return ids[: ids.index(note.id)]
    except ValueError:
        return []


def logical_previous_note(db: Session, note: models.RawNote) -> Optional[models.RawNote]:
    ids = prior_note_ids(db, note)
    return db.query(models.RawNote).filter(models.RawNote.id == ids[-1]).first() if ids else None


def _window_chunks(text: str, size: int = 1600, overlap: int = 200) -> Iterable[tuple[str, int, int]]:
    text = (text or "").strip()
    if not text:
        return
    start = 0
    while start < len(text):
        target = min(len(text), start + size)
        end = target
        if target < len(text):
            candidates = [text.rfind(mark, start + size // 2, target) for mark in ("\n\n", ". ", "\n")]
            boundary = max(candidates)
            if boundary > start:
                end = boundary + (2 if text[boundary:boundary + 2] in {"\n\n", ". "} else 1)
        chunk = text[start:end].strip()
        if chunk:
            yield chunk, start, end
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)


def build_source_chunks(note: models.RawNote) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    def add(source_type: str, content: str, start: Optional[int] = None, end: Optional[int] = None) -> None:
        content = (content or "").strip()
        if not content:
            return
        result.append({
            "source_type": source_type,
            "content": content,
            "content_hash": _hash(f"{source_type}\0{start}\0{content}"),
            "chunk_index": len(result),
            "char_start": start,
            "char_end": end,
        })

    for content, start, end in _window_chunks(note.transcription or ""):
        add("transcription", content, start, end)
    for source_type, text in (("my_notes", note.my_notes), ("summary", note.class_summary)):
        for content, start, end in _window_chunks(text or ""):
            add(source_type, content, start, end)
    for snippet in note.code_snippets or []:
        add("code", f"Lenguaje: {snippet.get('lang', '')}\n{snippet.get('code', '')}")
    for snippet in note.command_snippets or []:
        add("command", f"Lenguaje: {snippet.get('lang', '')}\n{snippet.get('cmd', '')}")
    for image in note.images or []:
        if image.descripcion_llm:
            add("image", image.descripcion_llm)
    return result


def embed_texts(texts: list[str], batch_size: int = 32) -> tuple[list[list[float]], list[bool]]:
    if not texts:
        return [], []
    key = os.getenv("VOYAGE_API_KEY")
    if not key:
        return [ZERO_VECTOR[:] for _ in texts], [True] * len(texts)
    try:
        import voyageai
        client = voyageai.Client(api_key=key)
        vectors: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            response = client.embed(texts[start:start + batch_size], model="voyage-4")
            vectors.extend(response.embeddings)
        return vectors, [False] * len(vectors)
    except Exception:
        return [ZERO_VECTOR[:] for _ in texts], [True] * len(texts)


def parse_flashcards(markdown: str) -> list[dict[str, str]]:
    """Extrae las formas de Obsidian actuales sin alterar el Markdown."""
    match = re.search(r"^##\s+🗃️\s+Flashcards\s*$([\s\S]*?)(?=^##\s|\Z)", markdown or "", re.MULTILINE)
    if not match:
        return []
    section = match.group(1)
    cards: list[dict[str, str]] = []
    lines = section.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line or line.startswith("#flashcards/"):
            index += 1
            continue
        if "::" in line and not line.startswith(("http://", "https://")):
            question, answer = line.split("::", 1)
            if question.strip() and answer.strip():
                cards.append({"question": question.strip(), "answer": answer.lstrip("?").strip()})
        elif index + 2 < len(lines) and lines[index + 1].strip() in {"?", "??"}:
            answer_index = index + 2
            answer_lines = []
            while answer_index < len(lines) and lines[answer_index].strip():
                answer_lines.append(lines[answer_index].strip())
                answer_index += 1
            if line and answer_lines:
                cards.append({"question": line, "answer": " ".join(answer_lines)})
            index = answer_index - 1
        else:
            clozes = re.findall(r"==([^=]+)==", line)
            for cloze in clozes:
                cards.append({"question": line.replace(f"=={cloze}==", "[…]"), "answer": cloze.strip()})
        index += 1
    dedup: dict[str, dict[str, str]] = {}
    for card in cards:
        dedup.setdefault(_hash(_normalise(card["question"])), card)
    return list(dedup.values())


def _extract_json(text: str) -> Any:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    start_candidates = [pos for pos in (text.find("["), text.find("{")) if pos >= 0]
    if not start_candidates:
        raise ValueError("El modelo auxiliar no devolvió JSON")
    start = min(start_candidates)
    end = max(text.rfind("]"), text.rfind("}"))
    return json.loads(text[start:end + 1])


def recent_prior_claims(db: Session, note: models.RawNote, limit: int = 80) -> list[models.NoteClaim]:
    ids = prior_note_ids(db, note)
    if not ids:
        return []
    return (
        db.query(models.NoteClaim)
        .filter(models.NoteClaim.raw_note_id.in_(ids))
        .order_by(models.NoteClaim.created_at.desc())
        .limit(limit)
        .all()
    )


def extract_claims(note: models.RawNote, db: Session, historical: Optional[list[models.NoteClaim]] = None) -> list[dict[str, Any]]:
    evidence_parts = []
    for chunk in build_source_chunks(note):
        evidence_parts.append(
            f"[FUENTE:{chunk['source_type']}:{chunk['char_start'] or 0}-{chunk['char_end'] or 0}]\n{chunk['content']}"
        )
    evidence = "\n\n".join(evidence_parts)[:60000]
    if not evidence.strip():
        return []
    historical = historical if historical is not None else recent_prior_claims(db, note)
    prior_payload = [
        {"id": str(item.id), "concept": item.concept, "statement": item.statement}
        for item in historical
    ]
    prompt = f"""Eres el modelo auxiliar de un sistema de apuntes progresivos.
Extrae afirmaciones atómicas respaldadas por la evidencia actual. Compara cada una con el historial y clasifícala como NEW, EXTENDS, REPEATS, APPLIES, CLARIFIES o CONTRADICTS.
Política equilibrada: una aplicación nueva no es repetición aunque use teoría conocida. No inventes información y copia una evidencia breve literal de la fuente actual.

CURSO: {note.course_name}
CLASE: {note.class_title}
AFIRMACIONES HISTÓRICAS (id válido para prior_claim_id):
{json.dumps(prior_payload, ensure_ascii=False)}

EVIDENCIA ACTUAL:
{evidence}

Devuelve exclusivamente un array JSON con objetos:
{{"concept":"...","statement":"...","relation":"NEW|EXTENDS|REPEATS|APPLIES|CLARIFIES|CONTRADICTS","prior_claim_id":null|"uuid","evidence_source_type":"transcription|my_notes|summary|code|command|image","evidence_text":"...","confidence":0.0}}
Incluye toda afirmación útil, pero evita dividir una misma idea en paráfrasis redundantes."""
    resolved = llm_models.resolve_selected_model(db, "query_expansion")
    llm = llm_models.create_chat_model(resolved, timeout=90, max_retries=2)
    payload = None
    last_error: Optional[Exception] = None
    for attempt in range(3):
        retry_instruction = "" if attempt == 0 else (
            "\n\nTu respuesta anterior no era JSON válido. Repite toda la salida, "
            "usa comillas dobles, escapa comillas internas y no añadas Markdown."
        )
        response = llm.invoke(prompt + retry_instruction)
        content = response.content if isinstance(response.content, str) else str(response.content)
        try:
            payload = _extract_json(content)
            break
        except (ValueError, json.JSONDecodeError) as exc:
            last_error = exc
    if payload is None:
        raise ValueError(f"El modelo auxiliar no produjo JSON válido tras 3 intentos: {last_error}")
    if isinstance(payload, dict):
        payload = payload.get("claims", [])
    if not isinstance(payload, list):
        raise ValueError("El manifiesto de afirmaciones no es una lista")
    valid_prior = {str(item.id) for item in historical}
    output = []
    seen = set()
    for item in payload:
        if not isinstance(item, dict) or not str(item.get("statement", "")).strip():
            continue
        statement = str(item["statement"]).strip()
        claim_hash = _hash(_normalise(statement))
        if claim_hash in seen:
            continue
        seen.add(claim_hash)
        relation = str(item.get("relation", "NEW")).upper()
        prior_id = str(item.get("prior_claim_id") or "")
        output.append({
            "concept": str(item.get("concept", "")).strip()[:255],
            "statement": statement,
            "claim_hash": claim_hash,
            "novelty_relation": relation if relation in NOVELTY_RELATIONS else "NEW",
            "prior_claim_id": prior_id if prior_id in valid_prior else None,
            "evidence_source_type": str(item.get("evidence_source_type", "transcription"))[:32],
            "evidence_text": str(item.get("evidence_text", "")).strip()[:1200],
            "confidence": max(0.0, min(1.0, float(item.get("confidence", 0.8)))),
        })
    return output


def extract_claims_batch(notes: list[models.RawNote], db: Session) -> dict[UUID, list[dict[str, Any]]]:
    """Extrae un pequeño bloque cronológico en una llamada, preservando relaciones internas."""
    if not notes:
        return {}
    historical = recent_prior_claims(db, notes[0])
    prior_payload = [
        {"id": str(item.id), "concept": item.concept, "statement": item.statement}
        for item in historical
    ]
    note_payload = []
    for index, note in enumerate(notes):
        chunks = build_source_chunks(note)
        evidence = "\n\n".join(
            f"[FUENTE:{item['source_type']}] {item['content']}" for item in chunks
        )[:24000]
        note_payload.append({
            "index": str(index), "title": note.class_title,
            "module": note.course_module, "evidence": evidence,
        })
    required_keys = [str(index) for index in range(len(notes))]
    prompt = f"""Eres el modelo auxiliar de apuntes progresivos. Las clases actuales están en orden cronológico.
Extrae afirmaciones atómicas respaldadas y clasifícalas como NEW, EXTENDS, REPEATS, APPLIES, CLARIFIES o CONTRADICTS respecto al historial y a las clases anteriores del mismo bloque.
Una aplicación nueva no es repetición. No inventes ni generes paráfrasis redundantes.
HISTORIAL: {json.dumps(prior_payload, ensure_ascii=False)}
CLASES ACTUALES: {json.dumps(note_payload, ensure_ascii=False)}
Debes devolver exactamente las claves {json.dumps(required_keys)} aunque alguna lista quede vacía.
Devuelve exclusivamente un objeto JSON: {{"0":[{{"concept":"...","statement":"...","relation":"NEW|EXTENDS|REPEATS|APPLIES|CLARIFIES|CONTRADICTS","prior_claim_id":null|"uuid del historial","evidence_source_type":"transcription|my_notes|summary|code|command|image","evidence_text":"...","confidence":0.0}}],"1":[],"2":[]}}."""
    resolved = llm_models.resolve_selected_model(db, "query_expansion")
    llm = llm_models.create_chat_model(resolved, timeout=180, max_retries=2, max_tokens=8192)
    payload = None
    last_error: Optional[Exception] = None
    for attempt in range(3):
        suffix = "" if attempt == 0 else "\nLa salida anterior no era JSON válido. Repite todo sin Markdown y escapa las comillas internas."
        try:
            payload = _extract_json(_extract_response_text(llm.invoke(prompt + suffix)))
            break
        except (ValueError, json.JSONDecodeError) as exc:
            last_error = exc
    if not isinstance(payload, dict):
        raise ValueError(f"Extracción por lote inválida: {last_error}")

    valid_prior = {str(item.id) for item in historical}
    result: dict[UUID, list[dict[str, Any]]] = {note.id: [] for note in notes}
    for index, note in enumerate(notes):
        group = payload.get(str(index), [])
        if not isinstance(group, list):
            continue
        seen = set()
        for item in group:
            if not isinstance(item, dict):
                continue
            statement = str(item.get("statement", "")).strip()
            if not statement:
                continue
            claim_hash = _hash(_normalise(statement))
            if claim_hash in seen:
                continue
            seen.add(claim_hash)
            relation = str(item.get("relation", "NEW")).upper()
            prior_id = str(item.get("prior_claim_id") or "")
            try:
                confidence = max(0.0, min(1.0, float(item.get("confidence", 0.8))))
            except (TypeError, ValueError):
                confidence = 0.8
            result[note.id].append({
                "concept": str(item.get("concept", ""))[:255],
                "statement": statement,
                "claim_hash": claim_hash,
                "novelty_relation": relation if relation in NOVELTY_RELATIONS else "NEW",
                "prior_claim_id": prior_id if prior_id in valid_prior else None,
                "evidence_source_type": str(item.get("evidence_source_type", "transcription"))[:32],
                "evidence_text": str(item.get("evidence_text", ""))[:1200],
                "confidence": confidence,
            })
    return result


def _extract_response_text(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in content)
    return str(content)


def index_note_knowledge(
    db: Session,
    note: models.RawNote,
    *,
    extract_with_llm: bool = True,
    embed_vectors: bool = True,
    claims_override: Optional[list[dict[str, Any]]] = None,
) -> dict[str, int]:
    state = db.get(models.KnowledgeIndexState, note.id)
    if state is None:
        state = models.KnowledgeIndexState(raw_note_id=note.id, index_version=INDEX_VERSION)
        db.add(state)
    state.status = "processing"
    state.attempts = (state.attempts or 0) + 1
    state.last_error = None
    db.commit()
    try:
        source_data = build_source_chunks(note)
        processed_markdown = note.processed_note.structured_markdown if note.processed_note else ""
        card_data = parse_flashcards(processed_markdown)
        claim_data = claims_override if claims_override is not None else (extract_claims(note, db) if extract_with_llm else [])
        source_texts = [item["content"] for item in source_data]
        card_texts = [f"{item['question']}\n{item['answer']}" for item in card_data]
        claim_texts = [item["statement"] for item in claim_data]
        combined_texts = source_texts + card_texts + claim_texts
        if embed_vectors:
            all_vectors, all_dummy = embed_texts(combined_texts)
        else:
            all_vectors, all_dummy = [ZERO_VECTOR[:] for _ in combined_texts], [True] * len(combined_texts)
        source_end = len(source_texts)
        card_end = source_end + len(card_texts)
        source_vectors, source_dummy = all_vectors[:source_end], all_dummy[:source_end]
        card_vectors, card_dummy = all_vectors[source_end:card_end], all_dummy[source_end:card_end]
        claim_vectors, claim_dummy = all_vectors[card_end:], all_dummy[card_end:]

        db.query(models.SourceChunk).filter(models.SourceChunk.raw_note_id == note.id).delete()
        db.query(models.NoteClaim).filter(models.NoteClaim.raw_note_id == note.id).delete()
        db.query(models.FlashcardRecord).filter(models.FlashcardRecord.raw_note_id == note.id).delete()

        for item, vector, dummy in zip(source_data, source_vectors, source_dummy):
            db.add(models.SourceChunk(raw_note_id=note.id, embedding=vector, is_dummy_embedding=dummy, **item))
        for item, vector, dummy in zip(claim_data, claim_vectors, claim_dummy):
            claim_values = dict(item)
            prior_id = claim_values.get("prior_claim_id")
            claim_values["prior_claim_id"] = UUID(prior_id) if prior_id else None
            db.add(models.NoteClaim(raw_note_id=note.id, embedding=vector, is_dummy_embedding=dummy, **claim_values))
        for item, vector, dummy in zip(card_data, card_vectors, card_dummy):
            db.add(models.FlashcardRecord(
                raw_note_id=note.id,
                question=item["question"],
                answer=item["answer"],
                fingerprint=_hash(_normalise(item["question"])),
                embedding=vector,
                is_dummy_embedding=dummy,
            ))
        state.status = "complete"
        state.index_version = INDEX_VERSION
        state.last_error = None
        db.commit()
        return {"source_chunks": len(source_data), "claims": len(claim_data), "flashcards": len(card_data)}
    except Exception as exc:
        db.rollback()
        state = db.get(models.KnowledgeIndexState, note.id)
        if state is None:
            state = models.KnowledgeIndexState(raw_note_id=note.id, index_version=INDEX_VERSION)
            db.add(state)
        state.status = "failed"
        state.last_error = str(exc)[:4000]
        db.commit()
        raise


def reembed_dummy_knowledge(db: Session, batch_size: int = 64) -> dict[str, int]:
    """Vectoriza derivados pendientes en lotes entre tablas para reducir round-trips."""
    rows: list[tuple[Any, str]] = []
    rows.extend((row, row.content) for row in db.query(models.SourceChunk).filter(models.SourceChunk.is_dummy_embedding == True).all())
    rows.extend((row, row.statement) for row in db.query(models.NoteClaim).filter(models.NoteClaim.is_dummy_embedding == True).all())
    rows.extend((row, f"{row.question}\n{row.answer}") for row in db.query(models.FlashcardRecord).filter(models.FlashcardRecord.is_dummy_embedding == True).all())
    updated = failed = 0
    for start in range(0, len(rows), max(1, batch_size)):
        batch = rows[start:start + max(1, batch_size)]
        vectors, dummy_flags = embed_texts([text for _, text in batch], batch_size=max(1, batch_size))
        for (row, _), vector, is_dummy in zip(batch, vectors, dummy_flags):
            if is_dummy:
                failed += 1
                continue
            row.embedding = vector
            row.is_dummy_embedding = False
            updated += 1
        db.commit()
        print(f"Embeddings v2: {min(start + len(batch), len(rows))}/{len(rows)}", flush=True)
    return {"total": len(rows), "updated": updated, "failed": failed}


def _tokens(value: str) -> set[str]:
    return {word for word in re.findall(r"[\wáéíóúüñ]{4,}", value.lower())}


def retrieve_prior_knowledge(db: Session, note: models.RawNote, limit: int = 10) -> dict[str, Any]:
    """Recuperación densa+lexical con RRF, diversidad por nota y fallback legado."""
    ids = prior_note_ids(db, note)
    previous = logical_previous_note(db, note)
    if not ids:
        return {"previous": None, "claims": [], "evidence": [], "flashcards": []}
    queries = build_source_chunks(note)
    if queries:
        positions = sorted({0, len(queries) // 3, (2 * len(queries)) // 3, len(queries) - 1})
        representative = [queries[index]["content"] for index in positions]
    else:
        representative = [note.class_title]
    vectors, dummies = embed_texts(representative)
    scores: dict[tuple[str, UUID], float] = defaultdict(float)
    objects: dict[tuple[str, UUID], Any] = {}

    if vectors and not all(dummies):
        for vector in vectors:
            claim_rows = (
                db.query(models.NoteClaim)
                .filter(
                    models.NoteClaim.raw_note_id.in_(ids),
                    models.NoteClaim.is_dummy_embedding == False,
                    models.NoteClaim.embedding.cosine_distance(vector) <= 0.32,
                )
                .order_by(models.NoteClaim.embedding.cosine_distance(vector))
                .limit(30).all()
            )
            source_rows = (
                db.query(models.SourceChunk)
                .filter(
                    models.SourceChunk.raw_note_id.in_(ids),
                    models.SourceChunk.is_dummy_embedding == False,
                    models.SourceChunk.embedding.cosine_distance(vector) <= 0.32,
                )
                .order_by(models.SourceChunk.embedding.cosine_distance(vector))
                .limit(30).all()
            )
            for kind, rows in (("claim", claim_rows), ("source", source_rows)):
                for rank, row in enumerate(rows, 1):
                    key = (kind, row.id)
                    scores[key] += 1.0 / (60 + rank)
                    objects[key] = row

    query_terms = _tokens(" ".join(representative))
    lexical_pool = (
        db.query(models.SourceChunk)
        .filter(models.SourceChunk.raw_note_id.in_(ids))
        .order_by(models.SourceChunk.created_at.desc()).limit(300).all()
    )
    lexical_ranked = sorted(
        lexical_pool,
        key=lambda row: len(query_terms & _tokens(row.content)) / max(1, len(query_terms | _tokens(row.content))),
        reverse=True,
    )[:30]
    for rank, row in enumerate(lexical_ranked, 1):
        key = ("source", row.id)
        scores[key] += 1.0 / (60 + rank)
        objects[key] = row

    ranked = sorted(scores, key=scores.get, reverse=True)
    selected = []
    per_note: dict[UUID, int] = defaultdict(int)
    selected_texts: list[set[str]] = []
    for key in ranked:
        row = objects[key]
        if per_note[row.raw_note_id] >= 2:
            continue
        text = row.statement if key[0] == "claim" else row.content
        terms = _tokens(text)
        diversity = max((len(terms & prior) / max(1, len(terms | prior)) for prior in selected_texts), default=0.0)
        if diversity > 0.70:
            continue
        selected.append((key[0], row, scores[key]))
        selected_texts.append(terms)
        per_note[row.raw_note_id] += 1
        if len(selected) >= limit:
            break

    claims = [{"id": str(row.id), "concept": row.concept, "statement": row.statement,
               "relation": row.novelty_relation, "raw_note_id": str(row.raw_note_id)}
              for kind, row, _ in selected if kind == "claim"]
    evidence = [{"id": str(row.id), "content": row.content, "source_type": row.source_type,
                 "raw_note_id": str(row.raw_note_id)}
                for kind, row, _ in selected if kind == "source"]
    historical_cards = (
        db.query(models.FlashcardRecord)
        .filter(models.FlashcardRecord.raw_note_id.in_(ids))
        .order_by(models.FlashcardRecord.created_at.desc()).all()
    )
    return {
        "previous": {"id": str(previous.id), "title": previous.class_title} if previous else None,
        "claims": claims,
        "evidence": evidence,
        "flashcards": [{"question": item.question, "answer": item.answer} for item in historical_cards],
    }


def knowledge_status(db: Session) -> dict[str, Any]:
    states = db.query(models.KnowledgeIndexState).all()
    by_status: dict[str, int] = defaultdict(int)
    for state in states:
        by_status[state.status] += 1
    total_notes = db.query(models.RawNote).count()
    return {
        "index_version": INDEX_VERSION,
        "total_notes": total_notes,
        "indexed_notes": by_status.get("complete", 0),
        "pending_notes": max(0, total_notes - len(states)) + by_status.get("pending", 0),
        "processing_notes": by_status.get("processing", 0),
        "failed_notes": by_status.get("failed", 0),
        "source_chunks": db.query(models.SourceChunk).count(),
        "claims": db.query(models.NoteClaim).count(),
        "flashcards": db.query(models.FlashcardRecord).count(),
        "dummy_source_embeddings": db.query(models.SourceChunk).filter(models.SourceChunk.is_dummy_embedding == True).count(),
        "dummy_claim_embeddings": db.query(models.NoteClaim).filter(models.NoteClaim.is_dummy_embedding == True).count(),
        "dummy_flashcard_embeddings": db.query(models.FlashcardRecord).filter(models.FlashcardRecord.is_dummy_embedding == True).count(),
    }


def persist_v2_derivatives(
    db: Session,
    note: models.RawNote,
    processed_note: models.ProcessedNote,
    state: dict[str, Any],
) -> None:
    """Prepara todos los derivados v2 en la transacción abierta del llamador."""
    from app.glossary import compile_glossary_markdown, merge_entries, parse_glossary_entries

    source_data = build_source_chunks(note)
    claim_data = state.get("evidence_manifest", []) or []
    card_data = parse_flashcards(state.get("structured_markdown", ""))
    source_texts = [item["content"] for item in source_data]
    claim_texts = [str(item.get("statement", "")) for item in claim_data]
    card_texts = [f"{item['question']}\n{item['answer']}" for item in card_data]
    all_vectors, all_dummy = embed_texts(source_texts + claim_texts + card_texts)
    source_end = len(source_texts)
    claim_end = source_end + len(claim_texts)
    source_vectors, source_dummy = all_vectors[:source_end], all_dummy[:source_end]
    claim_vectors, claim_dummy = all_vectors[source_end:claim_end], all_dummy[source_end:claim_end]
    card_vectors, card_dummy = all_vectors[claim_end:], all_dummy[claim_end:]

    db.query(models.SourceChunk).filter(models.SourceChunk.raw_note_id == note.id).delete()
    db.query(models.NoteClaim).filter(models.NoteClaim.raw_note_id == note.id).delete()
    db.query(models.FlashcardRecord).filter(models.FlashcardRecord.raw_note_id == note.id).delete()

    for item, vector, dummy in zip(source_data, source_vectors, source_dummy):
        db.add(models.SourceChunk(raw_note_id=note.id, embedding=vector, is_dummy_embedding=dummy, **item))
    for item, vector, dummy in zip(claim_data, claim_vectors, claim_dummy):
        statement = str(item.get("statement", "")).strip()
        if not statement:
            continue
        relation = str(item.get("novelty_relation", item.get("relation", "NEW"))).upper()
        prior_id = item.get("prior_claim_id")
        db.add(models.NoteClaim(
            raw_note_id=note.id,
            prior_claim_id=UUID(str(prior_id)) if prior_id else None,
            concept=str(item.get("concept", ""))[:255],
            statement=statement,
            claim_hash=str(item.get("claim_hash") or _hash(_normalise(statement))),
            novelty_relation=relation if relation in NOVELTY_RELATIONS else "NEW",
            evidence_source_type=str(item.get("evidence_source_type", "transcription"))[:32],
            evidence_text=str(item.get("evidence_text", ""))[:1200],
            confidence=float(item.get("confidence", 0.8)),
            embedding=vector,
            is_dummy_embedding=dummy,
        ))
    for item, vector, dummy in zip(card_data, card_vectors, card_dummy):
        db.add(models.FlashcardRecord(
            raw_note_id=note.id,
            question=item["question"], answer=item["answer"],
            fingerprint=_hash(_normalise(item["question"])),
            embedding=vector, is_dummy_embedding=dummy,
        ))

    artifact = db.query(models.GenerationArtifact).filter(
        models.GenerationArtifact.processed_note_id == processed_note.id
    ).first()
    historical = state.get("historical_context", {}) or {}
    historical_audit = {
        "previous": historical.get("previous"),
        "claims": historical.get("claims", []),
        "evidence": [
            {"id": item.get("id"), "raw_note_id": item.get("raw_note_id"), "source_type": item.get("source_type")}
            for item in historical.get("evidence", [])
        ],
        "flashcards_considered": len(historical.get("flashcards", [])),
    }
    values = {
        "pipeline_version": "v2",
        "body_markdown": state.get("body_markdown", ""),
        "glossary_markdown": state.get("glossary_markdown", ""),
        "flashcards_markdown": state.get("flashcards_markdown", ""),
        "evidence_manifest": {"claims": claim_data, "historical": historical_audit},
        "metrics": state.get("metrics", {}),
    }
    if artifact is None:
        artifact = models.GenerationArtifact(processed_note_id=processed_note.id, **values)
        db.add(artifact)
    else:
        for key, value in values.items():
            setattr(artifact, key, value)

    new_glossary_entries = parse_glossary_entries(state.get("glossary_markdown", ""), note.class_title)
    glossary = db.query(models.CourseGlossary).filter(models.CourseGlossary.course_name == note.course_name).first()
    if new_glossary_entries:
        merged = merge_entries(glossary.entries if glossary else [], new_glossary_entries)
        compiled = compile_glossary_markdown(merged, note.course_name)
        if glossary is None:
            db.add(models.CourseGlossary(course_name=note.course_name, entries=merged, compiled_markdown=compiled))
        else:
            glossary.entries = merged
            glossary.compiled_markdown = compiled

    index_state = db.get(models.KnowledgeIndexState, note.id)
    if index_state is None:
        index_state = models.KnowledgeIndexState(raw_note_id=note.id, index_version=INDEX_VERSION)
        db.add(index_state)
    index_state.index_version = INDEX_VERSION
    index_state.status = "complete"
    index_state.last_error = None
