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
2. **Grading scale** — full scale + exact **A** threshold (or points total for calendars)
3. **Assignment details** — start date, due date, group-project flag
4. **PDF documents** — one per category; structured sections + verbatim extract
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

1. **`extract_text.py`** — PDF/Word/HTML → plain text (+ PDF table JSON for calendars)
2. **`auto_dissect.py`** — automatic extraction per category → JSON
3. **`build_workbook.py`** — JSON → Excel sheet + PDF documents

## Two document types

### A. Full syllabus (e.g. HIST-103)

Uses the **Assignments section** + full-document grep:

1. Detect name + weight (e.g. `Sleep Paper -20%`)
2. Parse grading scale → exact A threshold
3. Grep every paragraph mentioning the category (aliases: `paper 1`, `midterm`, etc.)
4. Capture dedicated blocks (study guides, prompt pages, due-date sections)
5. Structure into sections (Prompts, Helpful Hints, Format Requirements…)
6. Archive all matching text verbatim in `extracted_text`

**Expected quality:** ~7–9/10 detail. Verbatim blocks are full syllabus paragraphs.

### B. Course Calendar (e.g. BUAD-281)

Point-based schedule tables — **no Assignments section**.

1. **`extract_text.py`** parses PDF **tables** via pdfplumber and embeds
   `=== CALENDAR_TABLE_JSON ===` rows (class, date, topic, reading, homework)
2. **`auto_dissect.py`** detects `Course Calendar` and parses categories from
   point lines (`Midterm 1: 250 Points`, homework rows, certifications)
3. **Structured verbatim** — one clean line per calendar row:
   `Class 5 | Date: 9/9 | Topic: … | Required Reading: … | Homework: …`
4. Exam/review lines merged from table rows + plain-text grep (exams often sit
   outside table cells)
5. Grading scale → points total; A threshold = N/A if not in document

**Expected quality:** ~7/10 after table extraction (was ~4/10 with grep-only).

See [reference.md](reference.md) for past errors and quality checks.

## Quality review (Step 2)

Review script output per category:

```
Sleep Paper: 6 sections, 5783 chars verbatim       # full syllabus — good
Homework: 2 sections, 2173 chars verbatim          # calendar — good if rows are clean
LinkedIn Learning: 2 sections, 632 chars verbatim  # calendar cert — short is OK if source is short
```

**Red flags (calendar PDFs):**

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Verbatim starts mid-word (`ked In Learning`) | Grep-window fallback, no table JSON | Re-run; check `extract_text` embeds `CALENDAR_TABLE_JSON` |
| Unrelated categories in one PDF (Stukent in Midterm) | 200-char context windows | Table path should be active; verify embedded JSON |
| Huge verbatim (3000+ chars) for 75-pt cert | Alias grep pulling whole calendar | Table path + category-specific row filter |
| 0 sections / <200 chars | Missing Assignments block or empty table | Inspect source formatting |

**Red flags (full syllabi):**

| Symptom | Fix |
|---------|-----|
| 0 sections | TOC duplicate Assignments block — check `find_assignments_block()` |
| Extra Credit pulls wrong block | Dedicated block pattern needs tuning |

Do **not** manually author `sections` or `extracted_text` unless auto-extract
failed and you are patching a known gap.

### Manual steps the agent still provides

- `--class-code`, `--class-name`, `--instructor`, `--term` (from syllabus header)
- `--link-base` URL for hosted PDF links (required for standalone xlsx download)

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
| `extract_text.py` | Syllabus file → plain text + calendar table JSON |
| `auto_dissect.py` | Plain text → JSON (syllabus grep or calendar tables) |
| `build_workbook.py` | JSON → Excel + PDFs |
| `dissect_syllabus.py` | All three in one command |
| `generate_pdfs.py` | PDF rendering (called by build_workbook) |

See [reference.md](reference.md) for JSON schema and calendar lessons learned.
