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
    if "case analysis" in low:
        aliases.update({"case analysis", "case preparation", "usc-ct", "critical thinking framework"})
    if "team project" in low and "paper" in low:
        aliases.update({"team project", "project paper", "fieldwork study", "issue analysis"})
    if "reflection" in low:
        aliases.update({"final reflection", "reflection paper", "learning journal"})
    if "proposal" in low and "contract" in low:
        aliases.update({"project proposal", "team contract"})
    if low == "presentation":
        aliases.update({"team project presentation", "in-class presentation", "q&a"})
    if "peer evaluation" in low or "self & peer" in low:
        aliases.update({"peer evaluation", "self and peer", "self & peer evaluation"})
    if "participation" in low:
        aliases.update({"class participation", "research studies participation", "attendance"})
    if "midterm" in low and "exam" in low:
        aliases.update({"midterm", "mid-term", "mid term"})
        if "first" in low:
            aliases.update({"midterm 1", "first midterm", "midterm one"})
        if "second" in low:
            aliases.update({"midterm 2", "second midterm"})
        if "third" in low:
            aliases.update({"midterm 3", "third midterm"})
        if "fourth" in low or "forth" in low:
            aliases.update({"midterm 4", "fourth midterm"})
    if "ai forecast" in low or "forecast project" in low:
        aliases.update(
            {
                "ai forecast project",
                "ai forecasting project",
                "ai project",
                "final project",
                "forecasting project",
            }
        )
    if "wsj" in low or "future view" in low:
        aliases.update({"wsj future view", "wall street journal", "future view"})
    return sorted(aliases, key=len, reverse=True)


COURSE_CALENDAR = re.compile(r"Course Calendar", re.I)
CALENDAR_TABLE_START = "=== CALENDAR_TABLE_JSON ==="
CALENDAR_TABLE_END = "=== END CALENDAR_TABLE ==="
SUPPLEMENT_START = "=== SUPPLEMENT_SYLLABUS ==="
SUPPLEMENT_END = "=== END SUPPLEMENT ==="
RESEARCH_GUIDE_START = "=== RESEARCH_GUIDE ==="
RESEARCH_GUIDE_END = "=== END RESEARCH_GUIDE ==="
MARSHALL_SCHEDULE_RULES: list[tuple[str, list[str]]] = [
    ("Midterm Exam", [r"Midterm\s*\n\s*(\d{1,2}/\d{1,2})\s*Exam"]),
    (
        "Case Analysis Assignments",
        [
            r"(\d{1,2}/\d{1,2})[^\n]{0,160}Memo due",
            r"(\d{1,2}/\d{1,2})[^\n]{0,160}Analysis Memo Due",
        ],
    ),
    ("Proposal & Team Contract", [r"(\d{1,2}/\d{1,2})[^\n]{0,200}contract due"]),
    (
        "Team Project Paper",
        [
            r"[Tt]eam project paper due[^0-9\n]{0,40}(\d{1,2}/\d{1,2})",
            r"[Tt]eam project outline due[^0-9\n]{0,40}(\d{1,2}/\d{1,2})",
            r"(\d{1,2}/\d{1,2})[^\n]{0,120}[Tt]eam project outline due",
        ],
    ),
    ("Presentation", [r"Presentation slides are due on\s*\n?\s*(\d{1,2}/\d{1,2})"]),
    (
        "Self & Peer Evaluation",
        [r"[Ss]elf and peer evaluation due\s*\n?\s*(\d{1,2}/\d{1,2})"],
    ),
    (
        "Final Reflection Paper",
        [r"Personal Reflection Paper due\s*\n?\s*(\d{1,2}/\d{1,2})"],
    ),
    ("Final Exam", [r"Wed\.?,?\s*December\s+(\d{1,2})", r"Final Exam[^\n]{0,200}December\s+(\d{1,2})"]),
]
# Inferred start dates from schedule prose (earliest milestone before a due date)
MARSHALL_CONNECT_START = "8/24"
MARSHALL_CONNECT_DUE = "12/20"
MARSHALL_SHARPEN_START = "7/6"
MARSHALL_SHARPEN_DUE = "9/4"
# Connect prep is NOT a Course Evaluation grade bucket (see reference.md).
MARSHALL_CONNECT_CATEGORY = "Personal Assessments (Connect)"
BUAD_281_STRATEGY = (
    "If your AI tool breaks down and solves the homework bank problems - "
    "extracting step-by-step mechanics from the textbook - mastering those exact "
    "mechanics is all you need to get an A without reading prose."
)
MARSHALL_INFERRED_STARTS: list[tuple[str, str, str]] = [
    ("Participation", r"8/24", r"\b8/24\b"),
    ("Case Analysis Assignments", r"8/26", r"USC-CT and Case\s*\n?\s*Analysis videos"),
    ("Proposal & Team Contract", r"8/31", r"Team project will be explained"),
    ("Proposal & Team Contract", r"9/9", r"forming teams this week"),
    ("Team Project Paper", r"8/31", r"Team project will be explained"),
    ("Presentation", r"8/31", r"Team project will be explained"),
    ("Self & Peer Evaluation", r"8/31", r"Team project will be explained"),
    ("Final Reflection Paper", r"8/31", r"Team project will be explained"),
    ("Midterm Exam", r"8/24", r"\b8/24\b"),
    ("Final Exam", r"8/24", r"\b8/24\b"),
]
RESEARCH_MILESTONES: list[tuple[str, str, str, str]] = [
    ("SONA registration opens", r"Opens Aug(?:ust)?\s+24|August 24", "2026-08-24", "start"),
    ("Prescreening questionnaire opens", r"Opens Sep(?:tember)?\s+11|Available Sep(?:tember)?\s+11|starting September 11", "2026-09-11", "start"),
    ("Setup deadline (registration, prescreening, contacts)", r"Deadline Sep(?:tember)?\s+25|September 25, 2026", "2026-09-25", "due"),
    ("Study invitations begin (after setup)", r"Opens Sep(?:tember)?\s+25|Unlocks Step 3|Completes setup", "2026-09-26", "start"),
    ("Employee contact surveys sent", r"surveys in late October|sent in late October", "2026-10-26", "due"),
    ("Complete 2.0 research credits", r"Deadline Dec(?:ember)?\s+4|December 4", "2026-12-04", "due"),
]
MD_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})\b")

# Strict type labels for sub-assignment rows (Category column in Excel; `notes` in JSON)
LABEL_READING = "Reading"
LABEL_HOMEWORK = "Homework"
LABEL_ASSIGNMENT = "Assignment"
LABEL_EXAM = "Exam"
LABEL_RESEARCH = "Research"
LABEL_CERTIFICATION = "Certification"


def sub_assignment(
    name: str,
    start: str,
    due: str,
    label: str,
) -> dict:
    """Sub-row for Excel: `notes` is the strict type label shown in the Category column."""
    return {
        "name": name[:120],
        "start_date": start,
        "due_date": due,
        "notes": label,
    }


def classify_major_vs_daily(name: str) -> str:
    """Classify sub-row type: Reading, Homework, Assignment, or Exam."""
    low = name.lower()
    if re.search(r"\b(midterm|final exam)\b", low):
        return LABEL_EXAM
    if re.search(r"\bfinal\b", low) and re.search(r"\b(exam|december|dec)\b", low):
        return LABEL_EXAM
    if re.search(
        r"\b(paper due|paper\b|project paper|team project|proposal|contract|memo due|memo\b|"
        r"analysis memo|reflection paper|presentation slides|peer evaluation|outline due|"
        r"certification|sleep paper|witchcraft paper|case analysis)\b",
        low,
    ):
        return LABEL_ASSIGNMENT
    if re.search(
        r"\b(self-assessment|connect:|sharpen|questionnaire|problem|quiz|identification|"
        r"primary source activity|points?\)|\d-\d+\s*[,;]?\s*\d+\s*points?)\b",
        low,
    ):
        return LABEL_HOMEWORK
    if re.search(
        r"\b(reading|textbook|chapter|ch\.|ares reading|case coursepack|lecture topic)\b",
        low,
    ):
        return LABEL_READING
    return LABEL_HOMEWORK


def classify_hist103_sub_item(kind: str, name: str) -> str:
    """HIST-103 weekly schedule rows: readings vs daily work vs major deliverables."""
    if kind in ("week", "week_lecture", "section_reading"):
        return LABEL_READING
    return classify_major_vs_daily(name)


def _hist103_sub_item(
    name: str,
    start: str,
    due: str,
    label: str,
    category_hint: str,
    kind: str,
) -> dict:
    return {
        **sub_assignment(name, start, due, label),
        "category_hint": category_hint,
        "kind": kind,
    }


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


def is_grading_policies_syllabus(text: str) -> bool:
    """Marshall ECON-style syllabi: Grading Policies table + embedded COURSE CALENDAR."""
    return bool(
        re.search(
            r"Grading Policies\s*\n\s*ASSIGNMENTS\s+Points\s+%\s+of\s+Grade",
            text,
            re.I,
        )
    )


def is_point_course_calendar(text: str) -> bool:
    """Point-based calendar PDFs (BUAD-281), not percentage syllabi with schedule tables."""
    if not COURSE_CALENDAR.search(text):
        return False
    if is_grading_policies_syllabus(text):
        return False
    return bool(
        re.search(r"Midterm \d+:\s*\d+\s*Points?", text, re.I)
        or re.search(r"Final Exam:\s*\d+\s*Points?", text, re.I)
        or re.search(r"Linked\s*In\s*Learning[^\n]+\d+\s*Points?", text, re.I)
    )


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
    """Strip embedded JSON table and supplement blocks; keep readable calendar prose."""
    for marker in (CALENDAR_TABLE_START, SUPPLEMENT_START):
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx]
    return text.strip()


def parse_supplement_text(text: str) -> str:
    """Optional full syllabus merged after the calendar for extra assignment detail."""
    start = text.find(SUPPLEMENT_START)
    end = text.find(SUPPLEMENT_END)
    if start == -1 or end == -1:
        return ""
    return text[start + len(SUPPLEMENT_START) : end].strip()


def parse_research_guide_text(text: str) -> str:
    """Optional Marshall research participation guide merged into syllabus text."""
    start = text.find(RESEARCH_GUIDE_START)
    end = text.find(RESEARCH_GUIDE_END)
    if start == -1 or end == -1:
        return ""
    return text[start + len(RESEARCH_GUIDE_START) : end].strip()


def is_marshall_syllabus(text: str) -> bool:
    """Percentage-weight Marshall OB syllabi with Course Evaluation (not point calendars)."""
    return (
        bool(find_course_evaluation_block(text))
        and not is_point_course_calendar(text)
        and not is_grading_policies_syllabus(text)
    )


