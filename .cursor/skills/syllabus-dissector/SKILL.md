---
name: syllabus-dissector
description: Analyze a class syllabus (PDF, Word, HTML, or text) and append it to a color-coded Excel workbook separated by class. Extracts graded categories with weights (sorted highest first), the exact percentage/points required for an 'A', and each assignment's start date, due date, and group-project status; generates a detailed PDF document per assignment with all syllabus info extracted, and hyperlinks to those PDFs from the workbook. Use when the user uploads or mentions a syllabus, or asks to dissect, parse, or track syllabi, assignments, grade weights, or due dates.
---

# Syllabus Dissector

Turn a syllabus file into a structured, color-coded Excel workbook (one sheet
per class) plus a **PDF document per assignment** containing everything the
syllabus says about that item.

## What this produces

For each syllabus, the workbook gets a per-class sheet containing:

1. **Sorting & weighting** — every graded category with its grade percentage or
   point weight, sorted so the **highest-weighted items come first**.
2. **Grading scale** — the full scale and the **exact percentage/points required
   for an 'A'**, shown prominently near the top of the sheet.
3. **Assignment details** — **start date, due date, and a group-project flag**
   (Yes/No) for every category.
4. **Detailed PDF documents & links** — each assignment gets its own **PDF**
   with all extracted syllabus info (prompts, readings, rubrics, submission
   rules, verbatim text). The workbook's **"Open PDF"** column hyperlinks to it.
5. **Formatting** — each class gets its **own tab color and row shading**.

## Workflow

```
- [ ] Step 1: Extract the syllabus text
- [ ] Step 2: Structure the content into JSON (extract ALL info per assignment)
- [ ] Step 3: Build/append the workbook + PDF documents
- [ ] Step 4: Package and deliver (zip bundle so PDF links work)
```

### Step 1: Extract the syllabus text

```bash
python scripts/extract_text.py "<path-to-syllabus>" --out /tmp/syllabus.txt
```

Supports `.pdf`, `.docx`, `.html`/`.htm`, `.txt`, `.md`.

### Step 2: Structure the content into JSON

Read the extracted text and produce a JSON file. **Extract every piece of
information the syllabus contains about each assignment** — not just a summary.

For each category include:
- `sections` — structured headings → content (lists or paragraphs). Examples:
  `"Prompts (pick ONE)"`, `"Required Readings"`, `"Format Requirements"`,
  `"Helpful Hints"`, `"Exam Format"`, `"Due Date & Submission"`.
- `extracted_text` — verbatim or near-verbatim syllabus passages for that
  assignment (everything relevant from the PDF).
- Standard fields: `weight`, `weight_unit`, `start_date`, `due_date`,
  `is_group_project`, `notes`.

See [examples/hist103.json](examples/hist103.json) for a full example and
[reference.md](reference.md) for the schema.

### Step 3: Build/append the workbook

```bash
python scripts/build_workbook.py /tmp/class.json --workbook output/syllabi.xlsx \
  --link-base "https://raw.githubusercontent.com/<owner>/<repo>/<branch>/output/documents"
```

The `--link-base` flag is **required for published output**. It makes each
**"Open PDF"** cell a `HYPERLINK` formula pointing at the hosted PDF on GitHub.
The user downloads **only** `syllabi.xlsx`, clicks **Open PDF**, and the
document opens in their browser — no zip, no local `documents/` folder needed.

This creates/updates:
- `output/syllabi.xlsx` — one summary sheet per class
- `output/documents/*.pdf` — hosted on GitHub at the link-base URL

Re-running for the same `class.code` replaces that class's sheet and PDFs.

### Step 4: Publish

Commit and push `output/syllabi.xlsx` and `output/documents/*.pdf`. Give the
user the direct download link to **just the xlsx**:

`https://raw.githubusercontent.com/<owner>/<repo>/<branch>/output/syllabi.xlsx`

## Requirements

```bash
pip install -r requirements.txt
```

(`openpyxl`, `pdfplumber`, `python-docx`, `beautifulsoup4`, `reportlab`)
