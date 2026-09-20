from __future__ import annotations

import json
from html import escape
from typing import Any

from credential_lab.domain.pack import PackValidationError

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
                raise PackValidationError(f"courses[{i}].courses[{j}] needs no and title")
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


def render_course_table_html(
    semesters: list[dict[str, Any]],
    *,
    coursework_credits: str = "",
    thesis_credits: str = "",
    total_credits: str = "",
    thesis_examination: str = "",
) -> str:
    # Outer frame only — no cell grid. Fixed mm height (iText ignores % flex grow);
    # trailing spacer row extends the border into leftover page space (blue area).
    cell = "padding:3px 4px;border:none;"
    parts: list[str] = [
        '<table style="width:100%;height:155mm;min-height:155mm;border-collapse:collapse;'
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
    for label, value in (
        ("Coursework Credits Gained", coursework_credits),
        ("Thesis Credits Gained", thesis_credits),
        ("Total Number of Credits Gained", total_credits),
        ("Thesis Examination", thesis_examination),
    ):
        if str(value).strip():
            parts.append(
                f'<tr><td colspan="5" style="{cell}">'
                f"{escape(label)}</td>"
                f'<td colspan="3" style="{cell}">'
                f"{escape(str(value))}</td></tr>"
            )
    # Empty stretch inside the frame so the border covers leftover vertical space.
    parts.append(
        f'<tr><td colspan="8" style="{cell}height:100%;">&nbsp;</td></tr>'
    )
    parts.append("</tbody></table>")
    return "".join(parts)


def _th(text: str) -> str:
    return (
        f'<th style="padding:3px 4px;border:none;font-weight:700;">{escape(text)}</th>'
    )


def _td(text: Any, align: str = "center") -> str:
    return (
        f'<td style="padding:3px 4px;border:none;text-align:{align};">'
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