def find_course_schedule_section(text: str) -> str:
    m = re.search(r"Course Schedule\s*\n", text, re.I)
    if not m:
        return ""
    snippet = text[m.end() :]
    end = re.search(r"\nAdditional Information\b", snippet, re.I)
    return snippet[: end.start()] if end else snippet[:8000]


def _normalize_md_date(raw: str, year: int) -> str:
    cleaned = re.sub(r"\s+", "", raw.strip())
    m = re.match(r"(\d{1,2})/(\d{1,2})", cleaned)
    if m:
        return f"{year:04d}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    m = re.match(r"(\d{1,2})", cleaned)
    if m:
        return f"{year:04d}-12-{int(m.group(1)):02d}"
    return ""


def _normalize_schedule_text(schedule: str) -> str:
    """Fix common PDF/OCR line breaks before regex matching."""
    text = schedule
    text = re.sub(r"1\s+1/9", "11/9", text)
    text = re.sub(
        r"(\d{1,2}/\d{1,2})\s*\n\s*([^\n]{0,120}(?:due|Due|Exam))",
        r"\1 \2",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"(Personal Reflection Paper due)\s*\n\s*(\d{1,2}/\d{1,2})",
        r"\1 \2",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"([Tt]eam project paper due \(one)\s*\n\s*(\d{1,2}/\d{1,2})",
        r"\1 \2",
        text,
    )
    text = re.sub(
        r"([Ss]elf and peer evaluation due)\s*\n\s*(\d{1,2}/\d{1,2})",
        r"\1 \2",
        text,
    )
    text = re.sub(
        r"([Tt]eam project outline due)\s*\n\s*(\d{1,2}/\d{1,2})",
        r"\2 \1",
        text,
        flags=re.I,
    )
    return text


def parse_marshall_schedule_deliverables(schedule: str, year: int) -> list[dict]:
    """Extract dated deliverables from a Marshall Course Schedule section."""
    if not schedule:
        return []
    schedule = _normalize_schedule_text(schedule)
    entries: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for cat_label, patterns in MARSHALL_SCHEDULE_RULES:
        for pat in patterns:
            for m in re.finditer(pat, schedule, re.I | re.S):
                raw_date = m.group(1)
                iso = _normalize_md_date(raw_date, year)
                if not iso:
                    continue
                key = (cat_label, iso)
                if key in seen:
                    continue
                seen.add(key)
                ctx_start = max(0, m.start() - 40)
                ctx_end = min(len(schedule), m.end() + 120)
                entries.append(
                    {
                        "category": cat_label,
                        "date_iso": iso,
                        "kind": "due" if re.search(r"due|exam", schedule[ctx_start:ctx_end], re.I) else "milestone",
                        "raw": re.sub(r"\s+", " ", schedule[ctx_start:ctx_end]).strip(),
                    }
                )
    return sorted(entries, key=lambda e: e["date_iso"])


def marshall_inferred_start_dates(schedule: str, year: int) -> dict[str, str]:
    """Map category -> earliest inferred ISO start from schedule language."""
    out: dict[str, list[str]] = {}
    for cat_key, md, pattern in MARSHALL_INFERRED_STARTS:
        if re.search(pattern, schedule, re.I | re.S):
            iso = _normalize_md_date(md, year)
            if iso:
                out.setdefault(cat_key, []).append(iso)
    return {k: min(v) for k, v in out.items()}


def marshall_dates_for_category(
    cat: Category, deliverables: list[dict], schedule: str, year: int
) -> tuple[str, str]:
    key = marshall_category_key(cat.name)
    inferred = marshall_inferred_start_dates(schedule, year)
    due_dates = sorted(
        {
            d["date_iso"]
            for d in deliverables
            if d["category"] == key and d.get("kind", "due") == "due"
        }
    )
    milestone_dates = sorted(
        {
            d["date_iso"]
            for d in deliverables
            if d["category"] == key and d.get("kind") == "milestone"
        }
    )
    all_dates = sorted({d["date_iso"] for d in deliverables if d["category"] == key})
    start = inferred.get(key, "")
    due = due_dates[-1] if due_dates else (all_dates[-1] if all_dates else "")
    if not due and milestone_dates:
        due = milestone_dates[-1]
    return start, due


def schedule_lines_for_category(schedule: str, cat: Category, year: int) -> list[str]:
    """All dated schedule rows relevant to a category (including page 7 sessions)."""
    schedule = _normalize_schedule_text(schedule)
    key = marshall_category_key(cat.name)
    lines: list[str] = []
    keywords: dict[str, list[str]] = {
        "Participation": [r"\b8/24\b", r"VIA", r"Character Strengths", r"forming teams"],
        "Case Analysis Assignments": [r"Case Analysis", r"Memo due", r"Analysis Memo Due", r"USC-CT"],
        "Midterm Exam": [r"Midterm", r"10/14"],
        "Proposal & Team Contract": [r"proposal", r"contract due", r"Team project will be explained"],
        "Team Project Paper": [r"Team [Pp]roject", r"outline due", r"paper due", r"Workshop"],
        "Presentation": [r"Presentation", r"slides are due"],
        "Self & Peer Evaluation": [r"peer evaluation"],
        "Final Reflection Paper": [r"Reflection Paper", r"Organiza.*Change"],
        "Final Exam": [r"Final Exam", r"December 9"],
    }
    pats = keywords.get(key, [re.escape(cat.name)])
    # Walk schedule in chunks anchored on M/W date lines
    for m in re.finditer(
        r"((?:[MW]\s+)?(?:\d{1,2}/\d{1,2})[^\n]*(?:\n(?!\s*(?:[MW]\s+)?\d{1,2}/)[^\n]*){0,8})",
        schedule,
        re.I,
    ):
        chunk = m.group(1)
        if any(re.search(p, chunk, re.I) for p in pats):
            dm = re.search(r"(\d{1,2}/\d{1,2})", chunk)
            iso = _normalize_md_date(dm.group(1), year) if dm else ""
            prefix = f"{iso} | " if iso else ""
            lines.append(prefix + re.sub(r"\s+", " ", chunk).strip()[:240])
    return lines


def marshall_category_key(name: str) -> str:
    low = name.lower()
    if "case analysis" in low:
        return "Case Analysis Assignments"
    if "proposal" in low and "contract" in low:
        return "Proposal & Team Contract"
    if "team project" in low and "paper" in low:
        return "Team Project Paper"
    if "presentation" in low:
        return "Presentation"
    if "peer evaluation" in low or "self & peer" in low:
        return "Self & Peer Evaluation"
    if "reflection" in low:
        return "Final Reflection Paper"
    if "midterm" in low:
        return "Midterm Exam"
    if "final" in low and "exam" in low:
        return "Final Exam"
    return name


def parse_research_participation_milestones(rg_text: str, year: int) -> list[dict]:
    """Key Fall research-participation dates from the Marshall guide."""
    if not rg_text:
        return []
    milestones: list[dict] = []
    for label, pattern, default_iso, kind in RESEARCH_MILESTONES:
        if not re.search(pattern, rg_text, re.I):
            continue
        iso = default_iso.replace("2026", str(year)) if year != 2026 else default_iso
        milestones.append({"label": label, "date_iso": iso, "kind": kind})
    return milestones


def research_dates_for_participation(milestones: list[dict]) -> tuple[str, str]:
    starts = [m["date_iso"] for m in milestones if m["kind"] == "start"]
    dues = [m["date_iso"] for m in milestones if m["kind"] == "due"]
    start = min(starts) if starts else ""
    due = max(dues) if dues else ""
    return start, due


def _nearest_class_date_before(schedule: str, pos: int) -> str:
    lookback = schedule[max(0, pos - 400) : pos]
    dates = re.findall(r"\b(\d{1,2}/\d{1,2})\b", lookback)
    return dates[-1] if dates else ""


def parse_marshall_connect_assessments(schedule: str, year: int) -> list[dict]:
    """McGraw-Hill Connect self-assessments - ungraded prep (own workbook section)."""
    if not schedule:
        return []
    schedule = _normalize_schedule_text(schedule)
    connect_due = _normalize_md_date(MARSHALL_CONNECT_DUE, year)
    seen: set[str] = set()
    items: list[dict] = []
    pat = re.compile(
        r"Self[- ]Assessment\s+(\d+\.\d+)\s*:?\s*([^\n]{3,90}?)(?:\s+on Connect|$|\n)",
        re.I,
    )
    for m in pat.finditer(schedule):
        code = m.group(1)
        if code in seen:
            continue
        seen.add(code)
        title = re.sub(r"\s+", " ", m.group(2)).strip(" :-")
        class_md = _nearest_class_date_before(schedule, m.start())
        session_iso = _normalize_md_date(class_md, year) if class_md else ""
        items.append(
            sub_assignment(
                f"Connect: Self-Assessment {code} - {title}",
                "",
                session_iso or connect_due,
                LABEL_HOMEWORK,
            )
        )
    return items


def _deliverable_assignment_name(raw: str, category: str) -> str:
    raw = re.sub(r"\s+", " ", raw).strip()
    patterns = [
        (r"Personal Reflection Paper due", "Personal Reflection Paper"),
        (r"Midterm[^\n]{0,30}Exam", "Midterm Exam"),
        (r"Final Exam[^\n]{0,40}December", "Final Exam"),
        (r"Thomas Green|Case Analysis[^\n]{0,40}Memo due", "Thomas Green Case Analysis Memo"),
        (r"SkillsForTomorrow|Analysis Memo Due", "SkillsForTomorrow Analysis Memo"),
        (r"proposal[^\n]{0,120}contract due", "Team project proposal & team contract"),
        (r"outline due", "Team project outline"),
        (r"[Tt]eam project paper due", "Team project paper"),
        (r"Presentation slides", "Presentation slides"),
        (r"peer evaluation due", "Self & peer evaluation"),
    ]
    for pat, label in patterns:
        if re.search(pat, raw, re.I):
            return label
    return raw[:80] or category


