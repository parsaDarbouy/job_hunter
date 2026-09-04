"""Tests for recruiter and hiring-manager lookup."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from job_hunter.role_contacts.agent_contacts import parse_extracted_candidates, parse_search_queries
from job_hunter.role_contacts.job_identity import (
    parse_ashby_reference,
    parse_greenhouse_reference,
    parse_lever_reference,
    resolve_job_identity,
)
from job_hunter.role_contacts.models import ContactCandidate, JobIdentity, RoleContactReport, SearchHit
from job_hunter.role_contacts.posting_extract import (
    extract_contacts_from_ats_payload,
    extract_contacts_from_text,
)
from job_hunter.role_contacts.run_lookup import merge_contact_candidates, run_role_contact_lookup
from job_hunter.role_contacts.search import (
    company_linkedin_slug,
    default_search_queries,
    parse_duckduckgo_html,
    parse_linkedin_job_search_html,
    parse_linkedin_organization_id,
    unwrap_duckduckgo_url,
)
from job_hunter.role_contacts.yaml_writer import write_contacts_yaml


def _candidate(**overrides: object) -> ContactCandidate:
    values: dict[str, object] = {
        "name": "Alex Recruiter",
        "kind": "recruiter",
        "title": "Technical Recruiter",
        "linkedin_url": "https://www.linkedin.com/in/alexrecruiter",
        "email": "",
        "confidence": "medium",
        "evidence": ("snippet",),
        "source": "web_search",
    }
    values.update(overrides)
    return ContactCandidate(**values)  # type: ignore[arg-type]


def test_parse_greenhouse_reference_from_gh_board_query() -> None:
    reference = parse_greenhouse_reference(
        "https://www.samsara.com/company/careers/roles/7997916?gh_jid=7997916&gh_board=samsara"
    )
    assert reference == ("samsara", "7997916")


def test_parse_greenhouse_reference_from_boards_host() -> None:
    reference = parse_greenhouse_reference("https://boards.greenhouse.io/samsara/jobs/7997916")
    assert reference == ("samsara", "7997916")


def test_parse_lever_and_ashby_references() -> None:
    assert parse_lever_reference("https://jobs.lever.co/acme/abc-123") == ("acme", "abc-123")
    assert parse_ashby_reference("https://jobs.ashbyhq.com/acme/job/uuid-1") == ("acme", "uuid-1")
    assert parse_ashby_reference("https://jobs.ashbyhq.com/acme/uuid-1") == ("acme", "uuid-1")


def test_resolve_job_identity_from_greenhouse_json() -> None:
    payload = {
        "title": "Senior Software Engineer I/II - Infrastructure",
        "company_name": "Samsara",
        "location": {"name": "Remote - Canada"},
        "departments": [{"name": "Platform"}],
        "requisition_id": "JR11500",
    }
    with patch(
        "job_hunter.role_contacts.job_identity.get_json_optional",
        return_value=(payload, None),
    ):
        identity = resolve_job_identity(
            "https://www.samsara.com/company/careers/roles/7997916?gh_jid=7997916&gh_board=samsara"
        )
    assert identity.company_name == "Samsara"
    assert identity.job_title.startswith("Senior Software Engineer")
    assert identity.department == "Platform"
    assert identity.requisition_id == "JR11500"
    assert identity.provider_kind == "greenhouse"


def test_extract_mailto_and_skip_privacy_inbox() -> None:
    html = (
        '<p>Email <a href="mailto:jane.doe@acme.com">Jane</a></p>'
        '<p>Privacy: <a href="mailto:privacy@acme.com">privacy</a></p>'
    )
    contacts = extract_contacts_from_text(html)
    emails = {contact.email for contact in contacts}
    assert "jane.doe@acme.com" in emails
    assert "privacy@acme.com" not in emails


def test_extract_labeled_recruiter_name() -> None:
    contacts = extract_contacts_from_text("Recruiter: Josie Schwartz\nHiring Manager: Dana Lee")
    names = {contact.name: contact.kind for contact in contacts}
    assert names["Josie Schwartz"] == "recruiter"
    assert names["Dana Lee"] == "hiring_manager"


def test_extract_contacts_from_ats_payload() -> None:
    contacts = extract_contacts_from_ats_payload(
        {"recruiter": {"name": "Pat Kim", "email": "pat.kim@acme.com", "title": "Recruiter"}}
    )
    assert contacts[0].name == "Pat Kim"
    assert contacts[0].email == "pat.kim@acme.com"
    assert contacts[0].source == "job_posting"


def test_parse_duckduckgo_html_unwraps_redirect() -> None:
    html = """
    <a class="result__a" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.linkedin.com%2Fin%2Fjosieschwartz">
      Josie Schwartz - Talent
    </a>
    <a class="result__snippet">Technical recruiter for platform roles at Samsara</a>
    """
    hits = parse_duckduckgo_html(html)
    assert hits[0].url == "https://www.linkedin.com/in/josieschwartz"
    assert "platform" in hits[0].snippet.lower()


def test_unwrap_duckduckgo_url_passthrough() -> None:
    assert unwrap_duckduckgo_url("https://www.linkedin.com/in/example") == (
        "https://www.linkedin.com/in/example"
    )


def test_parse_linkedin_guest_markup() -> None:
    html = """
    urn:li:organization:6453825
    <h3 class="base-search-card__title">
        Senior Software Engineer I/II - Infrastructure
    </h3>
    <a href="https://www.linkedin.com/jobs/view/senior-software-engineer-i-ii-infrastructure-at-samsara-4455011677?position=1">
    """
    assert parse_linkedin_organization_id(html) == "6453825"
    hits = parse_linkedin_job_search_html(html)
    assert hits[0].url.endswith("4455011677")
    assert "Infrastructure" in hits[0].title


def test_company_linkedin_slug_strips_legal_suffix() -> None:
    assert company_linkedin_slug("Samsara Inc.") == "samsara"


def test_default_search_queries_include_company() -> None:
    identity = JobIdentity(job_url="https://example.com/job", company_name="Samsara", job_title="SRE")
    queries = default_search_queries(identity)
    assert queries
    assert all("Samsara" in query for query in queries)


def test_parse_search_queries_and_candidates() -> None:
    queries = parse_search_queries('{"queries": ["site:linkedin.com/in Acme recruiter", ""]}')
    assert queries == ["site:linkedin.com/in Acme recruiter"]
    candidates = parse_extracted_candidates(
        """
        {
          "candidates": [
            {
              "name": "Josie Schwartz",
              "kind": "recruiter",
              "title": "Talent",
              "linkedin_url": "https://www.linkedin.com/in/josieschwartz",
              "email": "",
              "confidence": "medium",
              "evidence": ["Manager post assigned platform hiring"]
            }
          ]
        }
        """
    )
    assert candidates[0].name == "Josie Schwartz"
    assert candidates[0].kind == "recruiter"


def test_merge_contact_candidates_prefers_posting_then_dedupes() -> None:
    posting = [_candidate(name="Pat Kim", email="pat.kim@acme.com", source="job_posting")]
    search = [
        _candidate(name="Pat Kim", email="pat.kim@acme.com", source="web_search"),
        _candidate(name="Dana Lee", kind="hiring_manager", linkedin_url="https://linkedin.com/in/dana"),
    ]
    merged = merge_contact_candidates(posting, search)
    assert [item.name for item in merged] == ["Pat Kim", "Dana Lee"]
    assert merged[0].source == "job_posting"


def test_write_contacts_yaml(tmp_path: Path) -> None:
    report = RoleContactReport(
        job_url="https://example.com/job",
        company_name="Acme",
        job_title="SRE",
        looked_up_at="2026-09-03T00:00:00+00:00",
        ai_used=True,
        candidates=[_candidate()],
    )
    path = write_contacts_yaml(report, tmp_path / "contacts.yaml")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert loaded["company_name"] == "Acme"
    assert loaded["candidates"][0]["name"] == "Alex Recruiter"


def test_run_role_contact_lookup_writes_yaml(tmp_path: Path) -> None:
    identity = JobIdentity(
        job_url="https://example.com/job",
        company_name="Acme",
        job_title="Platform Engineer",
        department="Platform",
    )
    output = tmp_path / "contacts.yaml"
    path = run_role_contact_lookup(
        job_url=identity.job_url,
        output_path=output,
        job_description_text="Build platforms.",
        resolve_identity=lambda url: identity,
        fetch_posting_html=lambda url: "<p>Recruiter: Pat Kim</p>",
        plan_queries=lambda identity, **kwargs: ['site:linkedin.com/in "Acme" recruiter'],
        collect_hits=lambda **kwargs: [
            SearchHit(
                title="Pat Kim - Recruiter",
                url="https://www.linkedin.com/in/patkim",
                snippet="Hiring platform engineers at Acme",
                source="duckduckgo",
            )
        ],
        extract_from_hits=lambda **kwargs: [
            _candidate(
                name="Pat Kim",
                linkedin_url="https://www.linkedin.com/in/patkim",
                evidence=("Hiring platform engineers at Acme",),
            )
        ],
    )
    assert path == output.resolve()
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    names = [row["name"] for row in loaded["candidates"]]
    assert "Pat Kim" in names
    assert loaded["ai_used"] is True


def test_run_lookup_after_cv_generate_writes_beside_pdf(tmp_path: Path) -> None:
    from job_hunter.role_contacts.run_lookup import run_lookup_after_cv_generate

    resume = tmp_path / "resume.yaml"
    resume.write_text("target_job_url: https://example.com/job\n", encoding="utf-8")
    pdf_path = tmp_path / "Acme" / "SRE" / "CV.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(b"%PDF")
    contacts_path = pdf_path.parent / "contacts.yaml"
    with patch(
        "job_hunter.role_contacts.run_lookup.run_role_contact_lookup",
        return_value=contacts_path,
    ) as mocked:
        result = run_lookup_after_cv_generate(pdf_path=pdf_path, resume_path=resume)
    assert result == contacts_path
    assert mocked.call_args.kwargs["job_url"] == "https://example.com/job"
    assert mocked.call_args.kwargs["output_path"] == contacts_path


def test_run_lookup_after_cv_generate_swallows_lookup_errors(tmp_path: Path) -> None:
    from job_hunter.role_contacts.run_lookup import run_lookup_after_cv_generate

    resume = tmp_path / "resume.yaml"
    resume.write_text("target_job_url: https://example.com/job\n", encoding="utf-8")
    pdf_path = tmp_path / "CV.pdf"
    pdf_path.write_bytes(b"%PDF")
    with patch(
        "job_hunter.role_contacts.run_lookup.run_role_contact_lookup",
        side_effect=RuntimeError("network"),
    ):
        assert run_lookup_after_cv_generate(pdf_path=pdf_path, resume_path=resume) is None


def test_cv_generate_cli_skip_contacts_does_not_run_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from job_hunter.cli import main

    pdf_path = tmp_path / "CV.pdf"
    pdf_path.write_bytes(b"%PDF")
    lookup_calls: list[object] = []

    monkeypatch.setattr(
        "job_hunter.cv_generate.run_cv_generate.run_cv_generate",
        lambda **kwargs: pdf_path,
    )
    monkeypatch.setattr(
        "job_hunter.role_contacts.run_lookup.run_lookup_after_cv_generate",
        lambda **kwargs: lookup_calls.append(kwargs) or pdf_path.parent / "contacts.yaml",
    )

    assert main(["cv:generate", "--skip-contacts"]) == 0
    captured = capsys.readouterr()
    assert str(pdf_path) in captured.out
    assert lookup_calls == []

    assert main(["cv:generate"]) == 0
    captured = capsys.readouterr()
    assert str(pdf_path) in captured.out
    assert lookup_calls


def test_contacts_lookup_cli_prints_yaml_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from job_hunter.cli import main

    output = tmp_path / "contacts.yaml"
    monkeypatch.setattr(
        "job_hunter.role_contacts.run_lookup.run_role_contact_lookup",
        lambda **kwargs: output,
    )
    assert main(["contacts:lookup", "--job-url", "https://example.com/job"]) == 0
    assert str(output) in capsys.readouterr().out
