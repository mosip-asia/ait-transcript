"""TEMPORARY, with the rest of sis-bridge/ (ticket 08 of the issuer reshape; ticket 11 deletes it).

Tests for the SIS bridge, over its HTTP interface, against a stand-in SIS that serves the redacted st123456 sample of
wayfinder ticket 03 (fixtures/st123456.json) on the SIS Adapter's current route. The stand-in is a real server on a
local port, so "the SIS is unreachable" is a closed port. Needs fastapi, uvicorn, httpx and PyYAML (portal/requirements.txt).
Run: python3 sis-bridge/test_bridge.py
"""

from __future__ import annotations

import contextlib
import json
import socket
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "data"))  # ait_courses, which the image copies next to the bridge
sys.path.insert(0, str(HERE.parent / "adapter"))  # the contract mode of ticket 03
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse, PlainTextResponse  # noqa: E402

import bridge  # noqa: E402
import sis_mapping  # noqa: E402
from test_adapter import check_contract, load_contract, scope_schema  # noqa: E402

SCOPE = "ait_transcript_vc_ldp"
SAMPLE = json.loads((HERE / "fixtures" / "st123456.json").read_text(encoding="utf-8"))

# The record the sample must map to, written out by hand (not derived from the sample by the mapping's own rules).
EXPECTED = {
    "fullName": "Somchai Prasert",
    "dateOfBirth": "1998-05-12",
    "country": "",
    "registrationNo": "",
    "previousDegree": "",
    "yearAwarded": "",
    "dateAdmitted": "2024-08-19",
    "option": "",
    "degreeAwarded": "Master of Engineering",
    "dateGraduation": "2026-08-31",
    "faculty": "",
    "academicProgram": "M.Eng Information Management",
    "areaOfSpecialization": "",
    "notes": "",
    "issueDate": "",
    "courses": [
        {"term": "August Semester 2024", "courses": [
            {"no": "IM601", "title": "Database Systems", "credits": "3", "grade": "A"},
            {"no": "IM602", "title": "Information Retrieval", "credits": "3", "grade": "A-"},
            {"no": "IM603", "title": "Data Warehousing", "credits": "3", "grade": "B+"}]},
        {"term": "January Semester 2025", "courses": [
            {"no": "IM604", "title": "Data Integration", "credits": "3", "grade": "A"},
            {"no": "IM605", "title": "Information Security Management", "credits": "3", "grade": "A"},
            {"no": "IM606", "title": "Research Methods", "credits": "3", "grade": "B"}]},
        {"term": "August Semester 2025", "courses": [
            {"no": "IM701", "title": "Knowledge Management", "credits": "3", "grade": "A"},
            {"no": "IM702", "title": "Data Governance", "credits": "3", "grade": "B+"},
            {"no": "IM703", "title": "Professional Seminar", "credits": "2", "grade": "S"}]},
        {"term": "January Semester 2026", "courses": [
            {"no": "IM801", "title": "Thesis Proposal", "credits": "3", "grade": "S"},
            {"no": "IM802", "title": "Elective Studies", "credits": "2.5", "grade": "A-"},
            {"no": "IM803", "title": "Colloquium", "credits": "0.5", "grade": "S"}]},
    ],
    "courseList": "Database Systems — A\nInformation Retrieval — A-\nData Warehousing — B+\nData Integration — A\n"
                  "Information Security Management — A\nResearch Methods — B\nKnowledge Management — A\n"
                  "Data Governance — B+\nProfessional Seminar — S\nThesis Proposal — S\nElective Studies — A-\n"
                  "Colloquium — S",
    "thesisTitle": "Record Linkage Across Campus Information Systems",
    "thesisGrade": "A",
    "programCommittee": "",
    "courseworkCredits": "",
    "thesisCredits": "",
    "totalCredits": "32",
    "thesisExamination": "",
}


# ---------- the stand-in SIS ----------

class StandInSis:
    """The SIS Adapter's current route for the sample student; any other student is `404 {"detail": ...}`.
    `mode` makes it misbehave; `asked` collects the raw request targets."""

    def __init__(self) -> None:
        self.mode, self.asked, self.body = "ok", [], SAMPLE
        self.app = app = FastAPI()

        @app.middleware("http")
        async def note_the_target(request: Request, call_next):
            self.asked.append(request.scope["raw_path"].decode())
            return await call_next(request)

        @app.get("/api/v1/credentials/transcript/{student_id}")
        def transcript(student_id: str):
            if self.mode == "error":
                return JSONResponse({"detail": "boom"}, status_code=500)
            if self.mode == "not json":
                return PlainTextResponse("<html>gateway</html>")
            if student_id != "st123456":
                return JSONResponse({"detail": f"Student {student_id} not found"}, status_code=404)
            return self.body


@contextlib.contextmanager
def serving(app):
    """`app` on a free local port; yields its base URL."""
    import uvicorn

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(5)


