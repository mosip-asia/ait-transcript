"""Tests for the credential-type registry: each type's models of the adapter's answers, its checklist and its claim
mapping, and the Gateway's gateway_error for a record that does not parse.

Run: python3 gateway/tests/test_credential_types.py      host only, no Docker
Needs fastapi and httpx (portal/requirements.txt): the claim test reads the mock adapter in-process.
"""

from __future__ import annotations

import csv
import io
import tempfile
from pathlib import Path

from pydantic import ValidationError
from test_issuances import (ROSTER, FakeStore, assert_only_failing, claim_names, escaped,  # puts gateway/ and data/ on sys.path
                            host_gateway, mock_adapter, post_with, stringify)

import credential_types as ct  # noqa: E402
import generate_csv as gc  # noqa: E402

TRANSCRIPT = ct.REGISTRY["ait_transcript_vc_ldp"]
ELIGIBLE = {"holds": [], "conferralStatus": "Conferred", "balance": "0.00"}
RESERVED = {"_holderId", "_issuer", "id", "validFrom", "validUntil", "credentialStatus"}
COURSE = {"no": "AT01", "title": "Ethics", "credits": "3", "grade": "A"}


def evaluate(ctype: ct.CredentialType, eligibility: dict) -> list[dict]:
    return ct.evaluate(ctype, ctype.eligibility.model_validate(eligibility))


def claims(ctype: ct.CredentialType, record: dict) -> dict:
    return ct.claims(ctype, ctype.record.model_validate(record))


def assert_does_not_parse(model, answer: dict, label: str) -> None:
    try:
        model.model_validate(answer)
    except ValidationError:
        return
    raise AssertionError(f"{model.__name__} parsed {label}: {answer}")


def transcript_record(**fields) -> dict:
    return {**{k: "" for k in TRANSCRIPT.record.model_fields}, "courses": [{"term": "T1", "courses": [COURSE]}], **fields}


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


def test_claims_equal_the_escaped_generated_csv_row_for_every_persona() -> None:
    """The Gateway's 200 body, after the plugin's stringify rule, is the generator's verbatim row escaped for the
    quoted template: the same claim set, every claim, for every persona."""
    assert sorted(claim_names(TRANSCRIPT)) == sorted(gc.CLAIM_COLUMNS)
    with mock_adapter() as (adapter, _, rows):
        assert any("\n" in row["programCommittee"] for row in rows)  # a multiline claim is among them
        for row in rows:
            body = claims(TRANSCRIPT, adapter.get(f"/students/{row['id']}/transcript").json())
            assert isinstance(body["courses"], list), row["id"]
            assert not RESERVED & body.keys() and "courseTableHtml" not in body
            assert stringify(body) == escaped(row, gc.CLAIM_COLUMNS), row["id"]


def test_multiline_claims_are_escaped_for_the_quoted_template() -> None:
    record = transcript_record(
        courses=[{"term": "T1", "courses": [{**COURSE, "title": "Thai \"Basics\""}, {**COURSE, "grade": ""}]}],
        programCommittee="Dr. A (Chair)\nDr. B", fullName="Somchai Café")
    body = claims(TRANSCRIPT, record)
    assert body["courseList"] == 'Thai \\"Basics\\" \\u2014 A\\nEthics'
    assert body["programCommittee"] == "Dr. A (Chair)\\nDr. B"
    assert body["fullName"] == "Somchai Caf\\u00e9"
    assert body["courses"][0]["courses"][0]["title"] == 'Thai "Basics"'  # substituted unquoted: left as it is


def test_every_claim_but_courses_is_a_string_on_the_wire() -> None:
    """A list, a dict, a number or a null where a string claim belongs does not parse; it never becomes a repr."""
    for label, broken in (("dict faculty", {"faculty": {"k": "v"}}), ("list notes", {"notes": ["a"]}),
                          ("numeric yearAwarded", {"yearAwarded": 2023}), ("null thesisTitle", {"thesisTitle": None})):
        assert_does_not_parse(TRANSCRIPT.record, transcript_record(**broken), label)


