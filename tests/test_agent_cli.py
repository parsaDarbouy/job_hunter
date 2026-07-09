"""Tests for Antigravity / Gemini CLI helpers."""

from __future__ import annotations

import json

import pytest

from job_hunter.agent_cli import (
    build_headless_command,
    diagnose_agy_empty_stdout,
    is_antigravity_cli,
    is_cursor_cli,
    map_cursor_model,
    parse_headless_stdout,
    run_agent_cli_headless,
)


def test_is_antigravity_cli() -> None:
    assert is_antigravity_cli("agy")
    assert is_antigravity_cli("/Users/me/.local/bin/agy")
    assert not is_antigravity_cli("gemini")
    assert not is_antigravity_cli("/usr/local/bin/gemini")
    assert not is_antigravity_cli("cursor")


def test_is_cursor_cli() -> None:
    assert is_cursor_cli("cursor")
    assert is_cursor_cli("/usr/local/bin/cursor")
    assert not is_cursor_cli("agy")
    assert not is_cursor_cli("gemini")


def test_map_cursor_model() -> None:
    assert map_cursor_model("flash") == "composer-2.5"
    assert map_cursor_model("composer-2.5") == "composer-2.5"
    assert map_cursor_model("auto") == "auto"


def test_build_headless_command_agy() -> None:
    command = build_headless_command(agent_binary="agy", prompt="hello", model="flash")
    assert command == ["agy", "-p", "hello", "--model", "flash", "--dangerously-skip-permissions"]


def test_build_headless_command_gemini() -> None:
    command = build_headless_command(agent_binary="gemini", prompt="hello", model="flash")
    assert command == [
        "gemini",
        "-p",
        "hello",
        "--output-format",
        "json",
        "-m",
        "flash",
        "--skip-trust",
    ]


def test_parse_headless_stdout_agy_plain_text() -> None:
    assert parse_headless_stdout('{"ok": true}', agent_binary="agy") == '{"ok": true}'


def test_parse_headless_stdout_gemini_envelope() -> None:
    envelope = json.dumps({"response": '{"score": 80}'})
    assert parse_headless_stdout(envelope, agent_binary="gemini") == '{"score": 80}'


def test_parse_headless_stdout_gemini_error() -> None:
    envelope = json.dumps({"error": {"message": "quota exceeded"}})
    with pytest.raises(RuntimeError, match="quota exceeded"):
        parse_headless_stdout(envelope, agent_binary="gemini")


def test_parse_headless_stdout_agy_empty_uses_diagnosis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "job_hunter.agent_cli.diagnose_agy_empty_stdout",
        lambda: "Antigravity CLI quota exhausted (individual quota reached).",
    )
    with pytest.raises(RuntimeError, match="quota exhausted"):
        parse_headless_stdout("", agent_binary="agy")


def test_diagnose_agy_empty_stdout_reads_recent_log(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    log_dir = tmp_path / "log"
    log_dir.mkdir()
    (log_dir / "cli-old.log").write_text("I line\n", encoding="utf-8")
    (log_dir / "cli-new.log").write_text(
        "E line RESOURCE_EXHAUSTED (code 429): Individual quota reached.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("job_hunter.agent_cli._agy_cli_log_candidates", lambda: [log_dir / "cli-new.log"])
    message = diagnose_agy_empty_stdout()
    assert message is not None
    assert "quota exhausted" in message.lower()


def test_run_agent_cli_headless_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def fake_cursor_headless(**kwargs: object) -> str:
        captured["prompt"] = str(kwargs["prompt"])
        captured["stdin_payload"] = str(kwargs["stdin_payload"])
        captured["model"] = str(kwargs["model"])
        return '{"ok": true}'

    monkeypatch.setattr("job_hunter.agent_cli._run_cursor_headless", fake_cursor_headless)
    response = run_agent_cli_headless(
        agent_binary="cursor",
        prompt="extract resume",
        stdin_payload="---RESUME---\nJane Doe",
        model="flash",
    )
    assert response == '{"ok": true}'
    assert captured["prompt"] == "extract resume"
    assert captured["stdin_payload"] == "---RESUME---\nJane Doe"
    assert captured["model"] == "flash"
