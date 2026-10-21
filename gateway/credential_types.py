"""The credential types the Gateway serves: a registry in code, keyed by the OAuth scope.

Each type names its scope, its credential type, its checks (evaluated in order over the adapter's eligibility
attributes, each reading the attributes it names) and the template's variable names, each taken from the
adapter's record field of that name unless the type derives it. The installation's settings say which scopes are
enabled; nothing else differs between installations. The transcript (AIT) and the Developer Passport
(hackathon) are registered; the Achievement joins them as a further entry.
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
    claim_names: tuple[str, ...]
    derived: Callable[[dict], dict] = lambda record: {}  # claims computed from the record, overriding by name


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
    which the template embeds unquoted) are left as they are. A field the record lacks is an empty string."""
    named = {k: record.get(k, "") for k in ctype.claim_names} | ctype.derived(record)
    return {k: v if isinstance(v, list) else escape_vc_quoted_claim("" if v is None else str(v))
            for k, v in named.items()}


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


TRANSCRIPT = CredentialType(
    scope="ait_transcript_vc_ldp",
    credential_type="AitTranscriptCredential",
    checks=(
        Check("no_holds", lambda e: not e["holds"], lambda e: "Holds on record: " + ", ".join(e["holds"])),
        Check("conferred", lambda e: e["conferralStatus"] == "Conferred", lambda e: "Degree not yet conferred"),
        Check("zero_balance", lambda e: Decimal(e["balance"]) == 0, lambda e: f"Outstanding balance: {e['balance']}"),
    ),
    claim_names=TRANSCRIPT_CLAIMS,
    derived=lambda record: {"courseList": derive_course_list(record["courses"])},
)


# --- Hackathon Developer Passport -------------------------------------------------------------------------

# The claims Certify's developer-passport template substitutes: roster columns, as the organiser fills them.
PASSPORT_CLAIMS = ("teamId", "teamName", "oidcClientId", "authEndpoint", "issuerEndpoint", "verifierEndpoint")

DEVELOPER_PASSPORT = CredentialType(
    scope="developer_passport_vc_ldp",
    credential_type="DeveloperPassportCredential",
    checks=(
        # A registered participant without a team has an empty teamId on the roster.
        Check("on_roster", lambda e: bool(e["teamId"].strip()), lambda e: "Not on a team on the hackathon roster"),
    ),
    claim_names=PASSPORT_CLAIMS,
)

REGISTRY: dict[str, CredentialType] = {t.scope: t for t in (TRANSCRIPT, DEVELOPER_PASSPORT)}
