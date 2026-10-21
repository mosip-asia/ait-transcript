"""Tests for the mock adapter (contracts.md section 2b).

Run: python3 adapter/test_adapter.py                      on the host, no Docker: a temp CSV from the generator
     python3 adapter/test_adapter.py URL CSV              against the running container (smoke.sh), where
                                                          CSV is the file the container mounts; the edit case
                                                          rewrites it and puts it back
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


def read_rows(csv_path: Path) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def set_balance(csv_path: Path, sub: str, balance: str) -> None:
    rows = read_rows(csv_path)
    next(r for r in rows if r["id"] == sub)["balance"] = balance
    gc.write_csv(rows, csv_path)


def check_adapter(get, csv_path: Path) -> None:
    """`get(path)` returns (status, body). Checks every row of csv_path, then an unknown sub, then an edit."""
    rows = read_rows(csv_path)
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

    first = rows[0]["id"]
    for path in ("degrees", "transcript", "eligibility"):
        assert get(f"/students/nobody/{path}")[0] == 404, path
    assert get(f"/students/{first}/transcript?degreeId=other")[0] == 404
    assert get(f"/students/{first}/eligibility?degreeId=other")[0] == 404

    # The file is read again on every request: an edited value is served at once.
    original = csv_path.read_bytes()
    try:
        before = get(f"/students/{first}/eligibility")[1]["balance"]
        assert before != "777.00"
        set_balance(csv_path, first, "777.00")
        assert get(f"/students/{first}/eligibility")[1]["balance"] == "777.00"
    finally:
        csv_path.write_bytes(original)
    assert get(f"/students/{first}/eligibility")[1]["balance"] == before


def test_mock_adapter_on_a_generated_csv() -> None:
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "student_identity_data.csv"
        gc.write_csv(gc.build_rows(gc.load_students()["students"]), csv_path)
        os.environ["ADAPTER_CSV"] = str(csv_path)
        import main

        client = TestClient(main.app)

        def get(path: str) -> tuple[int, object]:
            r = client.get(path)
            return r.status_code, r.json()

        check_adapter(get, csv_path)


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
        test_mock_adapter_on_a_generated_csv()
        print("PASS test_mock_adapter_on_a_generated_csv")
