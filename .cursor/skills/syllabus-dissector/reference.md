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

Two shapes depending on document type. Golden references:

- **Full syllabus:** [examples/hist103.auto.json](examples/hist103.auto.json)
- **Course calendar:** [examples/buad281.auto.json](examples/buad281.auto.json)

### Full syllabus (percentage weights)

```jsonc
{
  "class": { "code": "HIST-103", "name": "...", "instructor": "...", "term": "Fall 2026" },
  "grading_scale": {
    "a_threshold": "93% (100-93)",
    "raw_scale": "A: 100-93; ...",
    "scale_type": "percentage"
  },
  "categories": [{
    "name": "Sleep Paper",
    "weight": 20,
    "weight_unit": "percent",
    "start_date": "2026-09-04",
    "due_date": "2026-09-15",
    "is_group_project": false,
    "sections": {
      "Overview (Assignments section)": "...",
      "Prompts (pick ONE)": ["..."],
      "Helpful Hints": ["..."]
    },
    "extracted_text": "...\n\n---\n\n..."
  }]
}
```

### Course calendar (point weights, ISO dates)

```jsonc
{
  "class": { "code": "BUAD-281", "name": "Managerial Accounting", "instructor": "Braunegg", "term": "Fall 2026" },
  "grading_scale": {
    "a_threshold": "N/A",
    "raw_scale": "Total graded points in calendar: 1070 (letter scale not in document)",
    "scale_type": "points"
  },
  "categories": [
    {
      "name": "Homework",
      "weight": 170,
      "weight_unit": "points",
      "start_date": "2026-09-09",       // earliest homework ISO due
      "due_date": "2026-11-16",         // latest homework ISO due
      "is_group_project": false,
      "sections": {
        "Homework Assignments (by due date)": [
          "Class 5 | Due: 2026-09-09 (8:00 am) | Topic: Product Cost Accumulation: Job; Order Costing | Required Reading: Chapter 3 | Homework: 2-29, 2-30, 2-40; 15 Points",
          "Class 7 | Due: 2026-09-16 (8:00 am) | Topic: Activity Based Costing | Required Reading: Chapter 5- ONLY; LO 5.1, 2, 4 & 5 | Homework: 3-24, 3-28, 3-32; 15 Points"
        ],
        "Calendar Footnotes": [
          "Unless specifically Identified, Chapter Appendices ARE NOT included as Required Reading"
        ]
      },
      "extracted_text": "Class 5 | Due: 2026-09-09 (8:00 am) | ...\n\nClass 7 | Due: 2026-09-16 (8:00 am) | ..."
    },
    {
      "name": "LinkedIn Learning Excel Certification",
      "weight": 75,
      "weight_unit": "points",
      "start_date": "2026-09-23",       // in-class announcement
      "due_date": "2026-12-02",         // 11:59 PM footer deadline
      "sections": {
        "Assignment Details": [
          "Class 9 | Mentioned: 2026-09-23 (in-class announcement) | Linked In Learning Excel - 75 Points | Context: Introduced during this session; submit by 12/2 11:59 PM",
          "Class 2 | Due: 2026-12-02 (11:59 PM) | Linked In Learning Excel Certification | Context: Final submission deadline (calendar footer)"
        ],
        "Due Date & Submission": "Due: 2026-12-02 (11:59 PM) - Assignments listed below due by 11:59 PM"
      }
    },
    {
      "name": "Final Exam",
      "weight": 250,
      "weight_unit": "points",
      "due_date": "2026-12-16",
      "sections": {
        "Exam": "Final Exam: 250 Points | Final Exam; Wednesday,; December 16th; 8:00 AM -10:00 AM PST | ISO date: 2026-12-16 | Chapters 10, 11, 13, 14a | Knowledge of Cost Behavior (Chapter 6) & Contribution Margin (Chapter 7) are essential to cor-"
      }
    }
  ]
}
```

**Calendar row format:** `Class N | Due: YYYY-MM-DD (8:00 am) | Topic: ... | Required Reading: ... | Homework: ...`

**Cert split format:** announcement row (Class 9) + submission row (Class 2) — never one combined blob.

**With `--supplement`:** adds `"Additional Instructions (supplement syllabus)"` section when a full syllabus is merged.

## Path C: Marshall percentage syllabus + Course Schedule (BUAD-304)

When `Course Evaluation` is present (and document is **not** a point-based Course Calendar):

| Step | Behavior |
|------|----------|
| Category detection | `Participation 15%`, `Midterm Exam 15%`, etc.; drop parent rows when children sum to parent |
| Verbatim | Dedicated assignment blocks only (no whole-syllabus grep) |
| Due dates | Parse **Course Schedule** deliverable lines → ISO dates on each category row |
| Research guide | `--research-guide` PDF → Participation sections + `research_guide_url` in JSON |

