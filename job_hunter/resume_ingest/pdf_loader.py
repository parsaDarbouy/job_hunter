"""Load plain text from a PDF resume."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader


def load_pdf_text(resume_pdf_path: Path) -> str:
    """
    Extract concatenated page text from a PDF file.

    Raises FileNotFoundError if the path does not exist.
    Raises ValueError if the file is not a readable PDF or yields no text.
    """
    if not resume_pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {resume_pdf_path}")

    reader = PdfReader(str(resume_pdf_path))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:  # noqa: BLE001 — pypdf may raise varied errors
            raise ValueError("Encrypted PDF; cannot decrypt without password") from exc

    parts: list[str] = []
    for page in reader.pages:
        extracted = page.extract_text()
        if extracted:
            parts.append(extracted)

    text = "\n".join(parts).strip()
    if not text:
        raise ValueError("No extractable text in PDF (scanned PDFs need OCR first)")
    return text