def build_marshall_assignments_by_category(
    text: str,
    year: int,
    research_guide: str,
    categories: list[Category],
) -> tuple[dict[str, list[dict]], list[dict]]:
    """Graded deliverables + research under categories; Connect prep returned separately."""
    out: dict[str, list[dict]] = {c.name: [] for c in categories}
    connect_items: list[dict] = []
    schedule = find_course_schedule_section(text)
    inferred = marshall_inferred_start_dates(schedule, year)

    # Graded deliverables from schedule
    for d in parse_marshall_schedule_deliverables(schedule, year):
        cat_key = d["category"]
        cat_name = next((c.name for c in categories if marshall_category_key(c.name) == cat_key), cat_key)
        if cat_name not in out:
            out[cat_name] = []
        start = inferred.get(cat_key, "")
        if not start:
            start = ""
        out[cat_name].append(
            sub_assignment(
                _deliverable_assignment_name(d["raw"], cat_key),
                start,
                d["date_iso"],
                classify_major_vs_daily(_deliverable_assignment_name(d["raw"], cat_key)),
            )
        )

    # Connect self-assessments - NOT part of Participation or other graded buckets
    connect_items.extend(parse_marshall_connect_assessments(schedule, year))

    if re.search(r"McGraw-Hill Connect|Connect module", text, re.I):
        sharpen_start, sharpen_due = sharpen_dates_from_text(text, year)
        connect_items.append(
            sub_assignment(
                "Connect: Sharpen Companion",
                sharpen_start,
                sharpen_due,
                LABEL_HOMEWORK,
            )
        )

    # Research participation milestones  -  under Participation only
    if research_guide:
        part_name = next((c.name for c in categories if "participation" in c.name.lower()), None)
        if part_name:
            for m in parse_research_participation_milestones(research_guide, year):
                out[part_name].append(
                    sub_assignment(
                        f"Research: {m['label']}",
                        m["date_iso"] if m["kind"] == "start" else "",
                        m["date_iso"] if m["kind"] == "due" else "",
                        LABEL_RESEARCH,
                    )
                )

    for cat_name, items in out.items():
        seen_names: set[str] = set()
        unique: list[dict] = []
        for item in sorted(items, key=lambda x: (x.get("start_date") or "", x.get("due_date") or "", x["name"])):
            key = item["name"].lower()
            if key in seen_names:
                continue
            seen_names.add(key)
            unique.append(item)
        out[cat_name] = unique

    seen_connect: set[str] = set()
    unique_connect: list[dict] = []
    for item in sorted(connect_items, key=lambda x: (x.get("due_date") or "", x["name"])):
        key = item["name"].lower()
        if key in seen_connect:
            continue
        seen_connect.add(key)
        unique_connect.append(item)
    return out, unique_connect


def gather_marshall_connect_content(text: str) -> tuple[dict, str]:
    """Verbatim for Personal Assessments (Connect) - ungraded prep, not Participation."""
    matched: list[str] = []
    for pat in [
        r"Personal assessments are listed in the course schedule[^\n]+(?:\n[^\n]+){0,3}",
        r"\(1\) Textbook & Connect/LearnSmart\.[^\n]+(?:\n[^\n]+){0,8}",
        r"\d+\.\s*Under Content, find the Connect module[^\n]+(?:\n[^\n]+){0,6}",
    ]:
        m = re.search(pat, text, re.I)
        if m:
            matched.append(re.sub(r"\s+", " ", m.group(0)).strip())
    schedule = find_course_schedule_section(text)
    if schedule:
        for m in re.finditer(
            r"Self[- ]Assessment\s+\d+\.\d+[^\n]{0,120}",
            schedule,
            re.I,
        ):
            line = re.sub(r"\s+", " ", m.group(0)).strip()
            if line not in matched:
                matched.append(line)
    sections: dict = {}
    if matched:
        sections["Personal Assessments (Connect prep)"] = matched[:20]
    verbatim = "\n\n---\n\n".join(matched)
    return sections, verbatim


def calendar_homework_assignments(rows: list[dict], year: int) -> list[dict]:
    """BUAD-281 Homework category: Reading + Homework pairs by class date, earliest first.

    The calendar PDF lists one session date per row ('due by 8:00 am')  -  no separate start date.
    """
    items: list[dict] = []
    dated_rows: list[tuple[str, dict]] = []
    for row in rows:
        iso = md_to_iso(calendar_row_date(row), year)
        if iso:
            dated_rows.append((iso, row))
    dated_rows.sort(key=lambda x: x[0])

    for iso, row in dated_rows:
        if not row_has_homework_points(row):
            continue
        reading = (row.get("reading") or "").replace(" / ", "; ").strip()
        hw = (row.get("homework") or "").replace(" / ", "; ").strip()
        topic = (row.get("topic") or "").replace(" / ", "; ").strip()
        cls = row.get("class") or ""
        date = calendar_row_date(row)
        prefix = f"Class {cls} ({date})" if cls else str(date)
        if reading:
            name = f"{prefix} - {topic[:40]}: {reading[:70]}" if topic else f"{prefix} - {reading[:90]}"
            items.append(sub_assignment(name, "", iso, LABEL_READING))
        elif topic:
            items.append(sub_assignment(f"{prefix} - {topic[:90]}", "", iso, LABEL_READING))
        if hw:
            hw_main = re.split(
                r"/\s*(?:Assignments listed|Linked\s*In|Stukent|Certification|Simternship)",
                hw,
                maxsplit=1,
                flags=re.I,
            )[0].strip()
            items.append(sub_assignment(f"{prefix} - {hw_main[:90]}", "", iso, LABEL_HOMEWORK))
    return items


def calendar_week_assignments(rows: list[dict], year: int) -> list[dict]:
    """All calendar session rows (reading/topic); due date only  -  no inferred start."""
    items: list[dict] = []
    dated_rows: list[tuple[str, dict]] = []
    for row in rows:
        iso = md_to_iso(calendar_row_date(row), year)
        if iso:
            dated_rows.append((iso, row))
    dated_rows.sort(key=lambda x: x[0])

    for iso, row in dated_rows:
        reading = (row.get("reading") or "").replace(" / ", "; ").strip()
        hw = (row.get("homework") or "").replace(" / ", "; ").strip()
        topic = (row.get("topic") or "").replace(" / ", "; ").strip()
        has_hw = row_has_homework_points(row)
        cls = row.get("class") or ""
        date = calendar_row_date(row)
        prefix = f"Class {cls} ({date})" if cls else str(date)
        if reading:
            name = f"{prefix} - {reading[:90]}"
            if topic:
                name = f"{prefix} - {topic[:40]}: {reading[:70]}"
            items.append(sub_assignment(name, "", iso, LABEL_READING))
        if has_hw and hw:
            items.append(sub_assignment(f"{prefix} - {hw[:90]}", "", iso, LABEL_HOMEWORK))
        elif topic and not reading and not has_hw:
            items.append(sub_assignment(f"{prefix} - {topic[:90]}", "", iso, LABEL_READING))
    return items


def build_calendar_assignments_by_category(
    text: str, year: int, categories: list[Category]
) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {c.name: [] for c in categories}
    rows = parse_embedded_calendar_table(text)
    if not rows:
        return out
    exams = calendar_exam_snippets(text)
    for cat in categories:
        low = cat.name.lower()
        if "homework" in low:
            out[cat.name] = calendar_homework_assignments(rows, year)
        elif "midterm 1" in low and exams.get("Midterm 1"):
            iso = parse_calendar_dates(text, cat, year)
            out[cat.name] = [
                sub_assignment(line[:100], "", iso[1], LABEL_EXAM)
                for line in exams["Midterm 1"]
            ]
        elif "midterm 2" in low and exams.get("Midterm 2"):
            iso = parse_calendar_dates(text, cat, year)
            out[cat.name] = [
                sub_assignment(line[:100], "", iso[1], LABEL_EXAM)
                for line in exams["Midterm 2"]
            ]
        elif "final" in low and "exam" in low:
            merged = build_merged_final_exam_block(text, rows, year)
            if merged:
                iso = parse_calendar_dates(text, cat, year)
                out[cat.name] = [
                    sub_assignment(
                        "Final Exam",
                        "",
                        iso[1],
                        LABEL_EXAM,
                    )
                ]
        elif "linkedin" in low or "stukent" in low:
            cert = "linkedin" if "linkedin" in low else "stukent"
            start, due = calendar_cert_dates(rows, cert, year)
            out[cat.name] = [
                sub_assignment(cat.name, start, due, LABEL_CERTIFICATION)
            ]
    return out


HIST_MONTH = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _hist_month_day_to_iso(month_str: str, day: int, year: int) -> str:
    mon = HIST_MONTH.get(month_str[:3].lower(), 0)
    if not mon:
        return ""
    return f"{year:04d}-{mon:02d}-{day:02d}"


def find_hist103_schedule_block(text: str) -> str:
    """Detailed week-by-week schedule (after Grading Scale, not TOC)."""
    m = re.search(
        r"Grading Scale\s*\n.+?\n((?:Aug|Sep|Oct|Nov|Dec) \d{1,2}-\d{1,2}:)",
        text,
        re.I | re.S,
    )
    if not m:
        return ""
    start = m.start(1)
    tail = text[start:]
    end = re.search(r"\nUniversity Academic|\nExtra Credit\nOver the course", tail, re.I)
    return tail[: end.start()] if end else tail[:14000]


