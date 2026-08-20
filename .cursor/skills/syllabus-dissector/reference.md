# Syllabus Dissector — Reference

## Automatic extraction (primary workflow)

The agent runs `dissect_syllabus.py` or `auto_dissect.py` — **not** hand-written JSON.

`auto_dissect.py` pipeline per category:

1. Parse **Assignments** block → category names + weights
2. Build **search aliases** (e.g. Sleep Paper → `paper 1`, `hist 103 paper 1`)
3. **Grep** every paragraph in the full syllabus text
4. **Capture** dedicated regions (study guides, prompt pages, Extra Credit block)
5. **Structure** into sections via heading heuristics
6. **Concatenate** all matches into `extracted_text` (verbatim, separated by `---`)

## JSON schema (auto-generated)

```jsonc
{
  "class": { "code": "HIST-103", "name": "...", "instructor": "...", "term": "..." },
  "grading_scale": {
    "a_threshold": "93% (100-93)",
    "raw_scale": "A: 100-93; ...",
    "scale_type": "percentage"
  },
  "categories": [{
    "name": "Sleep Paper",
    "weight": 20,
    "weight_unit": "percent",
    "start_date": "2025-09-04",   // inferred from matched text
    "due_date": "2025-09-15",
    "is_group_project": false,
    "sections": {                  // auto-structured from grep results
      "Overview (Assignments section)": "...",
      "Prompts (pick ONE)": ["...", "..."],
      "Helpful Hints": ["..."]
    },
    "extracted_text": "...\n\n---\n\n..."  // all grep hits, verbatim
  }]
}
```

## Category detection

Looks for the **real** Assignments section (skips TOC duplicates) with lines like:

- `Discussion Section – 15%`
- `Sleep Paper -20%`
- `Extra Credit` (unweighted, appended if present anywhere in syllabus)

Supports `-`, `–` (en-dash), and `%` / `pts` / `points`.

## Grep aliases (examples)

| Category | Also searches for |
|----------|-------------------|
| Sleep Paper | `paper 1`, `hist 103 paper 1` |
| Witchcraft Paper | `paper 2`, `witchcraft & daily life` |
| Mid-term | `midterm`, `midterm study guide` |
| Final Exam | `final study guide` |
| Extra Credit | `experiencing the past`, `extra points` |
| Identification Quizzes | `identification quiz`, `id quiz` |

## Dedicated block patterns

Long assignment-specific regions are captured even when spread across pages:

- `HIST 103 Paper 1: Sleep in the Early Modern Period` → full prompt block
- `Witchcraft & Daily Life Paper` → full prompt block
- `Hist 103: Midterm Study Guide` / `Final Study Guide`
- `Extra Credit` section through attachment list

## Output layout

```
output/
  syllabi.xlsx
  documents/*.pdf
  hist103.json          # optional --keep-json
```

Excel **Open PDF** uses hosted URLs via `--link-base` (standalone download works).

## Limitations

- Cannot extract text **inside** attached Word/PDF files referenced by the syllabus
- Campus-event extra credit (announced later) only captures what the syllabus states
- Unusual Assignments formatting may need alias tweaks in `auto_dissect.py`
