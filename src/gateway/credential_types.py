"""The credential types the Gateway evaluates, keyed by the OAuth scope: each names its credential type, its
`eligibility` model of the adapter's eligibility answer (adapter/openapi.yaml), and the checks that read it in order.
The installation enables the scopes.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated, Callable, Literal

from pydantic import BaseModel, BeforeValidator, Field, create_model


def adapter_model(name: str, *strings: str, **typed) -> type[BaseModel]:
    """A model of an adapter answer: the `strings` fields, each a str, and the `typed` ones, every one required. It
    declares only what its type reads and ignores the rest, so a null in another field is no refusal."""
    return create_model(name, **dict.fromkeys(strings, str), **typed)


@dataclass(frozen=True)
class Check:
    name: str
    reason: Callable[[BaseModel], str | None]  # why the eligibility fails the check, None when it passes


@dataclass(frozen=True)
class CredentialType:
    scope: str
    credential_type: str
    eligibility: type[BaseModel]
    checks: tuple[Check, ...]


def evaluate(ctype: CredentialType, eligibility: BaseModel) -> list[dict]:
    """Every check, always all of them, in order; `reason` only on a failed one (the 403 body)."""
    return [{"check": c.name, "passed": True} if (reason := c.reason(eligibility)) is None
            else {"check": c.name, "passed": False, "reason": reason} for c in ctype.checks]


# --- AIT transcript ---------------------------------------------------------------------------------------

TranscriptEligibility = adapter_model(
    "TranscriptEligibility", holds=list[str], conferralStatus=Literal["Conferred", "Pending"],
    balance=Annotated[str, Field(pattern=r"^-?[0-9]+(\.[0-9]+)?$")])  # never a number

TRANSCRIPT = CredentialType(
    scope="ait_transcript_vc_ldp",
    credential_type="AitTranscriptCredential",
    eligibility=TranscriptEligibility,
    checks=(
        Check("no_holds", lambda e: "Holds on record: " + ", ".join(e.holds) if e.holds else None),
        Check("conferred", lambda e: None if e.conferralStatus == "Conferred" else "Degree not yet conferred"),
        Check("zero_balance", lambda e: None if Decimal(e.balance) == 0 else f"Outstanding balance: {e.balance}"),
    ),
)


# --- Hackathon Developer Passport and Achievement -----------------------------------------------------------

OnRoster = adapter_model("OnRoster", "teamId")  # an empty teamId: a registered participant without a team
# `winner` is "true" for a member of a winning team, in any case; any other string is not.
Winner = adapter_model("Winner", "teamId", winner=Annotated[bool, BeforeValidator(
    lambda v: v.strip().lower() == "true" if isinstance(v, str) else None, json_schema_input_type=str)])

ON_ROSTER = Check("on_roster", lambda e: None if e.teamId.strip() else "Not on a team on the hackathon roster")

DEVELOPER_PASSPORT = CredentialType(
    scope="developer_passport_vc_ldp",
    credential_type="DeveloperPassportCredential",
    eligibility=OnRoster,
    checks=(ON_ROSTER,),
)

ACHIEVEMENT = CredentialType(
    scope="achievement_certificate_vc_ldp",
    credential_type="AchievementCertificateCredential",
    eligibility=Winner,
    checks=(ON_ROSTER, Check("winner", lambda e: None if e.winner else "The team did not win an award")),
)

REGISTRY: dict[str, CredentialType] = {t.scope: t for t in (TRANSCRIPT, DEVELOPER_PASSPORT, ACHIEVEMENT)}
