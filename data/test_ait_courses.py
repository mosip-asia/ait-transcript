"""Plain-assert smoke tests for ait_courses.py (PLAN.md Phase 0 Tests).

Run: python3 data/test_ait_courses.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ait_courses import (  # noqa: E402
    PackValidationError,
    enrich_ait_transcript_subject,
    parse_courses,
    render_course_table_html,
)

_SAMPLE_COURSES = [
    {
        "term": "August Semester 2024",
        "courses": [
            {"no": "CS601", "title": "Advanced Algorithms", "lab": "0", "lec": "45", "credits": "3", "grade": "A"}
        ],
        "credits": "3",
        "gpa": "4.00",
        "cumGpa": "4.00",
    }
]


def test_enrich_happy_path() -> None:
    subject = {"id": "x", "courses": _SAMPLE_COURSES}
    out = enrich_ait_transcript_subject(subject)
    assert "CS601" in out["courseTableHtml"]
    assert "Advanced Algorithms" in out["courseTableHtml"]
    assert out["courseList"] == "Advanced Algorithms — A"


def test_missing_term_raises() -> None:
    try:
        parse_courses([{"courses": []}])
    except PackValidationError:
        return
    raise AssertionError("expected PackValidationError for missing term")


def test_missing_course_no_or_title_raises() -> None:
    try:
        parse_courses([{"term": "T", "courses": [{"title": "X"}]}])
    except PackValidationError:
        return
    raise AssertionError("expected PackValidationError for missing course no")


def test_html_escaped_in_table() -> None:
    semesters = parse_courses(
        [
            {
                "term": "T",
                "courses": [
                    {
                        "no": "X1",
                        "title": "<script>alert(1)</script> & Co",
                        "lab": "0",
                        "lec": "0",
                        "credits": "1",
                        "grade": "A",
                    }
                ],
                "credits": "1",
                "gpa": "4",
                "cumGpa": "4",
            }
        ]
    )
    html = render_course_table_html(semesters)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&amp;" in html


def test_subject_without_courses_passthrough() -> None:
    subject = {"id": "registrar-001", "role": "registrar"}
    out = enrich_ait_transcript_subject(subject)
    assert out == subject


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"{len(tests)} tests passed")
