"""Tests for the credential-type registry: the transcript's checklist and its claim mapping.

Run: python3 gateway/tests/test_credential_types.py      host only, no Docker
Needs fastapi and httpx (portal/requirements.txt): the claim test reads the mock adapter in-process.
"""

from __future__ import annotations

from test_issuances import ROSTER, assert_only_failing, mock_adapter, stringify  # puts gateway/ and data/ on sys.path

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


def test_claims_equal_the_generated_csv_row_for_every_persona() -> None:
    """The Gateway's 200 body, after the plugin's stringify rule, is what the CSV row gives Certify's template today."""
    with mock_adapter() as (adapter, _, rows):
        for row in rows:
            record = adapter.get(f"/students/{row['id']}/transcript").json()
            claims = ct.claims(TRANSCRIPT, record)
            assert isinstance(claims["courses"], list), row["id"]
            assert not RESERVED & claims.keys() and "courseTableHtml" not in claims
            expected = {k: row[k] for k in gc.CLAIM_COLUMNS if k != "courseTableHtml"}
            assert stringify(claims) == expected, row["id"]


def test_multiline_claims_are_escaped_for_the_quoted_template() -> None:
    record = {"courses": [{"term": "T1", "courses": [{"no": "AT01", "title": "Thai \"Basics\"", "grade": "A"},
                                                      {"no": "AT02", "title": "Ethics", "grade": ""}]}],
              "programCommittee": "Dr. A (Chair)\nDr. B", "fullName": "Somchai Café"}
    claims = ct.claims(TRANSCRIPT, record)
    assert claims["courseList"] == 'Thai \\"Basics\\" \\u2014 A\\nEthics'
    assert claims["programCommittee"] == "Dr. A (Chair)\\nDr. B"
    assert claims["fullName"] == "Somchai Caf\\u00e9"
    assert claims["courses"][0]["courses"][0]["title"] == 'Thai "Basics"'  # substituted unquoted: left as it is
    assert claims["thesisTitle"] == ""  # a field the record lacks is an empty string, as in the CSV


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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
