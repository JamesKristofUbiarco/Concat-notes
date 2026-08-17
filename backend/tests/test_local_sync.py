import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_ROOT = os.path.dirname(os.path.dirname(__file__))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app import local_sync


class LocalSyncFilesystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"LOCAL_SYNC_ROOT": self.temp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_path_is_confined_to_mounted_root(self):
        with self.assertRaises(local_sync.LocalSyncError):
            local_sync.list_directories("../outside")

    def test_symlinks_are_rejected(self):
        outside = Path(self.temp.name).parent
        link = Path(self.temp.name) / "escape"
        link.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(local_sync.LocalSyncError):
            local_sync.list_directories("escape")

    def test_directory_creation_and_listing(self):
        created = local_sync.create_directory("", "Cursos Nuevos")
        self.assertEqual(created["path"], "Cursos Nuevos")
        self.assertIn(created, local_sync.list_directories(""))

    def test_atomic_write_replaces_complete_content(self):
        path = Path(self.temp.name) / "course.md"
        local_sync._atomic_write(path, "primero\n")
        local_sync._atomic_write(path, "segundo\n")
        self.assertEqual(path.read_text(encoding="utf-8"), "segundo\n")
        self.assertFalse(any(item.suffix == ".tmp" for item in path.parent.iterdir()))

    def test_safe_filename_normalizes_accents_punctuation_and_spaces(self):
        filename = local_sync.safe_filename('Máster: Python, datos & más...')
        self.assertEqual(filename, "Master-Python-datos-mas.md")
        self.assertNotIn("/", filename)

    def test_course_preview_always_uses_normalized_filename(self):
        state = type("State", (), {
            "course_name": "Fundamentos de Investigación Científica",
            "enabled": False,
            "filename": "Fundamentos de Investigación Científica.md",
            "status": "disabled",
            "last_synced_at": None,
            "external_changed_at": None,
            "last_error": None,
            "conflict_db_path": None,
        })()
        preview = local_sync.serialize_course_state(state)
        self.assertEqual(preview["filename"], "Fundamentos-de-Investigacion-Cientifica.md")

    def test_markers_keep_stable_note_ids(self):
        note_id = "92dd10ce-8457-49a2-9701-2d42aea057c2"
        document = f"<!-- concat-notes-class:{note_id} -->\n# 📚 Nuevo título\nTexto\n<!-- concat-notes-end-class -->"
        blocks = local_sync.CLASS_RE.findall(document)
        self.assertEqual(blocks[0][0], note_id)
        self.assertEqual(local_sync._extract_title(blocks[0][1]), "Nuevo título")

    def test_clean_document_splits_classes_and_glossary_without_protocol(self):
        document = """---
tipo: clase
---
# 📚 Clase uno
Contenido uno

# 📚 Clase dos
Contenido dos

# 📖 Glosario — Curso

### State
#definicion Un state (estado) conserva datos.
"""
        blocks, glossary = local_sync._split_clean_document(document)
        self.assertEqual(len(blocks), 2)
        self.assertIn("# 📚 Clase uno", blocks[0])
        self.assertIn("# 📚 Clase dos", blocks[1])
        self.assertTrue(glossary.startswith("# 📖 Glosario"))
        self.assertNotIn("concat-notes", document)

    def test_compiled_glossary_parses_canonical_term(self):
        markdown = """# 📖 Glosario — Curso

## D

### Deadlock
#definicion Un deadlock (interbloqueo) es una espera circular.
Fuente: [[Clase 1]]
"""
        entries, compiled = local_sync._parse_compiled_glossary(markdown, "Curso")
        self.assertEqual(entries[0]["term"], "Deadlock")
        self.assertEqual(entries[0]["term_es"], "interbloqueo")
        self.assertIn("curso: Curso", compiled)


if __name__ == "__main__":
    unittest.main()
