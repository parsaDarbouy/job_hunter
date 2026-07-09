"""Run Cursor SDK, Antigravity CLI (``agy``), or legacy Gemini CLI in headless mode."""

from __future__ import annotations

import fcntl
import json
import logging
import os
import pty
import re
import select
import struct
import subprocess
import termios
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_AGENT_BINARY = "cursor"

_CURSOR_MODEL_ALIASES: dict[str, str] = {
    "flash": "composer-2.5",
    "pro": "composer-2.5",
}

_logger = logging.getLogger(__name__)
_ANSI_ESCAPE_PATTERN = re.compile(r"\x1B\[[0-9;]*[A-Za-z]")
_AGY_CLI_LOG_DIR = Path.home() / ".gemini" / "antigravity-cli"
_AGY_LOG_DIAGNOSTIC_MARKERS: tuple[tuple[str, str], ...] = (
    (
        "RESOURCE_EXHAUSTED",
        "Antigravity CLI quota exhausted (individual quota reached). "
        "Wait for the quota reset, upgrade your subscription, or try again later.",
    ),
    (
        "auth timed out",
        "Antigravity CLI authentication timed out in print mode. "
        "Run `agy` interactively once to complete sign-in.",
    ),
    (
        "silent auth failed",
        "Antigravity CLI authentication failed in print mode. "
        "Run `agy` interactively once to complete sign-in.",
    ),
    (
        "model unreachable",
        "Antigravity CLI could not reach the model. "
        "See ~/.gemini/antigravity-cli/cli.log for details.",
    ),
)


@dataclass(frozen=True)
class _SubprocessCapture:
    """Captured subprocess streams."""

    returncode: int
    stdout: str
    stderr: str


def is_cursor_cli(agent_binary: str) -> bool:
    """Return True when ``agent_binary`` selects the Cursor SDK backend."""
    name = Path(agent_binary).name.lower()
    return name == "cursor" or name.startswith("cursor.")


def is_antigravity_cli(agent_binary: str) -> bool:
    """Return True when ``agent_binary`` names the Antigravity CLI (``agy``)."""
    name = Path(agent_binary).name.lower()
    return name == "agy" or name.startswith("agy.") or name == "antigravity"


def map_cursor_model(model: str) -> str:
    """Map legacy agent CLI model aliases to Cursor model ids."""
    return _CURSOR_MODEL_ALIASES.get(model.lower(), model)


def _combine_prompt_and_stdin(*, prompt: str, stdin_payload: str) -> str:
    stdin_payload = stdin_payload.strip()
    if not stdin_payload:
        return prompt
    return f"{prompt}\n\n{stdin_payload}"


def agent_cli_install_hint(agent_binary: str) -> str:
    """Human-readable install hint for the configured agent binary."""
    if is_cursor_cli(agent_binary):
        return (
            "Cursor SDK not installed (pip install cursor-sdk). "
            "Set CURSOR_API_KEY from https://cursor.com/dashboard/integrations"
        )
    if is_antigravity_cli(agent_binary):
        return (
            f"Antigravity CLI not found ({agent_binary}). "
            "Install: curl -fsSL https://antigravity.google/cli/install.sh | bash"
        )
    return (
        f"Gemini CLI not found ({agent_binary}). "
        "Install with: npm install -g @google/gemini-cli"
    )


def build_headless_command(*, agent_binary: str, prompt: str, model: str) -> list[str]:
    """Build argv for a single non-interactive prompt with stdin context."""
    if is_cursor_cli(agent_binary):
        raise ValueError("Cursor agent does not use a subprocess command")
    if is_antigravity_cli(agent_binary):
        return [
            agent_binary,
            "-p",
            prompt,
            "--model",
            model,
            "--dangerously-skip-permissions",
        ]
    return [
        agent_binary,
        "-p",
        prompt,
        "--output-format",
        "json",
        "-m",
        model,
        "--skip-trust",
    ]


def _strip_ansi_escapes(text: str) -> str:
    return _ANSI_ESCAPE_PATTERN.sub("", text)


