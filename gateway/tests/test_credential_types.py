"""Tests for the credential-type registry: each type's eligibility model of the adapter's answer and its checklist.

Run: python3 gateway/tests/test_credential_types.py      host only, no Docker
Needs gateway/requirements.txt.
"""

from __future__ import annotations

from pydantic import ValidationError
from test_evaluations import assert_only_failing  # puts gateway/ on sys.path

import credential_types as ct  # noqa: E402

TRANSCRIPT = ct.REGISTRY["ait_transcript_vc_ldp"]
ELIGIBLE = {"holds": [], "conferralStatus": "Conferred", "balance": "0.00"}


def evaluate(ctype: ct.CredentialType, eligibility: dict) -> list[dict]:
    return ct.evaluate(ctype, ctype.eligibility.model_validate(eligibility))


def assert_does_not_parse(model, answer: dict, label: str) -> None:
    try:
        model.model_validate(answer)
    except ValidationError:
        return
    raise AssertionError(f"{model.__name__} parsed {label}: {answer}")


def test_the_transcript_scope_names_its_credential_type() -> None:
    assert TRANSCRIPT.credential_type == "AitTranscriptCredential"


def test_eligible_record_passes_every_check_in_order() -> None:
    assert evaluate(TRANSCRIPT, ELIGIBLE) == [
        {"check": "no_holds", "passed": True},
        {"check": "conferred", "passed": True},
        {"check": "zero_balance", "passed": True},
    ]


def test_each_failed_check_carries_a_reason_and_the_others_are_still_evaluated() -> None:
    cases = {
        "no_holds": {**ELIGIBLE, "holds": ["Library fine"]},
        "conferred": {**ELIGIBLE, "conferralStatus": "Pending"},
        "zero_balance": {**ELIGIBLE, "balance": "1250.00"},
    }
    for failing, eligibility in cases.items():
        assert_only_failing(evaluate(TRANSCRIPT, eligibility), failing, TRANSCRIPT)


def test_every_check_fails_together() -> None:
    checks = evaluate(TRANSCRIPT, {"holds": ["Library fine"], "conferralStatus": "Pending", "balance": "10.00"})
    assert [c["passed"] for c in checks] == [False, False, False] and all(c["reason"] for c in checks)
    assert checks[0]["reason"] == "Holds on record: Library fine" and checks[2]["reason"] == "Outstanding balance: 10.00"


def test_a_zero_balance_written_differently_still_passes() -> None:
    assert evaluate(TRANSCRIPT, {**ELIGIBLE, "balance": "0"})[2] == {"check": "zero_balance", "passed": True}


def test_transcript_eligibility_follows_openapi_strictly() -> None:
    """adapter/openapi.yaml's TranscriptEligibility: a conferralStatus outside its enum, a balance served as a number
    or not a decimal, or a null, does not parse, so the Gateway answers gateway_error rather than run a check."""
    for label, broken in (("unknown conferralStatus", {**ELIGIBLE, "conferralStatus": "Revoked"}),
                          ("numeric balance", {**ELIGIBLE, "balance": 0}),
                          ("balance not a decimal", {**ELIGIBLE, "balance": "n/a"}),
                          ("null holds", {**ELIGIBLE, "holds": None}),
                          ("no balance", {"holds": [], "conferralStatus": "Conferred"})):
        assert_does_not_parse(TRANSCRIPT.eligibility, broken, label)


def test_a_null_in_a_field_no_check_reads_is_no_refusal() -> None:
    """The mock serves a roster cell the row lacks as null: a type reads only its own fields."""
    assert evaluate(PASSPORT, {"teamId": "team-01", "winner": None, "email": None})[0]["passed"] is True
    assert evaluate(TRANSCRIPT, {**ELIGIBLE, "level": None})[0]["passed"] is True


# --- Developer Passport (the hackathon installation) ---

PASSPORT = ct.REGISTRY["developer_passport_vc_ldp"]


def test_the_passport_scope_names_its_credential_type() -> None:
    assert PASSPORT.credential_type == "DeveloperPassportCredential"


def test_a_participant_on_a_team_is_on_the_roster() -> None:
    assert evaluate(PASSPORT, {"teamId": "team-02", "winner": "false"}) == [{"check": "on_roster", "passed": True}]


def test_a_participant_without_a_team_is_not_on_the_roster() -> None:
    for team_id in ("", "  "):
        [check] = evaluate(PASSPORT, {"teamId": team_id, "winner": "false"})
        assert check["check"] == "on_roster" and check["passed"] is False and check["reason"], check


# --- Achievement (the hackathon installation) ---

ACHIEVEMENT = ct.REGISTRY["achievement_certificate_vc_ldp"]


def test_the_achievement_scope_names_its_credential_type() -> None:
    assert ACHIEVEMENT.credential_type == "AchievementCertificateCredential"


def test_a_winning_team_member_passes_on_roster_then_winner() -> None:
    assert evaluate(ACHIEVEMENT, {"teamId": "team-01", "winner": "true"}) == [
        {"check": "on_roster", "passed": True}, {"check": "winner", "passed": True}]


def test_a_member_of_a_team_that_did_not_win_fails_only_winner() -> None:
    for winner in ("false", "", "yes"):
        assert_only_failing(evaluate(ACHIEVEMENT, {"teamId": "team-02", "winner": winner}), "winner", ACHIEVEMENT)


def test_a_participant_without_a_team_fails_on_roster_and_winner_is_still_evaluated() -> None:
    checks = evaluate(ACHIEVEMENT, {"teamId": "", "winner": "false"})
    assert [(c["check"], c["passed"]) for c in checks] == [("on_roster", False), ("winner", False)]
    assert all(c["reason"] for c in checks)


def test_the_winner_column_is_read_as_true_whatever_its_case() -> None:
    for winner in ("true", "TRUE", " True "):
        assert ACHIEVEMENT.eligibility.model_validate({"teamId": "t", "winner": winner}).winner is True, winner
        assert evaluate(ACHIEVEMENT, {"teamId": "t", "winner": winner})[1]["passed"] is True, winner


def test_the_winner_column_is_a_string_on_the_wire() -> None:
    """A null winner, the cell a short roster row lacks, does not parse: the Achievement's evaluation is gateway_error."""
    for winner in (True, None, 1):
        assert_does_not_parse(ACHIEVEMENT.eligibility, {"teamId": "t", "winner": winner}, f"winner {winner!r}")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
