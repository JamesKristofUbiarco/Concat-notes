"""Sincronización determinística de cursos Markdown con una carpeta montada."""

from __future__ import annotations

import asyncio
import difflib
import hashlib
import os
import re
import shutil
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app import models
from app.database import SessionLocal
from app.deck_names import normalize_flashcard_deck


SYNC_VERSION = 1
DEFAULT_SUBPATH = "Cursos"
ZERO_VECTOR = [0.0] * 1024
sync_lock = asyncio.Lock()


class LocalSyncError(RuntimeError):
    pass


class LocalSyncConflict(LocalSyncError):
    pass


def sync_root() -> Path:
    return Path(os.getenv("LOCAL_SYNC_ROOT", "/sync")).expanduser().resolve()


def mount_status() -> dict[str, Any]:
    root = sync_root()
    return {
        "mounted": root.exists() and root.is_dir(),
        "writable": root.exists() and root.is_dir() and os.access(root, os.W_OK),
        "root_label": root.name or "sync",
    }


def _safe_path(relative: str, *, create: bool = False) -> Path:
    root = sync_root()
    if not root.exists() or not root.is_dir():
        raise LocalSyncError("La carpeta raíz de sincronización no está montada.")
    candidate_rel = Path(relative or ".")
    if candidate_rel.is_absolute() or ".." in candidate_rel.parts:
        raise LocalSyncError("La ruta debe permanecer dentro de la carpeta montada.")
    candidate = (root / candidate_rel).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise LocalSyncError("La ruta sale de la carpeta montada.") from exc
    if create:
        candidate.mkdir(parents=True, exist_ok=True)
    if candidate.exists():
        current = root
        for part in candidate.relative_to(root).parts:
            current = current / part
            if current.is_symlink():
                raise LocalSyncError("No se permiten enlaces simbólicos en el destino.")
    return candidate


def list_directories(relative: str = "") -> list[dict[str, str]]:
    base = _safe_path(relative)
    if not base.is_dir():
        raise LocalSyncError("La ruta indicada no es una carpeta.")
    return [
        {"name": item.name, "path": str(item.relative_to(sync_root()))}
        for item in sorted(base.iterdir(), key=lambda p: p.name.casefold())
        if item.is_dir() and not item.is_symlink() and item.name not in {".conflicts", ".trash"}
    ]


def create_directory(parent: str, name: str) -> dict[str, str]:
    clean = name.strip()
    if clean in {"", ".", ".."} or "/" in clean or "\\" in clean:
        raise LocalSyncError("Nombre de carpeta inválido.")
    path = _safe_path(str(Path(parent) / clean), create=True)
    return {"name": path.name, "path": str(path.relative_to(sync_root()))}


def _hash(content: str | bytes) -> str:
    payload = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(payload).hexdigest()


