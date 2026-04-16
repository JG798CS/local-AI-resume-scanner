from __future__ import annotations

import fitz


class PdfParseError(ValueError):
    pass


def extract_pdf_text(pdf_bytes: bytes) -> str:
    if not pdf_bytes:
        raise PdfParseError("Resume PDF is empty.")

    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
            pages = [page.get_text("text") for page in document]
    except Exception as exc:  # pragma: no cover
        raise PdfParseError("Failed to parse resume PDF.") from exc

    text = "\n".join(page.strip() for page in pages if page.strip()).strip()
    if not text:
        raise PdfParseError("Resume PDF did not contain extractable text.")
    return text
