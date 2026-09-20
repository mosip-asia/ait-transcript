"""Load mock personas from data/students.json (repo root)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
STUDENTS_JSON = REPO_ROOT / "data" / "students.json"


@lru_cache
def load_fixture() -> dict[str, Any]:
    with STUDENTS_JSON.open(encoding="utf-8") as f:
        return json.load(f)


def list_students() -> list[dict[str, Any]]:
    return list(load_fixture()["students"])


def list_registrars() -> list[dict[str, Any]]:
    return list(load_fixture()["registrars"])


def get_student(student_id: str) -> dict[str, Any] | None:
    for s in list_students():
        if s["id"] == student_id:
            return s
    return None


def list_degrees(student: dict[str, Any]) -> list[dict[str, Any]]:
    return list(student["degrees"])


def get_degree(student: dict[str, Any], degree_id: str) -> dict[str, Any] | None:
    for d in student["degrees"]:
        if d["degreeId"] == degree_id:
            return d
    return None


def get_registrar(registrar_id: str) -> dict[str, Any] | None:
    for r in list_registrars():
        if r["id"] == registrar_id:
            return r
    return None
