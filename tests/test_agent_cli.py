"""Tests for Antigravity / Gemini CLI helpers."""

from __future__ import annotations

import json

import pytest

from job_hunter.agent_cli import (
    build_headless_command,
    is_antigravity_cli,
    parse_headless_stdout,
)


def test_is_antigravity_cli() -> None:
    assert is_antigravity_cli("agy")
    assert is_antigravity_cli("/Users/me/.local/bin/agy")
    assert not is_antigravity_cli("gemini")
    assert not is_antigravity_cli("/usr/local/bin/gemini")


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
