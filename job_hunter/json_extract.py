"""Extract the first JSON object from LLM response text."""

from __future__ import annotations

import json
import re
from typing import Any


def strip_json_fence(text: str) -> str:
    stripped = text.strip()
    fence = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", stripped, re.DOTALL | re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    return stripped


def extract_json_object(text: str) -> dict[str, Any]:
    """
    Parse the first JSON object from model output.

    Handles markdown fences, leading commentary, and trailing text after a valid object
    (common when LaTeX in string values confuses naive brace slicing).
    """
    candidate = strip_json_fence(text)
    decoder = json.JSONDecoder()

    try:
        parsed, _ = decoder.raw_decode(candidate)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = 0
    while start < len(candidate):
        brace = candidate.find("{", start)
        if brace == -1:
            break
        try:
            parsed, end = decoder.raw_decode(candidate, brace)
        except json.JSONDecodeError:
            start = brace + 1
            continue
        if isinstance(parsed, dict):
            return parsed
        start = end

    raise ValueError("No JSON object found in model response")
