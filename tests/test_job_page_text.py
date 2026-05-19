"""Tests for job page text extraction and Greenhouse fallbacks."""

from __future__ import annotations

import json
from unittest.mock import patch

from job_hunter.job_filtering.job_page_text import (
    fetch_greenhouse_job_description,
    fetch_job_description,
    html_to_text,
    parse_greenhouse_job_reference,
)


class _FakeHttpResponse:
    def __init__(self, body: bytes, *, content_type: str = "text/html; charset=utf-8") -> None:
        self._body = body
        self.headers = {"content-type": content_type}

    def read(self, size: int = -1) -> bytes:
        return self._body[:size] if size >= 0 else self._body

    def __enter__(self) -> _FakeHttpResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_parse_greenhouse_job_reference_from_careers_site_with_gh_jid() -> None:
    reference = parse_greenhouse_job_reference(
        "https://careers.upstart.com/jobs/senior-devops-engineer?gh_jid=7821447",
    )
    assert reference == ("upstart", "7821447")


def test_parse_greenhouse_job_reference_from_boards_path() -> None:
    reference = parse_greenhouse_job_reference(
        "https://boards.greenhouse.io/upstart/jobs/7821447",
    )
    assert reference == ("upstart", "7821447")


def test_parse_greenhouse_job_reference_returns_none_without_job_id() -> None:
    assert parse_greenhouse_job_reference("https://example.com/jobs/platform-engineer") is None


def test_greenhouse_payload_to_text_via_fetch() -> None:
    payload = {
        "title": "Senior DevOps Engineer",
        "company_name": "Upstart",
        "location": {"name": "United States | Remote"},
        "content": "<p>Operate <strong>Kubernetes</strong> clusters.</p>",
    }

    def fake_urlopen(request, timeout=30):
        assert "boards-api.greenhouse.io" in request.full_url
        return _FakeHttpResponse(json.dumps(payload).encode("utf-8"), content_type="application/json")

    with patch("job_hunter.job_filtering.job_page_text.urllib.request.urlopen", fake_urlopen):
        text = fetch_greenhouse_job_description("upstart", "7821447")

    assert "Senior DevOps Engineer" in text
    assert "Upstart" in text
    assert "United States | Remote" in text
    assert "Kubernetes" in text


def test_fetch_job_description_uses_html_when_present() -> None:
    html_body = b"<html><body><p>Plain HTML role description</p></body></html>"

    def fake_urlopen(request, timeout=30):
        return _FakeHttpResponse(html_body)

    with patch("job_hunter.job_filtering.job_page_text.urllib.request.urlopen", fake_urlopen):
        text = fetch_job_description("https://example.com/jobs/a")

    assert text == "Plain HTML role description"
    assert "Kubernetes" not in text


def test_fetch_job_description_falls_back_to_greenhouse_when_html_empty() -> None:
    greenhouse_payload = {
        "title": "Senior DevOps Engineer",
        "company_name": "Upstart",
        "content": "<p>Greenhouse API description</p>",
    }

    def fake_urlopen(request, timeout=30):
        url = request.full_url
        if "boards-api.greenhouse.io" in url:
            return _FakeHttpResponse(
                json.dumps(greenhouse_payload).encode("utf-8"),
                content_type="application/json",
            )
        return _FakeHttpResponse(b"")

    with patch("job_hunter.job_filtering.job_page_text.urllib.request.urlopen", fake_urlopen):
        text = fetch_job_description(
            "https://careers.upstart.com/jobs/senior-devops-engineer?gh_jid=7821447",
        )

    assert "Senior DevOps Engineer" in text
    assert "Greenhouse API description" in text


def test_html_to_text_skips_script_content() -> None:
    text = html_to_text("<html><script>ignore()</script><p>Visible</p></html>")
    assert text == "Visible"
