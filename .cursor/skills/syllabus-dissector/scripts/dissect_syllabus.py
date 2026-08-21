#!/usr/bin/env python3
"""End-to-end syllabus pipeline: extract text -> auto-dissect -> workbook + PDFs.

Usage:
    python dissect_syllabus.py syllabus.pdf \\
        --class-code HIST-103 \\
        --class-name "The Emergence of Modern Europe" \\
        --instructor "Dr. Lindsay O'Neill" \\
        --term "Fall 2026" \\
        --workbook output/syllabi.xlsx \\
        --link-base "https://raw.githubusercontent.com/<owner>/<repo>/<branch>/output/documents"
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Full syllabus dissection pipeline.")
    parser.add_argument("syllabus", help="Path to syllabus file (.pdf, .docx, etc.)")
    parser.add_argument("--class-code", required=True)
    parser.add_argument("--class-name", default="")
    parser.add_argument("--instructor", default="")
    parser.add_argument("--term", default="")
    parser.add_argument("--color", default="")
    parser.add_argument("--workbook", default="output/syllabi.xlsx")
    parser.add_argument("--link-base", default="", help="Hosted PDF base URL for Excel links")
    parser.add_argument("--keep-json", default="", help="Save intermediate JSON to this path")
    parser.add_argument(
        "--supplement",
        default="",
        help="Optional full syllabus file to merge (adds instructions for calendar certs, etc.)",
    )
    args = parser.parse_args()

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

        dissect_cmd = [
            sys.executable,
            str(SCRIPTS / "auto_dissect.py"),
            str(text_path),
            "--class-code",
            args.class_code,
            "--out",
            str(json_path),
        ]
        for flag, val in [
            ("--class-name", args.class_name),
            ("--instructor", args.instructor),
            ("--term", args.term),
            ("--color", args.color),
        ]:
            if val:
                dissect_cmd.extend([flag, val])
        run(dissect_cmd)

        build_cmd = [
            sys.executable,
            str(SCRIPTS / "build_workbook.py"),
            str(json_path),
            "--workbook",
            args.workbook,
        ]
        if args.link_base:
            build_cmd.extend(["--link-base", args.link_base])
        run(build_cmd)

    print(f"\nDone. Workbook: {args.workbook}")
    if args.keep_json:
        print(f"JSON: {args.keep_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
