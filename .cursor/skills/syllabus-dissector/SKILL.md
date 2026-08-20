---
name: syllabus-dissector
description: Analyze a class syllabus (PDF, Word, HTML, or text) and append it to a color-coded Excel workbook separated by class. Automatically greps the full syllabus for every graded category, extracts all verbatim details per assignment into PDF documents, and hyperlinks them from the workbook. Use when the user uploads or mentions a syllabus, or asks to dissect, parse, or track syllabi, assignments, grade weights, or due dates.
---

# Syllabus Dissector

Turn a syllabus file into a structured, color-coded Excel workbook (one sheet
per class) plus a **PDF document per assignment** containing **every passage**
the syllabus mentions about that item — extracted automatically.

## What this produces

1. **Sorting & weighting** — categories sorted highest-weight first
2. **Grading scale** — full scale + exact **A** threshold
3. **Assignment details** — start date, due date, group-project flag
4. **PDF documents** — one per category; full syllabus grep + dedicated blocks
5. **Excel hyperlinks** — **Open PDF** opens hosted PDF in browser

## Workflow (automatic — do NOT hand-write JSON)

```
- [ ] Step 1: Run dissect_syllabus.py on the uploaded file
- [ ] Step 2: Review auto_dissect stats (sections + verbatim char counts)
- [ ] Step 3: Commit output/ and give user the xlsx download link
```

### One-command pipeline

```bash
python scripts/dissect_syllabus.py "<path-to-syllabus>" \
  --class-code HIST-103 \
  --class-name "The Emergence of Modern Europe" \
  --instructor "Dr. Lindsay O'Neill" \
  --term "Fall 2026" \
  --workbook output/syllabi.xlsx \
  --link-base "https://raw.githubusercontent.com/<owner>/<repo>/<branch>/output/documents" \
  --keep-json output/hist103.json
```

This runs, in order:

1. **`extract_text.py`** — PDF/Word/HTML → plain text
2. **`auto_dissect.py`** — automatic full-document grep per category → JSON
3. **`build_workbook.py`** — JSON → Excel sheet + PDF documents

### What auto_dissect.py does (no manual JSON)

For each graded category detected in the Assignments section:

1. **Detect** name + weight (e.g. `Sleep Paper -20%`)
2. **Parse** grading scale → exact A threshold
3. **Grep** every paragraph in the full syllabus that mentions the category
   (name, aliases like `midterm`, `paper 1`, `experiencing the past`)
4. **Capture** dedicated blocks (study guides, full prompt pages, due-date sections)
5. **Structure** matches into sections (Prompts, Helpful Hints, Format Requirements…)
6. **Archive** all matching text verbatim in `extracted_text`
7. **Infer** due dates and group-project flags from matched text

Review the script output — each category prints section count and verbatim size:

```
Sleep Paper: 4 sections, 9312 chars verbatim
Extra Credit: 3 sections, 1200 chars verbatim
```

If a category shows **0 sections** or very low char count, inspect the source
syllabus formatting; you may pass a corrected `--class-code` or re-run after
fixing the Assignments section labels.

### Manual steps the agent still provides

- `--class-code`, `--class-name`, `--instructor`, `--term` (from syllabus header)
- `--link-base` URL for hosted PDF links (required for standalone xlsx download)

Do **not** manually author category `sections` or `extracted_text` — the script
does the full-document grep.

### Publish

Commit `output/syllabi.xlsx`, `output/documents/*.pdf`, and optionally
`output/*.json`. Give the user:

`https://raw.githubusercontent.com/<owner>/<repo>/<branch>/output/syllabi.xlsx`

## Requirements

```bash
pip install -r requirements.txt
```

(`openpyxl`, `pdfplumber`, `python-docx`, `beautifulsoup4`, `reportlab`)

## Scripts

| Script | Purpose |
|--------|---------|
| `extract_text.py` | Syllabus file → plain text |
| `auto_dissect.py` | Plain text → JSON (automatic grep) |
| `build_workbook.py` | JSON → Excel + PDFs |
| `dissect_syllabus.py` | All three in one command |
| `generate_pdfs.py` | PDF rendering (called by build_workbook) |

See [reference.md](reference.md) for JSON schema and [examples/hist103.json](examples/hist103.json) for sample output shape.
