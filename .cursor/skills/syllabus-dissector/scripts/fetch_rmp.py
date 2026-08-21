#!/usr/bin/env python3
"""Fetch Rate My Professors stats for USC instructors and write output/rmp.json.

Usage:
    python fetch_rmp.py --professor-id 1642149 --class-code HIST-103 --instructor "Lindsay O'Neill"
    python fetch_rmp.py --refresh-all   # uses built-in professor IDs for known classes
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

KNOWN_PROFESSORS: dict[str, dict] = {
    "HIST-103": {
        "instructor": "Lindsay O'Neill",
        "professor_id": "1642149",
        "consensus": (
            "Passionate, engaging lectures (multimedia, humor); discussion- and reading-heavy. "
            "Mixed on grading strictness; occasional low-weight pop quizzes."
        ),
    },
    "BUAD-281": {
        "instructor": "George Braunegg",
        "professor_id": "2462056",
        "consensus": (
            "Warm, funny, and supportive outside class; strong career advice. "
            "Lectures and exams are polarizing—some find exams misaligned with material."
        ),
    },
    "BUAD-304": {
        "instructor": "Christine El Haddad",
        "professor_id": "1808480",
        "consensus": (
            "Highly supportive and organized; standout Marshall teacher (negotiations, OB). "
            "Caring environment with group work and generous extra credit."
        ),
    },
}

USER_AGENT = "Mozilla/5.0 (compatible; syllabus-dissector/1.0)"


def fetch_rmp_page(professor_id: str) -> str:
    url = f"https://www.ratemyprofessors.com/professor/{professor_id}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_rmp_html(html: str) -> dict:
    """Best-effort parse of RMP professor page."""
    quality_m = re.search(
        r"Overall Quality Based on (\d+) ratings[\s\S]{0,400}?(\d+\.\d+)\s*/\s*5",
        html,
        re.I,
    )
    if not quality_m:
        quality_m = re.search(r"(\d+\.\d+)\s*/\s*5[\s\S]{0,200}?Overall Quality", html, re.I)
    num_ratings = int(quality_m.group(1)) if quality_m and quality_m.lastindex >= 1 else None
    quality = float(quality_m.group(2 if quality_m and quality_m.lastindex >= 2 else 1)) if quality_m else None

    diff_m = re.search(r"Level of Difficulty[\s\S]{0,120}?(\d+\.\d+)", html, re.I)
    difficulty = float(diff_m.group(1)) if diff_m else None

    again_m = re.search(r"(\d+)%[\s\S]{0,80}?Would take again", html, re.I)
    if not again_m:
        again_m = re.search(r"Would take again[\s\S]{0,80}?(\d+)%", html, re.I)
    would_take_again = float(again_m.group(1)) if again_m else None

    if quality is None:
        raise ValueError("Could not parse RMP quality rating from page")
    return {
        "quality": quality,
        "difficulty": difficulty,
        "would_take_again_pct": would_take_again,
        "num_ratings": num_ratings,
    }


def build_entry(
    class_code: str,
    instructor: str,
    professor_id: str,
    consensus: str,
    stats: dict,
) -> dict:
    return {
        "instructor": instructor,
        "quality": stats["quality"],
        "difficulty": stats.get("difficulty"),
        "would_take_again_pct": stats.get("would_take_again_pct"),
        "num_ratings": stats.get("num_ratings"),
        "consensus": consensus,
        "url": f"https://www.ratemyprofessors.com/professor/{professor_id}",
        "source": "Rate My Professors",
        "as_of": date.today().isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch RMP ratings for syllabus classes.")
    parser.add_argument("--professor-id", default="")
    parser.add_argument("--class-code", default="")
    parser.add_argument("--instructor", default="")
    parser.add_argument("--consensus", default="")
    parser.add_argument("--out", default="output/rmp.json")
    parser.add_argument("--refresh-all", action="store_true")
    args = parser.parse_args()

    out_path = Path(args.out).expanduser()
    existing: dict = {}
    if out_path.exists():
        existing = json.loads(out_path.read_text(encoding="utf-8"))

    if args.refresh_all:
        for code, info in KNOWN_PROFESSORS.items():
            html = fetch_rmp_page(info["professor_id"])
            stats = parse_rmp_html(html)
            existing[code] = build_entry(
                code,
                info["instructor"],
                info["professor_id"],
                info["consensus"],
                stats,
            )
            print(f"{code}: quality={stats['quality']} difficulty={stats.get('difficulty')} n={stats.get('num_ratings')}")
    elif args.professor_id and args.class_code and args.instructor:
        html = fetch_rmp_page(args.professor_id)
        stats = parse_rmp_html(html)
        existing[args.class_code] = build_entry(
            args.class_code,
            args.instructor,
            args.professor_id,
            args.consensus or "",
            stats,
        )
    else:
        parser.error("Use --refresh-all or pass --professor-id, --class-code, and --instructor")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
