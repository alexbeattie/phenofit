"""PDF -> plain text, so a dropped lab report can feed the AI edge.

Only text extraction lives here. `pypdf` is a pure-Python dependency; if it
isn't installed we fail with a clear message rather than a stack trace.
"""

from __future__ import annotations

import io


class PdfError(RuntimeError):
    pass


def extract_text(data: bytes) -> str:
    """Return the concatenated text of every page in a PDF byte string."""

    try:
        from pypdf import PdfReader  # noqa: PLC0415  (optional dep, imported lazily)
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise PdfError(
            "pypdf is not installed. Run `pip install pypdf` to enable PDF drag-and-drop."
        ) from exc

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # any malformed PDF -> clean error, not a stack trace
        raise PdfError(f"Could not read PDF: {exc}") from exc

    text = "\n".join(pages).strip()
    if not text:
        raise PdfError(
            "No selectable text found in the PDF (it may be a scanned image, which needs OCR)."
        )
    return text
