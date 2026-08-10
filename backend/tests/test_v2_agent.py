import os
import sys
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace


BACKEND_ROOT = os.path.dirname(os.path.dirname(__file__))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.v2_agent import ensure_visible_class_header


class VisibleClassHeaderTests(unittest.TestCase):
    def note(self):
        return SimpleNamespace(
            class_title="7. Tipos de Datos",
            course_name="Máster Completo Python de cero a experto",
            teacher="Andrés Guzmán",
            course_module="Section 1: Introducción",
            created_at=datetime(2026, 7, 31, 6, 34, tzinfo=timezone.utc),
        )

    def test_header_is_inserted_after_frontmatter(self):
        result = ensure_visible_class_header("---\ncreated: 2026-07-31\n---\n\n## Contenido\nTexto", self.note())
        self.assertIn("---\n\n# 📚 7. Tipos de Datos", result)
        self.assertIn("**Curso:** Máster Completo Python de cero a experto", result)
        self.assertIn("**Instructor/Autor:** Andrés Guzmán | **Módulo del curso:** Section 1: Introducción", result)
        self.assertIn("**Fecha de clase:** 2026-07-31", result)
        self.assertLess(result.index("# 📚"), result.index("## Contenido"))

    def test_existing_visible_header_is_replaced_not_duplicated(self):
        source = """---
fecha: 2026-07-31
---
# Encabezado inventado
**Curso:** Otro
**Instructor/Autor:** Otro | **Módulo del curso:** Otro
**Fecha de clase:** 2000-01-01

## Contenido
Texto
"""
        result = ensure_visible_class_header(source, self.note())
        self.assertEqual(result.count("# 📚 7. Tipos de Datos"), 1)
        self.assertNotIn("# Encabezado inventado", result)
        self.assertNotIn("**Curso:** Otro", result)
        self.assertEqual(result.count("## Contenido"), 1)


if __name__ == "__main__":
    unittest.main()
