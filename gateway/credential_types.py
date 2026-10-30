"""The credential types the Gateway serves, keyed by the OAuth scope, and the models it parses the adapter's answers
into (adapter/openapi.yaml), so nothing after the fetch reads a raw dict. Each type names its credential type, its
`eligibility` model, which its checks read in order, its `record` model, whose fields are the template's claims, and
the claims it derives from the record. The installation's settings say which scopes are enabled.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Annotated, Callable, Literal

from pydantic import BaseModel, BeforeValidator, Field, WrapValidator, create_model


def model(name: str, *strings: str, **typed) -> type[BaseModel]:
    """A model of an adapter answer: the `strings` fields, each a str, and the `typed` ones, every one required. It
    declares only what its type reads and ignores the rest, so a null in another field is no refusal."""
    return create_model(name, **dict.fromkeys(strings, str), **typed)


Degree = model("Degree", degreeId=Annotated[str, Field(min_length=1)])


@dataclass(frozen=True)
class Check:
    name: str
    reason: Callable[[BaseModel], str | None]  # why the eligibility fails the check, None when it passes


@dataclass(frozen=True)
class CredentialType:
    scope: str
    credential_type: str
    eligibility: type[BaseModel]
    record: type[BaseModel]  # every field a str claim, except `courses`
    checks: tuple[Check, ...]
    derived: dict[str, Callable[[BaseModel], str]] = field(default_factory=dict)  # claim name: computed from the record


def evaluate(ctype: CredentialType, eligibility: BaseModel) -> list[dict]:
    """Every check, always all of them, in order; `reason` only on a failed one (contracts.md 2a, 403 body)."""
    return [{"check": c.name, "passed": True} if (reason := c.reason(eligibility)) is None
            else {"check": c.name, "passed": False, "reason": reason} for c in ctype.checks]


def escape_vc_quoted_claim(value: str) -> str:
    """Certify substitutes claims into its JSON Velocity template as `"claim": "${claim}"`, so a quote or a
    newline would break the JSON. The only place a claim is escaped: the adapter serves values verbatim."""
    return json.dumps(value)[1:-1]


UNQUOTED_JSON_CLAIM = "courses"  # the only claim with an unquoted slot in Certify's templates


def claims(ctype: CredentialType, record: BaseModel) -> dict:
    """The 200 body: the record's fields and the derived claims, every one a string escaped for the quoted template,
    except `courses` (the one slot the template embeds unquoted), which stays the list the adapter served."""
    named = {**dict(record), **{name: derive(record) for name, derive in ctype.derived.items()}}
    return {k: v if k == UNQUOTED_JSON_CLAIM else escape_vc_quoted_claim(v) for k, v in named.items()}


# --- AIT transcript ---------------------------------------------------------------------------------------

Course = model("Course", "no", "title", "credits", "grade")
Term = model("Term", "term", courses=list[Course])
TranscriptEligibility = model("TranscriptEligibility", holds=list[str], conferralStatus=Literal["Conferred", "Pending"],
                              balance=Annotated[str, Field(pattern=r"^-?[0-9]+(\.[0-9]+)?$")])  # never a number
# The claims Certify's ait-transcript template substitutes but `courseList`, which the type derives. `courses` is
# validated as Terms and Courses but kept as the adapter served it, key order and extra keys included.
TranscriptRecord = model(
    "TranscriptRecord", "fullName", "dateOfBirth", "country", "registrationNo", "previousDegree", "yearAwarded",
    "dateAdmitted", "option", "degreeAwarded", "dateGraduation", "faculty", "academicProgram", "areaOfSpecialization",
    "notes", "issueDate", "thesisTitle", "thesisGrade", "programCommittee", "courseworkCredits", "thesisCredits",
    "totalCredits", "thesisExamination",
    courses=Annotated[list[Term], WrapValidator(lambda served, validate: (validate(served), served)[1])])


def derive_course_list(record: BaseModel) -> str:
    """The one-line-per-course summary a wallet card shows; data/ait_courses.py's derive_course_list_from_courses."""
    return "\n".join(f"{c['title'].strip()} — {c['grade'].strip()}" if c["grade"].strip() else c["title"].strip()
                     for term in record.courses for c in term["courses"] if c["title"].strip())


TRANSCRIPT = CredentialType(
    scope="ait_transcript_vc_ldp",
    credential_type="AitTranscriptCredential",
    eligibility=TranscriptEligibility,
    record=TranscriptRecord,
    checks=(
        Check("no_holds", lambda e: "Holds on record: " + ", ".join(e.holds) if e.holds else None),
        Check("conferred", lambda e: None if e.conferralStatus == "Conferred" else "Degree not yet conferred"),
        Check("zero_balance", lambda e: None if Decimal(e.balance) == 0 else f"Outstanding balance: {e.balance}"),
    ),
    derived={"courseList": derive_course_list},
)


# --- Hackathon Developer Passport and Achievement -----------------------------------------------------------

OnRoster = model("OnRoster", "teamId")  # an empty teamId: a registered participant without a team
# `winner` is "true" for a member of a winning team, in any case; any other string is not.
Winner = model("Winner", "teamId", winner=Annotated[bool, BeforeValidator(
    lambda v: v.strip().lower() == "true" if isinstance(v, str) else None, json_schema_input_type=str)])
# The claims Certify's developer-passport and achievement templates substitute: roster columns.
PassportRecord = model("PassportRecord", "teamId", "teamName", "oidcClientId", "authEndpoint", "issuerEndpoint",
                       "verifierEndpoint")
AchievementRecord = model("AchievementRecord", "teamId", "award")

ON_ROSTER = Check("on_roster", lambda e: None if e.teamId.strip() else "Not on a team on the hackathon roster")

DEVELOPER_PASSPORT = CredentialType(
    scope="developer_passport_vc_ldp",
    credential_type="DeveloperPassportCredential",
    eligibility=OnRoster,
    record=PassportRecord,
    checks=(ON_ROSTER,),
)

ACHIEVEMENT = CredentialType(
    scope="achievement_certificate_vc_ldp",
    credential_type="AchievementCertificateCredential",
    eligibility=Winner,
    record=AchievementRecord,
    checks=(ON_ROSTER, Check("winner", lambda e: None if e.winner else "The team did not win an award")),
)

REGISTRY: dict[str, CredentialType] = {t.scope: t for t in (TRANSCRIPT, DEVELOPER_PASSPORT, ACHIEVEMENT)}