def safe_filename(course_name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", course_name).strip()
    value = "".join(character for character in decomposed if not unicodedata.combining(character))
    value = "".join(character for character in value if character.isalnum() or character.isspace() or character == "-")
    value = re.sub(r"[\s-]+", "-", value).strip("-") or "Curso"
    if value.upper() in {"CON", "PRN", "AUX", "NUL", "COM1", "LPT1"}:
        value = f"_{value}"
    if len(value) > 180:
        value = f"{value[:165].rstrip()}--{_hash(course_name)[:8]}"
    return f"{value}.md"


def _normalize_state_filename(destination: Path, state: models.CourseSyncState) -> Path:
    """Migra nombres antiguos al formato canónico sin sobrescribir otro archivo."""
    expected = safe_filename(state.course_name)
    old_path = destination / state.filename
    new_path = destination / expected
    if state.filename != expected and old_path.exists():
        if new_path.exists():
            raise LocalSyncError(f"Ya existe un archivo con el nombre normalizado: {expected}")
        os.replace(old_path, new_path)
    state.filename = expected
    return new_path


YAML_RE = re.compile(r"^---\n.*?\n---\n?", re.DOTALL)


def _clean_markdown(markdown: str) -> str:
    result = markdown.strip()
    if result.startswith("````txt\n"):
        result = result[len("````txt\n"):]
    if result.endswith("\n````"):
        result = result[:-5]
    return result.strip()


def build_course_markdown(db: Session, course_name: str, *, markers: bool = False) -> str:
    notes = (
        db.query(models.RawNote)
        .join(models.ProcessedNote, models.RawNote.id == models.ProcessedNote.raw_note_id)
        .filter(models.RawNote.course_name == course_name, models.RawNote.status == models.QueueStatus.PROCESSED)
        .order_by(models.RawNote.order_index.asc(), models.RawNote.created_at.asc())
        .all()
    )
    if not notes:
        raise LocalSyncError("El curso no contiene notas procesadas.")
    state = db.query(models.CourseSyncState).filter(models.CourseSyncState.course_name == course_name).first()
    pieces: list[str] = []
    if markers:
        state_id = state.id if state else "unconfigured"
        pieces.append(f"<!-- concat-notes-sync:v{SYNC_VERSION} course-state:{state_id} -->")
    for index, note in enumerate(notes):
        markdown = _clean_markdown(normalize_flashcard_deck(
            note.processed_note.structured_markdown,
            note.course_name,
            note.course_module,
        ))
        if index > 0:
            markdown = YAML_RE.sub("", markdown, count=1).strip()
        if markers:
            pieces.extend([
                f"<!-- concat-notes-class:{note.id} -->",
                markdown,
                "<!-- concat-notes-end-class -->",
            ])
        else:
            pieces.append(markdown)
    glossary = db.query(models.CourseGlossary).filter(models.CourseGlossary.course_name == course_name).first()
    glossary_md = ""
    if glossary and glossary.compiled_markdown.strip():
        glossary_md = YAML_RE.sub("", glossary.compiled_markdown.strip(), count=1).strip()
    if markers:
        pieces.extend([
            "<!-- concat-notes-glossary -->",
            glossary_md,
            "<!-- concat-notes-end-glossary -->",
        ])
    elif glossary_md:
        pieces.append(glossary_md)
    return "\n\n".join(pieces).rstrip() + "\n"


def get_config(db: Session) -> models.LocalSyncConfig:
    config = db.get(models.LocalSyncConfig, 1)
    if config is None:
        config = models.LocalSyncConfig(id=1, enabled=False, destination_subpath=DEFAULT_SUBPATH)
        db.add(config)
        db.flush()
    return config


def _destination(config: models.LocalSyncConfig, *, create: bool = True) -> Path:
    return _safe_path(config.destination_subpath or DEFAULT_SUBPATH, create=create)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            directory_stat = path.parent.stat()
            os.chown(temp_name, directory_stat.st_uid, directory_stat.st_gid)
        except (PermissionError, AttributeError):
            pass
        os.chmod(temp_name, path.stat().st_mode & 0o777 if path.exists() else 0o664)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _state_for(db: Session, course_name: str) -> models.CourseSyncState:
    state = db.query(models.CourseSyncState).filter(models.CourseSyncState.course_name == course_name).first()
    if state is None:
        state = models.CourseSyncState(course_name=course_name, filename=safe_filename(course_name))
        db.add(state)
        db.flush()
    elif not state.filename:
        state.filename = safe_filename(course_name)
    return state


def _conflict_candidate(destination: Path, state: models.CourseSyncState, content: str) -> str:
    conflicts = destination / ".conflicts"
    conflicts.mkdir(parents=True, exist_ok=True)
    path = conflicts / f"{Path(state.filename).stem}.{_hash(content)[:10]}.database.md"
    if not path.exists():
        _atomic_write(path, content)
    return str(path.relative_to(sync_root()))


def reconcile_course(db: Session, course_name: str, *, force: bool = False) -> dict[str, Any]:
    config = get_config(db)
    state = _state_for(db, course_name)
    if not config.enabled or not state.enabled:
        state.status = "disabled"
        db.commit()
        return serialize_course_state(state)
    try:
        destination = _destination(config)
        path = _normalize_state_filename(destination, state)
        canonical = build_course_markdown(db, course_name)
        db_hash = _hash(canonical)
        if not path.exists():
            if state.last_export_hash and not force:
                state.status = "missing"
                state.external_changed_at = datetime.now(timezone.utc)
                state.conflict_db_path = _conflict_candidate(destination, state, canonical)
            else:
                _atomic_write(path, canonical)
                state.status = "synced"
                state.last_export_hash = db_hash
                state.last_file_hash = db_hash
                state.last_synced_at = datetime.now(timezone.utc)
                state.conflict_db_path = None
            state.last_error = None
            db.commit()
            return serialize_course_state(state)
        file_bytes = path.read_bytes()
        file_hash = _hash(file_bytes)
        unmanaged_existing = state.last_file_hash is None and state.last_export_hash is None
        externally_changed = unmanaged_existing or bool(state.last_file_hash and file_hash != state.last_file_hash)
        if externally_changed and not force:
            state.status = "conflict"
            state.external_changed_at = datetime.now(timezone.utc)
            state.conflict_db_path = _conflict_candidate(destination, state, canonical)
            state.last_error = None
        elif force or db_hash != state.last_export_hash or file_hash != db_hash:
            _atomic_write(path, canonical)
            state.status = "synced"
            state.last_export_hash = db_hash
            state.last_file_hash = db_hash
            state.last_synced_at = datetime.now(timezone.utc)
            state.external_changed_at = None
            state.conflict_db_path = None
            state.last_error = None
        else:
            state.status = "synced"
        db.commit()
    except Exception as exc:
        db.rollback()
        state = _state_for(db, course_name)
        state.status = "error"
        state.last_error = str(exc)
        db.commit()
    return serialize_course_state(state)


def reconcile_all(db: Session, course_name: str | None = None) -> list[dict[str, Any]]:
    query = db.query(models.CourseSyncState).filter(models.CourseSyncState.enabled.is_(True))
    if course_name:
        query = query.filter(models.CourseSyncState.course_name == course_name)
    return [reconcile_course(db, state.course_name) for state in query.all()]


def serialize_course_state(state: models.CourseSyncState, *, available: bool = True) -> dict[str, Any]:
    return {
        "course_name": state.course_name,
        "available": available,
        "enabled": state.enabled,
        # La API siempre presenta el resultado de la regla vigente, incluso si
        # un curso inactivo conserva temporalmente un nombre legado en la BD.
        "filename": safe_filename(state.course_name),
        "status": state.status,
        "last_synced_at": state.last_synced_at.isoformat() if state.last_synced_at else None,
        "external_changed_at": state.external_changed_at.isoformat() if state.external_changed_at else None,
        "last_error": state.last_error,
        "has_conflict": state.status in {"conflict", "missing"},
    }


def list_course_states(db: Session) -> list[dict[str, Any]]:
    courses = {
        row[0] for row in db.query(models.RawNote.course_name)
        .join(models.ProcessedNote, models.ProcessedNote.raw_note_id == models.RawNote.id)
        .distinct().all() if row[0]
    }
    states = {state.course_name: state for state in db.query(models.CourseSyncState).all()}
    result = []
    for course in sorted(courses | states.keys(), key=str.casefold):
        state = states.get(course) or _state_for(db, course)
        result.append(serialize_course_state(state, available=course in courses))
    db.commit()
    return result


def update_config(
    db: Session, *, enabled: bool | None = None, destination_subpath: str | None = None
) -> models.LocalSyncConfig:
    config = get_config(db)
    if destination_subpath is not None and destination_subpath != config.destination_subpath:
        conflicts = db.query(models.CourseSyncState).filter(
            models.CourseSyncState.status.in_(["conflict", "missing"])
        ).count()
        if conflicts:
            raise LocalSyncConflict("Resuelve los conflictos antes de cambiar el destino.")
        old_destination = _destination(config)
        new_destination = _safe_path(destination_subpath, create=True)
        probe = new_destination / ".concat-notes-write-test"
        _atomic_write(probe, "ok\n")
        probe.unlink()
        enabled_states = db.query(models.CourseSyncState).filter(models.CourseSyncState.enabled.is_(True)).all()
        written: list[Path] = []
        try:
            for state in enabled_states:
                content = build_course_markdown(db, state.course_name)
                target = new_destination / state.filename
                _atomic_write(target, content)
                written.append(target)
            trash = old_destination / ".trash"
            for state in enabled_states:
                source = old_destination / state.filename
                if source.exists() and source.parent != new_destination:
                    trash.mkdir(parents=True, exist_ok=True)
                    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                    shutil.move(str(source), str(trash / f"{stamp}__{state.filename}"))
                digest = _hash((new_destination / state.filename).read_bytes())
                state.last_export_hash = digest
                state.last_file_hash = digest
                state.status = "synced"
                state.last_synced_at = datetime.now(timezone.utc)
            config.destination_subpath = str(new_destination.relative_to(sync_root()))
        except Exception:
            for target in written:
                if target.exists():
                    target.unlink()
            raise
    if enabled is not None:
        config.enabled = enabled
    db.commit()
    db.refresh(config)
    return config


def set_course_enabled(db: Session, course_name: str, enabled: bool) -> dict[str, Any]:
    available = db.query(models.RawNote).join(models.ProcessedNote).filter(
        models.RawNote.course_name == course_name
    ).first()
    if not available:
        raise LocalSyncError("El curso no existe o no tiene notas procesadas.")
    state = _state_for(db, course_name)
    state.enabled = enabled
    if not enabled:
        state.status = "disabled"
        db.commit()
        return serialize_course_state(state)
    state.status = "syncing"
    state.last_export_hash = None if state.last_file_hash is None else state.last_export_hash
    db.commit()
    return reconcile_course(db, course_name)


CLASS_RE = re.compile(
    r"<!-- concat-notes-class:([0-9a-fA-F-]{36}) -->\s*([\s\S]*?)\s*<!-- concat-notes-end-class -->"
)
GLOSSARY_RE = re.compile(
    r"<!-- concat-notes-glossary -->\s*([\s\S]*?)\s*<!-- concat-notes-end-glossary -->"
)
CLEAN_CLASS_HEADING_RE = re.compile(r"^#\s+📚\s+.+?$", re.MULTILINE)
CLEAN_GLOSSARY_HEADING_RE = re.compile(r"^#\s+📖\s+Glosario\b", re.MULTILINE)


def _extract_title(markdown: str) -> str:
    match = re.search(r"^#\s+(?:📚\s*)?(.+?)\s*$", YAML_RE.sub("", markdown, count=1), re.MULTILINE)
    if not match:
        raise LocalSyncConflict("Cada clase debe conservar un encabezado H1 visible.")
    return match.group(1).strip()


def _split_clean_document(markdown: str) -> tuple[list[str], str]:
    """Separa el Markdown público sin depender de comentarios de protocolo."""
    glossary_start = CLEAN_GLOSSARY_HEADING_RE.search(markdown)
    classes_markdown = markdown[:glossary_start.start()] if glossary_start else markdown
    glossary_markdown = markdown[glossary_start.start():].strip() if glossary_start else ""
    starts = [match.start() for match in CLEAN_CLASS_HEADING_RE.finditer(classes_markdown)]
    if not starts:
        raise LocalSyncConflict("El documento no contiene encabezados de clase reconocibles.")
    starts[0] = 0  # Conserva el frontmatter de la primera clase, si existe.
    boundaries = starts[1:] + [len(classes_markdown)]
    blocks = [classes_markdown[start:end].strip() for start, end in zip(starts, boundaries)]
    return blocks, glossary_markdown


def _replace_yaml_class(frontmatter: str, title: str) -> str:
    if not frontmatter:
        return ""
    replacement = f"class: {title}"
    if re.search(r"^class:\s*.*$", frontmatter, re.MULTILINE):
        return re.sub(r"^class:\s*.*$", replacement, frontmatter, count=1, flags=re.MULTILINE)
    return frontmatter.replace("\n---", f"\n{replacement}\n---", 1)


def _parse_compiled_glossary(markdown: str, course_name: str) -> tuple[list[dict[str, Any]], str]:
    entries: list[dict[str, Any]] = []
    blocks = re.split(r"(?=^###\s+)", markdown, flags=re.MULTILINE)
    for block in blocks:
        heading = re.match(r"^###\s+(.+?)\s*$", block, re.MULTILINE)
        if not heading:
            continue
        term = heading.group(1).strip()
        definition_match = re.search(r"^#definicion\s+(.+?)(?=\n(?:#definicion-ampliada|>|#formula|\*\*Ejemplo|---|###|##)|\Z)", block, re.MULTILINE | re.DOTALL)
        definition = definition_match.group(1).strip() if definition_match else ""
        sources = re.findall(r"\[\[([^]]+)\]\]", block)
        translation_match = re.search(rf"{re.escape(term.strip('`'))}\s*\(([^)]+)\)", definition, re.IGNORECASE)
        entries.append({
            "term": term,
            "term_es": translation_match.group(1).strip() if translation_match else None,
            "definition": re.sub(r"\nFuente:.*$", "", definition, flags=re.DOTALL).strip(),
            "definition_sources": sources,
            "expansions": [
                {"content": item.strip(), "sources": re.findall(r"\[\[([^]]+)\]\]", item)}
                for item in re.findall(r"^#definicion-ampliada\s+(.+?)(?=\n#|\n>|\n---|\Z)", block, re.MULTILINE | re.DOTALL)
            ],
            "encyclopedia": [], "formulas": [], "uses": [], "sources": sources,
        })
    if markdown.strip() and not entries:
        raise LocalSyncConflict("El glosario final no conserva una estructura reconocible.")
    frontmatter = (
        "---\n"
        "tipo: glosario\n"
        f"curso: {course_name}\n"
        "estado: sincronizado\n"
        f"ultima_actualizacion: {datetime.now().date().isoformat()}\n"
        "---\n"
    )
    return entries, frontmatter + markdown.strip() + "\n"


def _rebuild_local_derivatives(db: Session, note: models.RawNote) -> None:
    from app.flashcards import refresh_note

    processed = note.processed_note
    db.query(models.NoteChunk).filter(models.NoteChunk.processed_note_id == processed.id).delete()
    sections = [part.strip() for part in re.split(r"(?=^#{2,3}\s)", processed.structured_markdown, flags=re.MULTILINE) if len(part.strip()) > 50]
    for index, content in enumerate(sections or [processed.structured_markdown[:2000]]):
        db.add(models.NoteChunk(processed_note_id=processed.id, content=content, embedding=ZERO_VECTOR, is_dummy_embedding=True, chunk_index=index))
    # La reconciliación especializada conserva el progreso de estudio por pregunta.
    refresh_note(db, note)
    db.query(models.GenerationArtifact).filter(models.GenerationArtifact.processed_note_id == processed.id).delete()
    index_state = db.get(models.KnowledgeIndexState, note.id)
    if index_state:
        index_state.status = "pending"
        index_state.last_error = "Markdown actualizado mediante sincronización local"


def conflict_details(db: Session, course_name: str) -> dict[str, Any]:
    config = get_config(db)
    state = _state_for(db, course_name)
    destination = _destination(config)
    path = destination / state.filename
    external = path.read_text(encoding="utf-8") if path.exists() else ""
    canonical = build_course_markdown(db, course_name)
    diff = "".join(difflib.unified_diff(
        canonical.splitlines(keepends=True), external.splitlines(keepends=True),
        fromfile="base-de-datos", tofile="archivo-local", n=3,
    ))
    return {
        "course_name": course_name,
        "status": state.status,
        "file_exists": path.exists(),
        "diff": diff,
        "external_size": len(external.encode("utf-8")),
        "database_size": len(canonical.encode("utf-8")),
    }


def integrate_external(db: Session, course_name: str) -> dict[str, Any]:
    config = get_config(db)
    state = _state_for(db, course_name)
    path = _destination(config) / state.filename
    if not path.exists():
        raise LocalSyncConflict("El archivo externo no existe; sólo puede restaurarse desde la app.")
    external = path.read_text(encoding="utf-8")
    blocks, glossary_markdown = _split_clean_document(external)
    notes = (
        db.query(models.RawNote)
        .join(models.ProcessedNote, models.ProcessedNote.raw_note_id == models.RawNote.id)
        .filter(models.RawNote.course_name == course_name, models.RawNote.status == models.QueueStatus.PROCESSED)
        .order_by(models.RawNote.order_index.asc(), models.RawNote.created_at.asc())
        .all()
    )
    if len(blocks) != len(notes):
        raise LocalSyncConflict("El documento debe contener cada clase existente exactamente una vez.")

    # Los títulos permiten reconocer clases reordenadas sin ensuciar el archivo
    # público con UUIDs. Los títulos editados se asignan a las clases restantes.
    remaining = list(notes)
    assignments: list[models.RawNote | None] = []
    unresolved: list[int] = []
    for index, external_block in enumerate(blocks):
        external_title = _extract_title(external_block)
        matches = [note for note in remaining if _extract_title(note.processed_note.structured_markdown) == external_title]
        if len(matches) == 1:
            assignments.append(matches[0])
            remaining.remove(matches[0])
        else:
            assignments.append(None)
            unresolved.append(index)
    for index, note in zip(unresolved, remaining):
        assignments[index] = note

    entries, compiled = _parse_compiled_glossary(glossary_markdown, course_name)
    try:
        for order, (note, external_block) in enumerate(zip(assignments, blocks)):
            if note is None:
                raise LocalSyncConflict("No fue posible asociar una sección con su clase original.")
            title = _extract_title(external_block)
            existing_frontmatter = YAML_RE.match(note.processed_note.structured_markdown)
            frontmatter = _replace_yaml_class(existing_frontmatter.group(0) if existing_frontmatter else "", title)
            body = YAML_RE.sub("", external_block.strip(), count=1).strip()
            note.class_title = title
            note.order_index = order
            note.processed_note.structured_markdown = normalize_flashcard_deck(
                (frontmatter + body).strip() + "\n",
                note.course_name,
                note.course_module,
            )
            _rebuild_local_derivatives(db, note)
        glossary = db.query(models.CourseGlossary).filter(models.CourseGlossary.course_name == course_name).first()
        if glossary is None:
            glossary = models.CourseGlossary(course_name=course_name)
            db.add(glossary)
        glossary.entries = entries
        glossary.compiled_markdown = compiled
        db.commit()
    except Exception:
        db.rollback()
        raise
    canonical = build_course_markdown(db, course_name)
    _atomic_write(path, canonical)
    state = _state_for(db, course_name)
    digest = _hash(canonical)
    state.status = "synced"
    state.last_export_hash = digest
    state.last_file_hash = digest
    state.last_synced_at = datetime.now(timezone.utc)
    state.external_changed_at = None
    state.conflict_db_path = None
    state.last_error = None
    db.commit()
    return serialize_course_state(state)


def restore_database(db: Session, course_name: str) -> dict[str, Any]:
    config = get_config(db)
    state = _state_for(db, course_name)
    destination = _destination(config)
    path = destination / state.filename
    if path.exists():
        conflicts = destination / ".conflicts"
        conflicts.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.move(str(path), str(conflicts / f"{Path(state.filename).stem}.{stamp}.external.md"))
    state.last_file_hash = None
    state.last_export_hash = None
    db.commit()
    return reconcile_course(db, course_name, force=True)


def archive_course_file(db: Session, course_name: str) -> None:
    config = get_config(db)
    state = db.query(models.CourseSyncState).filter(models.CourseSyncState.course_name == course_name).first()
    if not state or not state.enabled:
        return
    destination = _destination(config)
    source = destination / state.filename
    if source.exists():
        trash = destination / ".trash"
        trash.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.move(str(source), str(trash / f"{stamp}__{state.filename}"))
    state.enabled = False
    state.status = "disabled"
    db.flush()


def rename_course_state(db: Session, old_name: str, new_name: str) -> None:
    state = db.query(models.CourseSyncState).filter(models.CourseSyncState.course_name == old_name).first()
    if not state:
        return
    config = get_config(db)
    old_path = _destination(config) / state.filename
    new_filename = safe_filename(new_name)
    new_path = old_path.with_name(new_filename)
    if old_path.exists() and old_path != new_path:
        if new_path.exists():
            new_filename = f"{Path(new_filename).stem}--{_hash(new_name)[:8]}.md"
            new_path = old_path.with_name(new_filename)
        os.replace(old_path, new_path)
    state.course_name = new_name
    state.filename = new_filename
    state.last_export_hash = None
    state.last_file_hash = _hash(new_path.read_bytes()) if new_path.exists() else None
    state.status = "syncing" if state.enabled else "disabled"


async def local_sync_loop() -> None:
    interval = max(1, int(os.getenv("LOCAL_SYNC_INTERVAL_SECONDS", "3")))
    while True:
        try:
            async with sync_lock:
                await asyncio.to_thread(_reconcile_background)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(interval)


def _reconcile_background() -> None:
    db = SessionLocal()
    try:
        config = get_config(db)
        if config.enabled and mount_status()["writable"]:
            reconcile_all(db)
    finally:
        db.close()
