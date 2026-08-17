"""Nombres canónicos y deterministas para decks de flashcards."""

import re
import unicodedata


DECK_TAG_RE = re.compile(r"^#flashcards/\S+[ \t]*$", re.MULTILINE)
FLASHCARD_HEADING_RE = re.compile(r"^(##\s+🗃️\s+Flashcards\s*)$", re.MULTILINE)


def deck_segment(value: str | None, fallback: str) -> str:
    normalized = unicodedata.normalize("NFKD", (value or "").strip())
    ascii_value = "".join(character for character in normalized if not unicodedata.combining(character))
    tokens = re.findall(r"[A-Za-z0-9]+", ascii_value)
    if not tokens:
        return fallback

    def canonical_token(token: str) -> str:
        if token.islower():
            return token.capitalize()
        return token[0].upper() + token[1:]

    return "".join(canonical_token(token) for token in tokens)


def canonical_deck_tag(course_name: str, course_module: str | None) -> str:
    course = deck_segment(course_name, "Curso")
    module = deck_segment(course_module, "General")
    return f"#flashcards/{course}/{module}"


def normalize_flashcard_deck(markdown: str, course_name: str, course_module: str | None) -> str:
    """Impone una sola ruta canónica sin alterar preguntas ni respuestas."""
    expected = canonical_deck_tag(course_name, course_module)
    found = False

    def replace_tag(_: re.Match[str]) -> str:
        nonlocal found
        if found:
            return ""
        found = True
        return expected

    normalized = DECK_TAG_RE.sub(replace_tag, markdown or "")
    if not found and FLASHCARD_HEADING_RE.search(normalized):
        normalized = FLASHCARD_HEADING_RE.sub(rf"\1\n{expected}", normalized, count=1)
    return normalized


def has_canonical_deck(markdown: str, course_name: str, course_module: str | None) -> bool:
    tags = [tag.strip() for tag in DECK_TAG_RE.findall(markdown or "")]
    return tags == [canonical_deck_tag(course_name, course_module)]
