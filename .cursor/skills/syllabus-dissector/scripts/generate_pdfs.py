#!/usr/bin/env python3
"""Generate a detailed PDF document for one syllabus assignment/category.

Each PDF contains every piece of information extracted from the syllabus about
that assignment: weight, dates, prompts, rubrics, readings, submission rules,
and any verbatim syllabus text the agent captured in the JSON.

Usage:
    python generate_pdfs.py <class.json> --out-dir documents/
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from fpdf import FPDF


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


def safe_text(text: str) -> str:
    """Replace characters fpdf2 core fonts cannot render."""
    if not text:
        return ""
    replacements = {
        "\u2014": "-",  # em dash
        "\u2013": "-",  # en dash
        "\u2018": "'",  # left single quote
        "\u2019": "'",  # right single quote
        "\u201c": '"',  # left double quote
        "\u201d": '"',  # right double quote
        "\u2026": "...",  # ellipsis
        "\u2190": "<-",  # arrow used in back links
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", errors="replace").decode("latin-1")


class AssignmentPDF(FPDF):
    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, safe_text(f"Page {self.page_no()}"), align="C")


def section_heading(pdf: AssignmentPDF, title: str, usable_w: float) -> None:
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(30, 30, 30)
    pdf.ln(4)
    pdf.multi_cell(usable_w, 7, safe_text(title))
    pdf.ln(1)


def body_text(pdf: AssignmentPDF, text: str, usable_w: float, bold: bool = False) -> None:
    pdf.set_font("Helvetica", "B" if bold else "", 10)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(usable_w, 5, safe_text(text))
    pdf.ln(1)


def bullet(pdf: AssignmentPDF, text: str, usable_w: float) -> None:
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(usable_w, 5, safe_text(f"  - {text}"))


def write_assignment_pdf(
    out_path: Path,
    class_code: str,
    class_name: str,
    instructor: str,
    term: str,
    cat: dict,
) -> Path:
    pdf = AssignmentPDF()
    pdf.set_margins(18, 18, 18)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    usable_w = pdf.w - pdf.l_margin - pdf.r_margin

    # Title block
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(180, 30, 30)
    pdf.multi_cell(usable_w, 10, safe_text(cat.get("name", "Assignment")))
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(60, 60, 60)
    subtitle = class_code
    if class_name:
        subtitle += f" — {class_name}"
    pdf.multi_cell(usable_w, 6, safe_text(subtitle))
    if instructor:
        pdf.ln(1)
        pdf.multi_cell(usable_w, 6, safe_text(f"Instructor: {instructor}"))
    if term:
        pdf.ln(1)
        pdf.multi_cell(usable_w, 6, safe_text(f"Term: {term}"))
    pdf.ln(6)

    # Summary metadata
    section_heading(pdf, "Assignment Summary", usable_w)
    bullet(pdf, f"Grade weight: {format_weight(cat)}", usable_w)
    if cat.get("start_date"):
        bullet(pdf, f"Start date: {cat['start_date']}", usable_w)
    if cat.get("due_date"):
        bullet(pdf, f"Due date: {cat['due_date']}", usable_w)
    bullet(pdf, f"Group project: {'Yes' if cat.get('is_group_project') else 'No'}", usable_w)
    if cat.get("notes"):
        bullet(pdf, f"Notes: {cat['notes']}", usable_w)

    sections = cat.get("sections") or {}
    if sections:
        for heading, content in sections.items():
            section_heading(pdf, heading, usable_w)
            if isinstance(content, list):
                for item in content:
                    bullet(pdf, str(item), usable_w)
            else:
                body_text(pdf, str(content), usable_w=usable_w)
    else:
        details = (cat.get("details_md") or "").strip()
        if details:
            section_heading(pdf, "Details from Syllabus", usable_w)
            body_text(pdf, details, usable_w=usable_w)

    extracted = (cat.get("extracted_text") or "").strip()
    if extracted:
        section_heading(pdf, "Full Syllabus Extract", usable_w)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(50, 50, 50)
        for para in extracted.split("\n\n"):
            para = para.strip()
            if para:
                pdf.multi_cell(usable_w, 4.5, safe_text(para))
                pdf.ln(2)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out_path))
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
        write_assignment_pdf(
            pdf_path, class_code, class_name, instructor, term, cat
        )
        paths.append(pdf_path)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate assignment PDF documents.")
    parser.add_argument("json", help="Path to the class JSON file")
    parser.add_argument(
        "--out-dir",
        default="documents",
        help="Directory for generated PDF files",
    )
    args = parser.parse_args()

    data = json.loads(Path(args.json).expanduser().read_text(encoding="utf-8"))
    paths = generate_all(data, Path(args.out_dir).expanduser())
    print(f"Wrote {len(paths)} PDF(s) to {args.out_dir}")
    for p in paths:
        print(f"  {p.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
