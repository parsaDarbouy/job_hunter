"""Unit tests for deterministic resume normalization."""

from __future__ import annotations

from datetime import datetime, timezone

from job_hunter.resume_ingest.normalize import normalize_extracted_resume


def test_skills_dedupe_cross_category_prefers_higher_priority_bucket() -> None:
    extracted = {
        "profile": {},
        "summary": {"total_years_experience": None, "domains": ["Backend", "backend"]},
        "skills": {
            "languages": ["Python", "python"],
            "frameworks": ["Django"],
            "cloud": ["AWS"],
            "tools": ["Python", "docker"],
            "other": [],
        },
        "experience": [],
        "education": [],
    }
    fixed_now = datetime(2024, 6, 15, tzinfo=timezone.utc)
    normalized = normalize_extracted_resume(extracted, reference_time=fixed_now)
    assert normalized["skills"]["languages"] == ["Python"]
    assert "Python" not in normalized["skills"]["tools"]
    assert normalized["skills"]["tools"] == ["docker"]
    assert normalized["summary"]["domains"] == ["backend"]


def test_duration_months_present_end() -> None:
    extracted = {
        "profile": {},
        "summary": {},
        "skills": {k: [] for k in ("languages", "frameworks", "cloud", "tools", "other")},
        "experience": [
            {
                "company": "Acme",
                "title": "Engineer",
                "start_date": "2020-01",
                "end_date": "Present",
                "highlights": ["Shipped widgets", "Shipped widgets"],
            }
        ],
        "education": [],
    }
    fixed_now = datetime(2021, 1, 1, tzinfo=timezone.utc)
    normalized = normalize_extracted_resume(extracted, reference_time=fixed_now)
    assert normalized["experience"][0]["duration_months"] == 13


def test_total_years_null_becomes_zero() -> None:
    extracted = {
        "profile": {},
        "summary": {"total_years_experience": None, "domains": []},
        "skills": {k: [] for k in ("languages", "frameworks", "cloud", "tools", "other")},
        "experience": [],
        "education": [],
    }
    normalized = normalize_extracted_resume(extracted)
    assert normalized["summary"]["total_years_experience"] == 0


def test_profile_phone_and_location() -> None:
    extracted = {
        "profile": {
            "name": "Alex Rivera",
            "email": "alex@example.com",
            "phone": "+1 555-010-2030",
            "location": "Edmonton, AB",
            "github": "alex-dev",
            "linkedin": "alex-rivera",
        },
        "summary": {"total_years_experience": None, "domains": []},
        "skills": {k: [] for k in ("languages", "frameworks", "cloud", "tools", "other")},
        "experience": [],
        "education": [],
    }
    normalized = normalize_extracted_resume(extracted)
    assert normalized["profile"]["phone"] == "+1 555-010-2030"
    assert normalized["profile"]["location"] == "Edmonton, AB"


def test_accomplishments_sorted_and_deduped() -> None:
    extracted = {
        "profile": {},
        "summary": {"total_years_experience": None, "domains": []},
        "skills": {k: [] for k in ("languages", "frameworks", "cloud", "tools", "other")},
        "experience": [],
        "education": [],
        "accomplishments": [
            {"title": "AWS Certified Cloud Practitioner", "detail": "AWS", "date": "2023"},
            {"title": "AWS Certified Cloud Practitioner", "detail": "duplicate", "date": "2022"},
            {"title": "Speaker", "detail": "Guild talk", "date": "2024"},
        ],
    }
    normalized = normalize_extracted_resume(extracted)
    titles = [row["title"] for row in normalized["accomplishments"]]
    assert titles == ["Speaker", "AWS Certified Cloud Practitioner"]
