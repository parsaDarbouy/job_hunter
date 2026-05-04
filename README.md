# Job Hunter

Agentic job-hunting utilities. This repository starts with **resume ingestion**: turn a PDF resume into a normalized `resume.yaml` for downstream matching, ranking, and filtering agents. **Position criteria** for the next pipeline stage live in YAML as well: copy `data/position.example.yaml` to a working file (for example `data/position.yaml`) and tune location (countries and cities), compensation (including cross-currency comparison), seniority, stated years-of-experience on postings, and title filters.

## Prerequisites

- Python 3.11+
- [Gemini CLI](https://github.com/google-gemini/gemini-cli) installed and authenticated (`gemini auth`)

## Setup

```bash
cd job_hunter
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Command: `resume:ingest`

Ingest a PDF, extract structure with **Gemini CLI** (headless JSON mode), normalize deterministically in Python, and write YAML.

```bash
python3 -m job_hunter resume:ingest ./resume.pdf
python3 -m job_hunter resume:ingest ./resume.pdf -o ./data/resume.yaml
python3 -m job_hunter resume:ingest ./resume.pdf --debug
python3 -m job_hunter resume:ingest ./resume.pdf --model flash
```

After `pip install -e .`, you can also run:

```bash
job-hunter resume:ingest ./resume.pdf
```

**Stdout:** prints only the absolute path to the generated YAML (unless `--debug`).

**Output file (default `./data/resume.yaml`):** machine-oriented schema:

- `profile` (name, email, `links.github`, `links.linkedin`)
- `summary` (`total_years_experience`, `domains`)
- `skills` (`languages`, `frameworks`, `cloud`, `tools`, `other`) — deduplicated case-insensitively with bucket priority
- `experience` (with `duration_months` computed from dates when parsable)
- `education`
- `metadata` (`parsed_by`, `source_file`)

### Gemini CLI custom command

Gemini CLI loads project commands from `.gemini/commands/`. See `.gemini/commands/resume-ingest.toml`.

## Layout

| Path | Role |
|------|------|
| `data/` | Default directory for CLI-generated files (gitignored contents; see `data/.gitkeep`). Tracked template: `data/position.example.yaml` (copy and edit for your search constraints). |
| `job_hunter/cli.py` | CLI entry (`resume:ingest`) |
| `job_hunter/paths.py` | Shared default paths (`DATA_DIRECTORY`, etc.) |
| `job_hunter/resume_ingest/pdf_loader.py` | PDF → text |
| `job_hunter/resume_ingest/text_cleaner.py` | Deterministic whitespace cleanup |
| `job_hunter/resume_ingest/resume_parser.py` | Gemini CLI subprocess + JSON extraction |
| `job_hunter/resume_ingest/normalize.py` | Durations, dedupe, stable ordering |
| `job_hunter/resume_ingest/yaml_writer.py` | Canonical YAML serialization |

`.gitignore` also excludes typical Python noise (extra venv names, mypy/ruff/pytest caches, packaging outputs, coverage, `.env`, `.DS_Store`) and keeps **resume intake private**: `resume.pdf` and `resume.yaml` match in any folder, plus everything under `data/` except `data/.gitkeep` and `data/position.example.yaml`.

## Determinism and hallucinations

- **YAML on disk:** For a fixed JSON payload from Gemini, normalization and `yaml.safe_dump` (fixed key order, sorted lists where applicable) are deterministic.
- **Model output:** Different Gemini runs can still differ. The extraction prompt forbids fabrication; empty strings and zeros are used when fields are unknown. Use the same model and CLI version for best repeatability.

## Tests

```bash
pytest
```

## Limits

- Text-based PDFs only; scanned PDFs need OCR first.
- Encrypted PDFs are not supported without a password workflow.