def _clean_hist103_reading_text(text: str) -> str:
    """Strip PDF page markers, Brightspace module noise, and file blobs."""
    text = PAGE_MARKER.sub(" ", text)
    text = re.sub(r"--\s*\d+\s+of\s+\d+\s*--", " ", text, flags=re.I)
    text = re.sub(r"\b\d+\.Levack\.\d+\s*PDF document\b", " ", text, flags=re.I)
    text = re.sub(r"\b(?:PDF|Word) document\b", " ", text, flags=re.I)
    text = re.sub(r"\bmodule:\s*contains[^\n]*", " ", text, flags=re.I)
    text = re.sub(r"\b\d+\s+bookmarked topics\b", " ", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def _hist103_reading_title(reading: str, max_len: int = 95) -> str:
    reading = _clean_hist103_reading_text(reading)
    if not reading:
        return ""
    m = re.match(r'^(.{10,95}?)(?:\s+\d+\s+\d|$)', reading)
    if m:
        reading = m.group(1).strip()
    if len(reading) > max_len:
        cut = reading[: max_len - 3].rsplit(" ", 1)[0]
        reading = cut + "..." if cut else reading[: max_len - 3] + "..."
    return reading


def parse_hist103_weekly_items(text: str, year: int) -> list[dict]:
    block = find_hist103_schedule_block(text)
    if not block:
        return []
    block = PAGE_MARKER.sub(" ", block)
    items: list[dict] = []
    week_re = re.compile(
        r"(Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})-(\d{1,2}):\s*([^\n]+)",
        re.I,
    )
    matches = list(week_re.finditer(block))
    for i, wm in enumerate(matches):
        mon, d1, d2, title = wm.group(1), int(wm.group(2)), int(wm.group(3)), wm.group(4).strip()
        chunk_end = matches[i + 1].start() if i + 1 < len(matches) else len(block)
        chunk = PAGE_MARKER.sub(" ", block[wm.end() : chunk_end])
        start_iso = _hist_month_day_to_iso(mon, d1, year)
        due_iso = _hist_month_day_to_iso(mon, d2, year)
        readings: list[str] = []
        for sm in re.finditer(
            r"(?:Readings for Section|Section Readings?):?\s*\n(.+?)(?=\n(?:Aug|Sep|Oct|Nov|Dec) \d{1,2}:|\n(?:Aug|Sep|Oct|Nov|Dec) \d{1,2}-\d{1,2}:|\Z)",
            chunk,
            re.I | re.S,
        ):
            reading_text = _clean_hist103_reading_text(sm.group(1))
            if reading_text and len(reading_text) > 8:
                readings.append(reading_text)
        week_name = f"Week {mon} {d1}-{d2}: {title}"
        items.append(
            _hist103_sub_item(
                week_name,
                start_iso,
                due_iso,
                classify_hist103_sub_item("week", week_name),
                "Discussion Section",
                "week",
            )
        )
        for ri, reading in enumerate(readings, 1):
            reading_title = _hist103_reading_title(reading)
            if not reading_title:
                continue
            reading_name = f"{week_name} - Section reading {ri}: {reading_title}"
            items.append(
                _hist103_sub_item(
                    reading_name,
                    start_iso,
                    due_iso,
                    classify_hist103_sub_item("section_reading", reading_name),
                    "Discussion Section",
                    "section_reading",
                )
            )
        for dm in re.finditer(
            r"(Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}):\s*([^\n]*(?:Due|Paper Due)[^\n]*)",
            chunk,
            re.I,
        ):
            due_line = re.sub(r"\s+", " ", dm.group(3)).strip()
            due_iso_day = _hist_month_day_to_iso(dm.group(1), int(dm.group(2)), year)
            items.append(
                _hist103_sub_item(
                    due_line[:100],
                    "",
                    due_iso_day,
                    classify_hist103_sub_item("due", due_line),
                    _hist103_route(due_line),
                    "due",
                )
            )
        if re.search(r"Primary Source Activity", chunk, re.I):
            for dm in re.finditer(
                r"(Nov|Oct|Sep) (\d{1,2})[^\n]*Primary Source Activity[^\n]*",
                chunk,
                re.I,
            ):
                due_iso_day = _hist_month_day_to_iso(dm.group(1), int(dm.group(2)), year)
                psa_name = "Primary Source Activity (due in section)"
                items.append(
                    _hist103_sub_item(
                        psa_name,
                        "",
                        due_iso_day,
                        classify_hist103_sub_item("due", psa_name),
                        "Discussion Section",
                        "due",
                    )
                )
    # Explicit paper due lines elsewhere in syllabus
    for pat, label, cat, item_label in [
        (r"Due September 15th[^\n]*", "Sleep Paper due", "Sleep Paper", LABEL_ASSIGNMENT),
        (r"Due Nov 10 at[^\n]*", "Witchcraft Paper due", "Witchcraft Paper", LABEL_ASSIGNMENT),
        (r"Dec 10: Final Exam", "Final Exam", "Final Exam", LABEL_EXAM),
        (r"Oct 6: Midterm", "Midterm Exam", "Mid-term", LABEL_EXAM),
    ]:
        m = re.search(pat, text, re.I)
        if m:
            line = label
            dm = re.search(r"(Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2})", m.group(0), re.I)
            due_iso = ""
            if dm:
                due_iso = _hist_month_day_to_iso(dm.group(1), int(dm.group(2)), year)
            items.append(
                _hist103_sub_item(
                    line,
                    "",
                    due_iso,
                    item_label,
                    cat,
                    "due",
                )
            )
    return items


def _hist103_route(text: str) -> str:
    """Route explicit due lines only - never week schedule chunks."""
    low = text.lower()
    if re.search(r"\bsleep paper due\b", low):
        return "Sleep Paper"
    if re.search(r"\bwitchcraft paper due\b", low):
        return "Witchcraft Paper"
    if re.search(r"\boct 6:\s*midterm\b", low) or re.search(r"\bmidterm exam\b", low):
        return "Mid-term"
    if re.search(r"\bfinal exam\b", low) or re.search(r"\bdec 10:\s*final\b", low):
        return "Final Exam"
    if "primary source" in low or "section reading" in low or "readings for section" in low:
        return "Discussion Section"
    if "quiz" in low or "identification" in low:
        return "Identification Quizzes"
    if "extra credit" in low:
        return "Extra Credit"
    return "Discussion Section"


def _match_category_name(categories: list[Category], hint: str) -> str:
    hint_low = hint.lower()
    for cat in categories:
        if cat.name.lower() == hint_low:
            return cat.name
    aliases = {
        "sleep paper": "Sleep Paper",
        "witchcraft paper": "Witchcraft Paper",
        "mid-term": "Mid-term",
        "midterm exam": "Mid-term",
        "discussion section": "Discussion Section",
        "identification quizzes": "Identification Quizzes",
        "final exam": "Final Exam",
        "extra credit": "Extra Credit",
    }
    for key, name in aliases.items():
        if key in hint_low:
            for cat in categories:
                if cat.name.lower() == name.lower():
                    return cat.name
    for cat in categories:
        if hint_low in cat.name.lower() or cat.name.lower() in hint_low:
            return cat.name
    return categories[0].name if categories else hint


def build_full_syllabus_assignments(
    text: str, year: int, categories: list[Category]
) -> dict[str, list[dict]]:
    """Weekly readings and due dates for full syllabi (e.g. HIST-103)."""
    out: dict[str, list[dict]] = {c.name: [] for c in categories}
    if re.search(r"HIST\s*103|Emergence of Modern Europe", text, re.I):
        items = parse_hist103_weekly_items(text, year)
    else:
        items = []
    seen: set[tuple[str, str]] = set()
    seen_week_names: set[str] = set()
    for item in items:
        kind = item.get("kind", "")
        if kind == "week":
            item["category_hint"] = "Discussion Section"
            wk = item["name"].lower()
            if wk in seen_week_names:
                continue
            seen_week_names.add(wk)
        cat_name = _match_category_name(categories, item.pop("category_hint", ""))
        if cat_name not in out:
            out[cat_name] = []
        key = (cat_name, item["name"].lower())
        if key in seen:
            continue
        seen.add(key)
        out[cat_name].append({k: v for k, v in item.items() if k != "kind"})
    for cat_name, sub in out.items():
        sub.sort(key=lambda x: (x.get("start_date") or "", x.get("due_date") or "", x["name"]))
    return out


def find_marshall_evaluation_line(text: str, cat: Category) -> str:
    block = find_course_evaluation_block(text)
    if not block:
        return ""
    target = cat.name.lower()
    for line in block.splitlines():
        line = line.strip()
        if not line or line.lower() == "total":
            continue
        if line.lower().startswith(target):
            return line
    return ""


def gather_marshall_content(
    text: str, cat: Category, year: int, research_guide: str = ""
) -> tuple[dict, str, tuple[str, str]]:
    """Targeted extraction for Marshall percentage syllabi (BUAD-304 style)."""
    matched: list[str] = []
    sections: dict[str, list[str] | str] = {}
    eval_line = find_marshall_evaluation_line(text, cat)
    if eval_line:
        sections["Overview (Course Evaluation)"] = eval_line
        matched.append(eval_line)

    for block in find_dedicated_blocks(text, cat):
        matched.append(block)

    schedule = find_course_schedule_section(text)
    deliverables = parse_marshall_schedule_deliverables(schedule, year)
    key = marshall_category_key(cat.name)
    sched_lines = [
        f"Due: {d['date_iso']} | {d['raw'][:200]}"
        for d in deliverables
        if d["category"] == key
    ]
    if sched_lines:
        sections["Course Schedule (due dates)"] = sched_lines
        matched.extend(sched_lines)
    session_lines = schedule_lines_for_category(schedule, cat, year)
    if session_lines:
        sections["Course Schedule (dated sessions)"] = session_lines
        matched.extend(session_lines)

    if "participation" in cat.name.lower() and research_guide:
        milestones = parse_research_participation_milestones(research_guide, year)
        if milestones:
            items = [f"{m['date_iso']} ({m['kind']}): {m['label']}" for m in milestones]
            sections["Research Participation Guide (key dates)"] = items
            matched.extend(items)
        contacts = []
        if re.search(r"mor\.sona@marshall\.usc\.edu", research_guide, re.I):
            contacts.append("Marshall Behavioral Research Lab: mor.sona@marshall.usc.edu")
        if re.search(r"bit\.ly/MOR-BUAD", research_guide, re.I):
            contacts.append("Guide online: bit.ly/MOR-BUAD")
        if re.search(r"bit\.ly/SONA-BUAD304", research_guide, re.I):
            contacts.append("SONA registration walkthrough (3 min): bit.ly/SONA-BUAD304")
        if re.search(r"marshall-mor\.sona-systems\.com", research_guide, re.I):
            contacts.append("SONA registration: marshall-mor.sona-systems.com")
        if contacts:
            sections["Research Participation Guide (contacts)"] = contacts
            matched.extend(contacts)
        quick = re.search(
            r"QUICK REFERENCE(.+?)(?:Page \d+ of \d+|\Z)",
            research_guide,
            re.I | re.S,
        )
        if quick:
            snippet = re.sub(r"\s+", " ", quick.group(1)).strip()[:1200]
            sections["Research Participation Guide (quick reference excerpt)"] = snippet
            matched.append(snippet)

    matched = dedupe_passages(matched)
    verbatim = "\n\n---\n\n".join(matched)
    for block in matched:
        for heading, content in structure_block(block).items():
            if heading in sections:
                prev = sections[heading]
                if isinstance(prev, list) and isinstance(content, list):
                    prev.extend(content)
                elif isinstance(content, list):
                    sections[heading] = (
                        ([prev] if not isinstance(prev, list) else prev) + content
                    )
                else:
                    sections[heading] = content
            else:
                sections[heading] = content

    start, due = marshall_dates_for_category(cat, deliverables, schedule, year)
    if "participation" in cat.name.lower() and research_guide:
        rg_start, rg_due = research_dates_for_participation(
            parse_research_participation_milestones(research_guide, year)
        )
        start = rg_start or start
        due = rg_due or due

    return sections, verbatim, (start, due)


def infer_group_project(cat: Category, verbatim: str) -> bool:
    low = cat.name.lower()
    if "participation" in low:
        return False
    if any(
        x in low
        for x in (
            "team project",
            "proposal",
            "presentation",
            "peer evaluation",
            "self & peer",
        )
    ):
        return True
    if any(x in low for x in ("case analysis", "midterm", "final exam", "reflection")):
        return False
    return bool(GROUP_RE.search(verbatim))


def md_to_iso(md: str, year: int) -> str:
    m = re.match(r"(\d{1,2})/(\d{1,2})", (md or "").strip())
    if not m:
        return ""
    return f"{year:04d}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"


def calendar_row_date(row: dict) -> str:
    return row.get("date_mon") or row.get("date_wed") or ""


def format_calendar_row(row: dict, year: int = 2026, *, strip_certs: bool = False) -> str:
    """One clean verbatim line per calendar table row, with ISO due date when known."""
    parts: list[str] = []
    if row.get("class") and not re.search(r"december|final exam", row["class"], re.I):
        parts.append(f"Class {row['class']}")
    date = calendar_row_date(row)
    iso = md_to_iso(date, year)
    if iso:
        parts.append(f"Due: {iso} (8:00 am)")
    elif date:
        parts.append(f"Date: {date}")
    topic = row.get("topic") or ""
    if strip_certs and topic:
        topic = re.sub(r"\u2022?\s*Linked In Learning Excel[^\n/;]*75 Points\s*", "", topic, flags=re.I)
        topic = re.sub(r"\u2022?\s*Stukent Simternship[^\n/;]*75 Points\s*", "", topic, flags=re.I)
        topic = re.sub(r"\s+", " ", topic).strip(" ;/")
    if topic:
        parts.append(f"Topic: {topic.replace(' / ', '; ')}")
    if row.get("reading"):
        parts.append(f"Required Reading: {row['reading'].replace(' / ', '; ')}")
    if row.get("homework"):
        parts.append(f"Homework: {row['homework'].replace(' / ', '; ')}")
    return " | ".join(parts)


def extract_cert_phrase(blob: str, cert: str) -> str:
    flat = re.sub(r"\s+", " ", blob.replace(" / ", " "))
    patterns = {
        "linkedin": [
            r"Linked\s*In\s*Learning\s*Excel\s*Certification",
            r"Linked\s*In\s*Learning\s*Excel\s*-\s*75\s*Points",
        ],
        "stukent": [
            r"Stukent\s*Simternship\s*-\s*75\s*Points",
            r"Stukent\s*Simternship",
        ],
    }
    for pat in patterns.get(cert, []):
        m = re.search(pat, flat, re.I)
        if m:
            return m.group(0).strip()
    return ""


def format_cert_line(row: dict, cert: str, year: int) -> str:
    """Split combined calendar rows into one certification-specific line."""
    blob = " ".join(str(v) for v in row.values() if v)
    phrase = extract_cert_phrase(blob, cert)
    if not phrase:
        return ""
    parts: list[str] = []
    if row.get("class") and row["class"].isdigit():
        parts.append(f"Class {row['class']}")
    date = calendar_row_date(row)
    iso = md_to_iso(date, year)
    is_final_due = date == "12/2" or (iso and iso.endswith("-12-02"))
    if is_final_due:
        parts.append(f"Due: {iso or date} (11:59 PM)")
        parts.append(phrase)
        parts.append("Context: Final submission deadline (calendar footer)")
    elif iso:
        parts.append(f"Mentioned: {iso} (in-class announcement)")
        parts.append(phrase)
        parts.append("Context: Introduced during this session; submit by 12/2 11:59 PM")
    else:
        parts.append(phrase)
    return " | ".join(parts)


def build_merged_final_exam_block(text: str, rows: list[dict], year: int) -> str:
    """Single exam block merging points, schedule, chapters, and prerequisites."""
    plain = calendar_plain_text(text)
    parts: list[str] = []

    pts_m = re.search(r"Final Exam:\s*(\d+)\s*Points", plain, re.I)
    if pts_m:
        parts.append(f"Final Exam: {pts_m.group(1)} Points")

    final_row = next((r for r in rows if "december" in (r.get("class") or "").lower()), None)
    if final_row:
        schedule = final_row["class"].replace(" / ", "; ")
        parts.append(schedule)
        day_m = re.search(r"December\s+(\d{1,2})", schedule, re.I)
        if day_m:
            parts.append(f"ISO date: {year:04d}-12-{int(day_m.group(1)):02d}")
    else:
        dt_m = re.search(
            r"December\s+(\d{1,2})(?:st|nd|rd|th)?[^\n]*?(\d{1,2}:\d{2}\s*AM\s*-\s*\d{1,2}:\d{2}\s*AM\s*PST)",
            plain,
            re.I,
        )
        if dt_m:
            parts.append(
                f"Wednesday, December {dt_m.group(1)} | {dt_m.group(2)} | "
                f"ISO: {year:04d}-12-{int(dt_m.group(1)):02d}"
            )

    ch_m = re.search(r"Chapters 10, 11, 13, 14[^\n]*", plain, re.I)
    if ch_m:
        parts.append(re.sub(r"\s+", " ", ch_m.group(0)).strip())

    fn_m = re.search(
        r"Knowledge of Cost Behavior \(Chapter 6\)[^\n]+",
        plain,
        re.I,
    )
    if fn_m:
        parts.append(re.sub(r"\s+", " ", fn_m.group(0)).strip())

    return " | ".join(parts)


def calendar_cert_dates(rows: list[dict], cert: str, year: int) -> tuple[str, str]:
    """Start = first in-class mention; due = footer deadline (12/2)."""
    mentions: list[str] = []
    due_dates: list[str] = []
    cert_re = r"linked\s*in" if cert == "linkedin" else r"stukent"
    for r in rows:
        if not re.search(cert_re, " ".join(str(v) for v in r.values()), re.I):
            continue
        iso = md_to_iso(calendar_row_date(r), year)
        if not iso:
            continue
        if iso.endswith("-12-02"):
            due_dates.append(iso)
        else:
            mentions.append(iso)
    start = min(mentions) if mentions else ""
    due = max(due_dates) if due_dates else f"{year:04d}-12-02"
    return start, due


def calendar_homework_dates(rows: list[dict], year: int) -> tuple[str, str]:
    """Due span only - calendar lists session due dates, not explicit homework starts."""
    isos = sorted(
        md_to_iso(calendar_row_date(r), year)
        for r in rows
        if row_has_homework_points(r)
    )
    isos = [d for d in isos if d]
    return ("", isos[-1]) if isos else ("", "")


def gather_supplement_passages(supplement: str, cat: Category) -> list[str]:
    """Grep optional full syllabus supplement for category-specific instructions."""
    if not supplement:
        return []
    matched: list[str] = []
    seen: set[str] = set()
    for chunk in split_chunks(supplement):
        if chunk_matches_category(chunk, cat):
            key = normalize(chunk)
            if key not in seen:
                seen.add(key)
                matched.append(chunk)
    return dedupe_passages(matched)


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
    # Problem sets may share a cell with cert footer text (e.g. Class 2 / 12/2)
    hw_main = re.split(
        r"/\s*(?:Assignments listed|Linked\s*In|Stukent|Certification|Simternship)",
        hw,
        maxsplit=1,
        flags=re.I,
    )[0]
    if re.search(r"linked\s*in|stukent|certification|simternship", hw_main, re.I):
        return False
    return bool(
        re.search(r"\d+\s*[\-\u2013]?\s*Points?", hw_main, re.I)
        or re.search(r"\d-\d+", hw_main)
    )


def gather_calendar_content_from_table(
    rows: list[dict], cat: Category, text: str, year: int
) -> tuple[dict, str]:
    """Build clean verbatim from structured PDF table rows."""
    low = cat.name.lower()
    matched: list[str] = []
    sections: dict[str, list[str] | str] = {}
    exams = calendar_exam_snippets(text)
    supplement = parse_supplement_text(text)

    if "homework" in low:
        hw_rows = [r for r in rows if row_has_homework_points(r)]
        items = [format_calendar_row(r, year) for r in hw_rows]
        if items:
            sections["Homework Assignments (by due date)"] = items
            matched.extend(items)
    elif "midterm 1" in low:
        if exams["Midterm 1"]:
            sections["Exam"] = exams["Midterm 1"]
            matched.extend(exams["Midterm 1"])
        review = [
            format_calendar_row(r, year, strip_certs=True)
            for r in rows
            if re.search(r"catchup|midterm review|practice midterm", r.get("topic", ""), re.I)
            and not re.search(r"16-28, 16-40|midterm 2", format_calendar_row(r, year, strip_certs=True), re.I)
        ]
        if review:
            sections["Review & Practice"] = review
            matched.extend(review)
    elif "midterm 2" in low:
        if exams["Midterm 2"]:
            sections["Exam"] = exams["Midterm 2"]
            matched.extend(exams["Midterm 2"])
        review = [
            format_calendar_row(r, year)
            for r in rows
            if re.search(r"catchup|midterm review|practice midterm", r.get("topic", ""), re.I)
            and not re.search(r"8-28, 8-29", format_calendar_row(r, year))
            and (
                re.search(r"10/19|10/21|16-28", format_calendar_row(r, year))
                or "10/19" in r.get("date_mon", "")
                or "10/21" in r.get("date_wed", "")
            )
        ]
        if review:
            sections["Review & Practice"] = review
            matched.extend(review)
    elif "final" in low and "exam" in low:
        merged = build_merged_final_exam_block(text, rows, year)
        if merged:
            sections["Exam"] = merged
            matched.append(merged)
        review = [
            format_calendar_row(r, year)
            for r in rows
            if re.search(r"catchup & final|practice final", r.get("topic", ""), re.I)
        ]
        if review:
            sections["Review & Practice"] = review
            matched.extend(review)
    elif "linkedin" in low:
        mentions = [
            line
            for r in rows
            if re.search(r"linked\s*in\s*learning", " ".join(r.values()), re.I)
            for line in [format_cert_line(r, "linkedin", year)]
            if line
        ]
        due_line = f"Due: {year:04d}-12-02 (11:59 PM) - Assignments listed below due by 11:59 PM"
        sections["Assignment Details"] = mentions or ["LinkedIn Learning Excel Certification - 75 Points"]
        sections["Due Date & Submission"] = due_line
        matched.extend(mentions)
        matched.append(due_line)
    elif "stukent" in low:
        mentions = [
            line
            for r in rows
            if re.search(r"stukent", " ".join(r.values()), re.I)
            for line in [format_cert_line(r, "stukent", year)]
            if line
        ]
        due_line = f"Due: {year:04d}-12-02 (11:59 PM) - Assignments listed below due by 11:59 PM"
        sections["Assignment Details"] = mentions or ["Stukent Simternship - 75 Points"]
        sections["Due Date & Submission"] = due_line
        matched.extend(mentions)
        matched.append(due_line)

    sup_passages = gather_supplement_passages(supplement, cat)
    if sup_passages:
        sections["Additional Instructions (supplement syllabus)"] = sup_passages
        matched.extend(sup_passages)

    footnotes = calendar_footnotes(text)
    relevant_notes = list(footnotes)
    if "final" in low or "homework" in low:
        sections["Calendar Footnotes"] = relevant_notes
        matched.extend(relevant_notes)

    verbatim = "\n\n".join(dedupe_passages(matched))
    return sections, verbatim


def gather_calendar_content(text: str, cat: Category, year: int = 2025) -> tuple[dict, str]:
    """Collect calendar rows and context for a course-calendar category."""
    rows = parse_embedded_calendar_table(text)
    if rows:
        return gather_calendar_content_from_table(rows, cat, text, year)

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
        _, due = parse_dates_from_text(text, year)
        return "", due

    unique = sorted(set(dates))
    return "", unique[-1]


def find_course_evaluation_block(text: str) -> str:
    """Locate Course Evaluation / grading breakdown (Marshall-style syllabi)."""
    m = re.search(r"Course Evaluation\s*\n", text, re.I)
    if not m:
        return ""
    snippet = text[m.end() : m.end() + 2500]
    end = re.search(r"\nTotal\s+100\s*%|\nFinal grades represent", snippet, re.I)
    return snippet[: end.start()] if end else snippet[:1200]


def _drop_aggregate_parents(cats: list[Category]) -> list[Category]:
    """Remove parent rows when child weights sum to the parent (e.g. Team Project 30%)."""
    by_name = {c.name: c for c in cats}
    drop: set[str] = set()
    aggregates = {
        "Individual Assignments": [
            "Midterm Exam",
            "Case Analysis Assignments",
            "Final Reflection Paper",
        ],
        "Team Project": [
            "Proposal & Team Contract",
            "Paper",
            "Presentation",
            "Self & Peer Evaluation",
        ],
    }
    for parent, children in aggregates.items():
        if parent not in by_name:
            continue
        child_sum = sum(by_name[c].weight or 0 for c in children if c in by_name)
        if abs(child_sum - (by_name[parent].weight or 0)) < 0.01:
            drop.add(parent)
    filtered = [c for c in cats if c.name not in drop]
    for c in filtered:
        if c.name == "Paper":
            c.name = "Team Project Paper"
            c.aliases = make_aliases("Team Project Paper")
    return filtered


def parse_course_evaluation_categories(text: str) -> list[Category]:
    """Parse 'Participation 15%' style lines from a Course Evaluation block."""
    block = find_course_evaluation_block(text)
    if not block:
        return []
    cats: list[Category] = []
    for line in block.splitlines():
        line = line.strip()
        cm = re.match(r"^(.+?)\s+(\d+(?:\.\d+)?)\s*%\s*$", line)
        if not cm:
            continue
        name = cm.group(1).strip()
        if name.lower() == "total":
            continue
        cats.append(
            Category(
                name=name,
                weight=float(cm.group(2)),
                weight_unit="percent",
                aliases=make_aliases(name),
            )
        )
    return _drop_aggregate_parents(cats)


def find_grading_policies_block(text: str) -> str:
    m = re.search(r"Grading Policies\s*\n", text, re.I)
    if not m:
        return ""
    snippet = text[m.end() : m.end() + 4500]
    end = re.search(r"\nCOURSE CALENDAR\b|\nCollaboration policy\b", snippet, re.I)
    return snippet[: end.start()] if end else snippet[:3500]


def parse_grading_policies_categories(text: str) -> list[Category]:
    """Parse 'First midterm exam 20 20.0%' rows from Grading Policies (ECON-351 style)."""
    block = find_grading_policies_block(text)
    if not block:
        return []
    cats: list[Category] = []
    for line in block.splitlines():
        line = line.strip()
        cm = re.match(
            r"^(.+?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s*%\s*$",
            line,
        )
        if not cm:
            continue
        name = cm.group(1).strip()
        if name.lower() == "total":
            continue
        if name.lower().startswith("forth midterm"):
            name = "Fourth midterm exam"
        cats.append(
            Category(
                name=name,
                weight=float(cm.group(3)),
                weight_unit="percent",
                aliases=make_aliases(name),
            )
        )
    return cats


def econ_dot_date_to_iso(raw: str, year: int) -> str:
    """Parse Sep.4 or Sep/14 style dates from ECON-351 calendar/prose."""
    raw = raw.strip()
    m = re.match(r"([A-Za-z]+)[./](\d{1,2})", raw)
    if not m:
        return ""
    mon = HIST_MONTH.get(m.group(1)[:3].lower(), 0)
    if not mon:
        return ""
    return f"{year:04d}-{mon:02d}-{int(m.group(2)):02d}"


def parse_econ351_week_end(class_field: str, year: int) -> str:
    flat = (class_field or "").replace(" / ", "")
    m = re.search(
        r"([A-Za-z]+)\.(\d{1,2})/(?:([A-Za-z]+)\.)?(\d{1,2})",
        flat,
        re.I,
    )
    if not m:
        m2 = re.search(r"([A-Za-z]+)\.(\d{1,2})\b", flat, re.I)
        if m2:
            return econ_dot_date_to_iso(f"{m2.group(1)}.{m2.group(2)}", year)
        return ""
    end_mon = m.group(3) or m.group(1)
    end_day = m.group(4) if m.group(3) else m.group(2)
    return econ_dot_date_to_iso(f"{end_mon}.{end_day}", year)


def econ351_midterm_number(cat_name: str) -> int:
    low = cat_name.lower()
    for word, num in (("first", 1), ("second", 2), ("third", 3), ("fourth", 4), ("forth", 4)):
        if word in low:
            return num
    return 0


def parse_econ351_exam_dates(text: str, year: int) -> dict[int, str]:
    out: dict[int, str] = {}
    for m in re.finditer(
        r"Midterm\s+(\d+):\s*(?:Monday|Wednesday)?\s*([A-Za-z]+)/(\d{1,2})",
        text,
        re.I,
    ):
        out[int(m.group(1))] = econ_dot_date_to_iso(f"{m.group(2)}.{m.group(3)}", year)
    return out


def _econ351_wed_bullets(date_wed: str) -> list[str]:
    flat = (date_wed or "").replace(" / ", " ").strip()
    parts = re.split(r"\s*•\s*", flat)
    return [re.sub(r"\s+", " ", p).strip() for p in parts if p.strip()]


def _econ351_is_homework_bullet(bullet: str) -> bool:
    return bool(
        re.search(
            r"Complete the .*homework|homework on Brightspace|course survey on Brightspace",
            bullet,
            re.I,
        )
    )


def parse_econ351_homework_and_readings(rows: list[dict], year: int) -> list[dict]:
    """Reading + Homework sub-rows from embedded COURSE CALENDAR table."""
    items: list[dict] = []
    for row in rows:
        week = (row.get("class") or "").replace(" / ", " ").strip()
        week_end = parse_econ351_week_end(row.get("class") or "", year)
        reading_col = (row.get("reading") or "").replace(" / ", " ")
        hw_m = re.search(r"Homework\s+(\d+)\s*/?\s*([A-Za-z]+)[./](\d+)", reading_col, re.I)
        due_iso = ""
        hw_num = ""
        if hw_m:
            hw_num = hw_m.group(1)
            due_iso = econ_dot_date_to_iso(f"{hw_m.group(2)}.{hw_m.group(3)}", year)
        elif week_end and (row.get("date_wed") or "").strip():
            due_iso = week_end

        for bullet in _econ351_wed_bullets(row.get("date_wed") or ""):
            if _econ351_is_homework_bullet(bullet):
                continue
            if len(bullet) < 8:
                continue
            prefix = week or "Week"
            items.append(
                sub_assignment(
                    f"{prefix} - {bullet[:100]}",
                    "",
                    due_iso,
                    LABEL_READING,
                )
            )

        if hw_num and due_iso:
            chapter_hint = ""
            for bullet in _econ351_wed_bullets(row.get("date_wed") or ""):
                ch = re.search(r"Chapter\s+\d+", bullet, re.I)
                if ch:
                    chapter_hint = f" ({ch.group(0)})"
                    break
            items.append(
                sub_assignment(
                    f"Homework {hw_num}{chapter_hint} — Brightspace, due 11:59 pm",
                    "",
                    due_iso,
                    LABEL_HOMEWORK,
                )
            )
    return items


def parse_econ351_midterm_coverage(rows: list[dict], exam_num: int) -> str:
    for i, row in enumerate(rows):
        topic = (row.get("topic") or "").replace(" / ", " ")
        m = re.search(
            rf"Midterm\s+{exam_num}\s+covers\s+(.+)",
            topic,
            re.I,
        )
        if m:
            cov = m.group(1).strip()
            if re.search(r"\band\s*$", cov) and i + 1 < len(rows):
                nxt = (rows[i + 1].get("topic") or "").replace(" / ", " ").strip()
                if nxt and len(nxt) < 40 and not re.search(r"midterm|exam|•", nxt, re.I):
                    cov = f"{cov} {nxt}"
            return re.sub(r"\s+", " ", cov).strip()
    return ""


def build_econ351_assignments_by_category(
    text: str,
    year: int,
    categories: list[Category],
) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {c.name: [] for c in categories}
    rows = parse_embedded_calendar_table(text)
    exam_dates = parse_econ351_exam_dates(text, year)

    hw_items = parse_econ351_homework_and_readings(rows, year) if rows else []
    for cat in categories:
        low = cat.name.lower()
        if low == "homework":
            out[cat.name] = hw_items
        elif "midterm" in low and "exam" in low:
            num = econ351_midterm_number(cat.name)
            due = exam_dates.get(num, "")
            coverage = parse_econ351_midterm_coverage(rows, num) if rows else ""
            label = f"Midterm {num} (in class)"
            if coverage:
                label = f"Midterm {num} — covers {coverage}"
            out[cat.name] = [sub_assignment(label, "", due, LABEL_EXAM)]
        elif "ai forecast" in low:
            part_i = ""
            part_ii = ""
            for pat in (
                r"Part I due\s+([A-Za-z]+)\s+(\d+)",
                r"AI Project[^\n]{0,40}Part I due\s+([A-Za-z]+)\s+(\d+)",
            ):
                m_i = re.search(pat, text, re.I)
                if m_i:
                    part_i = econ_dot_date_to_iso(f"{m_i.group(1)}.{m_i.group(2)}", year)
                    break
            m_ii = re.search(r"Part II due\s+([A-Za-z]+)\s+(\d+)", text, re.I)
            if m_ii:
                part_ii = econ_dot_date_to_iso(f"{m_ii.group(1)}.{m_ii.group(2)}", year)
            out[cat.name] = [
                sub_assignment("AI Forecast Project — Part I", "", part_i, LABEL_ASSIGNMENT),
                sub_assignment("AI Forecast Project — Part II", "", part_ii, LABEL_ASSIGNMENT),
            ]
    return out


def find_grading_policies_line(text: str, cat: Category) -> str:
    block = find_grading_policies_block(text)
    if not block:
        return ""
    target = cat.name.lower()
    for line in block.splitlines():
        line = line.strip()
        if line.lower().startswith(target.split()[0]) and re.search(r"\d+(?:\.\d+)?\s*%\s*$", line):
            return line
        if normalize(line).startswith(normalize(cat.name)):
            return line
    return ""


def gather_econ351_content(
    text: str, cat: Category, year: int
) -> tuple[dict, str, tuple[str, str]]:
    matched: list[str] = []
    sections: dict[str, list[str] | str] = {}
    gp_line = find_grading_policies_line(text, cat)
    if gp_line:
        sections["Overview (Grading Policies)"] = gp_line
        matched.append(gp_line)

    for block in find_dedicated_blocks(text, cat):
        matched.append(block)

    rows = parse_embedded_calendar_table(text)
    cal_lines: list[str] = []
    low = cat.name.lower()
    if low == "homework":
        for item in parse_econ351_homework_and_readings(rows, year):
            cal_lines.append(
                f"Due: {item.get('due_date', '')} | {item.get('name', '')}"
            )
    elif "midterm" in low and "exam" in low:
        num = econ351_midterm_number(cat.name)
        due = parse_econ351_exam_dates(text, year).get(num, "")
        cov = parse_econ351_midterm_coverage(rows, num)
        if due:
            cal_lines.append(f"Exam date: {due}")
        if cov:
            cal_lines.append(f"Coverage: {cov}")
    elif "ai forecast" in low:
        for row in rows:
            blob = " ".join(
                filter(
                    None,
                    [
                        row.get("date_wed") or "",
                        row.get("topic") or "",
                        row.get("date_mon") or "",
                    ],
                )
            )
            if re.search(r"AI Project", blob, re.I):
                cal_lines.append(re.sub(r"\s+", " ", blob.replace(" / ", "; "))[:200])
    if cal_lines:
        sections["Course Calendar (schedule)"] = cal_lines
        matched.extend(cal_lines)

    matched = dedupe_passages(matched)
    verbatim = "\n\n---\n\n".join(matched)
    for block in matched:
        for heading, content in structure_block(block).items():
            if heading in sections:
                prev = sections[heading]
                if isinstance(prev, list) and isinstance(content, list):
                    prev.extend(content)
                elif isinstance(content, list):
                    sections[heading] = (
                        ([prev] if not isinstance(prev, list) else prev) + content
                    )
                else:
                    sections[heading] = content
            else:
                sections[heading] = content

    start, due = "", ""
    if low == "homework":
        dues = sorted(
            {item.get("due_date") for item in parse_econ351_homework_and_readings(rows, year) if item.get("due_date")}
        )
        due = dues[-1] if dues else ""
    elif "midterm" in low and "exam" in low:
        due = parse_econ351_exam_dates(text, year).get(econ351_midterm_number(cat.name), "")
    elif "ai forecast" in low:
        m_ii = re.search(r"Part II due\s+([A-Za-z]+)\s+(\d+)", text, re.I)
        if m_ii:
            due = econ_dot_date_to_iso(f"{m_ii.group(1)}.{m_ii.group(2)}", year)

    return sections, verbatim, (start, due)


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
    if block:
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

    if not cats:
        cats = parse_grading_policies_categories(text)

    if not cats:
        cats = parse_course_evaluation_categories(text)

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
    if scale["a_threshold"] == "N/A" and re.search(
        r"Final grades represent how you perform.*relative to other students",
        text,
        re.I | re.S,
    ):
        scale["a_threshold"] = "Curved (class rank)"
        scale["raw_scale"] = (
            "Weighted score (% of points earned) + class average + student ranking "
            "(relative grading - no fixed A threshold in syllabus)"
        )
    if scale["a_threshold"] == "N/A":
        lm = re.search(
            r"above\s+(\d+)%\s+an\s+A|grades between 70% and 85% a B.*?above\s+(\d+)%\s+an\s+A",
            text,
            re.I | re.S,
        )
        if lm:
            pct = lm.group(1) or lm.group(2)
            scale["a_threshold"] = f"{pct}%+ (rough guideline)"
            scale["scale_type"] = "percentage"
            block = re.search(
                r"Letter Grades\s*-(.+?)(?:\nCollaboration|\nEvaluation of)",
                text,
                re.I | re.S,
            )
            if block:
                scale["raw_scale"] = re.sub(r"\s+", " ", block.group(1)).strip()[:800]
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
    if "case analysis" in low:
        specs += [
            (r"Case Analysis Assignments\.", [r"\nFinal Reflection Paper", r"\nTeam Project"]),
        ]
    if "reflection" in low and "paper" in low:
        specs += [
            (r"Final Reflection Paper\.", [r"\nTeam Project", r"\nFinal Exam"]),
        ]
    if "team project" in low and "paper" in low:
        specs += [
            (r"Team Project\s*\n", [r"\nFinal Exam", r"\nOnline Class Expectations"]),
        ]
    if "participation" in low:
        specs += [
            (r"Participation\s*\nAttendance Policy", [r"\nIndividual Assignments", r"\n4\n"]),
        ]
    if "mid" in low and "term" in low and "hist" not in low:
        specs += [
            (r"Midterm Exam\.", [r"\nCase Analysis", r"\nTeam Project"]),
        ]
    if "proposal" in low and "contract" in low:
        specs += [
            (r"Team Project\s*\n", [r"\nFinal Exam", r"\nOnline Class Expectations"]),
        ]
    if low == "presentation":
        specs += [
            (r"Team Project\s*\n", [r"\nFinal Exam", r"\nOnline Class Expectations"]),
        ]
    if "peer evaluation" in low or "self & peer" in low:
        specs += [
            (r"Team Project\s*\n", [r"\nFinal Exam", r"\nOnline Class Expectations"]),
        ]
    if "final" in low and "exam" in low and "hist" not in low:
        specs += [
            (r"Final Exam\s*\n", [r"\nOnline Class Expectations", r"\nCourse Notes"]),
        ]
    if is_grading_policies_syllabus(clean):
        if low == "homework":
            specs += [(r"Homework\s*-\s*We will have", [r"\nWSJ Future View", r"\nExams\s*-"])]
        if "midterm" in low and "exam" in low:
            specs += [
                (r"Exams\s*-\s*The four midterms", [r"\nFinal Project", r"\nLetter Grades"]),
                (r"Makeup Tests\s*-", [r"\nHomework\s*-"]),
            ]
        if "ai forecast" in low:
            specs += [(r"Final Project\s*[–-]\s*The AI Forecasting", [r"\nLetter Grades", r"\nCollaboration"])]
        if "extra credit" in low:
            specs += [(r"WSJ Future View\s*-?\s*Extra credit", [r"\nExams\s*-", r"\nFinal Project"])]

    # Generic schedule due-line (skip Extra Credit - no stable end marker)
    if "extra credit" not in low and not (
        is_grading_policies_syllabus(clean) and low == "homework"
    ):
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
    """Extract due date only. Never infer a start date from grep/context windows."""
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
    return "", due


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


def infer_year(term: str, text: str = "", source_hint: str = "") -> int:
    """Academic year for ISO dates - prefer explicit term/text, else calendar heuristics."""
    for src in (term, text[:20000], source_hint):
        m = re.search(r"(20\d{2})", src or "")
        if m:
            return int(m.group(1))
    if is_course_calendar(text) or re.search(r"\bCourse Calendar\b", text[:800], re.I):
        from datetime import date

        return date.today().year
    from datetime import date

    return date.today().year


def infer_term(text: str, year: int) -> str:
    """Best-effort term when syllabus omits it (common on calendar-only PDFs)."""
    tm = re.search(
        r"(?:Syllabus\s*-\s*)?(Fall|Spring|Summer|Winter)\s+(20\d{2})",
        text[:15000],
        re.I,
    )
    if tm:
        return f"{tm.group(1).title()} {tm.group(2)}"
    months: list[int] = []
    for row in parse_embedded_calendar_table(text):
        for key in ("date_mon", "date_wed"):
            raw = str(row.get(key) or "")
            if "/" in raw:
                try:
                    months.append(int(raw.split("/")[0]))
                except ValueError:
                    pass
    if months:
        if min(months) >= 8:
            return f"Fall {year}"
        if max(months) <= 5:
            return f"Spring {year}"
    if re.search(r"\bHIST\s*103\b|Emergence of Modern Europe", text[:5000], re.I):
        return f"Fall {year}"
    return ""


def parse_syllabus_metadata(text: str, source_hint: str = "") -> dict[str, str]:
    """Best-effort class code, title, instructor, and term from syllabus text or filename."""
    meta: dict[str, str] = {}
    head = text[:15000]
    skip_codes = {"PDF", "LO", "ISO", "ARES", "ONLY", "NOT", "THE", "AND", "LL"}

    em = re.search(r"ECON\s*351x?\s*[–-]\s*([^\n]+)", head, re.I)
    if em:
        meta["code"] = "ECON-351"
        meta["name"] = em.group(1).strip()[:100]

    m = re.search(r"\b([A-Z]{2,5})[\s-](\d{3}[A-Z]?)\s*:\s*([^\n]+)", head)
    if m and m.group(1) not in skip_codes:
        meta["code"] = f"{m.group(1)}-{m.group(2)}"
        meta["name"] = m.group(3).strip()[:100]

    if not meta.get("code"):
        for m in re.finditer(r"\b([A-Z]{2,5})[\s-]?(\d{3}[A-Z]?)\b", head):
            if m.group(1) not in skip_codes:
                meta["code"] = f"{m.group(1)}-{m.group(2)}"
                break

    hint = source_hint.lower()
    if not meta.get("code") and hint:
        hm = re.search(r"(hist|buad|acct|econ|math|writ|chem|phys)[-_ ]?(\d{3})", hint, re.I)
        if hm:
            meta["code"] = f"{hm.group(1).upper()}-{hm.group(2)}"

    tm = re.search(
        r"(?:Syllabus\s*-\s*)?(Fall|Spring|Summer|Winter)\s+(20\d{2})",
        head,
        re.I,
    )
    if tm:
        meta["term"] = f"{tm.group(1).title()} {tm.group(2)}"

    im = re.search(
        r"(?:HIST[-\s]?103|BUAD[-\s]?\d{3})[^\n]+\n(?:[^\n]+\n)?"
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+(?:\s+[IVXLC]+)?)\s*$",
        head,
        re.M,
    )
    if im and "module" not in im.group(1).lower():
        meta["instructor"] = im.group(1).strip()

    for pat in (
        r"Professors?:?\s*([^\n]+)",
        r"Professor:?\s*([^\n]+)",
        r"Instructor:?\s*([^\n]+)",
        r"Faculty:?\s*([^\n]+)",
    ):
        im = re.search(pat, head, re.I)
        if im:
            name = im.group(1).strip()
            name = re.sub(r",\s*(MBA|PhD|EdD|JD)[^,\n]*", "", name, flags=re.I).strip()
            if (
                3 < len(name) < 70
                and "module" not in name.lower()
                and "teaching assistant" not in name.lower()
            ):
                meta["instructor"] = name
                break

    if not meta.get("instructor"):
        im = re.search(
            r"(?:Dr\.?\s+)?([A-Z][a-z]+(?:\s+[A-Z][\'a-z]+)+)\s*\n",
            head[:3000],
        )
        if im and "teaching assistant" not in im.group(0).lower():
            meta["instructor"] = im.group(1).strip()

    if not meta.get("name"):
        tm2 = re.search(r"Course (?:Title|Name):?\s*([^\n]+)", head, re.I)
        if tm2:
            meta["name"] = tm2.group(1).strip()[:100]

    bad_instructor = re.compile(
        r"course calendar|teaching assistant|brightspace|module|syllabus|assignments",
        re.I,
    )
    if meta.get("instructor") and bad_instructor.search(meta["instructor"]):
        del meta["instructor"]

    if "managerial accounting" in head.lower():
        meta.setdefault("code", "BUAD-281")
        meta.setdefault("name", "Managerial Accounting")
        if not meta.get("instructor"):
            meta["instructor"] = "George Braunegg"

    return meta


