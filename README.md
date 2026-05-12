# Job Hunter

Agentic job-hunting utilities. **Resume ingestion** turns a PDF resume into a normalized `resume.yaml`. **Listing export** reads `weblist.yaml` (job board sources) plus `position.yaml` (your filters), writes a machine-readable `query.yaml` plan (fetch URLs and title-matching matrix), pulls public listings where supported, filters rows against your position criteria, and merges matches into `jobs_export.csv` (new URLs only when the file already exists). **AI job filtering** uses Gemini CLI to review jobs added on a specific date against `resume.yaml` and `position.yaml`, then writes a filtered CSV.

Copy `data/position.example.yaml` → `data/position.yaml` and `data/weblist.example.yaml` → `data/weblist.yaml`, then edit boards, titles, and geography to match your search.

## Prerequisites

- Python 3.11+
- [Gemini CLI](https://github.com/google-gemini/gemini-cli) installed and authenticated (`gemini auth`)

## Setup

```bash
cd job_hunter
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
npm install -g @google/gemini-cli
gemini auth
gemini --version
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

## Command: `listings:export`

Build `data/query.yaml`, fetch jobs from configured **Greenhouse**, **Ashby**, and **Workable** public JSON (Workable uses the apply-site widget API for the account slug in `https://apply.workable.com/{slug}/`), filter using `position.yaml`, and merge into **`data/jobs_export.csv`** with columns `url`, `job_title`, `listing_posted_date`, `added_to_list_date`, `location`, `company_name`, `job_description` (`listing_posted_date` is the calendar day the ATS reports the role was listed—`YYYY-MM-DD`—when provided; otherwise empty; `added_to_list_date` is the first local-calendar day this tool appended that ``url`` to this CSV—already-exported URLs are skipped on later runs instead of overwriting the row; roles that vanished from ATS listings remain in the sheet until you delete them; `company_name` is the board API name when present, otherwise a heuristic from token/slug; `job_description` is left empty by export and filled later by `jobs:filter` only for the date being processed).

```bash
python3 -m job_hunter listings:export
python3 -m job_hunter listings:export --weblist ./data/weblist.yaml --position ./data/position.yaml
python3 -m job_hunter listings:export --query-output ./data/query.yaml --csv-output ./data/jobs_export.csv --debug
```

After `pip install -e .`, you can also run `job-hunter listings:export`.

**Defaults:** `--weblist` prefers `./data/weblist.yaml` when it exists, otherwise `./data/weblist.example.yaml`. `--position` prefers `./data/position.yaml`, otherwise `./data/position.example.yaml`. **Stdout** prints the absolute path to the CSV (same pattern as `resume:ingest` printing the YAML path).

**`query.yaml`:** metadata (input paths, timestamp, `csv_output_path`), `criteria_snapshot` (titles, geography, comp notes copied from `position.yaml`), `fetch_tasks` (one HTTP GET per concrete board after expansion, plus `enabled` / `request: null` when a source is turned off), and `title_query_matrix` (each expanded source × each acceptable title; custom career URLs use a manual-review strategy string).

**`weblist.yaml` and coverage:** Greenhouse, Ashby, and Workable do **not** publish a public “list every customer worldwide” API. This tool instead **expands** each `sources` row into **one fetch task per company** using:

- **Singles** (unchanged): `board_token`, `organization_slug`, `apply_account_slug`, or one `careers_page_url`.
- **Inline lists**: `board_tokens`, `organization_slugs`, `apply_account_slugs`, or `careers_pages` (`[{url, display_name}, …]`).
- **Registry files**: `board_tokens_registry`, `organization_slugs_registry`, `apply_account_slugs_registry`, or `careers_pages_registry` — YAML paths **relative to the weblist file**, or absolute paths, or **`package:filename.yaml`** for bundled lists under `job_hunter/job_listings/registries/` (see `data/weblist.example.yaml`).

Bundled **`package:*.blockchain.yaml`** registries split a footprint-ranked set of crypto / blockchain employers across Greenhouse tokens, Ashby slugs, Workable apply slugs (each company appears in exactly one file), plus custom careers URLs without a scrape yet. **`data/weblist.example.yaml`** and the default **`data/weblist.yaml`** include separate `sources` rows (``greenhouse_blockchain``, etc.) that reference those files; remove them or set ``enabled: false`` if you do not want that coverage.

You can merge singles + lists + registry on one row; tokens are de-duplicated. For **custom career pages**, URLs are included in `query.yaml` for tracking; there is still **no automated HTML scrape** (fetch returns no rows until a fetcher exists). Set `enabled: false` on a row to skip expansion and HTTP for that block.

**Filters today:** `titles.acceptable` entries match job titles as **phrases with regex-style word boundaries** (case-insensitive), so roles like ``Site Reliability Engineer - AI & ML Infrastructure (…)`` match an allow-list line for ``Site Reliability Engineer``. Entries that are only short qualifiers such as ``Platform``, ``Cloud``, or ``Infrastructure`` also require a recognizable **engineering / infra role cue** elsewhere in the title (so listings like ``Product Marketing Manager, Platform`` do not pass on the trailing department name alone). `titles.not_acceptable` stays substring-based (drops the row when any phrase appears anywhere in the title, case-insensitive). Geography uses `location_constraints` (ATS **location** string heuristics only). **Seniority** uses `acceptable_seniority_levels` / `not_acceptable_seniority_levels`: in addition to the usual inferred bucket from **job title keywords**, ``not_acceptable_seniority_levels`` rejects when blocked level wording appears as real words/phrases (e.g. ``Account Executive`` when ``executive`` is blocked) without substring false positives such as rejecting ``International`` solely because ``intern`` appears mid-word. Titles with no seniority signal still pass when only an ``acceptable`` seniority allow-list applies. Compensation ranges and stated YOE in `position.yaml` are captured in `criteria_snapshot` for transparency; compensation is not used to drop rows automatically when listings do not include structured pay.

## Command: `jobs:filter`

Review exported jobs with **Gemini CLI** one by one. The command only evaluates rows where `added_to_list_date` equals the date you pass, so each listing batch can be processed once. If `data/jobs_export.csv` does not yet have the final `job_description` column, or a matching row has an empty value, the command fetches the job URL, extracts readable page text, stores it back in `jobs_export.csv`, and sends that description to Gemini.

Add or edit the threshold in `data/position.yaml`:

```yaml
ai_filtering:
  minimum_alignment_percentage: 70
```

Run the flow:

```bash
python3 -m job_hunter resume:ingest ./resume.pdf -o ./data/resume.yaml
python3 -m job_hunter listings:export
python3 -m job_hunter jobs:filter --date 2026-05-08
```

Useful options:

```bash
python3 -m job_hunter jobs:filter \
  --date 2026-05-08 \
  --jobs-csv ./data/jobs_export.csv \
  --resume ./data/resume.yaml \
  --position ./data/position.yaml \
  --output ./data/filtered_jobs_2026-05-08.csv \
  --model flash \
  --debug
```

**Output:** stdout prints the absolute path to the filtered CSV. By default it writes `data/filtered_jobs_YYYY-MM-DD.csv` with the same columns as the current jobs export, including `job_description`.

## Layout

| Path | Role |
|------|------|
| `data/` | Default directory for CLI-generated files (gitignored contents; see `data/.gitkeep`). Tracked templates: `data/position.example.yaml`, `data/weblist.example.yaml`. Generated: `data/query.yaml`, `data/jobs_export.csv`, `data/resume.yaml`, etc. |
| `job_hunter/cli.py` | CLI entry (`resume:ingest`, `listings:export`) |
| `job_hunter/paths.py` | Shared default paths (`DATA_DIRECTORY`, default resume / weblist / position / query / CSV paths) |
| `job_hunter/job_listings/` | Listing export: YAML plan, HTTP fetchers, filters, CSV writer |
| `job_hunter/job_filtering/` | Date-scoped AI filtering: job page text extraction, Gemini scoring, filtered CSV writer |
| `job_hunter/job_listings/registries/*.yaml` | Bundled example board lists (Greenhouse tokens, Ashby slugs, Workable slugs, career URLs) for `package:` weblist references; optional `*.blockchain.yaml` packs. The `*.example.yaml` files include an extension aimed at globally remote-friendly employers (tokens/slugs validated against each vendor’s public listing API). |
| `job_hunter/job_listings/weblist_expand.py` | Expands multi-company weblist rows before `query.yaml` and fetching |
| `job_hunter/resume_ingest/pdf_loader.py` | PDF → text |
| `job_hunter/resume_ingest/text_cleaner.py` | Deterministic whitespace cleanup |
| `job_hunter/resume_ingest/resume_parser.py` | Gemini CLI subprocess + JSON extraction |
| `job_hunter/resume_ingest/normalize.py` | Durations, dedupe, stable ordering |
| `job_hunter/resume_ingest/yaml_writer.py` | Canonical YAML serialization |

`.gitignore` also excludes typical Python noise (extra venv names, mypy/ruff/pytest caches, packaging outputs, coverage, `.env`, `.DS_Store`) and keeps **resume intake private**: `resume.pdf` and `resume.yaml` match in any folder, plus everything under `data/` except `data/.gitkeep`, `data/position.example.yaml`, and `data/weblist.example.yaml`.

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
