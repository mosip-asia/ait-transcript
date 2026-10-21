"""The credential types the Gateway serves: a registry in code, keyed by the OAuth scope.

Each type names its scope, its credential type, its checks (evaluated in order over the adapter's eligibility
attributes) and its mapping from the adapter's record to the template's variable names. The installation's
settings say which scopes are enabled; nothing else differs between installations. Only the transcript is
registered today; the Developer Passport and the Achievement join it as further entries.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable


@dataclass(frozen=True)
class Check:
    name: str
    passed: Callable[[dict], bool]
    reason: Callable[[dict], str]


@dataclass(frozen=True)
class CredentialType:
    scope: str
    credential_type: str
    checks: tuple[Check, ...]
    claims: Callable[[dict], dict]


def evaluate(ctype: CredentialType, eligibility: dict) -> list[dict]:
    """Every check, always all of them, in order; `reason` only on a failed one (contracts.md 2a, 403 body)."""
    result = []
    for check in ctype.checks:
        entry = {"check": check.name, "passed": check.passed(eligibility)}
        if not entry["passed"]:
            entry["reason"] = check.reason(eligibility)
        result.append(entry)
    return result


def escape_vc_quoted_claim(value: str) -> str:
    """Certify substitutes claims into its JSON Velocity template as `"claim": "${claim}"`, so a quote or a
    newline would break the JSON. The same rule as data/generate_csv.py's escape_vc_quoted_claim."""
    return json.dumps(value)[1:-1]


def claims(ctype: CredentialType, record: dict) -> dict:
    """The 200 body: the type's claims, every string escaped for the quoted template; other scalars become strings, and arrays (`courses`,
    which the template embeds unquoted) are left as they are."""
    return {k: v if isinstance(v, list) else escape_vc_quoted_claim("" if v is None else str(v))
            for k, v in ctype.claims(record).items()}


# --- AIT transcript ---------------------------------------------------------------------------------------

# The claims Certify's ait-transcript template substitutes, in data/generate_csv.py's CLAIM_COLUMNS order.
TRANSCRIPT_CLAIMS = (
    "fullName", "dateOfBirth", "country", "registrationNo", "previousDegree", "yearAwarded", "dateAdmitted",
    "option", "degreeAwarded", "dateGraduation", "faculty", "academicProgram", "areaOfSpecialization", "notes",
    "issueDate", "courses", "courseList", "thesisTitle", "thesisGrade", "programCommittee", "courseworkCredits",
    "thesisCredits", "totalCredits", "thesisExamination",
)


def derive_course_list(semesters: list[dict]) -> str:
    """The one-line-per-course summary a wallet card shows; data/ait_courses.py's derive_course_list_from_courses."""
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


def transcript_claims(record: dict) -> dict:
    out = {k: record.get(k, "") for k in TRANSCRIPT_CLAIMS}
    out["courseList"] = derive_course_list(record["courses"])
    return out


TRANSCRIPT = CredentialType(
    scope="ait_transcript_vc_ldp",
    credential_type="AitTranscriptCredential",
    checks=(
        Check("no_holds", lambda e: not e["holds"], lambda e: "Holds on record: " + ", ".join(e["holds"])),
        Check("conferred", lambda e: e["conferralStatus"] == "Conferred", lambda e: "Degree not yet conferred"),
        Check("zero_balance", lambda e: Decimal(e["balance"]) == 0, lambda e: f"Outstanding balance: {e['balance']}"),
    ),
    claims=transcript_claims,
)

REGISTRY: dict[str, CredentialType] = {t.scope: t for t in (TRANSCRIPT,)}
