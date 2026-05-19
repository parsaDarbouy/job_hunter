"""Tests for experience note extraction used by cv:generate."""

from __future__ import annotations

from job_hunter.cv_generate.experience_notes import collect_experience_notes


def test_collect_inline_note_on_role() -> None:
    document = {
        "experience": [
            {
                "company": "Kleros",
                "title": "Site Reliability Engineer",
                "note": "Sole SRE on the team.",
                "highlights": ["Ran on-call."],
            }
        ]
    }
    hints = collect_experience_notes(document)
    assert hints == [
        {
            "company": "Kleros",
            "title": "Site Reliability Engineer",
            "note": "Sole SRE on the team.",
        }
    ]


def test_collect_orphan_note_list_item_after_role() -> None:
    document = {
        "experience": [
            {
                "company": "Kleros",
                "title": "SRE",
                "highlights": ["Shipped reliability work."],
            },
            {"Note": "Only SRE at the company."},
        ]
    }
    hints = collect_experience_notes(document)
    assert hints == [{"company": "Kleros", "title": "SRE", "note": "Only SRE at the company."}]


def test_collect_ignores_roles_without_notes() -> None:
    document = {
        "experience": [
            {"company": "Acme", "title": "Engineer", "highlights": []},
        ]
    }
    assert collect_experience_notes(document) == []
