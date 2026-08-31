#!/usr/bin/env python3
"""Generate a detailed PDF document for one syllabus assignment/category.

Uses ReportLab for reliable layout (no fpdf2 cursor/fragment bugs).

Usage:
    python generate_pdfs.py <class.json> --out-dir documents/
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ACCENT = colors.HexColor("#B41E1E")
MARGIN = 0.85 * inch  # equal left/right margins


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return slug or "item"


def format_weight(cat: dict) -> str:
    w = cat.get("weight")
    if w is None:
        return "Not graded / optional"
    unit = (cat.get("weight_unit") or "percent").lower()
    if unit.startswith("point") or unit in {"pts", "pt"}:
        return f"{w:g} points"
    return f"{w:g}%"


def esc(text: str) -> str:
    """Escape text for ReportLab Paragraph markup."""
    if not text:
        return ""
    text = str(text)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    replacements = {
        "\u2014": "-", "\u2013": "-",
        "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"',
        "\u2026": "...",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text


def build_styles():
    base = getSampleStyleSheet()
    content_w = letter[0] - 2 * MARGIN

    return {
        "content_w": content_w,
        "title": ParagraphStyle(
            "DocTitle",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=20,
            textColor=ACCENT,
            spaceAfter=6,
            alignment=TA_LEFT,
        ),
        "subtitle": ParagraphStyle(
            "DocSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            textColor=colors.HexColor("#555555"),
            spaceAfter=3,
            alignment=TA_LEFT,
        ),
        "section": ParagraphStyle(
            "SectionHead",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            textColor=colors.white,
            alignment=TA_LEFT,
            leftIndent=0,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            textColor=colors.HexColor("#222222"),
            spaceAfter=6,
            leading=14,
            alignment=TA_LEFT,
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            textColor=colors.HexColor("#222222"),
            leftIndent=14,
            bulletIndent=0,
            spaceAfter=4,
            leading=14,
            alignment=TA_LEFT,
        ),
        "extract": ParagraphStyle(
            "Extract",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=9,
            textColor=colors.HexColor("#444444"),
            spaceAfter=8,
            leading=13,
            alignment=TA_LEFT,
        ),
        "meta_label": ParagraphStyle(
            "MetaLabel",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            textColor=colors.HexColor("#555555"),
            alignment=TA_LEFT,
        ),
        "meta_value": ParagraphStyle(
            "MetaValue",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            textColor=colors.HexColor("#111111"),
            alignment=TA_LEFT,
        ),
    }


def section_bar(title: str, styles: dict) -> Table:
    w = styles["content_w"]
    t = Table(
        [[Paragraph(esc(title), styles["section"])]],
        colWidths=[w],
    )
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), ACCENT),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return t


def bullet_list(items: list[str], styles: dict) -> ListFlowable:
    flow = []
    for item in items:
        flow.append(ListItem(Paragraph(esc(item), styles["bullet"]), leftIndent=12))
    return ListFlowable(flow, bulletType="bullet", start="•", leftIndent=18)


def meta_table(rows: list[tuple[str, str]], styles: dict) -> Table:
    w = styles["content_w"]
    label_w = 1.35 * inch
    data = [
        [Paragraph(esc(l), styles["meta_label"]), Paragraph(esc(v), styles["meta_value"])]
        for l, v in rows
    ]
    t = Table(data, colWidths=[label_w, w - label_w])
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return t


def write_assignment_pdf(
    out_path: Path,
    class_code: str,
    class_name: str,
    instructor: str,
    term: str,
    cat: dict,
) -> Path:
    styles = build_styles()
    story = []

    # Title block
    story.append(Paragraph(esc(cat.get("name", "Assignment")), styles["title"]))
    subtitle = esc(class_code + (f"  |  {class_name}" if class_name else ""))
    story.append(Paragraph(subtitle, styles["subtitle"]))
    if instructor:
        story.append(Paragraph(f"Instructor: {esc(instructor)}", styles["subtitle"]))
    if term:
        story.append(Paragraph(f"Term: {esc(term)}", styles["subtitle"]))
    story.append(Spacer(1, 0.15 * inch))

    # Summary
    story.append(section_bar("Assignment Summary", styles))
    story.append(Spacer(1, 0.08 * inch))
    meta_rows = [("Grade weight:", format_weight(cat))]
    if cat.get("start_date"):
        meta_rows.append(("Start date:", cat["start_date"]))
    if cat.get("due_date"):
        meta_rows.append(("Due date:", cat["due_date"]))
    meta_rows.append(("Group project:", "Yes" if cat.get("is_group_project") else "No"))
    if cat.get("notes"):
        meta_rows.append(("Notes:", cat["notes"]))
    story.append(meta_table(meta_rows, styles))
    story.append(Spacer(1, 0.12 * inch))

    # Structured sections
    sections = cat.get("sections") or {}
    for heading, content in sections.items():
        story.append(section_bar(heading, styles))
        story.append(Spacer(1, 0.08 * inch))
        if isinstance(content, list):
            story.append(bullet_list([str(i) for i in content], styles))
        else:
            story.append(Paragraph(esc(str(content)), styles["body"]))
        story.append(Spacer(1, 0.1 * inch))

    if not sections:
        details = (cat.get("details_md") or "").strip()
        if details:
            story.append(section_bar("Details from Syllabus", styles))
            story.append(Spacer(1, 0.08 * inch))
            story.append(Paragraph(esc(details), styles["body"]))

    extracted = (cat.get("extracted_text") or "").strip()
    if extracted and not cat.get("omit_verbatim"):
        story.append(section_bar("Full Syllabus Extract", styles))
        story.append(Spacer(1, 0.08 * inch))
        for para in extracted.split("\n\n"):
            para = para.strip()
            if para:
                story.append(Paragraph(esc(para), styles["extract"]))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=letter,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title=esc(cat.get("name", "Assignment")),
        author=esc(instructor or class_code),
    )
    doc.build(story)
    return out_path


def generate_all(data: dict, out_dir: Path) -> list[Path]:
    cls = data.get("class", {})
    class_code = str(cls.get("code") or "Class").strip()
    class_name = cls.get("name") or ""
    instructor = cls.get("instructor") or ""
    term = cls.get("term") or ""

    paths: list[Path] = []
    for cat in data.get("categories", []):
        slug = slugify(f"{class_code}-{cat.get('name', 'item')}")
        pdf_path = out_dir / f"{slug}.pdf"
        write_assignment_pdf(pdf_path, class_code, class_name, instructor, term, cat)
        paths.append(pdf_path)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate assignment PDF documents.")
    parser.add_argument("json", help="Path to the class JSON file")
    parser.add_argument("--out-dir", default="documents")
    args = parser.parse_args()

    data = json.loads(Path(args.json).expanduser().read_text(encoding="utf-8"))
    paths = generate_all(data, Path(args.out_dir).expanduser())
    print(f"Wrote {len(paths)} PDF(s) to {args.out_dir}")
    for p in paths:
        print(f"  {p.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
