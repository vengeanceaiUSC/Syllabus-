#!/usr/bin/env python3
"""End-to-end syllabus pipeline: extract text -> auto-dissect -> workbook + PDFs.

Usage:
    python dissect_syllabus.py syllabus.pdf \\
        --class-code HIST-103 \\
        --class-name "The Emergence of Modern Europe" \\
        --instructor "Dr. Lindsay O'Neill" \\
        --term "Fall 2026" \\
        --workbook output/syllabi.xlsx \\
        --link-base "https://raw.githubusercontent.com/<owner>/<repo>/<branch>/output/documents" \\
        --source-link-base "https://raw.githubusercontent.com/<owner>/<repo>/<branch>/output/sources"
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from generate_pdfs import slugify  # noqa: E402


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Full syllabus dissection pipeline.")
    parser.add_argument("syllabus", help="Path to syllabus file (.pdf, .docx, etc.)")
    parser.add_argument("--class-code", default="", help="Optional if detectable from syllabus text/filename")
    parser.add_argument("--class-name", default="")
    parser.add_argument("--instructor", default="")
    parser.add_argument("--term", default="")
    parser.add_argument("--color", default="")
    parser.add_argument("--workbook", default="output/syllabi.xlsx")
    parser.add_argument("--link-base", default="", help="Hosted PDF base URL for Excel links")
    parser.add_argument(
        "--source-link-base",
        default="",
        help="Hosted URL base for original syllabus PDFs (SEE HERE row in Excel)",
    )
    parser.add_argument("--keep-json", default="", help="Save intermediate JSON to this path")
    parser.add_argument(
        "--supplement",
        default="",
        help="Optional full syllabus file to merge (adds instructions for calendar certs, etc.)",
    )
    parser.add_argument(
        "--research-guide",
        default="",
        help="Marshall research participation guide PDF (e.g. BUAD-304 SONA guide)",
    )
    parser.add_argument(
        "--as-of-date",
        default="",
        help="Overview focus month (YYYY-MM-DD). Defaults to system date.",
    )
    args = parser.parse_args()

    workbook_path = Path(args.workbook).expanduser()
    sources_dir = workbook_path.parent / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)

    source_slug = f"{slugify(args.class_code or Path(args.syllabus).stem.replace('-source', ''))}-source.pdf"
    source_dest = sources_dir / source_slug
    syllabus_path = Path(args.syllabus).expanduser().resolve()
    if syllabus_path != source_dest.resolve():
        shutil.copy2(syllabus_path, source_dest)
    source_url = ""
    if args.source_link_base:
        source_url = f"{args.source_link_base.rstrip('/')}/{source_slug}"

    with tempfile.TemporaryDirectory() as tmp:
        text_path = Path(tmp) / "syllabus.txt"
        json_path = Path(args.keep_json) if args.keep_json else Path(tmp) / "class.json"

        run([sys.executable, str(SCRIPTS / "extract_text.py"), args.syllabus, "--out", str(text_path)])

        if args.supplement:
            sup_path = Path(tmp) / "supplement.txt"
            run(
                [
                    sys.executable,
                    str(SCRIPTS / "extract_text.py"),
                    args.supplement,
                    "--out",
                    str(sup_path),
                ]
            )
            merged = (
                text_path.read_text(encoding="utf-8")
                + f"\n=== SUPPLEMENT_SYLLABUS ===\n"
                + sup_path.read_text(encoding="utf-8")
                + f"\n=== END SUPPLEMENT ===\n"
            )
            text_path.write_text(merged, encoding="utf-8")

        research_guide_url = ""
        if args.research_guide:
            rg_path = Path(tmp) / "research_guide.txt"
            run(
                [
                    sys.executable,
                    str(SCRIPTS / "extract_text.py"),
                    args.research_guide,
                    "--out",
                    str(rg_path),
                ]
            )
            rg_slug = f"{slugify(args.class_code or syllabus_path.stem.replace('-source', ''))}-research-guide.pdf"
            rg_dest = sources_dir / rg_slug
            rg_src = Path(args.research_guide).expanduser().resolve()
            if rg_src != rg_dest.resolve():
                shutil.copy2(rg_src, rg_dest)
            if args.source_link_base:
                research_guide_url = f"{args.source_link_base.rstrip('/')}/{rg_slug}"
            merged = (
                text_path.read_text(encoding="utf-8")
                + f"\n=== RESEARCH_GUIDE ===\n"
                + rg_path.read_text(encoding="utf-8")
                + f"\n=== END RESEARCH_GUIDE ===\n"
            )
            text_path.write_text(merged, encoding="utf-8")

        dissect_cmd = [
            sys.executable,
            str(SCRIPTS / "auto_dissect.py"),
            str(text_path),
            "--out",
            str(json_path),
            "--source-hint",
            syllabus_path.name,
        ]
        if args.class_code:
            dissect_cmd.extend(["--class-code", args.class_code])
        for flag, val in [
            ("--class-name", args.class_name),
            ("--instructor", args.instructor),
            ("--term", args.term),
            ("--color", args.color),
        ]:
            if val:
                dissect_cmd.extend([flag, val])
        run(dissect_cmd)

        if source_url:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            data.setdefault("class", {})["source_url"] = source_url
            if research_guide_url:
                data["class"]["research_guide_url"] = research_guide_url
            json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        build_cmd = [
            sys.executable,
            str(SCRIPTS / "build_workbook.py"),
            str(json_path),
            "--workbook",
            str(workbook_path),
        ]
        if args.link_base:
            build_cmd.extend(["--link-base", args.link_base])
        if args.as_of_date:
            build_cmd.extend(["--as-of-date", args.as_of_date])
        run(build_cmd)

    print(f"\nDone. Workbook: {workbook_path}")
    if source_url:
        print(f"Source PDF: {source_dest}")
    if args.research_guide:
        print(f"Research guide PDF: {rg_dest}")
    if args.keep_json:
        print(f"JSON: {args.keep_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
