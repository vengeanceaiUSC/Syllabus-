#!/usr/bin/env python3
"""Append a dissected syllabus to a color-coded Excel workbook.

Reads a JSON description of one class (see schema below), then:
  * creates/updates a per-class worksheet (data is "separated by class"),
  * writes the grading scale and the exact threshold required for an 'A',
  * lists each grading category sorted by weight (highest first),
  * records start date, due date, and group-project flag per category,
  * generates a detailed PDF per assignment (all syllabus info extracted),
  * hyperlinks each row to its PDF document,
  * color-codes the sheet tab and rows based on the class.

Re-running for the same class replaces that class's sheet and PDFs (idempotent).

Usage:
    python build_workbook.py <class.json> --workbook syllabi.xlsx
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# Import PDF generator from sibling script
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_pdfs import generate_all, slugify  # noqa: E402

PALETTE = [
    "1F77B4", "D62728", "2CA02C", "9467BD",
    "FF7F0E", "17BECF", "8C564B", "E377C2",
]

HEADERS = [
    "Category", "Weight", "Start Date", "Due Date", "Group Project", "Details",
]

THIN = Side(style="thin", color="D9D9D9")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def clean_hex(value: str) -> str:
    value = (value or "").lstrip("#").strip().upper()
    if len(value) == 8:
        value = value[2:]
    if not re.fullmatch(r"[0-9A-F]{6}", value):
        raise ValueError(f"Invalid hex color: {value!r}")
    return value


def auto_color(class_code: str) -> str:
    return PALETTE[sum(ord(c) for c in class_code) % len(PALETTE)]


def tint(hex_color: str, factor: float) -> str:
    r, g, b = (int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)
    return f"{r:02X}{g:02X}{b:02X}"


def sanitize_sheet_name(name: str) -> str:
    name = re.sub(r"[:\\/?*\[\]]", "-", name).strip() or "Sheet"
    return name[:31]


def format_weight(cat: dict) -> str:
    w = cat.get("weight")
    if w is None:
        return "—"
    unit = (cat.get("weight_unit") or "percent").lower()
    if unit.startswith("point") or unit in {"pts", "pt"}:
        return f"{w:g} pts"
    return f"{w:g}%"


def weight_sort_key(cat: dict):
    w = cat.get("weight")
    if w is None:
        return (1, 0.0)
    try:
        return (0, -float(w))
    except (TypeError, ValueError):
        return (1, 0.0)


def remove_class_sheet(wb: Workbook, class_code: str) -> None:
    name = sanitize_sheet_name(class_code)
    if name in wb.sheetnames:
        wb.remove(wb[name])


def remove_old_detail_sheets(wb: Workbook) -> None:
    """Remove leftover detail tabs from an older workbook format."""
    for name in list(wb.sheetnames):
        if "-" in name and name not in {sanitize_sheet_name(n) for n in wb.sheetnames}:
            # detail sheets look like "HIST-103-Sleep Paper"
            parts = name.split("-", 1)
            if len(parts) == 2 and any(
                name.startswith(f"{sanitize_sheet_name(c)}-")
                for c in wb.sheetnames
                if "-" not in c or c == sanitize_sheet_name(c)
            ):
                pass  # handled below
    # Remove any sheet whose name starts with "<ClassCode>-" except we keep summary sheets
    summary = {n for n in wb.sheetnames if "-" not in n or n.count("-") == 0}
    # Summary sheets are like HIST-103 (one hyphen) - detail sheets have more content after
    to_remove = []
    for name in wb.sheetnames:
        for summary_name in wb.sheetnames:
            if name != summary_name and name.startswith(f"{summary_name}-"):
                to_remove.append(name)
    for name in to_remove:
        if name in wb.sheetnames:
            wb.remove(wb[name])


def remove_class_pdfs(docs_dir: Path, class_code: str) -> None:
    prefix = slugify(class_code) + "-"
    if docs_dir.exists():
        for f in docs_dir.glob("*.pdf"):
            if f.stem.startswith(prefix):
                f.unlink()


def remove_blank_template_sheet(wb: Workbook) -> None:
    if "Sheet" not in wb.sheetnames or len(wb.sheetnames) <= 1:
        return
    ws = wb["Sheet"]
    if ws.max_row == 1 and ws.max_column == 1 and ws["A1"].value is None:
        wb.remove(ws)


def default_template() -> Path:
    return Path(__file__).resolve().parent.parent / "templates" / "blank_template.xlsx"


def pdf_hyperlink(target: str, label: str = "Open PDF") -> str:
    """Excel formula that opens a URL or file path when clicked."""
    safe = target.replace('"', '""')
    return f'=HYPERLINK("{safe}","{label}")'


def build(
    data: dict,
    workbook_path: Path,
    template_path: Path | None = None,
    link_base: str | None = None,
) -> None:
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

    docs_dir = workbook_path.parent / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)

    if workbook_path.exists():
        wb = load_workbook(str(workbook_path))
    else:
        tmpl = template_path or default_template()
        wb = load_workbook(str(tmpl)) if tmpl.exists() else Workbook()

    remove_old_detail_sheets(wb)
    remove_class_sheet(wb, class_code)
    remove_class_pdfs(docs_dir, class_code)

    # Generate PDF documents (full extracted syllabus info per assignment)
    pdf_paths = generate_all(data, docs_dir)
    pdf_by_slug = {p.stem: p for p in pdf_paths}

    ws = wb.create_sheet(title=sheet_name)
    ws.sheet_properties.tabColor = base_color

    ncols = len(HEADERS)
    last_col = get_column_letter(ncols)

    ws.merge_cells(f"A1:{last_col}1")
    title = ws["A1"]
    class_name = cls.get("name")
    title.value = f"{class_code}" + (f" — {class_name}" if class_name else "")
    title.font = title_font
    title.fill = header_fill
    title.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 22

    row = 2
    for label, value in [
        ("Instructor", cls.get("instructor")),
        ("Term", cls.get("term")),
    ]:
        if value:
            ws.cell(row=row, column=1, value=label).font = label_font
            ws.cell(row=row, column=2, value=value)
            row += 1

    scale = data.get("grading_scale", {})
    ws.cell(row=row, column=1, value="Required for an A").font = label_font
    ws.cell(row=row, column=2, value=scale.get("a_threshold", "N/A")).font = Font(
        bold=True, color="C00000"
    )
    row += 1
    if scale.get("raw_scale"):
        ws.cell(row=row, column=1, value="Grading scale").font = label_font
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=ncols)
        ws.cell(row=row, column=2, value=scale["raw_scale"])
        row += 1

    row += 1
    header_row = row
    for col, name in enumerate(HEADERS, start=1):
        c = ws.cell(row=header_row, column=col, value=name)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = BORDER
    row += 1

    categories = sorted(data.get("categories", []), key=weight_sort_key)
    for i, cat in enumerate(categories):
        slug = slugify(f"{class_code}-{cat.get('name', 'item')}")
        pdf_path = pdf_by_slug.get(slug)
        if pdf_path and link_base:
            # Hosted PDF URL — works from a standalone downloaded workbook (opens in browser).
            target = f"{link_base.rstrip('/')}/{slug}.pdf"
        elif pdf_path:
            target = f"documents/{slug}.pdf"
        else:
            target = ""

        values = [
            cat.get("name", ""),
            format_weight(cat),
            cat.get("start_date") or "",
            cat.get("due_date") or "",
            "Yes" if cat.get("is_group_project") else "No",
            pdf_hyperlink(target) if target else "",
        ]
        band = band_light if i % 2 == 0 else band_lighter
        for col, value in enumerate(values, start=1):
            c = ws.cell(row=row, column=col, value=value)
            c.fill = band
            c.border = BORDER
            c.alignment = Alignment(vertical="center", wrap_text=(col == 1))
            if col == ncols and target:
                c.font = Font(color="0563C1", underline="single")
        row += 1

    total = sum(float(c["weight"]) for c in categories if c.get("weight") is not None)
    if any(c.get("weight") is not None for c in categories):
        ws.cell(row=row, column=1, value="Total").font = label_font
        unit = "%" if not str(scale.get("scale_type", "")).lower().startswith("point") else " pts"
        ws.cell(row=row, column=2, value=f"{total:g}{unit}").font = label_font

    for col, width in enumerate([30, 12, 14, 14, 14, 16], start=1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)

    remove_blank_template_sheet(wb)
    wb.save(str(workbook_path))
    print(f"Updated sheet '{sheet_name}' in {workbook_path}")
    print(f"Wrote {len(pdf_paths)} PDF document(s) to {docs_dir}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build/append a syllabus workbook.")
    parser.add_argument("json", help="Path to the class JSON file")
    parser.add_argument("--workbook", default="syllabi.xlsx")
    parser.add_argument("--template", default=None)
    parser.add_argument(
        "--link-base",
        default=None,
        help=(
            "Base URL where PDFs are hosted (e.g. raw GitHub documents/ URL). "
            "When set, Open PDF links use full https:// URLs so a standalone "
            "downloaded workbook opens PDFs in the browser — no zip needed."
        ),
    )
    args = parser.parse_args()

    data = json.loads(Path(args.json).expanduser().read_text(encoding="utf-8"))
    template = Path(args.template).expanduser() if args.template else None
    build(data, Path(args.workbook).expanduser(), template, args.link_base)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
