"""Offline tests for PDF text extraction (mocked pypdf)."""

from __future__ import annotations

import unittest
from unittest import mock

from phenofit import pdf


class PdfTests(unittest.TestCase):
    def test_extracts_page_text(self):
        fake_reader = type("R", (), {"pages": [type("P", (), {"extract_text": lambda self: "SCN1A c.3637C>T"})()]})
        with mock.patch("pypdf.PdfReader", lambda *_a, **_k: fake_reader()):
            self.assertIn("SCN1A", pdf.extract_text(b"%PDF-fake"))

    def test_missing_text_raises(self):
        fake_reader = type("R", (), {"pages": [type("P", (), {"extract_text": lambda self: ""})()]})
        with mock.patch("pypdf.PdfReader", lambda *_a, **_k: fake_reader()):
            with self.assertRaises(pdf.PdfError):
                pdf.extract_text(b"%PDF-fake")


if __name__ == "__main__":
    unittest.main()
