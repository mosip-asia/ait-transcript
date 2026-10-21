"""Generate installations/ait/adapter/student_identity_data.csv from data/students.json.

data/students.json is the single source of truth (see PRD.md §7-8, AGENTS.md).
Run: python3 data/generate_csv.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ait_courses import enrich_ait_transcript_subject  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
STUDENTS_JSON = Path(__file__).parent / "students.json"
OUT_CSV = REPO_ROOT / "installations" / "ait" / "adapter" / "student_identity_data.csv"

# Locked claim list — PRD.md §7. Order here becomes the CSV column order and matches the
# credentialSubject of the template in installations/ait/certify_seed.sql.
CLAIM_COLUMNS = [
    "fullName",
    "dateOfBirth",
    "country",
    "registrationNo",
    "previousDegree",
    "yearAwarded",
    "dateAdmitted",
    "option",
    "degreeAwarded",
    "dateGraduation",
    "faculty",
    "academicProgram",
    "areaOfSpecialization",
    "notes",
    "issueDate",
    "courses",
    "courseList",
    "thesisTitle",
    "thesisGrade",
    "programCommittee",
    "courseworkCredits",
    "thesisCredits",
    "totalCredits",
    "thesisExamination",
]

# Read by the mock adapter (adapter/), not by Certify: the degree level and the eligibility
# attributes of contracts.md section 2b. They follow the claims.
ADAPTER_COLUMNS = ["level", "holds", "conferralStatus", "balance"]

CSV_COLUMNS = ["id", *CLAIM_COLUMNS, *ADAPTER_COLUMNS]


def load_students(path: Path = STUDENTS_JSON) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def escape_vc_quoted_claim(value: str) -> str:
    """Escape a claim value for Certify's `"claim": "${claim}"` Velocity substitution.

    Certify's vc_template does naive string substitution, not JSON-aware
    templating — an unescaped `"` or newline (e.g. in courseList or
    programCommittee) breaks the surrounding JSON string and issuance
    fails with `json_processing_error`. `courses` is the one claim embedded
    unquoted (raw JSON array) and must stay untouched by this.
    """
    return json.dumps(value)[1:-1]


def build_rows(students: list[dict]) -> list[dict]:
    """One CSV row per degree, not per student — each degree is its own issuable
    Certify/Keycloak identity (`degree["keycloakId"]`) so a multi-degree student
    can claim a distinct transcript VC per degree (see PLAN.md Phase 7)."""
    rows = []
    for student in students:
        for degree in student["degrees"]:
            subject = {
                "fullName": student["fullName"],
                "dateOfBirth": student["dateOfBirth"],
                "country": student["country"],
                **degree,
            }
            enriched = enrich_ait_transcript_subject(subject)
            row = {"id": degree["keycloakId"]}
            for claim in CLAIM_COLUMNS:
                value = str(enriched.get(claim, ""))
                row[claim] = value if claim == "courses" else escape_vc_quoted_claim(value)
            eligibility = degree["eligibility"]
            row.update(level=degree["level"], holds=json.dumps(eligibility["holds"]),
                       conferralStatus=eligibility["conferralStatus"], balance=eligibility["balance"])
            rows.append(row)
    return rows


def write_csv(rows: list[dict], out_path: Path = OUT_CSV) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    data = load_students()
    # Registrars don't get transcripts — only students go into the CSV.
    rows = build_rows(data["students"])
    write_csv(rows)
    print(f"Wrote {len(rows)} rows, {len(CSV_COLUMNS)} columns, to {OUT_CSV}")


if __name__ == "__main__":
    main()