### BUAD-304 Fall 2026 schedule dates (from syllabus Course Schedule)

| Category | Due date(s) |
|----------|-------------|
| Case Analysis Assignments | 2026-09-16 (Thomas Green memo), 2026-10-21 (SkillsForTomorrow memo) |
| Midterm Exam | 2026-10-14 |
| Proposal & Team Contract | 2026-09-28 |
| Team Project Paper | 2026-11-09 |
| Presentation | 2026-11-09 (slides before class) |
| Self & Peer Evaluation | 2026-11-18 |
| Final Reflection Paper | 2026-12-02 |
| Final Exam | 2026-12-09 |

### Research participation dates (from guide — use `--research-guide`)

| Date | Milestone |
|------|-----------|
| 2026-08-24 | SONA registration opens |
| 2026-09-11 | Prescreening questionnaire opens |
| 2026-09-25 | Setup deadline; study invitations after |
| ~2026-10-26 | Employee contact surveys sent (late October, after fall recess) |
| 2026-12-04 | Complete 2.0 research credits |

Participation PDF sections: `Research Participation Guide (key dates)`, `(contacts)`, `(quick reference excerpt)`.

### Sub-assignment type labels (Excel Category column)

Every sub-row under a graded category shows its **type in the Category column** (`notes` in JSON). The **Details** column holds the descriptive name (class session, week block, Connect item). Sub-rows are sorted: Reading → Homework → Assignment → Exam → Research → Certification, then by date.

Parent category **Weight** cells use bold 13pt text on a tinted background for visibility.

Implemented in `auto_dissect.py` (label assignment) and `build_workbook.py` (`sort_sub_assignments()`, color-coded Category labels).

**HIST-103 example:** Category = **Reading**, Details = `Week Sep 15-18: Renaissance`.

**BUAD-281 example:** under Homework (170 pts), Category = **Reading** for chapter prep rows, Category = **Homework** for problem-set rows.

**BUAD-304 example:** Category = **Homework** for Connect self-assessments; Category = **Assignment** for team deliverables.

### Which classes have true Homework sub-rows?

| Class | Homework rows | Reading rows | Notes |
|-------|---------------|--------------|-------|
| HIST-103 | 0 | 36 | Weekly schedule is all Reading |
| BUAD-281 | 12 | 25 | 12 graded problem sets |
| BUAD-304 | 14 | 0 | Connect self-assessments + Sharpen |

Only **BUAD-281** and **BUAD-304** have Homework sub-rows; HIST-103 has none (readings only).

### Start dates — verified only

Populate **Start Date** only when the syllabus explicitly states when work begins. Otherwise leave the cell **blank** (not `N/A`, not the due date).

**Verified sources:**
- HIST-103 / calendar **Reading** sub-rows: week range or class-session date from the schedule table
- BUAD-281 calendar rows: class date from `CALENDAR_TABLE_JSON`
- BUAD-304 Connect/Sharpen: explicit Connect window dates from syllabus (`8/24`–`12/20`)
- Marshall categories: `MARSHALL_INFERRED_STARTS` prose matches only (not earliest deliverable due)
- Research guide: milestones with `kind: start` (*opens*, *registration opens*)

**Never use as start:**
- Due-only lines (`Due September 15th`, `Sleep Paper Due`)
- Earliest date from `parse_dates_from_text()` grep
- `start = due` for single-day exams or papers
- Pre-Aug 1 dates (dropped to blank)

Implemented in `sanitize_start_date()`, `parse_dates_from_text()` (due-only), `marshall_dates_for_category()`, and HIST-103 due-line parsing.

**Example:** Sleep Paper → Start Date **blank**, Due Date **2026-09-15**.

### Marshall schedule parsing notes

- Join split lines: date on one line, `due` on the next
- OCR fix: `1 1/9` → `11/9` for presentation slides
- `is_group_project`: false for Participation (research credits are individual); true for team deliverables

---

## Past errors (BUAD-304) — do not repeat

| Error | What happened | Fix |
|-------|---------------|-----|
| **Whole-syllabus grep** | Every category got Course Evaluation + all assignment blurbs | Marshall mode: dedicated blocks + schedule lines only |
| **Missing schedule dates** | Course Schedule table JSON misparsed columns | Regex on prose schedule section with line-join heuristics |
| **Participation flagged group** | `team` in participation blurb triggered group flag | `infer_group_project()` excludes Participation |
| **Research credits missing** | Syllabus only says "see Brightspace" | Merge `--research-guide` PDF for SONA milestones |

---

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

examples/
  hist103.auto.json     # golden reference — full syllabus
  buad281.auto.json     # golden reference — course calendar (ISO dates)
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
