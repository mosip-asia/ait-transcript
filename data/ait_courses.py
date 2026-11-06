"""Adapted from ../design/ait_courses.py (frozen, vendored from inji/credential-lab).

Changes vs. the frozen copy:
- PackValidationError is defined locally instead of imported from
  credential_lab.domain.pack, which doesn't exist in this repo.
- render_course_table_html() and the HTML course-table claim it fed are gone
  (ticket 06): every claim is signed now, and the credential carries the course
  record once, as `courses`. The frozen ../design/ copy still renders the table.

Do not edit ../design/ait_courses.py to match — that file is the frozen
reference copy (see wiki/concepts/transcript-credential.md).
"""

from __future__ import annotations

import json
from typing import Any


class PackValidationError(ValueError):
    pass


_COURSE_KEYS = ("no", "title", "lab", "lec", "credits", "grade")


def parse_courses(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            raise PackValidationError("courses must not be empty")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise PackValidationError(f"courses must be valid JSON: {exc}") from exc
    else:
        data = raw
    if not isinstance(data, list) or not data:
        raise PackValidationError("courses must be a non-empty JSON array")
    semesters: list[dict[str, Any]] = []
    for i, block in enumerate(data):
        if not isinstance(block, dict):
            raise PackValidationError(f"courses[{i}] must be an object")
        term = str(block.get("term", "")).strip()
        if not term:
            raise PackValidationError(f"courses[{i}].term is required")
        courses_raw = block.get("courses")
        if not isinstance(courses_raw, list):
            raise PackValidationError(f"courses[{i}].courses must be an array")
        courses: list[dict[str, str]] = []
        for j, c in enumerate(courses_raw):
            if not isinstance(c, dict):
                raise PackValidationError(f"courses[{i}].courses[{j}] must be an object")
            course = {k: str(c.get(k, "")).strip() for k in _COURSE_KEYS}
            if not course["no"] or not course["title"]:
                raise PackValidationError(
                    f"courses[{i}].courses[{j}] needs no and title"
                )
            courses.append(course)
        semesters.append(
            {
                "term": term,
                "courses": courses,
                "credits": str(block.get("credits", "")).strip(),
                "gpa": str(block.get("gpa", "")).strip(),
                "cumGpa": str(block.get("cumGpa", "")).strip(),
            }
        )
    return semesters


def canonicalize_courses_json(semesters: list[dict[str, Any]]) -> str:
    return json.dumps(semesters, separators=(",", ":"), ensure_ascii=False)


def derive_course_list_from_courses(semesters: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for block in semesters:
        for c in block.get("courses") or []:
            title = str(c.get("title", "")).strip()
            grade = str(c.get("grade", "")).strip()
            if title and grade:
                lines.append(f"{title} — {grade}")
            elif title:
                lines.append(title)
    return "\n".join(lines)


def enrich_ait_transcript_subject(subject: dict[str, Any]) -> dict[str, Any]:
    if "courses" not in subject:
        return subject
    semesters = parse_courses(subject.get("courses"))
    out = dict(subject)
    out["courses"] = canonicalize_courses_json(semesters)
    out["courseList"] = derive_course_list_from_courses(semesters)
    return out
