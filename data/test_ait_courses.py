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


def test_enrich_derives_courses_and_course_list_only() -> None:
    subject = {"id": "x", "courses": _SAMPLE_COURSES}
    out = enrich_ait_transcript_subject(subject)
    assert out["courses"] == (
        '[{"term":"August Semester 2024","courses":[{"no":"CS601","title":"Advanced Algorithms",'
        '"lab":"0","lec":"45","credits":"3","grade":"A"}],"credits":"3","gpa":"4.00","cumGpa":"4.00"}]'
    )
    assert out["courseList"] == "Advanced Algorithms — A"
    assert set(out) == {"id", "courses", "courseList"}, "no other derived claim (the HTML course table is gone)"


def test_numbers_inside_courses_become_strings() -> None:
    # The context types courses as @json with no datatypes, so every value inside is a string.
    semesters = parse_courses(
        [{"term": "T", "courses": [{"no": "X1", "title": "Y", "lab": 0, "lec": 45, "credits": 3, "grade": "A"}],
          "credits": 3, "gpa": 4.0, "cumGpa": 3.5}]
    )
    assert semesters == [{"term": "T", "courses": [{"no": "X1", "title": "Y", "lab": "0", "lec": "45",
                                                    "credits": "3", "grade": "A"}],
                          "credits": "3", "gpa": "4.0", "cumGpa": "3.5"}]


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
