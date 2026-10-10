"""Límites de los componentes de una nota respetando cercas Markdown."""
import re


def split_note_markdown(markdown: str) -> dict[str, str]:
    parts = {"content": "", "glossary": "", "flashcards": "", "processing": ""}
    current = "content"
    fence = None
    for line in markdown.splitlines(keepends=True):
        match = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if match:
            token = match.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
        elif fence is None:
            if re.match(r"^##\s+(?:📖\s*)?Conceptos Clave\s*\(Glosario\)", line, re.IGNORECASE):
                current = "glossary"
            elif re.match(r"^##\s+(?:🗃️\s*)?Flashcards\s*$", line, re.IGNORECASE):
                current = "flashcards"
            elif re.match(r"^##\s+(?:🧠\s*)?Zona(?:\s|$)", line, re.IGNORECASE):
                current = "processing"
        parts[current] += line
    return parts


def supplement_section(markdown: str, component: str) -> str:
    """Un suplemento termina en el siguiente H2 real, aunque su título sea libre."""
    lines = split_note_markdown(markdown).get(component, "").splitlines(keepends=True)
    if not lines:
        return ""
    kept = [lines[0]]
    fence = None
    for line in lines[1:]:
        match = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if match:
            token = match.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
        elif fence is None and re.match(r"^##\s", line):
            break
        kept.append(line)
    return "".join(kept)


def supplement_span(markdown: str, component: str) -> tuple[int, int]:
    patterns = {"glossary": r"^##\s+(?:📖\s*)?Conceptos Clave\s*\(Glosario\)", "flashcards": r"^##\s+(?:🗃️\s*)?Flashcards\s*$"}
    start, offset, fence = None, 0, None
    for line in markdown.splitlines(keepends=True):
        match = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if match:
            token = match.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
        elif fence is None:
            if start is not None and re.match(r"^##\s", line):
                return start, offset
            if start is None and re.match(patterns[component], line, re.IGNORECASE):
                start = offset
        offset += len(line)
    if start is None:
        raise ValueError("No se encontró la sección solicitada.")
    return start, len(markdown)
