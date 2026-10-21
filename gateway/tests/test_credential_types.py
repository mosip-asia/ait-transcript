"""Tests for the credential-type registry: the transcript's checklist and its claim mapping, and the Gateway's
gateway_error for a record that lacks a claim.

Run: python3 gateway/tests/test_credential_types.py      host only, no Docker
Needs fastapi and httpx (portal/requirements.txt): the claim test reads the mock adapter in-process.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from test_issuances import (ROSTER, FakeStore, assert_only_failing, escaped, host_gateway,  # puts gateway/ and data/ on sys.path
                            mock_adapter, post_with, stringify)

import credential_types as ct  # noqa: E402
import generate_csv as gc  # noqa: E402

TRANSCRIPT = ct.REGISTRY["ait_transcript_vc_ldp"]
ELIGIBLE = {"holds": [], "conferralStatus": "Conferred", "balance": "0.00"}
RESERVED = {"_holderId", "_issuer", "id", "validFrom", "validUntil", "credentialStatus"}


def test_the_transcript_scope_names_its_credential_type() -> None:
    assert TRANSCRIPT.credential_type == "AitTranscriptCredential"


def test_eligible_record_passes_every_check_in_order() -> None:
    assert ct.evaluate(TRANSCRIPT, ELIGIBLE) == [
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
        assert_only_failing(ct.evaluate(TRANSCRIPT, eligibility), failing, TRANSCRIPT)


def test_every_check_fails_together() -> None:
    checks = ct.evaluate(TRANSCRIPT, {"holds": ["Library fine"], "conferralStatus": "Pending", "balance": "10.00"})
    assert [c["passed"] for c in checks] == [False, False, False] and all(c["reason"] for c in checks)


def test_a_zero_balance_written_differently_still_passes() -> None:
    assert ct.evaluate(TRANSCRIPT, {**ELIGIBLE, "balance": "0"})[2] == {"check": "zero_balance", "passed": True}


def test_claims_equal_the_escaped_generated_csv_row_for_every_persona() -> None:
    """The Gateway's 200 body, after the plugin's stringify rule, is the generator's verbatim row escaped for the
    quoted template: the same claim set, every claim, for every persona."""
    with mock_adapter() as (adapter, _, rows):
        assert any("\n" in row["programCommittee"] for row in rows)  # a multiline claim is among them
        for row in rows:
            record = adapter.get(f"/students/{row['id']}/transcript").json()
            claims = ct.claims(TRANSCRIPT, record)
            assert isinstance(claims["courses"], list), row["id"]
            assert not RESERVED & claims.keys() and "courseTableHtml" not in claims
            assert stringify(claims) == escaped(row, gc.CLAIM_COLUMNS), row["id"]


def test_multiline_claims_are_escaped_for_the_quoted_template() -> None:
    record = {**{k: "" for k in ct.TRANSCRIPT_CLAIMS},
              "courses": [{"term": "T1", "courses": [{"no": "AT01", "title": "Thai \"Basics\"", "grade": "A"},
                                                      {"no": "AT02", "title": "Ethics", "grade": ""}]}],
              "programCommittee": "Dr. A (Chair)\nDr. B", "fullName": "Somchai Café"}
    claims = ct.claims(TRANSCRIPT, record)
    assert claims["courseList"] == 'Thai \\"Basics\\" \\u2014 A\\nEthics'
    assert claims["programCommittee"] == "Dr. A (Chair)\\nDr. B"
    assert claims["fullName"] == "Somchai Caf\\u00e9"
    assert claims["courses"][0]["courses"][0]["title"] == 'Thai "Basics"'  # substituted unquoted: left as it is


def test_a_claim_the_record_lacks_or_serves_as_null_raises() -> None:
    record = {"teamId": "team-01", "teamName": "T", "oidcClientId": "c", "authEndpoint": "a", "issuerEndpoint": "i",
              "verifierEndpoint": "v"}
    assert ct.claims(PASSPORT, record)["teamName"] == "T"
    for broken in ({k: v for k, v in record.items() if k != "teamName"}, {**record, "teamName": None}):
        try:
            ct.claims(PASSPORT, broken)
        except (KeyError, ValueError):
            continue
        raise AssertionError(f"claims of {broken} did not raise")


def test_a_roster_row_missing_a_column_is_a_gateway_error_never_none() -> None:
    """Through the Gateway and the adapter in-process: a row shorter than the header (its trailing cells read as
    null), and a roster without a column a type needs, are 502 gateway_error, never a claim of "None" or ""."""
    header = ROSTER.read_text(encoding="utf-8").splitlines()[0]
    short = header + "\nhack-2026-0001,team-01,Sandbox Pioneers\n"
    columns = header.split(",")
    full = ROSTER.read_text(encoding="utf-8").splitlines()[1].split(",")
    without_team_name = ",".join(c for c in columns if c != "teamName") + "\n" + \
        ",".join(v for c, v in zip(columns, full) if c != "teamName") + "\n"
    with tempfile.TemporaryDirectory() as td:
        for label, text, scopes in (("short row", short, (PASSPORT.scope, ACHIEVEMENT.scope)),
                                    ("no teamName column", without_team_name, (PASSPORT.scope,))):
            csv_path = Path(td) / "student_identity_data.csv"
            csv_path.write_text(text, encoding="utf-8")
            with mock_adapter(csv_path) as (adapter, _, _):
                for scope in scopes:
                    store = FakeStore()
                    with host_gateway(adapter, store, (scope,)) as client:
                        answer = post_with(client)({"sub": "hack-2026-0001", "scope": scope}, "test-token")
                    assert answer == (502, {"error": "gateway_error"}), (label, scope, answer)
                    assert store.rows == [], (label, scope)


# --- Developer Passport (the hackathon installation) ---

PASSPORT = ct.REGISTRY["developer_passport_vc_ldp"]


def test_the_passport_scope_names_its_credential_type() -> None:
    assert PASSPORT.credential_type == "DeveloperPassportCredential"


def test_a_participant_on_a_team_is_on_the_roster() -> None:
    assert ct.evaluate(PASSPORT, {"teamId": "team-02", "winner": "false"}) == [{"check": "on_roster", "passed": True}]


def test_a_participant_without_a_team_is_not_on_the_roster() -> None:
    for team_id in ("", "  "):
        [check] = ct.evaluate(PASSPORT, {"teamId": team_id, "winner": "false"})
        assert check["check"] == "on_roster" and check["passed"] is False and check["reason"], check


def test_passport_claims_are_the_roster_columns() -> None:
    with mock_adapter(ROSTER) as (adapter, _, _):
        record = adapter.get("/students/hack-2026-0001/transcript").json()
    assert ct.claims(PASSPORT, record) == {
        "teamId": "team-01",
        "teamName": "Sandbox Pioneers",
        "oidcClientId": "hack-team-01",
        "authEndpoint": "http://localhost:9080/realms/hackathon",
        "issuerEndpoint": "http://localhost:9091",
        "verifierEndpoint": "http://localhost:9095",
    }


# --- Achievement (the hackathon installation) ---

ACHIEVEMENT = ct.REGISTRY["achievement_certificate_vc_ldp"]


def test_the_achievement_scope_names_its_credential_type() -> None:
    assert ACHIEVEMENT.credential_type == "AchievementCertificateCredential"


def test_a_winning_team_member_passes_on_roster_then_winner() -> None:
    assert ct.evaluate(ACHIEVEMENT, {"teamId": "team-01", "winner": "true"}) == [
        {"check": "on_roster", "passed": True}, {"check": "winner", "passed": True}]


def test_a_member_of_a_team_that_did_not_win_fails_only_winner() -> None:
    for winner in ("false", ""):
        assert_only_failing(ct.evaluate(ACHIEVEMENT, {"teamId": "team-02", "winner": winner}), "winner", ACHIEVEMENT)


def test_a_participant_without_a_team_fails_on_roster_and_winner_is_still_evaluated() -> None:
    checks = ct.evaluate(ACHIEVEMENT, {"teamId": "", "winner": "false"})
    assert [(c["check"], c["passed"]) for c in checks] == [("on_roster", False), ("winner", False)]
    assert all(c["reason"] for c in checks)


def test_the_winner_column_is_read_as_true_whatever_its_case() -> None:
    for winner in ("true", "TRUE", " True "):
        assert ct.evaluate(ACHIEVEMENT, {"teamId": "t", "winner": winner})[1]["passed"] is True, winner


def test_achievement_claims_are_the_team_id_and_the_award() -> None:
    with mock_adapter(ROSTER) as (adapter, _, _):
        record = adapter.get("/students/hack-2026-0001/transcript").json()
    assert ct.claims(ACHIEVEMENT, record) == {"teamId": "team-01", "award": "Best Use of Verifiable Credentials"}


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
