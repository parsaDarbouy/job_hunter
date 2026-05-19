"""Call Gemini CLI headlessly to extract structured resume fields as JSON."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from job_hunter.json_extract import extract_json_object

_EXTRACTION_PROMPT = """You are a resume extraction engine. Your input is plain text extracted from a PDF resume (it may have line breaks or minor OCR-like noise).

Rules (strict):
- Output exactly ONE JSON object and nothing else. No markdown fences, no commentary.
- Use only information explicitly supported by the resume text. If a field is unknown or not stated, use an empty string "" for strings, empty array [] for arrays, or null for optional numbers.
- Do not infer employers, dates, degrees, or skills that are not clearly present. Do not fabricate contact details.
- Normalize skill tokens: expand obvious abbreviations only when the resume defines them; otherwise keep wording from the resume. Split compound vendor+product when clearly separable (e.g. "AWS EC2" → record "AWS" under cloud and "EC2" under cloud or tools as appropriate). If unsure, keep a single token in the most fitting category.
- For domains, use short lowercase labels when clearly implied by roles (e.g. "backend", "infra", "devops", "sre", "ml", "data", "frontend", "mobile", "security"). If unclear, omit from the domains array.
- total_years_experience: set a number only if you can justify it from dated employment; otherwise null (do not guess).
- experience array: most recent first when the resume makes order obvious; otherwise preserve resume order.
- Date fields: prefer "YYYY-MM" when month is known; else "YYYY", else "".
- highlights: bullet strings copied or lightly shortened from the resume; no new claims.
- profile.phone and profile.location: copy only when explicitly stated in the resume header or contact block (do not infer from employers or education).
- accomplishments: certifications, licenses, awards, speaking engagements, and similar items from a dedicated section or clearly labeled entries. One object per item; no fabrication.

JSON shape (types matter):
{
  "profile": {
    "name": "",
    "email": "",
    "phone": "",
    "location": "",
    "github": "",
    "linkedin": ""
  },
  "summary": {
    "total_years_experience": null,
    "domains": []
  },
  "skills": {
    "languages": [],
    "frameworks": [],
    "cloud": [],
    "tools": [],
    "other": []
  },
  "experience": [
    {
      "company": "",
      "title": "",
      "start_date": "",
      "end_date": "",
      "highlights": []
    }
  ],
  "education": [
    {
      "institution": "",
      "degree": "",
      "field": "",
      "start_date": "",
      "end_date": ""
    }
  ],
  "accomplishments": [
    {
      "title": "",
      "detail": "",
      "date": ""
    }
  ]
}

The resume text follows on stdin after a single line containing only: ---RESUME---"""


def parse_resume_with_gemini_cli(
    cleaned_resume_text: str,
    *,
    gemini_binary: str = "gemini",
    model: str = "flash",
    debug: bool = False,
) -> dict[str, Any]:
    """
    Run Gemini CLI in headless mode with JSON output and parse the inner payload.

    Raises RuntimeError on CLI failures or invalid JSON.
    Raises FileNotFoundError if the gemini binary is missing.
    """
    stdin_payload = f"---RESUME---\n{cleaned_resume_text}"
    command = [
        gemini_binary,
        "-p",
        _EXTRACTION_PROMPT,
        "--output-format",
        "json",
        "-m",
        model,
        "--skip-trust",
    ]
    try:
        completed = subprocess.run(
            command,
            input=stdin_payload,
            text=True,
            capture_output=True,
            check=False,
            timeout=600,
        )
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Gemini CLI not found ({gemini_binary}). Install with: npm install -g @google/gemini-cli"
        ) from exc

    if debug:
        if completed.stdout:
            print("[debug] gemini stdout length:", len(completed.stdout))
        if completed.stderr:
            print("[debug] gemini stderr:\n", completed.stderr)

    if completed.returncode != 0:
        raise RuntimeError(
            f"Gemini CLI exited with {completed.returncode}: {completed.stderr.strip() or completed.stdout.strip()}"
        )

    try:
        envelope = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Gemini CLI did not return valid JSON envelope") from exc

    if isinstance(envelope, dict) and envelope.get("error"):
        err = envelope["error"]
        message = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        raise RuntimeError(f"Gemini CLI error: {message}")

    response_text = envelope.get("response") if isinstance(envelope, dict) else None
    if not isinstance(response_text, str) or not response_text.strip():
        raise RuntimeError("Gemini CLI JSON envelope missing response text")

    return extract_json_object(response_text)
