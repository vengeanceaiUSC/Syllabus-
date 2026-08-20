# Syllabus Dissector — JSON Reference

The `build_workbook.py` script consumes one JSON object describing a single
class. Point every class at the same `--workbook` so all classes accumulate in
one file (each on its own sheet).

## Full annotated schema

```jsonc
{
  "class": {
    "code": "HIST-103",           // REQUIRED. Sheet name (auto-truncated to 31 chars).
    "name": "Modern Europe",      // Optional long title shown in the header.
    "instructor": "Dr. O'Neill",  // Optional.
    "term": "Fall 2026",          // Optional; used to infer assignment years.
    "color": "#1F77B4"            // Optional hex. Omit to auto-assign a distinct color.
  },
  "grading_scale": {
    "a_threshold": "93% (100-93)",// Exact %/points needed for an 'A'. Shown in red.
    "raw_scale": "A: 100-93; ...",// Full scale text, copied verbatim.
    "scale_type": "percentage"    // "percentage" or "points".
  },
  "categories": [
    {
      "name": "Sleep Paper",       // REQUIRED.
      "weight": 20,                // Numeric weight, or null for ungraded/optional.
      "weight_unit": "percent",    // "percent" or "points".
      "start_date": "2025-09-04",  // ISO date, or "".
      "due_date": "2025-09-15",    // ISO date, or "".
      "is_group_project": false,   // true only when the syllabus says group/team.
      "details_md": "## Prompt...",// Granular Markdown -> saved to its own .md file.
      "notes": "Via Brightspace"   // Optional short note.
    }
  ]
}
```

## Behavior notes

- **Sorting:** rows are sorted by `weight` descending; `null` weights fall to the
  bottom.
- **Weight display:** `percent` renders as `20%`, `points` renders as `450 pts`.
- **Total row:** the sum of numeric weights is appended below the table.
- **Detail files:** written to `details/<class-slug>-<category-slug>.md` next to
  the workbook; the Details column hyperlinks to them with relative paths.
- **Idempotency:** re-running with the same `class.code` replaces that sheet only.
- **Colors:** the sheet tab and alternating row bands use the class color (a base
  color plus two light tints).

## Output layout

```
syllabi.xlsx
details/
  hist-103-sleep-paper.md
  hist-103-witchcraft-paper.md
  ...
```
