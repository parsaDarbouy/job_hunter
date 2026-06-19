# Job Hunter — user manual

A short guide to the commands. For setup details and how the project is organized, see [README.md](README.md).

## What this tool does

1. Turn your resume PDF into structured data (`resume.yaml`).
2. Pull job listings from boards you configure, keep ones that match your criteria, and save them to a spreadsheet (`jobs_export.csv`).
3. Use AI to score new listings against your resume and role preferences (`filtered_jobs_*.csv`).
4. Build a tailored PDF resume for a specific job posting (`cv:generate`).

You need **Python 3.11+**, **Antigravity CLI** (`agy`), and for PDF resumes **Tectonic** or **pdflatex** (see README).

## One-time setup

```bash
cd job_hunter
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
curl -fsSL https://antigravity.google/cli/install.sh | bash
agy   # first run: sign in with Google OAuth in the browser
```

Copy and edit your search config:

```bash
cp data/position.example.yaml data/position.yaml
cp data/weblist.example.yaml data/weblist.yaml
```

Edit `data/position.yaml` (titles, location, seniority, minimum AI score) and `data/weblist.yaml` (which job boards to watch). Details are in the example files.

After install you can run either:

- `python3 -m job_hunter <command>`
- `job-hunter <command>`

Most commands print **one line** on success: the path to the file they created.

---

## Typical workflow

```bash
# 1. Build resume.yaml from your PDF
job-hunter resume:ingest ./resume.pdf

# 2. Fetch and filter listings → jobs_export.csv
job-hunter listings:export

# 3. AI-review jobs added today (use the date shown in the CSV)
job-hunter jobs:filter --date 2026-05-21

# 4. Optional: tailored CV for one job (set target_job_url in resume.yaml first)
job-hunter cv:generate
```

Run `listings:export` regularly (e.g. daily). Run `jobs:filter` with the **same date** as `added_to_list_date` for the rows you want scored that day.

---

## `resume:ingest`

**Purpose:** Read a PDF resume and write `data/resume.yaml` (contact info, skills, jobs, education, etc.).

```bash
job-hunter resume:ingest ./resume.pdf
```

| Option | What it does |
|--------|----------------|
| `pdf_path` | Your resume PDF (required). |
| `-o`, `--output` | Where to save YAML (default: `data/resume.yaml`). |
| `--debug` | Extra diagnostics on stderr; still prints the output path. |
| `--model` | Agent model (default: `flash`). |
| `--gemini-binary` | Antigravity CLI (`agy`) or legacy `gemini` executable (default: `agy`). |

**Tip:** Re-running updates the YAML from the PDF. Fields you add by hand at the top of `resume.yaml` (like `target_job_url` for CV generation) are kept when you ingest again.

---

## `listings:export`

**Purpose:** Read your weblist and position settings, download jobs from configured boards (Greenhouse, Ashby, Workable, Lever), drop rows that do not match your filters, and append **new** jobs to `data/jobs_export.csv`.

```bash
job-hunter listings:export
```

| Option | What it does |
|--------|----------------|
| `--weblist` | Board list YAML (default: `data/weblist.yaml`, or the example file if yours is missing). |
| `--position` | Your filters YAML (default: `data/position.yaml`, or the example file). |
| `--query-output` | Where to write the search plan (default: `data/query.yaml`). |
| `--csv-output` | Output spreadsheet (default: `data/jobs_export.csv`). |
| `--debug` | Per-board fetch details on stderr. |

**Behavior:**

- Jobs already in the CSV (same URL) are skipped, not updated.
- New rows get today’s date in `added_to_list_date`.
- Job descriptions stay empty until `jobs:filter` fills them for the date you process.
- While boards are fetched, stderr shows a progress bar: sources done, postings fetched, and matches so far.

---

## `jobs:filter`

**Purpose:** For every job **added on the date you choose**, fetch the posting text if needed, ask the agent CLI how well it fits your resume and `position.yaml`, and write passing jobs to a filtered CSV.

```bash
job-hunter jobs:filter --date 2026-05-21
```

| Option | What it does |
|--------|----------------|
| `--date` | **Required.** `YYYY-MM-DD` — only rows with this `added_to_list_date` are reviewed. |
| `--jobs-csv` | Input spreadsheet (default: `data/jobs_export.csv`). |
| `--resume` | Your resume YAML (default: `data/resume.yaml`). |
| `--position` | Criteria YAML (default: `data/position.yaml`). |
| `--output` | Filtered CSV path (default: `data/filtered_jobs_YYYY-MM-DD.csv`). |
| `--model` | Agent model (default: `flash`). |
| `--gemini-binary` | Antigravity CLI (`agy`) or legacy `gemini` executable (default: `agy`). |
| `--max-description-chars` | Max characters of job text sent to AI per job (default: 30000). |
| `--debug` | Per-job details and progress on stderr. |

**In `position.yaml`:** set `ai_filtering.minimum_alignment_percentage` (e.g. `70`) — jobs below that score are dropped.

Accepted jobs are written as they pass, so you keep partial results if the run stops early.

---

## `cv:generate`

**Purpose:** Using `data/resume.yaml` and the job URL in `target_job_url`, tailor the LaTeX CV template with AI and compile a PDF under `data/cv/`.

**Before you run**, add to the top of `data/resume.yaml` (not filled in by ingest):

```yaml
resume_max_pages: 2
target_job_url: "https://…"
```

Optional: `cv_layout`, `about_me_note` — see README or the example in README’s `cv:generate` section.

If tailored LaTeX breaks `cv_layout` limits (skill name length, word counts, bullet counts), the tool re-asks the agent up to three times with the violation list and asks for shorter wording before failing.

```bash
job-hunter cv:generate
```

| Option | What it does |
|--------|----------------|
| `--resume` | Resume YAML with `target_job_url` (default: `data/resume.yaml`). |
| `--template` | LaTeX template folder (default: `data/cv_template`). |
| `--output-dir` | Where PDFs are saved (default: `data/cv`). |
| `--model` | Agent model (default: `flash`). |
| `--gemini-binary` | Antigravity CLI (`agy`) or legacy `gemini` executable (default: `agy`). |
| `--latex-engine` | `tectonic` or `pdflatex` (auto-picks if omitted). |
| `--pdflatex` | Explicit path to `pdflatex`. |
| `--debug` | Extra logs on stderr. |

---

## Files you touch most

| File | Role |
|------|------|
| `data/position.yaml` | What roles you want (titles, location, seniority, AI score threshold). |
| `data/weblist.yaml` | Which companies/boards to search. |
| `data/resume.yaml` | Your structured resume; add `target_job_url` for CV generation. |
| `data/jobs_export.csv` | All matching listings the tool has collected. |
| `data/filtered_jobs_YYYY-MM-DD.csv` | AI-approved jobs for that add date. |
| `data/cv/*.pdf` | Generated tailored resumes. |

Generated files under `data/` are usually gitignored; keep your own copies safe.

---

## Help

```bash
job-hunter --help
job-hunter resume:ingest --help
job-hunter listings:export --help
job-hunter jobs:filter --help
job-hunter cv:generate --help
```
