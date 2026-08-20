#!/usr/bin/env python3
"""Extract plain text from a syllabus file.

Supports PDF (.pdf), Word (.docx), HTML (.html/.htm), and plain text
(.txt/.md). Prints the extracted text to stdout so the agent can read and
structure it.

Usage:
    python extract_text.py <path-to-syllabus>
    python extract_text.py <path-to-syllabus> --out extracted.txt
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def extract_pdf(path: Path) -> str:
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "pdfplumber is required for PDF files. Install with: pip install pdfplumber"
        ) from exc

    pages: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            pages.append(text)
            pages.append(f"\n-- {i} of {len(pdf.pages)} --\n")
    return "\n".join(pages)


def extract_docx(path: Path) -> str:
    try:
        import docx
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "python-docx is required for .docx files. Install with: pip install python-docx"
        ) from exc

    document = docx.Document(str(path))
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(parts)


def extract_html(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        # Fallback: crude tag stripping.
        import re

        return re.sub(r"<[^>]+>", " ", raw)

    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(separator="\n")


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(path)
    if suffix == ".docx":
        return extract_docx(path)
    if suffix in {".html", ".htm"}:
        return extract_html(path)
    if suffix in {".txt", ".md", ".text"}:
        return path.read_text(encoding="utf-8", errors="replace")
    raise SystemExit(
        f"Unsupported file type '{suffix}'. Supported: .pdf, .docx, .html, .htm, .txt, .md"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract text from a syllabus file.")
    parser.add_argument("path", help="Path to the syllabus file")
    parser.add_argument("--out", help="Optional path to write the extracted text")
    args = parser.parse_args()

    path = Path(args.path).expanduser()
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    text = extract_text(path)

    if args.out:
        Path(args.out).expanduser().write_text(text, encoding="utf-8")
        print(f"Wrote extracted text to {args.out} ({len(text)} chars)")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
