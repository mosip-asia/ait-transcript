"""Phase 2 auth tests (PLAN.md). Run: python3 app/test_auth.py"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
_db_file.close()
os.environ["AIT_DEMO_DB"] = _db_file.name

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.fixtures import list_students  # noqa: E402
from app.main import app  # noqa: E402

db.reset_db()
client = TestClient(app)

STUDENT_A = list_students()[0]
STUDENT_B = list_students()[1]


def _login_student(c: TestClient, student_id: str) -> None:
    r = c.post("/student/login", data={"persona_id": student_id}, follow_redirects=False)
    assert r.status_code == 303


def _login_registrar(c: TestClient) -> None:
    r = c.post("/registrar/login", data={"persona_id": "registrar-001"}, follow_redirects=False)
    assert r.status_code == 303


def test_student_login_shows_own_transcript_summary() -> None:
    c = TestClient(app)
    _login_student(c, STUDENT_A["id"])
    home = c.get("/student")
    assert home.status_code == 200
    assert STUDENT_A["fullName"] in home.text
    assert STUDENT_A["degrees"][0]["academicProgram"] in home.text


def test_registrar_login_lists_all_students() -> None:
    c = TestClient(app)
    _login_registrar(c)
    home = c.get("/registrar")
    assert home.status_code == 200
    for s in list_students():
        assert s["fullName"] in home.text or s["id"] in home.text


def test_unknown_student_persona_rejected() -> None:
    c = TestClient(app)
    r = c.post("/student/login", data={"persona_id": "not-a-real-student"}, follow_redirects=False)
    assert r.status_code == 400
    unauth = c.get("/student", follow_redirects=False)
    assert unauth.status_code in (303, 307)
    follow = c.get("/student", follow_redirects=True)
    assert "/student/login" in follow.url.path


def test_student_without_session_redirects_to_login() -> None:
    c = TestClient(app)
    r = c.get("/student", follow_redirects=False)
    assert r.status_code in (303, 307)
    assert r.headers["location"].endswith("/student/login")


def test_cross_portal_isolation() -> None:
    c_student = TestClient(app)
    _login_student(c_student, STUDENT_A["id"])
    r = c_student.get("/registrar", follow_redirects=False)
    assert r.status_code in (303, 307)
    assert "/registrar/login" in r.headers["location"]

    c_reg = TestClient(app)
    _login_registrar(c_reg)
    r2 = c_reg.get("/student", follow_redirects=False)
    assert r2.status_code in (303, 307)
    assert "/student/login" in r2.headers["location"]


def test_two_students_separate_clients_see_own_data() -> None:
    c_a = TestClient(app)
    c_b = TestClient(app)
    _login_student(c_a, STUDENT_A["id"])
    _login_student(c_b, STUDENT_B["id"])
    text_a = c_a.get("/student").text
    text_b = c_b.get("/student").text
    assert STUDENT_A["fullName"] in text_a
    assert STUDENT_B["fullName"] not in text_a
    assert STUDENT_B["fullName"] in text_b
    assert STUDENT_A["fullName"] not in text_b


def main() -> None:
    test_student_login_shows_own_transcript_summary()
    test_registrar_login_lists_all_students()
    test_unknown_student_persona_rejected()
    test_student_without_session_redirects_to_login()
    test_cross_portal_isolation()
    test_two_students_separate_clients_see_own_data()
    print("app/test_auth.py: all tests passed")


if __name__ == "__main__":
    main()
