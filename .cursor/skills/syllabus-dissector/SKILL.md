---
name: syllabus-dissector
description: Analyze a class syllabus (PDF, Word, HTML, or text) and append it to a color-coded Excel workbook separated by class. Extracts graded categories with their weights (sorted highest first), the exact percentage/points required for an 'A', and each assignment's start date, due date, and group-project status; writes granular per-assignment Markdown files and hyperlinks to them from the workbook. Use when the user uploads or mentions a syllabus, or asks to dissect, parse, or track syllabi, assignments, grade weights, or due dates.
---

# Syllabus Dissector

Turn a syllabus file into a structured, color-coded Excel workbook (one sheet
per class) plus granular Markdown files for each assignment.

## What this produces

For each syllabus, the workbook gets a per-class sheet containing:

1. **Sorting & weighting** — every graded category with its grade percentage or
   point weight, sorted so the **highest-weighted items come first**.
2. **Grading scale** — the full scale and the **exact percentage/points required
   for an 'A'**, shown prominently near the top of the sheet.
3. **Assignment details** — **start date, due date, and a group-project flag**
   (Yes/No) for every category.
4. **Detailed files & links** — the granular details of each assignment saved to
   its own local `.md` file, with a **clickable hyperlink** from the workbook.
5. **Formatting** — each class gets its **own tab color and row shading** so
   classes are visually distinct.

## Workflow

Copy this checklist and track progress:

```
- [ ] Step 1: Extract the syllabus text
- [ ] Step 2: Structure the content into JSON
- [ ] Step 3: Build/append the workbook
- [ ] Step 4: Report results
```

### Step 1: Extract the syllabus text

Run the extractor. It handles `.pdf`, `.docx`, `.html`/`.htm`, `.txt`, `.md`.

```bash
python scripts/extract_text.py "<path-to-syllabus>" --out /tmp/syllabus.txt
```

Then read `/tmp/syllabus.txt`. If the file is a web page the user pasted, save
it to a `.txt` first and point the extractor at it.

### Step 2: Structure the content into JSON

Read the extracted text and produce a JSON file matching the schema below. This
is the intelligent part — you interpret the syllabus. Follow these rules:

- **Weight:** capture the numeric grade weight for each category (e.g. `20` for
  "Sleep Paper – 20%", `450` for a 450-point homework block). Set
  `weight_unit` to `"percent"` or `"points"`. Use `null` for ungraded/optional
  items (e.g. extra credit) — they sort to the bottom.
- **A threshold:** put the exact cutoff for an 'A' in `a_threshold` (e.g.
  `"93% (100-93)"` or `"900/1000 points"`). Copy the full scale into
  `raw_scale`. Set `scale_type` to `"percentage"` or `"points"`.
- **Dates:** use ISO `YYYY-MM-DD`. For `start_date`, use when work on the item
  begins/is assigned (or the term start if it is ongoing like participation);
  for `due_date`, use the submission/exam date. Infer the year from the term.
- **Group project:** set `is_group_project` to `true` only when the syllabus
  indicates group/team work; otherwise `false`.
- **Details:** put all granular specifics (prompts, page counts, rubric notes,
  submission method, exam format, readings) into `details_md` as Markdown. This
  becomes the linked `.md` file — be thorough.

Schema (see [reference.md](reference.md) for the full annotated version):

```json
{
  "class": {
    "code": "HIST-103",
    "name": "The Emergence of Modern Europe",
    "instructor": "Dr. Lindsay O'Neill",
    "term": "Fall 2026",
    "color": "#1F77B4"
  },
  "grading_scale": {
    "a_threshold": "93% (100-93)",
    "raw_scale": "A: 100-93; A-: 92-90; ...",
    "scale_type": "percentage"
  },
  "categories": [
    {
      "name": "Sleep Paper",
      "weight": 20,
      "weight_unit": "percent",
      "start_date": "2025-09-04",
      "due_date": "2025-09-15",
      "is_group_project": false,
      "details_md": "4-page paper using the Ekirch and Handley readings...",
      "notes": "Turned in via TA's Brightspace"
    }
  ]
}
```

Notes:
- `class.code` is required and becomes the sheet name (max 31 chars).
- `class.color` is optional — omit it and a distinct color is auto-assigned per
  class. Provide a hex value only if the user wants a specific color.

### Step 3: Build/append the workbook

```bash
python scripts/build_workbook.py /tmp/class.json --workbook "syllabi.xlsx"
```

- Categories are sorted by weight (descending) automatically.
- Detail `.md` files are written to a `details/` folder next to the workbook,
  and the "Details" column links to them with relative paths (keep the workbook
  and `details/` folder together when moving them).
- Re-running for the same `class.code` **replaces that class's sheet** (safe to
  re-run), while leaving other classes untouched. Point every class at the
  **same** `--workbook` so all four classes live in one file.

### Step 4: Report results

Tell the user which class sheet was added/updated, the total weight, the 'A'
threshold, and where the workbook and detail files live.

### Optional: export an openable HTML view

`.xlsx` files can't be previewed on GitHub and may not open on machines without
Excel. Produce a self-contained HTML copy (opens in any browser, keeps the
per-class colors and clickable detail links):

```bash
python scripts/export_html.py "syllabi.xlsx"   # writes syllabi.html next to it
```

Keep `syllabi.html` next to the `details/` folder so its links resolve.

## Requirements

Install once: `pip install -r requirements.txt`
(`openpyxl`, `pdfplumber`, `python-docx`, `beautifulsoup4`).
