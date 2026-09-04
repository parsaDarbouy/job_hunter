"""HTTP GET for HTML pages used by role-contact search."""

from __future__ import annotations

import urllib.error
import urllib.request

_MAX_RESPONSE_BYTES = 2_000_000
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def fetch_url_text(
    url: str,
    *,
    timeout_seconds: float = 20.0,
    method: str = "GET",
    body: bytes | None = None,
    content_type: str | None = None,
) -> str:
    """
    Fetch a URL and return decoded text.

    Returns an empty string on HTTP or network errors.
    """
    headers = {"User-Agent": _USER_AGENT, "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"}
    if content_type:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read(_MAX_RESPONSE_BYTES)
            charset_header = response.headers.get("content-type", "")
    except (urllib.error.URLError, TimeoutError, OSError):
        return ""
    charset = "utf-8"
    if "charset=" in charset_header.lower():
        charset = charset_header.split("charset=", 1)[1].split(";", 1)[0].strip().strip("\"'")
    return payload.decode(charset, errors="replace")
