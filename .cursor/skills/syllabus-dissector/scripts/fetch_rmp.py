#!/usr/bin/env python3
"""Fetch Rate My Professors stats for USC instructors and write output/rmp.json.

Uses RMP's public GraphQL API for quality/difficulty and paginates ratings to
compute the average self-reported reviewer letter grade.

Usage:
    python fetch_rmp.py --refresh-all
    python fetch_rmp.py --professor-id 1642149 --class-code HIST-103 --instructor "Lindsay O'Neill"
"""
from __future__ import annotations

import argparse
import base64
import json
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path

GRAPHQL_URL = "https://www.ratemyprofessors.com/graphql"
GRAPHQL_AUTH = "dGVzdDp0ZXN0"  # public key embedded in RMP pages

GRADE_POINTS = {
    "A+": 4.0,
    "A": 4.0,
    "A-": 3.7,
    "B+": 3.3,
    "B": 3.0,
    "B-": 2.7,
    "C+": 2.3,
    "C": 2.0,
    "C-": 1.7,
    "D+": 1.3,
    "D": 1.0,
    "D-": 0.7,
    "F": 0.0,
}

TEACHER_QUERY = """
query TeacherRatingList($id: ID!, $count: Int!, $cursor: String) {
  node(id: $id) {
    ... on Teacher {
      legacyId
      numRatings
      avgRating
      avgDifficulty
      wouldTakeAgainPercentRounded
      ratings(first: $count, after: $cursor) {
        edges {
          node { grade }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""

KNOWN_PROFESSORS: dict[str, dict] = {
    "HIST-103": {
        "instructor": "Lindsay O'Neill",
        "professor_id": "1642149",
    },
    "BUAD-281": {
        "instructor": "George Braunegg",
        "professor_id": "2462056",
    },
    "BUAD-304": {
        "instructor": "Christine El Haddad",
        "professor_id": "1808480",
    },
    "ECON-351": {
        "instructor": "Alejandro Martínez-Marquina / João Ramos",
        "professor_id": "2880539",
    },
}


def teacher_node_id(legacy_id: str | int) -> str:
    return base64.b64encode(f"Teacher-{legacy_id}".encode()).decode()


def gpa_to_letter(gpa: float) -> str:
    for letter, pts in sorted(GRADE_POINTS.items(), key=lambda x: -x[1]):
        if gpa >= pts - 0.05:
            return letter
    return "F"


def graphql_request(query: str, variables: dict) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; syllabus-dissector/1.0)",
            "Authorization": f"Basic {GRAPHQL_AUTH}",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode())
    if body.get("errors"):
        raise RuntimeError(body["errors"])
    return body["data"]


def fetch_teacher_stats(professor_id: str | int) -> dict:
    node_id = teacher_node_id(professor_id)
    letter_grades: list[str] = []
    cursor = None
    meta: dict = {}
    while True:
        data = graphql_request(
            TEACHER_QUERY,
            {"id": node_id, "count": 100, "cursor": cursor},
        )
        node = data["node"]
        if not node:
            raise RuntimeError(f"Professor {professor_id} not found")
        if cursor is None:
            meta = {
                "quality": round(float(node["avgRating"]), 1),
                "difficulty": round(float(node["avgDifficulty"]), 1),
                "would_take_again_pct": round(float(node["wouldTakeAgainPercentRounded"]), 1),
                "num_ratings": int(node["numRatings"]),
            }
        for edge in node["ratings"]["edges"]:
            grade = (edge["node"].get("grade") or "").strip()
            if grade in GRADE_POINTS:
                letter_grades.append(grade)
        page = node["ratings"]["pageInfo"]
        if not page["hasNextPage"]:
            break
        cursor = page["endCursor"]
    if letter_grades:
        gpas = [GRADE_POINTS[g] for g in letter_grades]
        avg_gpa = sum(gpas) / len(gpas)
        meta["avg_grade_gpa"] = round(avg_gpa, 2)
        meta["avg_grade_letter"] = gpa_to_letter(avg_gpa)
        meta["grades_reported"] = len(letter_grades)
        meta["grade_distribution"] = dict(Counter(letter_grades).most_common())
    return meta


def build_entry(
    class_code: str,
    instructor: str,
    professor_id: str,
    consensus: str,
    stats: dict,
) -> dict:
    entry = {
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
    for key in ("avg_grade_gpa", "avg_grade_letter", "grades_reported", "grade_distribution"):
        if stats.get(key) is not None:
            entry[key] = stats[key]
    return entry


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
            stats = fetch_teacher_stats(info["professor_id"])
            consensus = (existing.get(code) or {}).get("consensus") or ""
            existing[code] = build_entry(
                code,
                info["instructor"],
                info["professor_id"],
                consensus,
                stats,
            )
            grade = stats.get("avg_grade_letter", "-")
            gpa = stats.get("avg_grade_gpa", "-")
            print(
                f"{code}: quality={stats['quality']} difficulty={stats.get('difficulty')} "
                f"avg_grade={grade} ({gpa}) n={stats.get('num_ratings')}"
            )
    elif args.professor_id and args.class_code and args.instructor:
        stats = fetch_teacher_stats(args.professor_id)
        existing[args.class_code] = build_entry(
            args.class_code,
            args.instructor,
            args.professor_id,
            args.consensus or (existing.get(args.class_code) or {}).get("consensus", ""),
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
