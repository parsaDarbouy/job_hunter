"""Minimal HTTP GET JSON helper for public job board endpoints."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_USER_AGENT = "job-hunter/0.1 (public job board listing export)"


def get_json(url: str, *, timeout_seconds: float = 30.0) -> Any:
    """
    Perform an HTTP GET and parse JSON.

    Raises:
        HTTPError: Non-success HTTP status.
        URLError: Network or DNS failure.
        json.JSONDecodeError: Body is not JSON.
    """
    request = Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8"))


def get_json_optional(url: str, *, timeout_seconds: float = 30.0) -> tuple[Any | None, str | None]:
    """
    Like :func:`get_json`, but returns ``(payload, None)`` on success or ``(None, error_message)``.
    """
    try:
        return get_json(url, timeout_seconds=timeout_seconds), None
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
