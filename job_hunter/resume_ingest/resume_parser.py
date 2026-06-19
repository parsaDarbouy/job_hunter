"""Call Antigravity CLI or legacy Gemini CLI headlessly to extract structured resume fields as JSON."""

from __future__ import annotations

from typing import Any

from job_hunter.agent_cli import DEFAULT_AGENT_BINARY, run_agent_cli_headless
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
    gemini_binary: str = DEFAULT_AGENT_BINARY,
    model: str = "flash",
    debug: bool = False,
) -> dict[str, Any]:
    """
    Run Antigravity CLI (``agy``) or legacy Gemini CLI in headless mode and parse JSON payload.

    Raises RuntimeError on CLI failures or invalid JSON.
    Raises FileNotFoundError if the agent binary is missing.
    """
    stdin_payload = f"---RESUME---\n{cleaned_resume_text}"
    response_text = run_agent_cli_headless(
        agent_binary=gemini_binary,
        prompt=_EXTRACTION_PROMPT,
        stdin_payload=stdin_payload,
        model=model,
        debug=debug,
    )
    if debug:
        print("[debug] agent stdout length:", len(response_text))
    return extract_json_object(response_text)
