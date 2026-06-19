"""Run Antigravity CLI (``agy``) or legacy Gemini CLI in headless print mode."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

DEFAULT_AGENT_BINARY = "agy"

_logger = logging.getLogger(__name__)


def is_antigravity_cli(agent_binary: str) -> bool:
    """Return True when ``agent_binary`` names the Antigravity CLI (``agy``)."""
    name = Path(agent_binary).name.lower()
    return name == "agy" or name.startswith("agy.") or name == "antigravity"


def agent_cli_install_hint(agent_binary: str) -> str:
    """Human-readable install hint for the configured agent binary."""
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


def parse_headless_stdout(stdout: str, *, agent_binary: str) -> str:
    """
    Return model response text from CLI stdout.

    Antigravity CLI prints the model reply directly. Legacy Gemini CLI wraps it in a JSON envelope.
    """
    if is_antigravity_cli(agent_binary):
        response_text = stdout.strip()
        if not response_text:
            raise RuntimeError("Antigravity CLI returned empty stdout")
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
    Run ``agy`` or legacy ``gemini`` once in print mode and return response text.

    Raises FileNotFoundError if the binary is missing.
    Raises RuntimeError on non-zero exit or unparseable stdout.
    """
    command = build_headless_command(agent_binary=agent_binary, prompt=prompt, model=model)
    try:
        completed = subprocess.run(
            command,
            input=stdin_payload,
            text=True,
            capture_output=True,
            check=False,
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
