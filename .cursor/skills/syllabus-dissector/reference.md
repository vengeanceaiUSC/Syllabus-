# Syllabus Dissector — Reference

## Automatic extraction (primary workflow)

The agent runs `dissect_syllabus.py` or `auto_dissect.py` — **not** hand-written JSON.

## Path A: Full syllabus (`auto_dissect.py`)

Per category:

1. Parse **Assignments** block → category names + weights
2. Build **search aliases** (e.g. Sleep Paper → `paper 1`, `hist 103 paper 1`)
3. **Grep** every paragraph in the full syllabus text
4. **Capture** dedicated regions (study guides, prompt pages, Extra Credit block)
5. **Structure** into sections via heading heuristics
6. **Concatenate** all matches into `extracted_text` (verbatim, separated by `---`)

## Path B: Course Calendar (`extract_text.py` + `auto_dissect.py`)

For PDF schedules with table columns (Class / Date / Topic / Reading / Homework):

### Step 1 — Table extraction (`extract_text.py`)

`pdfplumber` reads table cells and embeds JSON in the extracted text:

```
=== CALENDAR_TABLE_JSON ===
[{"class":"5","date_mon":"","date_wed":"9/9","topic":"...","reading":"Chapter 3","homework":"2-29, 2-30, 2-40 / 15 Points"}, ...]
=== END CALENDAR_TABLE ===
```

### Step 2 — Category detection (`auto_dissect.py`)

When no Assignments block exists but `Course Calendar` is present:

| Category | Detection |
|----------|-----------|
| Midterm 1/2, Final Exam | `Midterm N: 250 Points` / `Final Exam: 250 Points` |
| LinkedIn / Stukent | Bullet or footer lines with 75 Points |
| Homework | Table rows with problem numbers + 10/15 Points |

### Step 3 — Structured verbatim (per category)

Each PDF gets clean rows with ISO due dates:

```
Class 7 | Due: 2026-09-16 (8:00 am) | Topic: Activity Based Costing | Required Reading: Chapter 5 | Homework: 3-24, 3-28, 3-32; 15 Points
```

Certifications are **split** (not combined):

```
Class 9 | Mentioned: 2026-09-23 (in-class announcement) | Linked In Learning Excel - 75 Points
Class 2 | Due: 2026-12-02 (11:59 PM) | Linked In Learning Excel Certification
```

Final exam is **one merged block**:

```
Final Exam: 250 Points | Wednesday, December 16th, 8:00 AM-10:00 AM PST | ISO: 2026-12-16 | Chapters 10, 11, 13, 14a
```

### Step 4 — Optional supplement syllabus

Pass `--supplement full-syllabus.pdf` to merge prose instructions (rubrics, submission
rules) into cert/homework PDFs via grep.

### Calendar section headings

| Section | Contents |
|---------|----------|
| Exam | Point value, chapters, date/time |
| Review & Practice | Catchup sessions, practice questions posted |
| Homework Assignments (by class date) | One bullet per graded problem set |
| Assignment Details | Certification mentions |
| Due Date & Submission | 11:59 PM footer dates |
| Calendar Footnotes | Appendix / prerequisite notes |

---

## Past errors (BUAD-281) — do not repeat

These caused **~4/10 verbatim quality** before the table-path fix:

| Error | What happened | Fix |
|-------|---------------|-----|
| **Grep-only on table PDFs** | `page.extract_text()` merges columns → run-on garbage | Parse PDF **tables** first |
| **200-char context windows** | `_context_line()` pulled unrelated rows into every category | One row = one verbatim line from table JSON |
| **Alias grep on short tokens** | `linkedin` matched anywhere → 3000-char noisy PDFs | Category-specific row filters |
| **Midterm review bleed** | Midterm 1 PDF included Stukent/LinkedIn from adjacent rows | Date-scoped review rows per exam |
| **Homework skip logic too broad** | Skipped rows if "midterm" appeared anywhere in 220-char window | Match exam/cert only on same line; require `\d-\d+` problem refs |
| **Truncated fragments** | `"Cost volume profit ana"`, `"ked In Learning Excel"` | Table cells preserve full cell text |
| **No structured sections** | Only "Overview" + "Calendar Entries" blobs | Exam / Homework / Footnotes sections |

---

## JSON schema (auto-generated)

```jsonc
{
  "class": { "code": "BUAD-281", "name": "...", "instructor": "...", "term": "..." },
  "grading_scale": {
    "a_threshold": "N/A",
    "raw_scale": "Total graded points in calendar: 1055 (letter scale not in document)",
    "scale_type": "points"
  },
  "categories": [{
    "name": "Homework",
    "weight": 155,
    "weight_unit": "points",
    "start_date": "",
    "due_date": "",
    "is_group_project": false,
    "sections": {
      "Homework Assignments (by class date)": [
        "Class 5 | Date: 9/9 | Topic: ... | Homework (due 8:00 am): 2-29, 2-30, 2-40; 15 Points"
      ],
      "Calendar Footnotes": ["Unless specifically Identified, Chapter Appendices ARE NOT included..."]
    },
    "extracted_text": "Class 5 | Date: 9/9 | ...\n\nClass 7 | ..."
  }]
}
```

## Category detection (full syllabus)

Looks for the **real** Assignments section (skips TOC duplicates) with lines like:

- `Discussion Section – 15%`
- `Sleep Paper -20%`
- `Extra Credit` (unweighted, appended if present anywhere in syllabus)

Supports `-`, en-dash (`\u2013`), and `%` / `pts` / `points`.

## Output layout

```
output/
  syllabi.xlsx
  documents/*.pdf
  buad281.json          # optional --keep-json
```

Excel **Open PDF** uses hosted URLs via `--link-base` (standalone download works).

## Limitations

- Cannot extract text **inside** attached Word/PDF files referenced by the syllabus
- Course calendars rarely include rubrics — PDFs only contain what the calendar states
- PDFs without extractable tables fall back to grep (lower quality)
- Campus-event extra credit (announced later) only captures what the syllabus states
- Unusual Assignments formatting may need alias tweaks in `auto_dissect.py`

## Quality rubric (1–10)

| Score | Full syllabus | Course calendar |
|-------|---------------|-----------------|
| 8–10 | Prompts, hints, format, due lines, study guides | Clean row-per-assignment, exam chapters/dates, footnotes |
| 5–7 | Most content present, some grep noise | Key facts present, minor cross-contamination |
| 1–4 | Missing blocks or mostly TOC noise | Garbled fragments, unrelated rows, mid-word cuts |
