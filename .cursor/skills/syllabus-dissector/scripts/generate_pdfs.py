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

# Layout constants (mm)
MARGIN = 20
LINE = 5.5
SECTION_GAP = 4
BULLET_INDENT = 6


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
    if not text:
        return ""
    replacements = {
        "\u2014": "-", "\u2013": "-",
        "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"',
        "\u2026": "...", "\u2190": "<-",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", errors="replace").decode("latin-1")


class AssignmentPDF(FPDF):
    def __init__(self, accent: tuple[int, int, int] = (180, 30, 30)):
        super().__init__()
        self.accent = accent

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(140, 140, 140)
        self.set_x(self.l_margin)
        self.cell(0, 8, safe_text(f"Page {self.page_no()}"), align="C")

    @property
    def body_w(self) -> float:
        return self.w - self.l_margin - self.r_margin


class PDFWriter:
    """Thin wrapper that always resets x before writing (avoids fpdf2 layout bugs)."""

    def __init__(self, pdf: AssignmentPDF):
        self.pdf = pdf

    def ln(self, h: float = LINE * 0.6) -> None:
        self.pdf.ln(h)

    def rule(self) -> None:
        self.pdf.set_x(self.pdf.l_margin)
        y = self.pdf.get_y()
        self.pdf.set_draw_color(220, 220, 220)
        self.pdf.line(self.pdf.l_margin, y, self.pdf.w - self.pdf.r_margin, y)
        self.ln(SECTION_GAP)

    def paragraph(self, text: str, size: int = 10, bold: bool = False) -> None:
        self.pdf.set_x(self.pdf.l_margin)
        self.pdf.set_font("Helvetica", "B" if bold else "", size)
        self.pdf.set_text_color(40, 40, 40)
        self.pdf.multi_cell(self.pdf.body_w, LINE, safe_text(text))
        self.ln(2)

    def bullet(self, text: str) -> None:
        self.pdf.set_x(self.pdf.l_margin)
        self.pdf.set_font("Helvetica", "", 10)
        self.pdf.set_text_color(40, 40, 40)
        x0 = self.pdf.l_margin
        self.pdf.set_x(x0)
        self.pdf.cell(BULLET_INDENT, LINE, "-")
        self.pdf.multi_cell(self.pdf.body_w - BULLET_INDENT, LINE, safe_text(text))
        self.ln(1)

    def section_title(self, title: str) -> None:
        self.ln(SECTION_GAP)
        self.pdf.set_x(self.pdf.l_margin)
        y = self.pdf.get_y()
        # Light accent bar behind heading
        self.pdf.set_fill_color(*self.pdf.accent)
        self.pdf.rect(self.pdf.l_margin, y, self.pdf.body_w, 8, style="F")
        self.pdf.set_xy(self.pdf.l_margin + 3, y + 1.5)
        self.pdf.set_font("Helvetica", "B", 11)
        self.pdf.set_text_color(255, 255, 255)
        self.pdf.cell(self.pdf.body_w - 6, 5, safe_text(title))
        self.pdf.set_y(y + 10)
        self.ln(2)

    def meta_row(self, label: str, value: str) -> None:
        self.pdf.set_x(self.pdf.l_margin)
        self.pdf.set_font("Helvetica", "B", 10)
        self.pdf.set_text_color(80, 80, 80)
        label_w = 36
        self.pdf.cell(label_w, LINE, safe_text(label))
        self.pdf.set_font("Helvetica", "", 10)
        self.pdf.set_text_color(30, 30, 30)
        remaining = self.pdf.body_w - label_w
        # Short values on one line; long values wrap beneath the label column.
        if len(value) < 70:
            self.pdf.cell(remaining, LINE, safe_text(value))
        else:
            self.pdf.multi_cell(remaining, LINE, safe_text(value))
        self.ln(2)


def write_assignment_pdf(
    out_path: Path,
    class_code: str,
    class_name: str,
    instructor: str,
    term: str,
    cat: dict,
) -> Path:
    pdf = AssignmentPDF()
    pdf.set_margins(MARGIN, MARGIN, MARGIN)
    pdf.set_auto_page_break(auto=True, margin=MARGIN)
    pdf.add_page()
    w = PDFWriter(pdf)

    # --- Title block ---
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(*pdf.accent)
    pdf.multi_cell(pdf.body_w, 10, safe_text(cat.get("name", "Assignment")))
    w.ln(2)

    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(90, 90, 90)
    subtitle = class_code + (f"  |  {class_name}" if class_name else "")
    pdf.multi_cell(pdf.body_w, 6, safe_text(subtitle))
    if instructor:
        w.ln(1)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(pdf.body_w, 6, safe_text(f"Instructor: {instructor}"))
    if term:
        w.ln(1)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(pdf.body_w, 6, safe_text(f"Term: {term}"))
    w.ln(4)
    w.rule()

    # --- Summary table ---
    w.section_title("Assignment Summary")
    w.meta_row("Grade weight:", format_weight(cat))
    if cat.get("start_date"):
        w.meta_row("Start date:", cat["start_date"])
    if cat.get("due_date"):
        w.meta_row("Due date:", cat["due_date"])
    w.meta_row("Group project:", "Yes" if cat.get("is_group_project") else "No")
    if cat.get("notes"):
        w.meta_row("Notes:", cat["notes"])

    # --- Structured sections ---
    sections = cat.get("sections") or {}
    for heading, content in sections.items():
        w.section_title(heading)
        if isinstance(content, list):
            for item in content:
                w.bullet(str(item))
        else:
            w.paragraph(str(content))
        w.ln(2)

    if not sections:
        details = (cat.get("details_md") or "").strip()
        if details:
            w.section_title("Details from Syllabus")
            w.paragraph(details)

    # --- Verbatim extract (smaller, at bottom) ---
    extracted = (cat.get("extracted_text") or "").strip()
    if extracted:
        w.section_title("Full Syllabus Extract")
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(70, 70, 70)
        for para in extracted.split("\n\n"):
            para = para.strip()
            if para:
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(pdf.body_w, 4.5, safe_text(para))
                w.ln(3)

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
