import io
import os
import sys
import unittest
import zipfile

from fastapi import UploadFile

BACKEND_ROOT = os.path.dirname(os.path.dirname(__file__))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.documents import DocumentError, _file_facts, _validate_epub, normalize_ranges
from app.schemas import DocumentConfirmRequest


class DocumentProcessingTests(unittest.TestCase):
    def test_confirmation_accepts_personal_notes(self):
        payload = DocumentConfirmRequest(drafts=[], my_notes="Mi observación")
        self.assertEqual(payload.my_notes, "Mi observación")

    def test_overlapping_and_adjacent_ranges_are_normalized(self):
        self.assertEqual(
            normalize_ranges([{"start": 10, "end": 12}, {"start": 1, "end": 3}, {"start": 3, "end": 6}, {"start": 7, "end": 7}], 20),
            [{"start": 1, "end": 7}, {"start": 10, "end": 12}],
        )

    def test_invalid_page_ranges_are_rejected(self):
        with self.assertRaises(DocumentError):
            normalize_ranges([{"start": 8, "end": 3}], 10)
        with self.assertRaises(DocumentError):
            normalize_ranges([{"start": 1, "end": 11}], 10)

    def test_epub_zip_slip_is_rejected(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            archive.writestr("../escape.xhtml", "unsafe")
        upload = UploadFile(filename="book.epub", file=io.BytesIO(payload.getvalue()))
        with self.assertRaises(DocumentError):
            _validate_epub(upload)

    def test_file_facts_hashes_stream_and_rewinds_it(self):
        upload = UploadFile(filename="small.pdf", file=io.BytesIO(b"%PDF-test"))
        size, digest, prefix = _file_facts(upload)
        self.assertEqual(size, 9)
        self.assertEqual(len(digest), 64)
        self.assertTrue(prefix.startswith(b"%PDF-"))
        self.assertEqual(upload.file.tell(), 0)


if __name__ == "__main__":
    unittest.main()
