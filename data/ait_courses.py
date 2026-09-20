"""Adapted from ../design/ait_courses.py (frozen, vendored from inji/credential-lab).

Changes vs. the frozen copy:
- PackValidationError is defined locally instead of imported from
  credential_lab.domain.pack, which doesn't exist in this repo.
- render_course_table_html()'s row spacing/height layout was reworked (2026-09-18)
  to fix double-spaced rows and push course rows to the top / summary rows to
  the bottom of the table; the frozen ../design/ copy intentionally still has
  the original layout. Port this back upstream to credential-lab if wanted there.

Do not edit ../design/ait_courses.py to match — that file is the frozen
reference copy (see wiki/concepts/transcript-credential.md).
"""

from __future__ import annotations

import json
from html import escape
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



# ponytail: iText's table layout ignores per-row CSS height and a table-level
# `height` — it distributes ANY forced total height evenly across every row,
# not just an intended "spacer" (confirmed against a real render: every row
# came out at an identical stretched height). So instead of forcing the whole
# table's height, only the single spacer row between course rows and summary
# rows gets an explicit height, computed here from how much page space the
# *other* rows are expected to take at their natural (unstretched) size —
# leaving every other row's height alone so it renders at its natural,
# single-line size. Both constants are empirical estimates tuned against a
# real iText render; re-tune if content overflows or the gap looks off.
_TABLE_HEIGHT_MM = 183
_ROW_HEIGHT_PT = 14
_MM_PER_PT = 25.4 / 72


def render_course_table_html(
    semesters: list[dict[str, Any]],
    *,
    coursework_credits: str = "",
    thesis_credits: str = "",
    total_credits: str = "",
    thesis_examination: str = "",
) -> str:
    # Outer frame only — no cell grid. Course rows (blue) are pinned to the top,
    # summary rows (red) to the bottom, with a single flexible spacer row
    # between them soaking up whatever page space is left.
    cell = "padding:2px 4px;border:none;"
    summary_rows = [
        (label, value)
        for label, value in (
            ("Coursework Credits Gained", coursework_credits),
            ("Thesis Credits Gained", thesis_credits),
            ("Total Number of Credits Gained", total_credits),
            ("Thesis Examination", thesis_examination),
        )
        if str(value).strip()
    ]
    content_row_count = sum(
        2 + len(block.get("courses") or []) for block in semesters
    )  # term header row + subtotal row + one per course
    other_rows = content_row_count + len(summary_rows)
    spacer_mm = max(0.0, _TABLE_HEIGHT_MM - other_rows * _ROW_HEIGHT_PT * _MM_PER_PT)
    parts: list[str] = [
        "<table style=\"width:100%;border-collapse:collapse;"
        "font-size:10px;font-family:'Arial Narrow',Arial,Helvetica,sans-serif;"
        'border:1px solid #000;margin:0;margin-top:-1px;">',
        "<thead><tr>",
        _th("Course No."),
        _th("Descriptive Course Title"),
        _th("Lab."),
        _th("Lec."),
        _th("Credits"),
        _th("Grade"),
        _th("GPA"),
        _th("Cumul. GPA"),
        "</tr></thead><tbody>",
    ]
    for block in semesters:
        term = escape(str(block.get("term", "")))
        parts.append(
            f'<tr><td colspan="8" style="text-align:center;font-weight:700;'
            f'{cell}">{term}</td></tr>'
        )
        courses = list(block.get("courses") or [])
        for idx, c in enumerate(courses):
            is_last = idx == len(courses) - 1
            gpa = escape(str(block.get("gpa", ""))) if is_last else ""
            cum = escape(str(block.get("cumGpa", ""))) if is_last else ""
            parts.append("<tr>")
            parts.append(_td(c.get("no", "")))
            parts.append(_td(c.get("title", ""), align="left"))
            parts.append(_td(c.get("lab", "")))
            parts.append(_td(c.get("lec", "")))
            parts.append(_td(c.get("credits", "")))
            parts.append(_td(c.get("grade", "")))
            parts.append(
                f'<td style="{cell}text-align:center;">{gpa}</td>'
            )
            parts.append(
                f'<td style="{cell}text-align:center;">{cum}</td>'
            )
            parts.append("</tr>")
        parts.append("<tr>")
        parts.append(f'<td colspan="4" style="{cell}"></td>')
        parts.append(_td(block.get("credits", "")))
        parts.append(f'<td style="{cell}"></td>')
        parts.append(_td(block.get("gpa", "")))
        parts.append(_td(block.get("cumGpa", "")))
        parts.append("</tr>")
    # The only row with an explicit height, so it alone carries the leftover
    # page space, pushing the summary rows down to the bottom of the frame.
    parts.append(
        f'<tr><td colspan="8" style="padding:0;border:none;height:{spacer_mm:.1f}mm;">&nbsp;</td></tr>'
    )
    for label, value in summary_rows:
        parts.append(
            f'<tr><td colspan="5" style="{cell}">'
            f"{escape(label)}</td>"
            f'<td colspan="3" style="{cell}">'
            f"{escape(str(value))}</td></tr>"
        )
    parts.append("</tbody></table>")
    return "".join(parts)


def _th(text: str) -> str:
    return f'<th style="padding:2px 4px;border:none;font-weight:700;">{escape(text)}</th>'


def _td(text: Any, align: str = "center") -> str:
    return (
        f'<td style="padding:2px 4px;border:none;text-align:{align};">'
        f"{escape(str(text))}</td>"
    )


def enrich_ait_transcript_subject(subject: dict[str, Any]) -> dict[str, Any]:
    if "courses" not in subject:
        return subject
    semesters = parse_courses(subject.get("courses"))
    out = dict(subject)
    out["courses"] = canonicalize_courses_json(semesters)
    out["courseTableHtml"] = render_course_table_html(
        semesters,
        coursework_credits=str(subject.get("courseworkCredits", "")),
        thesis_credits=str(subject.get("thesisCredits", "")),
        total_credits=str(subject.get("totalCredits", "")),
        thesis_examination=str(subject.get("thesisExamination", "")),
    )
    out["courseList"] = derive_course_list_from_courses(semesters)
    return out