def test_courses_are_validated_as_terms_and_courses_and_carried_exactly_as_served() -> None:
    served = [{"courses": [{"grade": "B+", "no": "CS601", "lab": "0", "title": "Algorithms", "credits": "3",
                            "remark": "kept"}], "term": "August Semester 2024"}]
    body = claims(TRANSCRIPT, transcript_record(courses=served))
    assert body["courses"] == served and stringify(body)["courses"] == stringify({"c": served})["c"]  # order kept
    without_grade = {k: v for k, v in COURSE.items() if k != "grade"}
    for label, broken in (("a course without grade", [{"term": "T1", "courses": [without_grade]}]),
                          ("a term without courses", [{"term": "T1"}]), ("a term as text", ["T1"])):
        assert_does_not_parse(TRANSCRIPT.record, transcript_record(courses=broken), label)


def test_dates_and_numbers_stay_the_strings_the_adapter_served() -> None:
    body = claims(TRANSCRIPT, transcript_record(dateOfBirth="1999-02-30", courseworkCredits="27.0"))
    assert (body["dateOfBirth"], body["courseworkCredits"]) == ("1999-02-30", "27.0")


def test_a_record_that_lacks_a_claim_or_serves_it_as_null_does_not_parse() -> None:
    record = {"teamId": "team-01", "teamName": "T", "oidcClientId": "c", "authEndpoint": "a", "issuerEndpoint": "i",
              "verifierEndpoint": "v"}
    assert claims(PASSPORT, record)["teamName"] == "T"
    assert_does_not_parse(PASSPORT.record, {k: v for k, v in record.items() if k != "teamName"}, "no teamName")
    assert_does_not_parse(PASSPORT.record, {**record, "teamName": None}, "null teamName")


def roster_text(transform) -> str:
    """The committed roster with `transform(columns, row)` applied to the header and every row."""
    with ROSTER.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(transform(rows[0], row) for row in rows)
    return buf.getvalue()


def issue_on_roster(text: str, scope: str) -> tuple[tuple[int, dict], list]:
    """POST /issuances for hack-2026-0001 through the Gateway and the mock adapter in-process, on a roster `text`."""
    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "student_identity_data.csv"
        csv_path.write_text(text, encoding="utf-8")
        with mock_adapter(csv_path) as (adapter, _, _):
            store = FakeStore()
            with host_gateway(adapter, store, (scope,)) as client:
                return post_with(client)({"sub": "hack-2026-0001", "scope": scope}, "test-token"), store.rows


def test_a_roster_row_missing_a_column_is_a_gateway_error_never_none() -> None:
    """A row shorter than the header (its trailing cells read as null), and a roster without a column a type needs,
    are 502 gateway_error, never a claim of "None" or ""."""
    header = ROSTER.read_text(encoding="utf-8").splitlines()[0]
    short = header + "\nhack-2026-0001,team-01,Sandbox Pioneers\n"
    without_team_name = roster_text(lambda columns, row: [v for c, v in zip(columns, row) if c != "teamName"])
    for label, text, scopes in (("short row", short, (PASSPORT.scope, ACHIEVEMENT.scope)),
                                ("no teamName column", without_team_name, (PASSPORT.scope,))):
        for scope in scopes:
            answer, rows = issue_on_roster(text, scope)
            assert answer == (502, {"error": "gateway_error"}), (label, scope, answer)
            assert rows == [], (label, scope)


def test_a_null_in_a_roster_column_no_type_reads_still_issues() -> None:
    """A roster with an extra column, `email`, that the row leaves out (served as null): both types still issue."""
    text = roster_text(lambda columns, row: row + ["email"] if row is columns else row)
    for ctype in (PASSPORT, ACHIEVEMENT):
        (status, body), rows = issue_on_roster(text, ctype.scope)
        assert status == 200 and sorted(body) == sorted(claim_names(ctype)), (ctype.scope, status, body)
        assert rows == [("hack-2026-0001", ctype.credential_type, ctype.scope, None)]


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


def test_passport_claims_are_the_roster_columns() -> None:
    with mock_adapter(ROSTER) as (adapter, _, _):
        record = adapter.get("/students/hack-2026-0001/transcript").json()
    assert claims(PASSPORT, record) == {
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
    for winner in (True, None, 1):
        assert_does_not_parse(ACHIEVEMENT.eligibility, {"teamId": "t", "winner": winner}, f"winner {winner!r}")


def test_achievement_claims_are_the_team_id_and_the_award() -> None:
    with mock_adapter(ROSTER) as (adapter, _, _):
        record = adapter.get("/students/hack-2026-0001/transcript").json()
    assert claims(ACHIEVEMENT, record) == {"teamId": "team-01", "award": "Best Use of Verifiable Credentials"}


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