def merge_class_metadata(
    text: str,
    class_code: str = "",
    class_name: str = "",
    instructor: str = "",
    term: str = "",
    source_hint: str = "",
) -> dict[str, str]:
    detected = parse_syllabus_metadata(text, source_hint)
    code = (class_code or detected.get("code") or "").strip()
    if not code:
        raise SystemExit(
            "Could not detect class code. Pass --class-code or use a filename like buad-281-source.pdf."
        )
    resolved_term = (term or detected.get("term") or "").strip()
    resolved_year = infer_year(resolved_term, text, source_hint)
    if not resolved_term:
        resolved_term = infer_term(text, resolved_year)
    return {
        "code": code,
        "name": (class_name or detected.get("name") or "").strip(),
        "instructor": (instructor or detected.get("instructor") or "").strip(),
        "term": resolved_term,
    }


def sanitize_start_date(iso: str, year: int) -> str:
    """Drop unverified or pre-term starts; leave Start Date blank in Excel."""
    if not iso or iso.upper() == "N/A":
        return ""
    cutoff = f"{year:04d}-08-01"
    if iso < cutoff:
        return ""
    return iso


def strip_false_start_when_same_as_due(start: str, due: str) -> str:
    """Never copy the due date into Start Date (common false detection)."""
    if start and due and start == due:
        return ""
    return start