def unused_url() -> str:
    """A base URL where nothing listens."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{s.getsockname()[1]}"


@contextlib.contextmanager
def bridge_over(sis: StandInSis | None = None, url: str | None = None):
    """`get(path) -> (status, body)` over the bridge in front of the stand-in (or of `url`), plus the stand-in."""
    from fastapi.testclient import TestClient

    sis = sis or StandInSis()
    with contextlib.ExitStack() as stack:
        base = url or stack.enter_context(serving(sis.app))
        client = TestClient(bridge.create_app(base))

        def get(path: str) -> tuple[int, object]:
            r = client.get(path)
            return r.status_code, r.json()

        yield get, sis


# ---------- the tests ----------

def test_the_list_names_the_sub_when_the_sis_has_the_student() -> None:
    with bridge_over() as (get, sis):
        assert get(f"/records?sub=st123456&scope={SCOPE}") == (200, [{"recordId": "st123456"}])
        assert sis.asked == ["/api/v1/credentials/transcript/st123456"]


def test_an_unknown_student_is_a_404_on_the_list_and_on_the_record() -> None:
    with bridge_over() as (get, _):
        assert get(f"/records?sub=nobody&scope={SCOPE}")[0] == 404
        assert get(f"/records/nobody?scope={SCOPE}")[0] == 404


def test_the_record_is_the_samples_claims_in_the_contracts_names() -> None:
    with bridge_over() as (get, _):
        status, record = get(f"/records/st123456?scope={SCOPE}")
        assert status == 200
        assert record == EXPECTED
        assert list(record) == list(EXPECTED)  # the contract's order


def test_the_mapped_record_passes_the_contract_mode() -> None:
    with bridge_over() as (get, _):
        check_contract(get, "st123456", SCOPE)
        check_contract(get, "st123456", f"openid {SCOPE}")  # the token's scope claim, whole


def test_the_mapped_record_holds_exactly_the_transcript_schemas_claims() -> None:
    schema = scope_schema(load_contract(), "/records/{recordId}", SCOPE)
    assert list(EXPECTED) == list(sis_mapping.CLAIMS) == schema["required"] == list(schema["properties"])


def test_a_student_id_is_one_path_segment_of_the_sis_route() -> None:
    with bridge_over() as (get, sis):
        assert get(f"/records?sub=..%2Fhealth&scope={SCOPE}")[0] == 404
        assert get(f"/records/a%3Fb%23c?scope={SCOPE}")[0] == 404
        assert sis.asked == ["/api/v1/credentials/transcript/..%2Fhealth", "/api/v1/credentials/transcript/a%3Fb%23c"]


def test_eligibility_is_not_served() -> None:
    with bridge_over() as (get, _):
        assert get(f"/records/st123456/eligibility?scope={SCOPE}")[0] == 404


def test_scope_is_required_as_in_the_contract() -> None:
    with bridge_over() as (get, _):
        assert get("/records?sub=st123456")[0] == 422
        assert get("/records/st123456")[0] == 422


def test_the_sis_unreachable_is_a_502_on_the_list_and_the_record() -> None:
    """Not 200, and not 404, which would read as "no such student": the contract makes the plugin refuse any other
    status with `adapter_error`."""
    with bridge_over(url=unused_url()) as (get, _):
        assert get(f"/records?sub=st123456&scope={SCOPE}")[0] == 502
        assert get(f"/records/st123456?scope={SCOPE}")[0] == 502


def test_a_sis_error_or_a_reply_that_is_not_the_sample_is_a_502() -> None:
    for mode, body in (("error", None), ("not json", None), ("ok", []), ("ok", {}),
                       ("ok", {"credentialSubject": {"fullName": "A", "academicRecords": "none"}}),
                       ("ok", {"credentialSubject": {"fullName": {"x": 1}, "academicRecords": []}}),
                       ("ok", {"credentialSubject": {"fullName": "A", "academicRecords": [
                           {"termLabel": "T", "courses": [{"courseCode": "X", "credits": [3]}]}]}})):
        sis = StandInSis()
        sis.mode, sis.body = mode, body
        with bridge_over(sis) as (get, _):
            assert get(f"/records/st123456?scope={SCOPE}")[0] == 502, (mode, body)
    sis = StandInSis()
    sis.mode = "error"
    with bridge_over(sis) as (get, _):
        assert get(f"/records?sub=st123456&scope={SCOPE}")[0] == 502


def test_the_record_follows_the_sis_not_the_sample() -> None:
    """A different student, a term without a label and a course without a grade."""
    sis = StandInSis()
    sis.body = {"credentialSubject": {
        "fullName": "Nok Chaiyo", "degreeName": "Doctor of Engineering", "totalCredits": 48,
        "thesis": None,
        "academicRecords": [{"term": "Fall 2025", "termLabel": "", "courses": [
            {"courseCode": "IM900", "courseTitle": "Dissertation", "credits": 12, "grade": None}]}]}}
    with bridge_over(sis) as (get, _):
        status, record = get(f"/records/st123456?scope={SCOPE}")
        assert status == 200
        assert record["fullName"] == "Nok Chaiyo" and record["degreeAwarded"] == "Doctor of Engineering"
        assert record["totalCredits"] == "48" and record["dateOfBirth"] == ""
        assert record["thesisTitle"] == record["thesisGrade"] == ""
        assert record["courses"] == [{"term": "Fall 2025", "courses": [
            {"no": "IM900", "title": "Dissertation", "credits": "12", "grade": ""}]}]
        assert record["courseList"] == "Dissertation"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
