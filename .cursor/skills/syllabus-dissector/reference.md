# Syllabus Dissector — JSON Reference

## Full annotated schema

```jsonc
{
  "class": {
    "code": "HIST-103",           // REQUIRED. Sheet name (max 31 chars).
    "name": "Modern Europe",
    "instructor": "Dr. O'Neill",
    "term": "Fall 2026",
    "color": "#1F77B4"            // Optional hex; auto-assigned if omitted.
  },
  "grading_scale": {
    "a_threshold": "93% (100-93)",// Exact %/points for an 'A'.
    "raw_scale": "A: 100-93; ...",
    "scale_type": "percentage"    // "percentage" or "points".
  },
  "categories": [
    {
      "name": "Sleep Paper",
      "weight": 20,
      "weight_unit": "percent",
      "start_date": "2025-09-04",
      "due_date": "2025-09-15",
      "is_group_project": false,
      "notes": "Optional short note",
      "sections": {               // Structured extraction — headings → content.
        "Overview": "Paragraph text...",
        "Prompts (pick ONE)": ["Prompt 1...", "Prompt 2..."],
        "Required Readings": ["Reading 1...", "Reading 2..."],
        "Format Requirements": ["4 pages, double spaced", "..."]
      },
      "extracted_text": "Verbatim syllabus passages for this assignment..."
    }
  ]
}
```

## Extraction rules

The agent must read the **entire** syllabus PDF and, for each graded category
or assignment, capture **all** information the syllabus contains:

- Grade weight and category description
- Due dates, exam dates, locations, submission method
- Every prompt, question, or option the student must choose from
- Required readings tied to that assignment
- Format requirements (page count, citation style, thesis, etc.)
- Rubric hints, "helpful hints", restrictions (e.g. no internet)
- Related section/week schedule entries
- Verbatim text in `extracted_text` as a fallback archive

## Output layout

```
output/
  syllabi.xlsx              # Excel workbook (one summary sheet per class)
  documents/
    hist-103-sleep-paper.pdf
    hist-103-witchcraft-paper.pdf
    ...
  syllabus-bundle.zip       # Deliver this — keeps xlsx + PDFs together
```

Excel **"Open PDF"** links use relative paths (`documents/….pdf`). They work
when the user unzips the bundle and opens `syllabi.xlsx` from that folder.

## Behavior

- Categories sorted by weight descending; `null` weights last.
- Re-running the same `class.code` replaces its sheet and PDFs.
- Workbook created from `templates/blank_template.xlsx`.

See [examples/hist103.json](examples/hist103.json) for a complete real example.