EXPLICIT_START_MARKERS = re.compile(
    r"\b(?:opens?|opening|available(?:\s+from|\s+on)?|assigned|begins?|starts?|"
    r"introduced|mentioned|announced|get\s+started|registration\s+opens?)\b",
    re.I,
)
MONTHS_SHORT = (
    "jan",
    "feb",
    "mar",
    "apr",
    "may",
    "jun",
    "jul",
    "aug",
    "sep",
    "oct",
    "nov",
    "dec",
)


def _category_rubric_text(cat: dict) -> str:
    """Concatenate extracted_text + structured sections for rubric checks."""
    parts = [cat.get("extracted_text") or ""]
    for value in (cat.get("sections") or {}).values():
        if isinstance(value, list):
            parts.extend(str(v) for v in value)
        elif isinstance(value, str):
            parts.append(value)
    return "\n".join(parts)


def _item_rubric_snippet(rubric: str, item_name: str, window: int = 420) -> str:
    """Narrow rubric window to the homework item (Connect code, problem set, etc.)."""
    if not rubric or not item_name:
        return rubric
    needles: list[str] = []
    code = re.search(r"(\d+\.\d+)", item_name)
    if code:
        needles.append(code.group(1))
    needles.append(item_name.replace("Connect: ", "")[:48].strip())
    for needle in needles:
        if not needle:
            continue
        idx = rubric.lower().find(needle.lower())
        if idx >= 0:
            return rubric[max(0, idx - window) : idx + window]
    return rubric


