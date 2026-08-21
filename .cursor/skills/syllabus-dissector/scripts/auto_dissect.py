#!/usr/bin/env python3
"""Automatically dissect syllabus text into per-category JSON.

Scans the FULL extracted syllabus text for each graded category:
  1. Detects categories + weights from the Assignments section
  2. Parses the grading scale (A threshold)
  3. Grep-matches every paragraph/block that mentions each category
  4. Captures dedicated assignment sections (prompts, hints, due blocks)
  5. Infers dates and group-project flags from matched text
  6. Writes JSON ready for build_workbook.py

Usage:
    python auto_dissect.py syllabus.txt --class-code HIST-103 --out class.json
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path


PAGE_MARKER = re.compile(r"^--\s*\d+\s+of\s+\d+\s*--\s*$", re.M)
GRADING_SCALE = re.compile(
    r"Grading Scale\s*\n(.+?)(?:\n\n|\n[A-Z][a-z]{2}\s+\d|\Z)",
    re.S | re.I,
)
A_THRESHOLD = re.compile(
    r"A\s*:\s*(\d+)\s*[\-\u2013]\s*(\d+)|A\s*:\s*(\d+)\s*\+?",
    re.I,
)
MONTH_DATE = re.compile(
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(\d{4}))?",
    re.I,
)
GROUP_RE = re.compile(r"\b(group|team|partner|collaborative)\b", re.I)
SECTION_LABELS = [
    ("Prompts (pick ONE)", re.compile(r"^Prompts?\s*:?\s*(?:Pick ONE)?", re.I)),
    ("Helpful Hints", re.compile(r"^Helpful Hints?\s*:?", re.I)),
    ("Tips", re.compile(r"^Tips?\s+(?:for\s+)?", re.I)),
    ("Format Requirements", re.compile(r"^Paper\s*:", re.I)),
    ("Exam Format", re.compile(r"^Part\s+\d+", re.I)),
    ("Required Readings", re.compile(r"^(?:Required )?Readings?\s*(?:for|:)", re.I)),
    ("Due Date & Submission", re.compile(r"^Due\s+", re.I)),
    ("Restrictions", re.compile(r"^(?:Do not|Don't|Cannot|Prohibited)", re.I)),
]
NOISE = re.compile(
    r"^(module:|PDF document|Word Document|Image|\d+ bookmarked|Table of Contents)",
    re.I,
)


@dataclass
class Category:
    name: str
    weight: float | None = None
    weight_unit: str = "percent"
    aliases: list[str] = field(default_factory=list)
    assignment_blurb: str = ""


def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def make_aliases(name: str) -> list[str]:
    aliases = {name, name.lower()}
    low = name.lower()
    aliases.add(re.sub(r"[^\w\s]", "", low))
    aliases.add(re.sub(r"[\s\-\u2013]+", "", low))
    skip = {"the", "a", "an", "and", "or", "section", "exam", "paper", "extra", "final", "term"}
    for word in re.split(r"[\s\-\u2013]+", low):
        if len(word) > 3 and word not in skip:
            aliases.add(word)
    if "mid" in low and "term" in low:
        aliases.update({"midterm", "mid-term", "mid term", "midterm study guide"})
    if "final" in low and "exam" in low:
        aliases.update({"final exam", "final", "final study guide"})
    if "sleep" in low:
        aliases.update({"sleep paper", "paper 1", "hist 103 paper 1", "sleep in the early modern"})
    if "witchcraft" in low:
        aliases.update({"witchcraft paper", "witchcraft & daily life", "paper 2", "103.paper.2"})
    if "quiz" in low:
        aliases.update({"identification quiz", "identification quizzes", "id quiz"})
    if "discussion" in low:
        aliases.update({"discussion section", "participation", "primary source activity"})
    if "extra credit" in low:
        aliases.update({"experiencing the past", "extra credit", "extra points"})
    if "linkedin" in low:
        aliases.update({"linked in learning", "linkedin learning excel", "excel certification"})
    if "stukent" in low:
        aliases.update({"stukent simternship", "simternship"})
    if low == "homework":
        aliases.update({"points", "problem", "chapter"})
    return sorted(aliases, key=len, reverse=True)


COURSE_CALENDAR = re.compile(r"Course Calendar", re.I)
CALENDAR_TABLE_START = "=== CALENDAR_TABLE_JSON ==="
CALENDAR_TABLE_END = "=== END CALENDAR_TABLE ==="
MD_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})\b")
CAL_EXAM = re.compile(
    r"(Midterm \d+|Final Exam)\s*:\s*(\d+)\s*Points?",
    re.I,
)
CAL_BULLET = re.compile(
    r"[\u2022\*]\s*(.+?)\s*[\-\u2013]\s*(\d+)\s*Points?",
    re.I,
)
CAL_HOMEWORK = re.compile(
    r"(\d+)\s*[\-\u2013]?\s*Points?\b",
    re.I,
)


def is_course_calendar(text: str) -> bool:
    return bool(COURSE_CALENDAR.search(text))


def _context_line(text: str, pos: int, radius: int = 200) -> str:
    start = max(0, pos - radius)
    end = min(len(text), pos + radius)
    snippet = text[start:end]
    return re.sub(r"\s+", " ", snippet).strip()


def _normalize_calendar_name(raw: str) -> str:
    name = re.sub(r"\s+", " ", raw.strip())
    if re.search(r"linked\s*in\s*learning", name, re.I):
        return "LinkedIn Learning Excel Certification"
    if re.search(r"stukent", name, re.I):
        return "Stukent Simternship"
    return name


def _line_window(text: str, pos: int, extra_lines: int = 1) -> str:
    line_start = text.rfind("\n", 0, pos) + 1
    line_end = text.find("\n", pos)
    if line_end == -1:
        line_end = len(text)
    start = line_start
    for _ in range(extra_lines):
        prev = text.rfind("\n", 0, start - 1)
        if prev < 0:
            break
        start = prev + 1
    end = line_end
    for _ in range(extra_lines):
        nxt = text.find("\n", end + 1)
        if nxt == -1:
            end = len(text)
            break
        end = nxt
    return text[start:end]


def _is_exam_or_cert_points(text: str, m: re.Match) -> bool:
    own_line = re.sub(r"\s+", " ", _line_window(text, m.start(), extra_lines=0)).strip()
    pts = float(m.group(1))
    if re.search(rf"Midterm \d+:\s*{pts:g}\s*Points?", own_line, re.I):
        return True
    if re.search(rf"Final Exam:\s*{pts:g}\s*Points?", own_line, re.I):
        return True
    if pts >= 75 and re.search(r"Linked\s*In|Stukent|Certification|Simternship", own_line, re.I):
        return True
    return False


def _is_homework_points(text: str, m: re.Match) -> bool:
    pts = float(m.group(1))
    if pts >= 50 or _is_exam_or_cert_points(text, m):
        return False
    lookback = text[max(0, m.start() - 220) : m.end()]
    return bool(re.search(r"\d-\d+", lookback))


def parse_course_calendar_categories(text: str) -> list[Category]:
    """Parse point-based categories from a Course Calendar document."""
    cats: list[Category] = []
    seen: set[str] = set()

    for m in CAL_EXAM.finditer(text):
        name = m.group(1).strip()
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        ctx = _context_line(text, m.start(), 180)
        cats.append(
            Category(
                name=name,
                weight=float(m.group(2)),
                weight_unit="points",
                aliases=make_aliases(name),
                assignment_blurb=ctx,
            )
        )

    for m in CAL_BULLET.finditer(text):
        name = _normalize_calendar_name(m.group(1))
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        ctx = _context_line(text, m.start(), 180)
        cats.append(
            Category(
                name=name,
                weight=float(m.group(2)),
                weight_unit="points",
                aliases=make_aliases(name),
                assignment_blurb=ctx,
            )
        )

    # Certifications sometimes appear without bullet on page 2
    for pat, label in [
        (r"Linked\s*In\s*Learning\s*\n?\s*Excel\s*Certification\s*\n?\s*(\d+)\s*Points?", "LinkedIn Learning Excel Certification"),
        (r"Stukent\s*Simternship\s*\n?\s*(\d+)\s*Points?", "Stukent Simternship"),
    ]:
        m = re.search(pat, text, re.I | re.S)
        if m and label.lower() not in seen:
            seen.add(label.lower())
            cats.append(
                Category(
                    name=label,
                    weight=float(m.group(1)),
                    weight_unit="points",
                    aliases=make_aliases(label),
                    assignment_blurb=_context_line(text, m.start(), 220),
                )
            )

    homework_lines: list[str] = []
    homework_total = 0.0
    for m in CAL_HOMEWORK.finditer(text):
        if not _is_homework_points(text, m):
            continue
        pts = float(m.group(1))
        ctx = re.sub(r"\s+", " ", _line_window(text, m.start(), extra_lines=2)).strip()
        if ctx in homework_lines:
            continue
        homework_lines.append(ctx)
        homework_total += pts

    if homework_lines and "homework" not in seen:
        cats.append(
            Category(
                name="Homework",
                weight=homework_total,
                weight_unit="points",
                aliases=make_aliases("Homework"),
                assignment_blurb="; ".join(homework_lines[:3]),
            )
        )
    return cats


def parse_embedded_calendar_table(text: str) -> list[dict]:
    """Read structured calendar rows embedded by extract_text.py."""
    start = text.find(CALENDAR_TABLE_START)
    end = text.find(CALENDAR_TABLE_END)
    if start == -1 or end == -1:
        return []
    payload = text[start + len(CALENDAR_TABLE_START) : end].strip()
    try:
        rows = json.loads(payload)
    except json.JSONDecodeError:
        return []
    return rows if isinstance(rows, list) else []


def calendar_plain_text(text: str) -> str:
    """Strip embedded JSON table block; keep readable calendar prose."""
    start = text.find(CALENDAR_TABLE_START)
    if start == -1:
        return text
    return text[:start].strip()


def calendar_row_date(row: dict) -> str:
    return row.get("date_mon") or row.get("date_wed") or ""


def format_calendar_row(row: dict) -> str:
    """One clean verbatim line per calendar table row."""
    parts: list[str] = []
    if row.get("class"):
        parts.append(f"Class {row['class']}")
    date = calendar_row_date(row)
    if date:
        parts.append(f"Date: {date}")
    if row.get("topic"):
        parts.append(f"Topic: {row['topic'].replace(' / ', '; ')}")
    if row.get("reading"):
        parts.append(f"Required Reading: {row['reading'].replace(' / ', '; ')}")
    if row.get("homework"):
        parts.append(f"Homework (due 8:00 am): {row['homework'].replace(' / ', '; ')}")
    return " | ".join(parts)


def calendar_footnotes(text: str) -> list[str]:
    plain = calendar_plain_text(text)
    notes: list[str] = []
    for pat in [
        r"Unless specifically Identified, Chapter Appendices ARE NOT included as Required Reading",
        r"Knowledge of Cost Behavior \(Chapter 6\) & Contribution Margin \(Chapter 7\) are essential[^\n]+",
        r"Homework & Assignments due by 8:00 am",
        r"Assignments listed Below Due by\s*11:59 PM",
    ]:
        m = re.search(pat, plain, re.I)
        if m:
            notes.append(re.sub(r"\s+", " ", m.group(0)).strip())
    return notes


def calendar_exam_snippets(text: str) -> dict[str, list[str]]:
    """Exam lines often missing from table cells; grep from plain text."""
    plain = calendar_plain_text(text)
    out: dict[str, list[str]] = {
        "Midterm 1": [],
        "Midterm 2": [],
        "Final Exam": [],
    }
    specs = [
        ("Midterm 1", r"(\d{1,2}/\d{1,2}\s*)?Midterm 1:\s*\d+\s*Points[^\n]*"),
        ("Midterm 2", r"(\d{1,2}/\d{1,2}\s*)?Midterm 2:\s*\d+\s*Points[^\n]*"),
        ("Final Exam", r"Final Exam:\s*\d+\s*Points[^\n]*"),
        ("Final Exam", r"Wednesday,?\s*December\s+\d{1,2}(?:st|nd|rd|th)?[^\n]*8:00\s*AM[^\n]*PST"),
        ("Final Exam", r"Chapters 10, 11, 13, 14[^\n]*"),
    ]
    seen: dict[str, set[str]] = {k: set() for k in out}
    for label, pat in specs:
        for m in re.finditer(pat, plain, re.I):
            line = re.sub(r"\s+", " ", m.group(0)).strip()
            key = normalize(line)
            if key not in seen[label]:
                seen[label].add(key)
                out[label].append(line)
    return out


def row_has_homework_points(row: dict) -> bool:
    hw = row.get("homework") or ""
    if re.search(r"linked\s*in|stukent|certification|simternship", hw, re.I):
        return False
    return bool(re.search(r"\d+\s*[\-\u2013]?\s*Points?", hw, re.I))


def gather_calendar_content_from_table(
    rows: list[dict], cat: Category, text: str
) -> tuple[dict, str]:
    """Build clean verbatim from structured PDF table rows."""
    low = cat.name.lower()
    matched: list[str] = []
    sections: dict[str, list[str] | str] = {}
    exams = calendar_exam_snippets(text)

    if "homework" in low:
        hw_rows = [r for r in rows if row_has_homework_points(r)]
        items = [format_calendar_row(r) for r in hw_rows]
        if items:
            sections["Homework Assignments (by class date)"] = items
            matched.extend(items)
    elif "midterm 1" in low:
        if exams["Midterm 1"]:
            sections["Exam"] = exams["Midterm 1"]
            matched.extend(exams["Midterm 1"])
        review = [
            format_calendar_row(r)
            for r in rows
            if re.search(r"catchup|midterm review|practice midterm", r.get("topic", ""), re.I)
            and not re.search(r"16-28, 16-40|midterm 2", format_calendar_row(r), re.I)
        ]
        if review:
            sections["Review & Practice"] = review
            matched.extend(review)
    elif "midterm 2" in low:
        if exams["Midterm 2"]:
            sections["Exam"] = exams["Midterm 2"]
            matched.extend(exams["Midterm 2"])
        review = [
            format_calendar_row(r)
            for r in rows
            if re.search(r"catchup|midterm review|practice midterm", r.get("topic", ""), re.I)
            and not re.search(r"8-28, 8-29", format_calendar_row(r))
            and (
                re.search(r"10/19|10/21|16-28", format_calendar_row(r))
                or "10/19" in r.get("date_mon", "")
                or "10/21" in r.get("date_wed", "")
            )
        ]
        if review:
            sections["Review & Practice"] = review
            matched.extend(review)
    elif "final" in low and "exam" in low:
        if exams["Final Exam"]:
            sections["Exam"] = exams["Final Exam"]
            matched.extend(exams["Final Exam"])
        review = [
            format_calendar_row(r)
            for r in rows
            if re.search(r"catchup & final|practice final", r.get("topic", ""), re.I)
        ]
        if review:
            sections["Review & Practice"] = review
            matched.extend(review)
        final_row = next((r for r in rows if "december 16" in r.get("class", "").lower()), None)
        if final_row:
            line = format_calendar_row(final_row)
            sections["Exam Schedule"] = line
            matched.append(line)
    elif "linkedin" in low:
        mentions: list[str] = []
        for r in rows:
            blob = " ".join(r.values())
            if re.search(r"linked\s*in\s*learning", blob, re.I):
                mentions.append(format_calendar_row(r))
        due_line = "Due: 12/2 by 11:59 PM (from calendar footer)"
        sections["Assignment Details"] = mentions or ["LinkedIn Learning Excel Certification - 75 Points"]
        sections["Due Date & Submission"] = due_line
        matched.extend(mentions)
        matched.append(due_line)
    elif "stukent" in low:
        mentions: list[str] = []
        for r in rows:
            blob = " ".join(r.values())
            if re.search(r"stukent", blob, re.I):
                mentions.append(format_calendar_row(r))
        due_line = "Due: 12/2 by 11:59 PM (from calendar footer)"
        sections["Assignment Details"] = mentions or ["Stukent Simternship - 75 Points"]
        sections["Due Date & Submission"] = due_line
        matched.extend(mentions)
        matched.append(due_line)

    footnotes = calendar_footnotes(text)
    relevant_notes = list(footnotes)
    if "final" in low or "homework" in low:
        sections["Calendar Footnotes"] = relevant_notes
        matched.extend(relevant_notes)

    verbatim = "\n\n".join(dedupe_passages(matched))
    return sections, verbatim


def gather_calendar_content(text: str, cat: Category) -> tuple[dict, str]:
    """Collect calendar rows and context for a course-calendar category."""
    rows = parse_embedded_calendar_table(text)
    if rows:
        return gather_calendar_content_from_table(rows, cat, text)

    # Fallback: legacy grep-window extraction (lower quality for table PDFs)
    low = cat.name.lower()
    matched: list[str] = []
    seen: set[str] = set()

    if cat.assignment_blurb:
        matched.append(cat.assignment_blurb)
        seen.add(normalize(cat.assignment_blurb))

    if "midterm" in low:
        num = re.search(r"\d+", cat.name)
        n = num.group() if num else ""
        patterns = [
            rf"Midterm {n}:\s*\d+\s*Points?[^\n]*",
            rf"Practice Midterm Questions[^\n]*",
            rf"Catchup & Midterm Review[^\n]*",
        ]
        for pat in patterns:
            for m in re.finditer(pat, text, re.I):
                line = m.group(0).strip()
                key = normalize(line)
                if key not in seen:
                    seen.add(key)
                    matched.append(line)
    elif "final" in low:
        patterns = [
            r"Final Exam:\s*\d+\s*Points?[^\n]*",
            r"Final Exam[^\n]*December[^\n]*",
            r"Practice Final Questions[^\n]*",
            r"Catchup & Final Review[^\n]*",
            r"Chapter 14[^\n]*Final",
        ]
        for pat in patterns:
            for m in re.finditer(pat, text, re.I | re.S):
                line = re.sub(r"\s+", " ", m.group(0)).strip()
                key = normalize(line)
                if key not in seen and len(line) > 15:
                    seen.add(key)
                    matched.append(line)
    elif "homework" in low:
        for m in CAL_HOMEWORK.finditer(text):
            if not _is_homework_points(text, m):
                continue
            ctx = re.sub(r"\s+", " ", _line_window(text, m.start(), extra_lines=2)).strip()
            key = normalize(ctx)
            if key not in seen:
                seen.add(key)
                matched.append(ctx)
    else:
        for alias in cat.aliases:
            if len(alias) < 5:
                continue
            for m in re.finditer(re.escape(alias), text, re.I):
                ctx = _context_line(text, m.start(), 180)
                key = normalize(ctx)
                if key not in seen:
                    seen.add(key)
                    matched.append(ctx)

    footnotes = re.findall(
        r"Unless specifically Identified[^\n]+|Knowledge of Cost Behavior[^\n]+",
        text,
        re.I,
    )
    for fn in footnotes:
        key = normalize(fn)
        if key not in seen:
            seen.add(key)
            matched.append(fn.strip())

    verbatim = "\n\n---\n\n".join(dedupe_passages(matched))
    sections: dict[str, list[str] | str] = {}
    if cat.assignment_blurb:
        sections["Overview (Course Calendar)"] = cat.assignment_blurb
    if matched:
        sections["Calendar Entries"] = matched
    return sections, verbatim


def parse_calendar_dates(text: str, cat: Category, year: int) -> tuple[str, str]:
    """Infer start/due dates from calendar-style M/D and month-day patterns."""
    low = cat.name.lower()
    dates: list[str] = []

    if "midterm 1" in low:
        m = re.search(r"(\d{1,2})/(\d{1,2})\s*Midterm 1", text, re.I)
        if m:
            dates.append(f"{year:04d}-{int(m.group(1)):02d}-{int(m.group(2)):02d}")
    elif "midterm 2" in low:
        m = re.search(r"(\d{1,2})/(\d{1,2})\s*Midterm 2", text, re.I)
        if m:
            dates.append(f"{year:04d}-{int(m.group(1)):02d}-{int(m.group(2)):02d}")
    elif "final" in low and "exam" in low:
        m = re.search(
            r"December\s+(\d{1,2})(?:st|nd|rd|th)?",
            text,
            re.I,
        )
        if m:
            dates.append(f"{year:04d}-12-{int(m.group(1)):02d}")
    elif "linkedin" in low or "stukent" in low:
        m = re.search(r"(\d{1,2})/(\d{1,2})[^\n]*(?:11:59|Due by)", text, re.I)
        if not m:
            m = re.search(r"\b(\d{1,2})/(\d{1,2})\b[^\n]*(?:Linked\s*In|Stukent|Certification|Simternship)", text, re.I)
        if m:
            mo, day = int(m.group(1)), int(m.group(2))
            dates.append(f"{year:04d}-{mo:02d}-{day:02d}")
    elif "homework" in low:
        return "", ""

    if not dates:
        return parse_dates_from_text(text, year)

    unique = sorted(set(dates))
    return (unique[0], unique[-1]) if len(unique) > 1 else ("", unique[0])


def find_assignments_block(text: str) -> str:
    """Locate the real Assignments section (skip TOC/nav duplicates)."""
    best = ""
    best_count = 0
    for m in re.finditer(r"Assignments\s*:?\s*\n", text, re.I):
        snippet = text[m.end() : m.end() + 4000]
        end = re.search(r"\nGrading Scale\b", snippet, re.I)
        block = snippet[: end.start()] if end else snippet[:2500]
        count = len(re.findall(r".+[\-\u2013]\s*\d+(?:\.\d+)?\s*%", block))
        if count > best_count:
            best_count = count
            best = block
    return best


def parse_categories(text: str) -> list[Category]:
    cats: list[Category] = []
    block = find_assignments_block(text)
    if not block:
        return cats

    lines = block.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        cm = re.match(
            r"^(.+?)\s*[\-\u2013]\s*(\d+(?:\.\d+)?)\s*(%|pts?|points)\s*(.*)$",
            line,
            re.I,
        )
        if cm:
            name = cm.group(1).strip()
            weight = float(cm.group(2))
            unit_raw = cm.group(3).lower()
            unit = "points" if unit_raw.startswith("pt") or unit_raw == "points" else "percent"
            blurb_parts = [cm.group(4).strip()] if cm.group(4).strip() else []
            i += 1
            while i < len(lines):
                nxt = lines[i].strip()
                if re.match(r"^.+?\s*[\-\u2013]\s*\d", nxt):
                    break
                if not nxt:
                    i += 1
                    continue
                blurb_parts.append(nxt)
                i += 1
            cats.append(
                Category(
                    name=name,
                    weight=weight,
                    weight_unit=unit,
                    aliases=make_aliases(name),
                    assignment_blurb=" ".join(blurb_parts),
                )
            )
        else:
            i += 1

    if re.search(r"\bExtra Credit\b", text, re.I):
        if not any(c.name.lower() == "extra credit" for c in cats):
            cats.append(Category(name="Extra Credit", weight=None, aliases=make_aliases("Extra Credit")))
    return cats


def parse_grading_scale(text: str) -> dict:
    scale = {"a_threshold": "N/A", "raw_scale": "", "scale_type": "percentage"}
    gm = GRADING_SCALE.search(text)
    if gm:
        scale["raw_scale"] = gm.group(1).strip().replace("\n", " ")
    raw = scale["raw_scale"]
    if raw:
        am = A_THRESHOLD.search(raw)
        if am and am.group(1) and am.group(2):
            scale["a_threshold"] = f"{am.group(2)}% ({am.group(1)}-{am.group(2)})"
        elif am and am.group(3):
            scale["a_threshold"] = f"{am.group(3)}%+"
        if re.search(r"\bpts?\b|\bpoints\b", raw, re.I):
            scale["scale_type"] = "points"
    return scale


def split_chunks(text: str) -> list[str]:
    text = PAGE_MARKER.sub("\n", text)
    chunks: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if len(para) < 15 or NOISE.match(para):
            continue
        chunks.append(para)
    return chunks


def chunk_matches_category(chunk: str, cat: Category) -> bool:
    chunk_norm = normalize(chunk)
    if chunk.count("module:") >= 2 and len(chunk) < 400:
        return False
    if cat.name.lower() == "extra credit":
        return "extra credit" in chunk_norm or "experiencing the past" in chunk_norm
    strong = {normalize(cat.name)}
    strong.update(normalize(a) for a in cat.aliases if len(a) >= 8)
    if not any(s in chunk_norm or re.search(rf"\b{re.escape(s)}\b", chunk_norm) for s in strong):
        return False
    for alias in cat.aliases:
        alias_norm = normalize(alias)
        if len(alias_norm) < 5:
            continue
        if alias_norm in chunk_norm or re.search(rf"\b{re.escape(alias_norm)}\b", chunk_norm):
            return True
    return False


def find_dedicated_blocks(text: str, cat: Category) -> list[str]:
    """Capture large assignment-specific regions by start/end markers."""
    clean = PAGE_MARKER.sub("\n", text)
    blocks: list[str] = []
    low = cat.name.lower()

    def extract(start_pat: str, end_pats: list[str]) -> str:
        m = re.search(start_pat, clean, re.I)
        if not m:
            return ""
        end = len(clean)
        for ep in end_pats:
            em = re.search(ep, clean[m.end() :], re.I)
            if em:
                end = min(end, m.end() + em.start())
        block = clean[m.start() : end].strip()
        return block if len(block) > 80 else ""

    specs: list[tuple[str, list[str]]] = []

    if "sleep" in low:
        specs += [
            (r"HIST 103 Paper 1:", [r"\nSep 20-24:", r"\nOct 6-9:", r"\nWitchcraft Paper"]),
            (r"Sleep Paper Due by Midnight", [r"\nSep 17:", r"\nSep 20-24:"]),
        ]
    if "witchcraft" in low:
        specs += [
            (r"Witchcraft & Daily Life Paper", [r"\nNov 17-20:", r"\nDec 1-4:", r"\nNov 24"]),
            (r"Nov 10: Witchcraft Paper Due", [r"\nNov 12:", r"\nNov 17-20:"]),
        ]
    if "mid" in low and "term" in low:
        specs += [
            (r"Hist 103: Midterm Study Guide", [r"\nOct 13-16:", r"\nOct 20-23:", r"\nNov 3-6:"]),
            (r"Oct 6: Midterm\n", [r"\nOct 8:", r"\nOct 13-16:"]),
        ]
    if "final" in low and "exam" in low:
        specs += [
            (r"Hist 103: Final Study Guide", [r"\nUniversity Academic", r"\nExtra Credit"]),
            (r"Dec 10: Final Exam", [r"\nUniversity Academic", r"\nExtra Credit"]),
        ]
    if "extra credit" in low:
        specs += [
            (r"\nExtra Credit\nOver the course", [r"\nUniversity Academic", r"\nOccupational Therapy"]),
        ]
    if "discussion" in low:
        specs += [
            (r"Discussion Section[\-\u2013]\s*\d+\s*%\n", [r"\nIdentification Quizzes"]),
        ]
    if "quiz" in low:
        specs += [
            (r"Identification Quizzes[\-\u2013]\s*\d+\s*%\n", [r"\nSleep Paper"]),
        ]

    # Generic schedule due-line (skip Extra Credit  no stable end marker)
    if "extra credit" not in low:
        specs.append(
            (
                rf"\n[^\n]*{re.escape(cat.name)}[^\n]*Due[^\n]*\n",
                [r"\n[A-Z][a-z]{2} \d{1,2}-\d{1,2}:", r"\nHIST 103", r"\nHist 103", r"\nUniversity"],
            )
        )

    seen: set[str] = set()
    for start_pat, end_pats in specs:
        block = extract(start_pat, end_pats)
        key = normalize(block)
        if block and key not in seen:
            seen.add(key)
            blocks.append(block)
    return blocks


def dedupe_passages(passages: list[str]) -> list[str]:
    """Drop passages wholly contained in a longer one."""
    ordered = sorted(passages, key=len, reverse=True)
    kept: list[str] = []
    kept_norm: list[str] = []
    for p in ordered:
        n = normalize(p)
        if any(n in kn for kn in kept_norm):
            continue
        kept.append(p)
        kept_norm.append(n)
    return kept


def _month_to_iso(m: re.Match, default_year: int) -> str:
    months = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    mon = m.group(1)[:3].lower()
    day = int(m.group(2))
    yr = int(m.group(3)) if m.group(3) else default_year
    if mon in months:
        return f"{yr:04d}-{months[mon]:02d}-{day:02d}"
    return ""


def parse_dates_from_text(text: str, default_year: int = 2025) -> tuple[str, str]:
    dates: list[tuple[int, str]] = []
    for m in MONTH_DATE.finditer(text):
        iso = _month_to_iso(m, default_year)
        if iso:
            pri = 2 if re.search(r"due", text[max(0, m.start() - 30) : m.end() + 30], re.I) else 1
            dates.append((pri, iso))
    if not dates:
        return "", ""
    unique = sorted({d for _, d in dates})
    due = next((d for p, d in dates if p == 2), unique[-1])
    start = unique[0] if len(unique) > 1 else ""
    return start, due


def structure_block(block: str) -> dict[str, list[str] | str]:
    sections: dict[str, list[str] | str] = {}
    lines = block.splitlines()
    current_label = "Related Mentions"
    current_items: list[str] = []
    label_patterns = dict(SECTION_LABELS)

    def flush():
        nonlocal current_items, current_label
        if not current_items:
            return
        if current_label in sections:
            prev = sections[current_label]
            if isinstance(prev, list):
                prev.extend(current_items)
            else:
                sections[current_label] = [str(prev), *current_items]
        else:
            sections[current_label] = list(current_items)
        current_items = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        matched_label = None
        for label, pat in SECTION_LABELS:
            if pat.match(stripped):
                matched_label = label
                break
        if matched_label:
            flush()
            current_label = matched_label
            continue
        if stripped.endswith("?") and len(stripped) > 40:
            if current_label != "Prompts (pick ONE)":
                flush()
                current_label = "Prompts (pick ONE)"
        current_items.append(stripped)
    flush()
    return sections


def gather_category_content(text: str, cat: Category) -> tuple[dict, str]:
    matched: list[str] = []
    seen: set[str] = set()

    if cat.assignment_blurb:
        matched.append(cat.assignment_blurb)
        seen.add(normalize(cat.assignment_blurb))

    if cat.name.lower() != "extra credit":
        for chunk in split_chunks(text):
            if chunk_matches_category(chunk, cat):
                key = normalize(chunk)
                if key not in seen:
                    seen.add(key)
                    matched.append(chunk)

    for block in find_dedicated_blocks(text, cat):
        key = normalize(block)
        if key not in seen:
            seen.add(key)
            matched.append(block)

    verbatim = "\n\n---\n\n".join(dedupe_passages(matched))
    all_sections: dict[str, list[str] | str] = {}
    if cat.assignment_blurb:
        all_sections["Overview (Assignments section)"] = cat.assignment_blurb

    for block in matched:
        for heading, content in structure_block(block).items():
            if heading in all_sections:
                prev = all_sections[heading]
                if isinstance(prev, list) and isinstance(content, list):
                    prev.extend(content)
                elif isinstance(content, list):
                    all_sections[heading] = (
                        ([prev] if not isinstance(prev, list) else prev) + content
                    )
                else:
                    all_sections[heading] = content
            else:
                all_sections[heading] = content

    if not all_sections and matched:
        all_sections["All Matching Passages"] = matched
    return all_sections, verbatim


def infer_year(term: str) -> int:
    m = re.search(r"(20\d{2})", term)
    return int(m.group(1)) if m else 2025


def dissect(
    text: str,
    class_code: str,
    class_name: str = "",
    instructor: str = "",
    term: str = "",
    color: str = "",
) -> dict:
    calendar_mode = is_course_calendar(text)
    categories = parse_categories(text)
    if not categories and calendar_mode:
        categories = parse_course_calendar_categories(text)
    if not categories:
        raise SystemExit(
            "No graded categories found. Expected an Assignments section like 'Sleep Paper - 20%' "
            "or a Course Calendar with point values like 'Midterm 1: 250 Points'."
        )
    grading_scale = parse_grading_scale(text)
    if calendar_mode and grading_scale["a_threshold"] == "N/A":
        total_pts = sum(c.weight or 0 for c in categories)
        grading_scale["scale_type"] = "points"
        grading_scale["raw_scale"] = f"Total graded points in calendar: {total_pts:g} (letter scale not in document)"
    year = infer_year(term)
    result_categories = []
    for cat in categories:
        if calendar_mode:
            sections, verbatim = gather_calendar_content(text, cat)
            start, due = parse_calendar_dates(text, cat, year)
        else:
            sections, verbatim = gather_category_content(text, cat)
            start, due = parse_dates_from_text(verbatim, year)
        result_categories.append(
            {
                "name": cat.name,
                "weight": cat.weight,
                "weight_unit": cat.weight_unit,
                "start_date": start,
                "due_date": due,
                "is_group_project": bool(GROUP_RE.search(verbatim)),
                "sections": sections,
                "extracted_text": verbatim,
            }
        )
    cls: dict = {"code": class_code}
    if class_name:
        cls["name"] = class_name
    if instructor:
        cls["instructor"] = instructor
    if term:
        cls["term"] = term
    if color:
        cls["color"] = color
    return {"class": cls, "grading_scale": grading_scale, "categories": result_categories}


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-dissect syllabus text to JSON.")
    parser.add_argument("text_file", help="Extracted syllabus plain text")
    parser.add_argument("--class-code", required=True)
    parser.add_argument("--class-name", default="")
    parser.add_argument("--instructor", default="")
    parser.add_argument("--term", default="")
    parser.add_argument("--color", default="")
    parser.add_argument("--out", default="class.json")
    args = parser.parse_args()

    text = Path(args.text_file).expanduser().read_text(encoding="utf-8")
    data = dissect(
        text,
        class_code=args.class_code,
        class_name=args.class_name,
        instructor=args.instructor,
        term=args.term,
        color=args.color,
    )
    out = Path(args.out).expanduser()
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(data['categories'])} categories to {out}")
    for c in data["categories"]:
        print(
            f"  {c['name']}: {len(c.get('sections', {}))} sections, "
            f"{len(c.get('extracted_text', ''))} chars verbatim"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
