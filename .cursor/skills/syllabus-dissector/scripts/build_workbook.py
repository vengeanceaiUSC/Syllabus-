#!/usr/bin/env python3
"""Append a dissected syllabus to a color-coded Excel workbook.

Reads a JSON description of one class (see schema below), then:
  * creates/updates a per-class worksheet (data is "separated by class"),
  * writes the grading scale and the exact threshold required for an 'A',
  * lists each grading category sorted by weight (highest first),
  * records start date, due date, and group-project flag per category,
  * writes granular per-assignment Markdown files and hyperlinks to them,
  * color-codes the sheet tab and rows based on the class.

Re-running for the same class replaces that class's sheet (idempotent), while
leaving the other classes' sheets untouched.

Usage:
    python build_workbook.py <class.json> --workbook syllabi.xlsx

Expected JSON schema:
{
  "class": {
    "code": "HIST-103",          # required, becomes the sheet name
    "name": "Modern Europe",
    "instructor": "Dr. O'Neill",
    "term": "Fall 2026",
    "color": "#1F77B4"           # optional hex; auto-assigned if omitted
  },
  "grading_scale": {
    "a_threshold": "93%",        # exact %/points needed for an A
    "raw_scale": "A: 100-93; A-: 92-90; ...",
    "scale_type": "percentage"   # "percentage" or "points"
  },
  "categories": [
    {
      "name": "Sleep Paper",
      "weight": 20,               # numeric; percent or points
      "weight_unit": "percent",   # "percent" or "points"
      "start_date": "2025-09-04",
      "due_date": "2025-09-15",
      "is_group_project": false,
      "details_md": "## Prompt...",  # granular markdown, saved to its own file
      "notes": ""
    }
  ]
}
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# Deterministic palette (distinct, readable base colors) for auto-assignment.
PALETTE = [
    "1F77B4",  # blue
    "D62728",  # red
    "2CA02C",  # green
    "9467BD",  # purple
    "FF7F0E",  # orange
    "17BECF",  # teal
    "8C564B",  # brown
    "E377C2",  # pink
]

HEADERS = [
    "Category",
    "Weight",
    "Start Date",
    "Due Date",
    "Group Project",
    "Details",
]

THIN = Side(style="thin", color="D9D9D9")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def clean_hex(value: str) -> str:
    """Normalize '#1f77b4' or '1F77B4' to 'RRGGBB' uppercase."""
    value = (value or "").lstrip("#").strip().upper()
    if len(value) == 8:  # strip alpha
        value = value[2:]
    if not re.fullmatch(r"[0-9A-F]{6}", value):
        raise ValueError(f"Invalid hex color: {value!r}")
    return value


def auto_color(class_code: str) -> str:
    idx = sum(ord(c) for c in class_code) % len(PALETTE)
    return PALETTE[idx]


def tint(hex_color: str, factor: float) -> str:
    """Lighten a color toward white. factor 0 -> same, 1 -> white."""
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)
    return f"{r:02X}{g:02X}{b:02X}"


def sanitize_sheet_name(name: str) -> str:
    # Excel sheet names: max 31 chars, cannot contain : \ / ? * [ ]
    name = re.sub(r"[:\\/?*\[\]]", "-", name).strip() or "Sheet"
    return name[:31]


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return slug or "item"


def weight_sort_key(cat: dict):
    """Sort by weight descending; unweighted (None) go last."""
    w = cat.get("weight")
    if w is None:
        return (1, 0.0)
    try:
        return (0, -float(w))
    except (TypeError, ValueError):
        return (1, 0.0)


def format_weight(cat: dict) -> str:
    w = cat.get("weight")
    if w is None:
        return "—"
    unit = (cat.get("weight_unit") or "percent").lower()
    if unit.startswith("point") or unit in {"pts", "pt"}:
        return f"{w:g} pts"
    return f"{w:g}%"


def write_detail_file(details_dir: Path, class_code: str, cat: dict) -> Path:
    slug = slugify(f"{class_code}-{cat.get('name', 'item')}")
    md_path = details_dir / f"{slug}.md"

    lines = [f"# {cat.get('name', 'Assignment')}", ""]
    lines.append(f"- **Class:** {class_code}")
    lines.append(f"- **Weight:** {format_weight(cat)}")
    if cat.get("start_date"):
        lines.append(f"- **Start date:** {cat['start_date']}")
    if cat.get("due_date"):
        lines.append(f"- **Due date:** {cat['due_date']}")
    lines.append(f"- **Group project:** {'Yes' if cat.get('is_group_project') else 'No'}")
    if cat.get("notes"):
        lines.append(f"- **Notes:** {cat['notes']}")
    lines.append("")
    details = (cat.get("details_md") or "").strip()
    if details:
        lines.append("## Details")
        lines.append("")
        lines.append(details)
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path


def get_or_replace_sheet(wb: Workbook, sheet_name: str):
    # Drop the default empty sheet openpyxl creates.
    if wb.sheetnames == ["Sheet"] and wb["Sheet"].max_row == 1 and wb["Sheet"].max_column == 1:
        if wb["Sheet"]["A1"].value is None:
            wb.remove(wb["Sheet"])
    if sheet_name in wb.sheetnames:
        wb.remove(wb[sheet_name])
    return wb.create_sheet(title=sheet_name)


def build(data: dict, workbook_path: Path) -> None:
    cls = data.get("class", {})
    class_code = str(cls.get("code") or cls.get("name") or "Class").strip()
    sheet_name = sanitize_sheet_name(class_code)

    base_color = clean_hex(cls["color"]) if cls.get("color") else auto_color(class_code)
    header_fill = PatternFill("solid", fgColor=base_color)
    band_light = PatternFill("solid", fgColor=tint(base_color, 0.85))
    band_lighter = PatternFill("solid", fgColor=tint(base_color, 0.93))
    title_font = Font(bold=True, size=14, color="FFFFFF")
    header_font = Font(bold=True, color="FFFFFF")
    label_font = Font(bold=True)

    details_dir = workbook_path.parent / "details"
    details_dir.mkdir(parents=True, exist_ok=True)

    if workbook_path.exists():
        wb = load_workbook(str(workbook_path))
    else:
        wb = Workbook()

    ws = get_or_replace_sheet(wb, sheet_name)
    ws.sheet_properties.tabColor = base_color

    ncols = len(HEADERS)
    last_col = get_column_letter(ncols)

    # --- Title / metadata block ---
    ws.merge_cells(f"A1:{last_col}1")
    title = ws["A1"]
    class_name = cls.get("name")
    title.value = f"{class_code}" + (f" — {class_name}" if class_name else "")
    title.font = title_font
    title.fill = header_fill
    title.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 22

    row = 2
    meta = []
    if cls.get("instructor"):
        meta.append(("Instructor", cls["instructor"]))
    if cls.get("term"):
        meta.append(("Term", cls["term"]))
    for label, value in meta:
        ws.cell(row=row, column=1, value=label).font = label_font
        ws.cell(row=row, column=2, value=value)
        row += 1

    scale = data.get("grading_scale", {})
    ws.cell(row=row, column=1, value="Required for an A").font = label_font
    a_cell = ws.cell(row=row, column=2, value=scale.get("a_threshold", "N/A"))
    a_cell.font = Font(bold=True, color="C00000")
    row += 1
    if scale.get("raw_scale"):
        ws.cell(row=row, column=1, value="Grading scale").font = label_font
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=ncols)
        ws.cell(row=row, column=2, value=scale["raw_scale"])
        row += 1

    row += 1  # spacer

    # --- Header row ---
    header_row = row
    for col, name in enumerate(HEADERS, start=1):
        c = ws.cell(row=header_row, column=col, value=name)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = BORDER
    row += 1

    # --- Data rows (sorted by weight desc) ---
    categories = sorted(data.get("categories", []), key=weight_sort_key)
    for i, cat in enumerate(categories):
        md_path = write_detail_file(details_dir, class_code, cat)
        rel = md_path.relative_to(workbook_path.parent).as_posix()

        values = [
            cat.get("name", ""),
            format_weight(cat),
            cat.get("start_date") or "",
            cat.get("due_date") or "",
            "Yes" if cat.get("is_group_project") else "No",
            "Open details",
        ]
        band = band_light if i % 2 == 0 else band_lighter
        for col, value in enumerate(values, start=1):
            c = ws.cell(row=row, column=col, value=value)
            c.fill = band
            c.border = BORDER
            c.alignment = Alignment(vertical="center", wrap_text=(col == 1))
        link_cell = ws.cell(row=row, column=ncols)
        link_cell.hyperlink = rel
        link_cell.font = Font(color="0563C1", underline="single")
        row += 1

    # --- Total weight row ---
    total = 0.0
    has_weight = False
    for cat in categories:
        try:
            total += float(cat.get("weight"))
            has_weight = True
        except (TypeError, ValueError):
            pass
    if has_weight:
        tc = ws.cell(row=row, column=1, value="Total")
        tc.font = label_font
        unit = "%" if not str(scale.get("scale_type", "")).lower().startswith("point") else " pts"
        ws.cell(row=row, column=2, value=f"{total:g}{unit}").font = label_font

    # --- Column widths & freeze ---
    widths = [30, 12, 14, 14, 14, 16]
    for col, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)

    wb.save(str(workbook_path))
    print(f"Updated sheet '{sheet_name}' in {workbook_path}")
    print(f"Wrote {len(categories)} detail file(s) to {details_dir}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build/append a syllabus workbook.")
    parser.add_argument("json", help="Path to the class JSON file")
    parser.add_argument(
        "--workbook",
        default="syllabi.xlsx",
        help="Path to the Excel workbook (created if missing)",
    )
    args = parser.parse_args()

    data = json.loads(Path(args.json).expanduser().read_text(encoding="utf-8"))
    build(data, Path(args.workbook).expanduser())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