def _iso_in_rubric_snippet(iso: str, snippet: str) -> bool:
    if not iso or not snippet:
        return False
    if iso in snippet:
        return True
    _, mo, day = iso.split("-")
    month_i = int(mo)
    day_i = int(day)
    md = [
        f"{month_i}/{day_i}",
        f"{month_i:02d}/{day_i:02d}",
    ]
    if any(m in snippet for m in md):
        return True
    mon = MONTHS_SHORT[month_i - 1]
    return bool(re.search(rf"\b{mon}\w*\s+{day_i}\b", snippet, re.I))


def rubric_explicitly_states_start(rubric: str, start_iso: str, item_name: str = "") -> bool:
    """True only when raw rubric prose states when work begins (not just a due/session date)."""
    if not start_iso or not rubric:
        return False
    snippet = _item_rubric_snippet(rubric, item_name) if item_name else rubric
    if not EXPLICIT_START_MARKERS.search(snippet):
        return False
    return _iso_in_rubric_snippet(start_iso, snippet)


def sharpen_dates_from_text(text: str, year: int) -> tuple[str, str]:
    """Sharpen due/start only when syllabus prose states them explicitly."""
    start = ""
    due = ""
    m = re.search(
        r"Sharpen[^\n]{0,240}?(?:opens?|available|from|due)[^\n]{0,80}?(\d{1,2}/\d{1,2})",
        text,
        re.I,
    )
    if m:
        iso = _normalize_md_date(m.group(1), year)
        ctx = text[max(0, m.start() - 40) : m.end() + 40]
        if re.search(r"\b(?:opens?|available|from|start)\b", ctx, re.I):
            start = sanitize_start_date(iso, year)
        if re.search(r"\bdue\b", ctx, re.I):
            due = iso
    if not due:
        due = _normalize_md_date(MARSHALL_SHARPEN_DUE, year)
    return start, due


