"""TEMPORARY: every rule that turns the SIS Adapter's current answer into the Adapter contract's record.

Deleted, with the rest of sis-bridge/ and vc-stack/sis-bridge/, once the SIS Adapter serves `GET /records/{recordId}`
itself (ticket 11). The rules are the changes the SIS Adapter is asked to make, applied here until it makes them:

- the VC envelope (`@context`, `type`, `issuer`, `issuanceDate`) and `credentialSubject.id` are dropped, and so is
  every SIS field the contract has no claim for: the record is exactly the claims of adapter/openapi.yaml's
  `TranscriptRecord`, so it cannot carry a key Certify reserves;
- renames: `admissionDate` to `dateAdmitted`, `graduationDate` to `dateGraduation`, `degreeName` to
  `degreeAwarded`, `studyProgram` to `academicProgram`, `thesis.title` and `thesis.grade` to `thesisTitle` and
  `thesisGrade`;
- `academicRecords` becomes `courses`, terms of `{ term, courses: [{ no, title, credits, grade }] }`; a term is named by
  the SIS's `termLabel` (`term` when the label is empty);
- numbers become strings, a whole number without a decimal point (`32.0` is `"32"`);
- `courseList` is built by data/ait_courses.py, the data generator's own function;
- a claim the SIS has no field for is served as an empty string, as is a SIS field that is absent or `null`.
"""

from __future__ import annotations

from typing import Any

from ait_courses import derive_course_list_from_courses


class UnexpectedSisAnswer(ValueError):
    """The SIS answered 200 with something that is not the transcript it is known to serve."""


# Contract claim <- SIS field of credentialSubject.
FIELDS = {
    "fullName": "fullName",
    "dateOfBirth": "dateOfBirth",
    "dateAdmitted": "admissionDate",
    "degreeAwarded": "degreeName",
    "dateGraduation": "graduationDate",
    "academicProgram": "studyProgram",
    "totalCredits": "totalCredits",
}
# The claims of TranscriptRecord, in its order. A test holds this list to adapter/openapi.yaml.
CLAIMS = (
    "fullName", "dateOfBirth", "country", "registrationNo", "previousDegree", "yearAwarded", "dateAdmitted", "option",
    "degreeAwarded", "dateGraduation", "faculty", "academicProgram", "areaOfSpecialization", "notes", "issueDate",
    "courses", "courseList", "thesisTitle", "thesisGrade", "programCommittee", "courseworkCredits", "thesisCredits",
    "totalCredits", "thesisExamination",
)


def text(value: Any, where: str) -> str:
    """A scalar as the contract's string: null is empty, a number is written without a trailing `.0`."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    raise UnexpectedSisAnswer(f"{where} is not a string or a number")


def terms(academic_records: Any) -> list[dict]:
    if not isinstance(academic_records, list):
        raise UnexpectedSisAnswer("academicRecords is not a list")
    found = []
    for i, term in enumerate(academic_records):
        if not isinstance(term, dict) or not isinstance(term.get("courses"), list):
            raise UnexpectedSisAnswer(f"academicRecords[{i}] has no list of courses")
        courses = []
        for j, course in enumerate(term["courses"]):
            if not isinstance(course, dict):
                raise UnexpectedSisAnswer(f"academicRecords[{i}].courses[{j}] is not an object")
            where = f"academicRecords[{i}].courses[{j}]"
            courses.append({"no": text(course.get("courseCode"), where), "title": text(course.get("courseTitle"), where),
                            "credits": text(course.get("credits"), where), "grade": text(course.get("grade"), where)})
        label = text(term.get("termLabel"), f"academicRecords[{i}]") or text(term.get("term"), f"academicRecords[{i}]")
        found.append({"term": label, "courses": courses})
    return found


def to_record(sis: Any) -> dict:
    """The contract's transcript record for the SIS Adapter's transcript answer, or UnexpectedSisAnswer."""
    subject = sis.get("credentialSubject") if isinstance(sis, dict) else None
    if not isinstance(subject, dict) or "academicRecords" not in subject:
        raise UnexpectedSisAnswer("no credentialSubject with academicRecords")
    thesis = subject.get("thesis") or {}
    if not isinstance(thesis, dict):
        raise UnexpectedSisAnswer("thesis is not an object")
    claims: dict[str, Any] = {claim: text(subject.get(field), field) for claim, field in FIELDS.items()}
    claims["thesisTitle"] = text(thesis.get("title"), "thesis.title")
    claims["thesisGrade"] = text(thesis.get("grade"), "thesis.grade")
    claims["courses"] = terms(subject["academicRecords"])
    claims["courseList"] = derive_course_list_from_courses(claims["courses"])
    return {claim: claims.get(claim, "") for claim in CLAIMS}
