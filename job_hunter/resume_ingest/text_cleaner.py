"""Normalize PDF-extracted text before sending to the language model."""

from __future__ import annotations

import re


def clean_resume_text(raw_text: str) -> str:
    """
    Collapse noisy whitespace and common PDF extraction artifacts.

    This step is deterministic and does not interpret resume semantics.
    """
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = "\n".join(line.strip(" \t") for line in text.split("\n"))
    return text.strip()
