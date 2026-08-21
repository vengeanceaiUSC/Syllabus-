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
3. **Assignment details** — start date (only when syllabus-verified), due date, group-project flag
4. **PDF documents** — one per category; structured sections + verbatim extract
5. **Excel hyperlinks** — **Open PDF** opens hosted PDF in browser
6. **Sub-assignments** — indented schedule rows under each graded category. Sub-rows are **grouped by type** (Reading, then Homework, etc.) and sorted by date. Each sub-row uses:

| Column | Parent category row | Sub-row |
|--------|---------------------|---------|
| **Category** | Graded category name (bold) | Type label: **Reading**, **Homework**, **Assignment**, **Exam**, **Research**, **Certification** (color-coded, bold) |
| **Weight** | Bold, tinted cell (`20%` or `170 pts`) | *(empty)* |
| **Details** | Open PDF hyperlink | Assignment description (class session, week, Connect item, etc.) |

| Label | Use for |
|-------|---------|
| **Reading** | Weekly readings, section readings, textbook/chapter prep, lecture topics, calendar required reading (paired before Homework on same due date) |
| **Homework** | Connect self-assessments, problem sets, quizzes, primary source activities, Sharpen |
| **Assignment** | Major graded work: papers, memos, proposals, outlines, presentations, peer eval |
| **Exam** | Midterm, final |
| **Research** | SONA / research participation milestones |
| **Certification** | LinkedIn / Stukent certs |

### Start dates — verified only

**Leave Start Date blank** unless the syllabus explicitly states when something begins. Do not infer starts from due dates, reading weeks, or grep noise.

| Verified start | Example |
|----------------|---------|
| Schedule block week range (start **before** end) | HIST-103 `Sep 1-4` → Reading start Sep 1, due Sep 4 |
| Explicit *opens* / *assigned* language | SONA *opens* Aug 24; team project explained 8/31 |
| Marshall `MARSHALL_INFERRED_STARTS` prose match | Schedule line matched, not deliverable due date |
| Cert announcement date (before submission due) | LinkedIn mentioned 9/23, due 12/2 |

| **Not** a start date | Action |
|---------------------|--------|
| Class session / due-by date only | Start Date **blank**, Due Date = session (BUAD-281, BUAD-304 Connect) |
| **Start Date = Due Date** on same row | **False detection** — clear Start Date |
| Due-only lines (e.g. Sleep Paper Sep 15) | Start Date blank |
| Earliest date from grep verbatim | Start Date blank |
| Pre-Aug 1 inferred dates | Start Date blank |

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
  --source-link-base "https://raw.githubusercontent.com/<owner>/<repo>/<branch>/output/sources" \
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

1. **`extract_text.py`** parses PDF **tables** via pdfplumber → `CALENDAR_TABLE_JSON`
2. **`auto_dissect.py`** detects `Course Calendar` → point-based categories
3. **Structured verbatim** per row with **ISO due dates** (`Due: 2026-09-09 (8:00 am)`)
4. **Split cert rows** — LinkedIn and Stukent get separate lines (not combined class-9 blob)
5. **Merged final exam block** — points + December 16 time + chapters in one Exam section
6. **Optional `--supplement`** — merge a full syllabus PDF for cert rubrics/instructions

```bash
python scripts/dissect_syllabus.py "Course_Calendar.pdf" \
  --class-code BUAD-281 \
  --supplement "Full_Syllabus.pdf" \   # optional — boosts cert detail toward 9/10
  ...
```

**Expected quality:** ~8/10 with calendar alone; ~9/10 if supplement syllabus provided.

### C. Marshall percentage syllabus + Course Schedule (e.g. BUAD-304)

Uses **Course Evaluation** (not an Assignments block) + a **Course Schedule** table:

