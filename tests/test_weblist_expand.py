"""Tests for weblist expansion."""

from __future__ import annotations

from pathlib import Path

import pytest

from job_hunter.job_listings.weblist_expand import expand_weblist_sources


def test_expand_preserves_id_for_single_greenhouse_token(tmp_path: Path) -> None:
    weblist = tmp_path / "weblist.yaml"
    weblist.write_text("x", encoding="utf-8")
    sources = [{"id": "solo", "kind": "greenhouse", "board_token": "acme"}]
    out = expand_weblist_sources(sources, weblist_path=weblist)
    assert len(out) == 1
    assert out[0]["id"] == "solo"
    assert out[0]["board_token"] == "acme"
    assert "expansion_parent_id" not in out[0]


def test_expand_splits_multi_greenhouse_tokens(tmp_path: Path) -> None:
    weblist = tmp_path / "weblist.yaml"
    weblist.write_text("x", encoding="utf-8")
    sources = [{"id": "pack", "kind": "greenhouse", "board_tokens": ["a", "b", "a"]}]
    out = expand_weblist_sources(sources, weblist_path=weblist)
    assert [row["id"] for row in out] == ["pack__a", "pack__b"]
    assert [row["board_token"] for row in out] == ["a", "b"]
    assert all(row.get("expansion_parent_id") == "pack" for row in out)


def test_expand_loads_registry_relative_to_weblist(tmp_path: Path) -> None:
    reg = tmp_path / "registries"
    reg.mkdir()
    (reg / "boards.yaml").write_text("board_tokens:\n  - x\n  - y\n", encoding="utf-8")
    weblist = tmp_path / "weblist.yaml"
    weblist.write_text("x", encoding="utf-8")
    sources = [
        {
            "id": "from_file",
            "kind": "greenhouse",
            "board_tokens_registry": "registries/boards.yaml",
        }
    ]
    out = expand_weblist_sources(sources, weblist_path=weblist)
    assert len(out) == 2
    assert {row["board_token"] for row in out} == {"x", "y"}


def test_expand_disabled_source_passes_through(tmp_path: Path) -> None:
    weblist = tmp_path / "weblist.yaml"
    weblist.write_text("x", encoding="utf-8")
    sources = [{"id": "off", "kind": "greenhouse", "board_token": "acme", "enabled": False}]
    out = expand_weblist_sources(sources, weblist_path=weblist)
    assert out == sources


def test_expand_custom_pages(tmp_path: Path) -> None:
    weblist = tmp_path / "weblist.yaml"
    weblist.write_text("x", encoding="utf-8")
    sources = [
        {
            "id": "sites",
            "kind": "custom_career_page",
            "careers_pages": [
                {"url": "https://a.example/careers", "display_name": "A"},
                {"url": "https://b.example/careers", "display_name": "B"},
            ],
        }
    ]
    out = expand_weblist_sources(sources, weblist_path=weblist)
    assert len(out) == 2
    assert out[0]["careers_page_url"] == "https://a.example/careers"
    assert out[0]["id"] == "sites__0"
    assert out[1]["id"] == "sites__1"


def test_expand_unknown_kind_raises(tmp_path: Path) -> None:
    weblist = tmp_path / "weblist.yaml"
    weblist.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported"):
        expand_weblist_sources([{"id": "bad", "kind": "unknown"}], weblist_path=weblist)