def _agy_cli_log_candidates() -> list[Path]:
    base_dir = Path.home() / ".gemini" / "antigravity-cli"
    candidates: list[Path] = []
    cli_log = base_dir / "cli.log"
    if cli_log.is_file():
        candidates.append(cli_log)
    log_dir = base_dir / "log"
    if log_dir.is_dir():
        recent_logs = sorted(
            log_dir.glob("cli-*.log"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        candidates.extend(recent_logs[:5])
    unique_candidates: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_candidates.append(path)
    return unique_candidates


def _read_agy_cli_log_tail(*, max_bytes: int = 32_768) -> str:
    chunks: list[str] = []
    for path in _agy_cli_log_candidates():
        try:
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    combined = "\n".join(chunks)
    if len(combined) > max_bytes:
        combined = combined[-max_bytes:]
    return combined


def diagnose_agy_empty_stdout() -> str | None:
    """
    Return a human-readable reason when ``agy -p`` exits cleanly with no stdout.

    Antigravity CLI often omits errors from captured stdout/stderr; recent lines in
    ``cli.log`` are the most reliable signal (quota exhaustion, auth failures, etc.).
    """
    log_text = _read_agy_cli_log_tail()
    if not log_text:
        return None
    for line in reversed(log_text.splitlines()):
        for needle, message in _AGY_LOG_DIAGNOSTIC_MARKERS:
            if needle in line:
                return message
    return None


def _format_agy_empty_stdout_error() -> str:
    diagnosed = diagnose_agy_empty_stdout()
    if diagnosed:
        return diagnosed
    return (
        "Antigravity CLI returned empty stdout in headless mode. "
        "This often happens when stdout is not a TTY or when the CLI fails silently; "
        "check ~/.gemini/antigravity-cli/cli.log and run `agy -p \"test\"` in a terminal."
    )


def parse_headless_stdout(stdout: str, *, agent_binary: str) -> str:
    """
    Return model response text from CLI stdout.

    Antigravity CLI prints the model reply directly. Legacy Gemini CLI wraps it in a JSON envelope.
    """
    if is_antigravity_cli(agent_binary):
        response_text = _strip_ansi_escapes(stdout).strip()
        if not response_text:
            raise RuntimeError(_format_agy_empty_stdout_error())
        return response_text

    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Gemini CLI did not return valid JSON envelope") from exc

    if isinstance(envelope, dict) and envelope.get("error"):
        err = envelope["error"]
        message = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        raise RuntimeError(f"Gemini CLI error: {message}")

    response_text = envelope.get("response") if isinstance(envelope, dict) else None
    if not isinstance(response_text, str) or not response_text.strip():
        raise RuntimeError("Gemini CLI JSON envelope missing response text")
    return response_text


def _run_subprocess_with_pty(
    command: list[str],
    *,
    stdin_payload: str,
    timeout: int,
) -> _SubprocessCapture:
    """
    Run a command under a pseudo-terminal.

    ``agy -p`` drops stdout when spawned with piped/redirected streams (upstream issue #76).
    """
    master_fd, slave_fd = pty.openpty()
    winsize = struct.pack("HHHH", 24, 120, 0, 0)
    fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)
    environment = os.environ.copy()
    environment.setdefault("TERM", "xterm-256color")

    try:
        process = subprocess.Popen(
            command,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
            env=environment,
        )
    except FileNotFoundError:
        os.close(master_fd)
        os.close(slave_fd)
        raise
    finally:
        os.close(slave_fd)

    if stdin_payload:
        os.write(master_fd, stdin_payload.encode())

    output_chunks: list[bytes] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output_chunks.extend(_drain_pty(master_fd))
            break
        readable, _, _ = select.select([master_fd], [], [], 0.1)
        if readable:
            chunk = _read_pty_chunk(master_fd)
            if chunk is None:
                break
            output_chunks.append(chunk)
    else:
        process.kill()
        process.wait(timeout=5)
        raise subprocess.TimeoutExpired(command, timeout)

    returncode = process.wait(timeout=5)
    os.close(master_fd)
    combined_output = _strip_ansi_escapes(b"".join(output_chunks).decode(errors="replace"))
    return _SubprocessCapture(returncode=returncode, stdout=combined_output, stderr="")


def _read_pty_chunk(master_fd: int) -> bytes | None:
    try:
        chunk = os.read(master_fd, 65_536)
    except OSError:
        return None
    if not chunk:
        return None
    return chunk


def _drain_pty(master_fd: int) -> list[bytes]:
    chunks: list[bytes] = []
    while True:
        readable, _, _ = select.select([master_fd], [], [], 0.05)
        if not readable:
            break
        chunk = _read_pty_chunk(master_fd)
        if chunk is None:
            break
        chunks.append(chunk)
    return chunks


def _run_cursor_headless(
    *,
    prompt: str,
    stdin_payload: str,
    model: str,
    timeout: int,
    debug: bool,
) -> str:
    try:
        from cursor_sdk import (
            Agent,
            AgentOptions,
            CursorAgentError,
            CursorClient,
            LocalAgentOptions,
        )
    except ImportError as exc:
        raise FileNotFoundError(agent_cli_install_hint("cursor")) from exc

    api_key = os.environ.get("CURSOR_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "CURSOR_API_KEY is not set. Create an API key at "
            "https://cursor.com/dashboard/integrations and export CURSOR_API_KEY."
        )

    full_prompt = _combine_prompt_and_stdin(prompt=prompt, stdin_payload=stdin_payload)
    cursor_model = map_cursor_model(model)

    try:
        with CursorClient.launch_bridge(
            workspace=os.getcwd(),
            client_timeout=float(timeout),
        ) as client:
            result = Agent.prompt(
                full_prompt,
                AgentOptions(
                    api_key=api_key,
                    model=cursor_model,
                    local=LocalAgentOptions(cwd=os.getcwd()),
                ),
                client=client,
            )
    except CursorAgentError as exc:
        raise RuntimeError(f"Cursor agent failed to start: {exc.message}") from exc

    if debug:
        _logger.debug(
            "cursor_sdk run id=%s agent_id=%s status=%s duration_ms=%s",
            result.id,
            result.agent_id,
            result.status,
            result.duration_ms,
        )

    if result.status == "error":
        raise RuntimeError(f"Cursor agent run failed (run id={result.id})")

    response_text = (result.result or "").strip()
    if not response_text:
        raise RuntimeError("Cursor agent returned empty response")
    return response_text


def _run_headless_capture(
    *,
    agent_binary: str,
    command: list[str],
    stdin_payload: str,
    timeout: int,
) -> _SubprocessCapture:
    if is_antigravity_cli(agent_binary):
        return _run_subprocess_with_pty(command, stdin_payload=stdin_payload, timeout=timeout)

    completed = subprocess.run(
        command,
        input=stdin_payload,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    return _SubprocessCapture(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def run_agent_cli_headless(
    *,
    agent_binary: str = DEFAULT_AGENT_BINARY,
    prompt: str,
    stdin_payload: str,
    model: str = "flash",
    timeout: int = 600,
    debug: bool = False,
) -> str:
    """
    Run Cursor SDK, ``agy``, or legacy ``gemini`` once and return response text.

    Raises FileNotFoundError if the backend is missing.
    Raises RuntimeError on non-zero exit or unparseable stdout.
    """
    if is_cursor_cli(agent_binary):
        return _run_cursor_headless(
            prompt=prompt,
            stdin_payload=stdin_payload,
            model=model,
            timeout=timeout,
            debug=debug,
        )

    command = build_headless_command(agent_binary=agent_binary, prompt=prompt, model=model)
    try:
        completed = _run_headless_capture(
            agent_binary=agent_binary,
            command=command,
            stdin_payload=stdin_payload,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise FileNotFoundError(agent_cli_install_hint(agent_binary)) from exc

    if debug:
        if completed.stdout:
            _logger.debug("agent_cli.subprocess stdout_bytes=%s", len(completed.stdout))
        if completed.stderr:
            err_text = completed.stderr.strip()
            if len(err_text) > 2_000:
                err_text = err_text[:2_000] + "…(truncated)"
            _logger.debug("agent_cli.subprocess stderr=%s", err_text)

    if completed.returncode != 0:
        cli_name = "Antigravity CLI" if is_antigravity_cli(agent_binary) else "Gemini CLI"
        raise RuntimeError(
            f"{cli_name} exited with {completed.returncode}: "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )

    return parse_headless_stdout(completed.stdout, agent_binary=agent_binary)