1. **`auto_dissect.py`** detects `Course Evaluation` → percentage categories (drops aggregate parents like `Team Project 30%` when children sum to parent)
2. **Dedicated blocks** per category (Participation policy, Midterm blurb, Team Project, etc.) — avoids grep noise from the whole syllabus
3. **Course Schedule parser** extracts ISO due dates from deliverable lines (handles split PDF lines and OCR like `1 1/9` → `11/9`)
4. **`--research-guide`** merges the Marshall Research Participation Guide PDF into **Participation** (SONA milestones only — not Connect)
5. **Connect / Sharpen** → separate unweighted row **`Personal Assessments (Connect)`** (prep work, not part of Participation 15%)

**Participation 15%** (syllabus): Active Class Participation + Team Engagement + Research Studies (2). Connect self-assessments are **Personal assessments** for class prep — never route them under Participation or other graded categories.

```bash
python scripts/dissect_syllabus.py "BUAD304_Syllabus.pdf" \
  --class-code BUAD-304 \
  --research-guide "Research_Participation_Guide.pdf" \
  ...
```

**Fall 2026 research participation dates** (from guide — attach with `--research-guide`):

| Date | Milestone |
|------|-----------|
| Aug 24 | SONA registration opens (first day of classes) |
| Sep 11 | Prescreening questionnaire opens |
| Sep 25 | Setup deadline (registration, prescreening, employee contacts); study invitations begin after |
| Late October | Surveys sent to employee contacts (after fall recess) |
| Dec 4 | Deadline to complete 2.0 research credits (last day of classes) |

Contact: **mor.sona@marshall.usc.edu** (not the instructor). Guide: bit.ly/MOR-BUAD · SONA walkthrough: bit.ly/SONA-BUAD304

**Expected quality:** ~7–8/10 with syllabus + research guide; schedule dates populate Excel start/due columns.

See [reference.md](reference.md) for past errors and quality checks.

## Quality review (Step 2)

Review script output per category:

```
Sleep Paper: 6 sections, 5783 chars verbatim       # full syllabus — good
Homework: 2 sections, 2173 chars verbatim          # calendar — good if rows are clean
LinkedIn Learning: 2 sections, 632 chars verbatim  # calendar cert — short is OK if source is short
```

**Start-date sanity check** (run on `--keep-json` output after each class):

```bash
python3 - <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path))
bad = []
for cat in data["categories"]:
    for sub in cat.get("assignments") or []:
        s, d = sub.get("start_date") or "", sub.get("due_date") or ""
        if s and d and s == d:
            bad.append(f"{cat['name']}: {sub.get('name','')[:50]}")
    s, d = cat.get("start_date") or "", cat.get("due_date") or ""
    if s and d and s == d:
        bad.append(f"{cat['name']} (category row)")
if bad:
    print("FAIL start==due:", *bad, sep="\n  ")
    raise SystemExit(1)
print("OK: no start==due false detections")
PY
output/buad304.json
```

**Red flags (all sheets):**

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Start Date = Due Date on Homework/Reading | Copied session date into both columns | `strip_false_start_when_same_as_due()`; calendar/Connect parsers use due-only |
| Connect under Participation | Old `CONNECT_WEEK_CATEGORY` routing | **`Personal Assessments (Connect)`** section |

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

Commit `output/syllabi.xlsx`, `output/documents/*.pdf`, `output/sources/*-source.pdf`,
and optionally `output/*.json`. Give the user:

`https://raw.githubusercontent.com/<owner>/<repo>/<branch>/output/syllabi.xlsx`

Each class sheet includes a large **SEE HERE** link (row 2) to the original syllabus PDF.

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
| `dissect_syllabus.py` | All three in one command (`--supplement`, `--research-guide`) |
| `generate_pdfs.py` | PDF rendering (called by build_workbook) |

See [reference.md](reference.md) for JSON schema and calendar lessons learned.

Golden auto-generated examples:

- [examples/hist103.auto.json](examples/hist103.auto.json) — full syllabus (percentage weights)
- [examples/buad281.auto.json](examples/buad281.auto.json) — course calendar (point weights, ISO dates)
