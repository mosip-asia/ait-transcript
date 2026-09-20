"""Plain-assert smoke tests for generate_csv.py (PLAN.md Phase 0 Tests).

Run: python3 data/test_generate_csv.py
"""

from __future__ import annotations

import csv
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import generate_csv as gc  # noqa: E402


def test_row_count_and_columns() -> None:
    data = gc.load_students()
    rows = gc.build_rows(data["students"])
    degree_count = sum(len(s["degrees"]) for s in data["students"])
    assert len(rows) == degree_count
    assert len(data["students"]) == 5
    assert set(rows[0].keys()) == set(gc.CSV_COLUMNS)


def test_multi_degree_student_gets_distinct_rows() -> None:
    data = gc.load_students()
    rows = gc.build_rows(data["students"])
    dual_degree_student = next(s for s in data["students"] if len(s["degrees"]) > 1)
    degree_ids = {d["keycloakId"] for d in dual_degree_student["degrees"]}
    matching_rows = [r for r in rows if r["id"] in degree_ids]
    assert len(matching_rows) == len(degree_ids)
    assert len({r["registrationNo"] for r in matching_rows}) == len(degree_ids)
    assert len({r["courses"] for r in matching_rows}) == len(degree_ids)


def test_registrars_excluded() -> None:
    data = gc.load_students()
    assert len(data["registrars"]) >= 1
    rows = gc.build_rows(data["students"])
    row_ids = {r["id"] for r in rows}
    registrar_ids = {r["id"] for r in data["registrars"]}
    assert row_ids.isdisjoint(registrar_ids)


def test_generated_csv_roundtrip() -> None:
    data = gc.load_students()
    rows = gc.build_rows(data["students"])
    with tempfile.TemporaryDirectory() as td:
        out_path = Path(td) / "out.csv"
        gc.write_csv(rows, out_path)
        with open(out_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            assert reader.fieldnames == gc.CSV_COLUMNS
            read_rows = list(reader)
    assert len(read_rows) == len(rows)
    assert any("CS601" in (r["courseTableHtml"] or "") for r in read_rows)
    assert all("${" not in (r["courseTableHtml"] or "") for r in read_rows)
    assert all("${" not in (r["courses"] or "") for r in read_rows)


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"{len(tests)} tests passed")

