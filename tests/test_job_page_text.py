"""Tests for job page text extraction and Greenhouse fallbacks."""

from __future__ import annotations

import json
from unittest.mock import patch

from job_hunter.job_filtering.job_page_text import (
    extract_html_meta_description,
    fetch_greenhouse_job_description,
    fetch_job_description,
    fetch_workday_job_description,
    html_to_text,
    parse_greenhouse_job_reference,
    parse_workday_job_reference,
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


def test_extract_html_meta_description_reads_open_graph() -> None:
    document = (
        '<html><head><meta property="og:description" content="Role summary with '
        '&#39;entities&#39;." /></head><body></body></html>'
    )
    assert extract_html_meta_description(document) == "Role summary with 'entities'."


def test_parse_workday_job_reference_from_career_url() -> None:
    reference = parse_workday_job_reference(
        "https://clio.wd3.myworkdayjobs.com/en-US/ClioCareerSite/job/"
        "Remote---Canada/Systems-Engineer--Production_BF-REQ-3194?source=LinkedIn",
    )
    assert reference == (
        "https://clio.wd3.myworkdayjobs.com",
        "clio",
        "ClioCareerSite",
        "Remote---Canada/Systems-Engineer--Production_BF-REQ-3194",
    )


def test_parse_workday_job_reference_returns_none_for_other_hosts() -> None:
    assert parse_workday_job_reference("https://boards.greenhouse.io/acme/jobs/1") is None


def test_fetch_workday_job_description_via_cxs_api() -> None:
    payload = {
        "jobPostingInfo": {
            "title": "Systems Engineer, Production",
            "location": "Remote - Canada",
            "jobDescription": "<p>Operate <strong>AWS</strong> infrastructure.</p>",
        },
    }

    def fake_urlopen(request, timeout=30):
        assert "/wday/cxs/clio/ClioCareerSite/job/" in request.full_url
        return _FakeHttpResponse(
            json.dumps(payload).encode("utf-8"),
            content_type="application/json",
        )

    with patch("job_hunter.job_filtering.job_page_text.urllib.request.urlopen", fake_urlopen):
        text = fetch_workday_job_description(
            "https://clio.wd3.myworkdayjobs.com",
            "clio",
            "ClioCareerSite",
            "Systems-Engineer--Production_BF-REQ-3194",
        )

    assert "Systems Engineer, Production" in text
    assert "Remote - Canada" in text
    assert "AWS" in text


def test_fetch_job_description_uses_meta_when_body_empty() -> None:
    html_body = (
        b"<html><head><meta property=\"og:description\" content=\"Workday SPA summary\" />"
        b"</head><body></body></html>"
    )

    def fake_urlopen(request, timeout=30):
        return _FakeHttpResponse(html_body)

    with patch("job_hunter.job_filtering.job_page_text.urllib.request.urlopen", fake_urlopen):
        text = fetch_job_description(
            "https://clio.wd3.myworkdayjobs.com/en-US/ClioCareerSite/job/example",
        )

    assert text == "Workday SPA summary"


def test_fetch_job_description_prefers_visible_html_over_meta() -> None:
    html_body = (
        b"<html><head><meta property=\"og:description\" content=\"Meta only\" />"
        b"</head><body><p>Visible body</p></body></html>"
    )

    def fake_urlopen(request, timeout=30):
        return _FakeHttpResponse(html_body)

    with patch("job_hunter.job_filtering.job_page_text.urllib.request.urlopen", fake_urlopen):
        text = fetch_job_description("https://example.com/jobs/a")

    assert text == "Visible body"


def test_fetch_job_description_falls_back_to_workday_api_when_html_empty() -> None:
    workday_payload = {
        "jobPostingInfo": {
            "title": "Platform Engineer",
            "jobDescription": "<p>Workday API description</p>",
        },
    }

    def fake_urlopen(request, timeout=30):
        url = request.full_url
        if "/wday/cxs/" in url:
            return _FakeHttpResponse(
                json.dumps(workday_payload).encode("utf-8"),
                content_type="application/json",
            )
        return _FakeHttpResponse(b"<html><body></body></html>")

    with patch("job_hunter.job_filtering.job_page_text.urllib.request.urlopen", fake_urlopen):
        text = fetch_job_description(
            "https://clio.wd3.myworkdayjobs.com/en-US/ClioCareerSite/job/Role_ID",
        )

    assert "Platform Engineer" in text
    assert "Workday API description" in text
