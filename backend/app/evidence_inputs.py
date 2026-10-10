"""Lossless evidence pages and conservative novelty-cache identity."""
import hashlib
import json
import re

VERSION = "evidence-v5"


def source_parts(note):
    parts = []
    for kind, attribute in (("transcription", "transcription"), ("my_notes", "my_notes"), ("summary", "class_summary")):
        text = (getattr(note, attribute, "") or "").strip()
        if text:
            parts.append((kind, text))
    for snippet in getattr(note, "code_snippets", None) or []:
        parts.append(("code", f"Lenguaje: {snippet.get('lang', '')}\n{snippet.get('code', '')}"))
    for snippet in getattr(note, "command_snippets", None) or []:
        parts.append(("command", f"Lenguaje: {snippet.get('lang', '')}\n{snippet.get('cmd', '')}"))
    for image in getattr(note, "images", None) or []:
        if image.descripcion_llm:
            parts.append(("image", image.descripcion_llm))
    return parts


def evidence_pages(parts, size=8000):
    """No overlapping windows or silent 60k truncation; every source is covered."""
    pages, page = [], ""
    for kind, text in parts:
        start = 0
        while start < len(text):
            end = min(len(text), start + size)
            if end < len(text):
                boundary = max(text.rfind(mark, start + size // 2, end) for mark in ("\n\n", ". ", "\n"))
                if boundary > start:
                    end = boundary + 1
            fragment = f"[FUENTE:{kind}:{start}-{end}]\n{text[start:end]}"
            if page and len(page) + len(fragment) + 2 > size:
                pages.append(page)
                page = ""
            page += ("\n\n" if page else "") + fragment
            start = end
    if page:
        pages.append(page)
    return pages


def referenced_evidence(parts, size=8000):
    """Backend-owned source references: the model selects IDs, never copies quotes."""
    refs = []
    for kind, text in parts:
        start = 0
        while start < len(text):
            end = min(len(text), start + 500)
            if end < len(text):
                boundary = max(text.rfind(mark, start + 250, end) for mark in ("\n\n", ". ", "\n"))
                if boundary > start:
                    end = boundary + 1
            refs.append({"source_type": kind, "text": text[start:end], "start": start, "end": end})
            start = end
    pages, current, chars = [], [], 0
    for ref in refs:
        if current and chars + len(ref["text"]) > size:
            pages.append(current)
            current, chars = [], 0
        current.append(ref)
        chars += len(ref["text"])
    if current:
        pages.append(current)
    return [("\n\n".join(f"[{index} {ref['source_type']}] {ref['text']}" for index, ref in enumerate(page)), page) for page in pages]


def evidence_key(note, parts, historical, scope, model):
    payload = {"version": VERSION, "course": note.course_name, "class": note.class_title,
               "parts": parts, "historical": sorted(historical, key=lambda row: row["id"]),
               "scope": scope, "model": model}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


_STOP = set("que qué como cómo para por una uno unos las los del con sin esta este esto son ser más donde cuando entre the and for with from what how does de el la en es se un al lo su o y a".split())


def terms(text):
    # Keep short commands, numbers and flags: 'cp' and 'cd' are different concepts.
    return set(re.findall(r"[\w]+(?:[-./][\w]+)*", text.lower())) - _STOP


def relevant_history(rows, query, *, text, limit=28, budget=12000):
    query_terms = terms(query)
    scored = []
    for index, row in enumerate(rows):
        content = text(row)
        words = terms(content)
        overlap = len(query_terms & words)
        if overlap:
            scored.append((overlap / max(1, len(words)) ** 0.5, -index, row, len(content)))
    result, used = [], 0
    for _, _, row, cost in sorted(scored, key=lambda item: item[:2], reverse=True):
        if used + cost > budget:
            continue
        result.append(row)
        used += cost
        if len(result) >= limit:
            break
    return result


def brief_claims(claims):
    return [{"concept": item.get("concept", ""), "statement": item.get("statement", ""),
             "relation": item.get("novelty_relation", "NEW"),
             **({"prior_claim_id": item["prior_claim_id"]} if item.get("prior_claim_id") else {})} for item in claims]


def novelty_outline(claims):
    """Supplements already see the final body; don't send all its facts twice."""
    groups = {}
    for item in claims:
        concept = item.get("concept", "")
        groups.setdefault(concept, set()).add(item.get("novelty_relation", "NEW"))
    return [{"concept": concept, "relations": sorted(relations)} for concept, relations in groups.items()]