def strip_unverified_homework_starts(categories: list[dict]) -> None:
    """Homework rows: blank Start Date unless the category rubric explicitly lists one."""
    for cat in categories:
        rubric = _category_rubric_text(cat)
        is_hw_category = (
            cat.get("name", "").lower() == "homework"
            or cat.get("name") == MARSHALL_CONNECT_CATEGORY
        )
        if is_hw_category and cat.get("start_date"):
            if not rubric_explicitly_states_start(rubric, cat["start_date"], cat.get("name", "")):
                cat["start_date"] = ""
        for sub in cat.get("assignments") or []:
            if sub.get("notes") != LABEL_HOMEWORK:
                continue
            if sub.get("start_date") and not rubric_explicitly_states_start(
                rubric, sub["start_date"], sub.get("name", "")
            ):
                sub["start_date"] = ""


def apply_start_date_cutoff(categories: list[dict], year: int) -> None:
    for cat in categories:
        cat["start_date"] = sanitize_start_date(cat.get("start_date", ""), year)
        cat["start_date"] = strip_false_start_when_same_as_due(
            cat["start_date"], cat.get("due_date", "")
        )
        for sub in cat.get("assignments") or []:
            sub["start_date"] = sanitize_start_date(sub.get("start_date", ""), year)
            sub["start_date"] = strip_false_start_when_same_as_due(
                sub["start_date"], sub.get("due_date", "")
            )
    strip_unverified_homework_starts(categories)


def dissect(
    text: str,
    class_code: str = "",
    class_name: str = "",
    instructor: str = "",
    term: str = "",
    color: str = "",
    source_hint: str = "",
) -> dict:
    meta = merge_class_metadata(text, class_code, class_name, instructor, term, source_hint)
    class_code = meta["code"]
    class_name = meta["name"]
    instructor = meta["instructor"]
    term = meta["term"]
    calendar_mode = is_point_course_calendar(text)
    grading_policies_mode = is_grading_policies_syllabus(text)
    marshall_mode = is_marshall_syllabus(text)
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
    year = infer_year(term, text, source_hint)
    research_guide = parse_research_guide_text(text)
    assignment_map: dict[str, list[dict]] = {}
    marshall_connect_items: list[dict] = []
    if marshall_mode:
        assignment_map, marshall_connect_items = build_marshall_assignments_by_category(
            text, year, research_guide, categories
        )
    elif grading_policies_mode:
        assignment_map = build_econ351_assignments_by_category(text, year, categories)
    elif calendar_mode:
        assignment_map = build_calendar_assignments_by_category(text, year, categories)
    else:
        assignment_map = build_full_syllabus_assignments(text, year, categories)
    result_categories = []
    for cat in categories:
        if calendar_mode:
            sections, verbatim = gather_calendar_content(text, cat, year)
            rows = parse_embedded_calendar_table(text)
            low = cat.name.lower()
            if "homework" in low and rows:
                start, due = calendar_homework_dates(rows, year)
            elif "linkedin" in low and rows:
                start, due = calendar_cert_dates(rows, "linkedin", year)
            elif "stukent" in low and rows:
                start, due = calendar_cert_dates(rows, "stukent", year)
            else:
                start, due = parse_calendar_dates(text, cat, year)
        elif marshall_mode:
            sections, verbatim, (start, due) = gather_marshall_content(
                text, cat, year, research_guide=research_guide
            )
        elif grading_policies_mode:
            sections, verbatim, (start, due) = gather_econ351_content(text, cat, year)
        else:
            sections, verbatim = gather_category_content(text, cat)
            supplement = parse_supplement_text(text)
            if supplement:
                sup = gather_supplement_passages(supplement, cat)
                if sup:
                    sections["Additional Instructions (supplement syllabus)"] = sup
                    verbatim = verbatim + "\n\n---\n\n" + "\n\n---\n\n".join(sup) if verbatim else "\n\n---\n\n".join(sup)
            start, due = parse_dates_from_text(verbatim, year)
        result_categories.append(
            {
                "name": cat.name,
                "weight": cat.weight,
                "weight_unit": cat.weight_unit,
                "start_date": start,
                "due_date": due,
                "is_group_project": infer_group_project(cat, verbatim),
                "assignments": assignment_map.get(cat.name, []),
                "sections": sections,
                "extracted_text": verbatim,
            }
        )
    if marshall_mode and marshall_connect_items:
        conn_sections, conn_verbatim = gather_marshall_connect_content(text)
        result_categories.append(
            {
                "name": MARSHALL_CONNECT_CATEGORY,
                "weight": None,
                "weight_unit": "percent",
                "start_date": "",
                "due_date": _normalize_md_date(MARSHALL_CONNECT_DUE, year),
                "is_group_project": False,
                "assignments": marshall_connect_items,
                "sections": conn_sections,
                "extracted_text": conn_verbatim,
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
    apply_start_date_cutoff(result_categories, year)
    payload: dict = {
        "class": cls,
        "grading_scale": grading_scale,
        "categories": result_categories,
    }
    code_key = re.sub(r"\s+", "-", class_code.strip().upper())
    if code_key == "BUAD-281" and calendar_mode:
        payload["strategy"] = BUAD_281_STRATEGY
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-dissect syllabus text to JSON.")
    parser.add_argument("text_file", help="Extracted syllabus plain text")
    parser.add_argument("--class-code", default="", help="Optional if detectable from text/filename")
    parser.add_argument("--class-name", default="")
    parser.add_argument("--instructor", default="")
    parser.add_argument("--term", default="")
    parser.add_argument("--color", default="")
    parser.add_argument("--source-hint", default="", help="Original PDF filename for metadata fallback")
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
        source_hint=args.source_hint or args.text_file,
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
