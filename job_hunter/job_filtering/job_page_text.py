"""Fetch and reduce public job pages to plain text for AI filtering."""

from __future__ import annotations

import re
import urllib.request
from html.parser import HTMLParser


_MAX_RESPONSE_BYTES = 2_000_000
_SKIPPED_TAGS = {"script", "style", "noscript", "svg"}


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in _SKIPPED_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in _SKIPPED_TAGS and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self._parts.append(text)

    def text(self) -> str:
        return _normalize_text(" ".join(self._parts))


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _charset_from_content_type(content_type: str) -> str:
    match = re.search(r"charset=([^;\s]+)", content_type, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip("\"'")
    return "utf-8"


def html_to_text(html: str) -> str:
    """Extract visible text from an HTML document."""
    parser = _VisibleTextParser()
    parser.feed(html)
    parser.close()
    return parser.text()


def fetch_job_description(url: str, *, timeout_seconds: int = 30) -> str:
    """Fetch a public job URL and return a compact plain-text description."""
    if not url.strip():
        return ""

    request = urllib.request.Request(
        url.strip(),
        headers={"User-Agent": "job-hunter/0.1 (+https://github.com/google-gemini/gemini-cli)"},
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = response.read(_MAX_RESPONSE_BYTES)
        content_type = response.headers.get("content-type", "")

    charset = _charset_from_content_type(content_type)
    text = payload.decode(charset, errors="replace")
    if "html" in content_type.lower() or "<html" in text[:500].lower():
        return html_to_text(text)
    return _normalize_text(text)
