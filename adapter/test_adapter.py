"""Tests for the mock adapter (contracts.md section 2b).

Run: python3 adapter/test_adapter.py                      on the host, no Docker: a temp CSV from the generator,
                                                          then a temp copy of the hackathon roster
     python3 adapter/test_adapter.py URL CSV              against the running container (smoke.sh), where
                                                          CSV is the file the container mounts (the transcript CSV
                                                          or a roster); the edit case rewrites it and puts it back
Needs fastapi and httpx (portal/requirements.txt).
"""

from __future__ import annotations

import csv
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "data"))
import generate_csv as gc  # noqa: E402

ROSTER = Path(__file__).parent.parent / "installations" / "hackathon" / "adapter" / "student_identity_data.csv"


def read_rows(csv_path: Path) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def set_column(csv_path: Path, sub: str, column: str, value: str) -> None:
    rows = read_rows(csv_path)
    next(r for r in rows if r["id"] == sub)[column] = value
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def check_adapter(get, csv_path: Path) -> None:
    """`get(path)` returns (status, body). Checks every row of csv_path, then an unknown sub, then an edit."""
    rows = read_rows(csv_path)
    # The transcript CSV carries contract 2b's eligibility attributes; a roster does not.
    edited = "balance" if "balance" in rows[0] else "teamId"
    if edited == "balance":
        check_transcript_rows(get, rows)
    else:
        check_roster_rows(get, rows)

    first = rows[0]["id"]
    for path in ("degrees", "transcript", "eligibility"):
        assert get(f"/students/nobody/{path}")[0] == 404, path
    assert get(f"/students/{first}/transcript?degreeId=other")[0] == 404
    assert get(f"/students/{first}/eligibility?degreeId=other")[0] == 404

    # The file is read again on every request: an edited value is served at once.
    original = csv_path.read_bytes()
    try:
        before = get(f"/students/{first}/eligibility")[1][edited]
        assert before != "777.00"
        set_column(csv_path, first, edited, "777.00")
        assert get(f"/students/{first}/eligibility")[1][edited] == "777.00"
    finally:
        csv_path.write_bytes(original)
    assert get(f"/students/{first}/eligibility")[1][edited] == before


def check_transcript_rows(get, rows: list[dict]) -> None:
    assert len(rows) >= 7
    for row in rows:
        sub = row["id"]
        status, body = get(f"/students/{sub}/degrees")
        assert status == 200 and len(body) == 1, (sub, status, body)
        assert body[0] == {"degreeId": sub, "level": row["level"], "degreeAwarded": row["degreeAwarded"],
                           "dateGraduation": row["dateGraduation"]}, body

        status, body = get(f"/students/{sub}/transcript?degreeId={sub}")
        assert status == 200, (sub, status)
        assert body["fullName"] == row["fullName"] and body["degreeId"] == sub and body["level"] == row["level"]
        assert body["registrationNo"] == row["registrationNo"] and "balance" not in body and "courseList" not in body
        assert isinstance(body["courses"], list) and body["courses"][0]["term"] and body["courses"][0]["courses"][0]["no"]
        if "\n" in row["programCommittee"]:
            assert "\n" in body["programCommittee"] and "\\" not in body["programCommittee"]  # Certify's escaping undone

        status, body = get(f"/students/{sub}/eligibility?degreeId={sub}")
        assert status == 200 and body == {"holds": json.loads(row["holds"]), "conferralStatus": row["conferralStatus"],
                                          "balance": row["balance"]}, (sub, body)
        assert get(f"/students/{sub}/eligibility")[0] == 200  # degreeId is optional: there is one degree per sub


def check_roster_rows(get, rows: list[dict]) -> None:
    """A roster (the hackathon installation): the degree list names the row, and the record and the eligibility
    paths both serve the row's columns."""
    for row in rows:
        sub = row["id"]
        columns = {k: v for k, v in row.items() if k != "id"}
        assert get(f"/students/{sub}/degrees") == (200, [{"degreeId": sub}]), sub
        assert get(f"/students/{sub}/transcript?degreeId={sub}") == (200, {"degreeId": sub, **columns}), sub
        assert get(f"/students/{sub}/eligibility?degreeId={sub}") == (200, columns), sub


def host_get(csv_path: Path):
    """`get(path)` over the adapter's app in-process, serving csv_path."""
    from fastapi.testclient import TestClient

    os.environ["ADAPTER_CSV"] = str(csv_path)
    import main

    client = TestClient(main.app)

    def get(path: str) -> tuple[int, object]:
        r = client.get(path)
        return r.status_code, r.json()

    return get


def test_mock_adapter_on_a_generated_csv() -> None:
    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "student_identity_data.csv"
        gc.write_csv(gc.build_rows(gc.load_students()["students"]), csv_path)
        check_adapter(host_get(csv_path), csv_path)


def test_mock_adapter_on_the_hackathon_roster() -> None:
    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "student_identity_data.csv"
        csv_path.write_bytes(ROSTER.read_bytes())
        get = host_get(csv_path)
        check_adapter(get, csv_path)
        assert get("/students/hack-2026-0001/transcript")[1]["teamName"] == "Sandbox Pioneers"
        # The participant without a team is on the roster, with an empty teamId.
        assert get("/students/hack-2026-0003/eligibility")[1]["teamId"] == ""


def run_live(url: str, csv_path: Path) -> None:
    import httpx

    def get(path: str) -> tuple[int, object]:
        r = httpx.get(url + path, timeout=10)
        return r.status_code, r.json()

    check_adapter(get, csv_path)


if __name__ == "__main__":
    if len(sys.argv) == 3:
        run_live(sys.argv[1], Path(sys.argv[2]))
        print(f"PASS adapter at {sys.argv[1]}")
    else:
        for name, fn in list(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
                print(f"PASS {name}")
