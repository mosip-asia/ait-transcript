"""Every installation's sign-in identities match its adapter CSV: one Keycloak user per CSV row, with the row's `id`
as username, plus the smoke's unknown persona, which signs in but has no row; and the smoke personas among them
(smoke.sh checks the same against the running stack).

Host only, no Docker. Run: python3 vc-stack/test_installations.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALLATIONS = REPO_ROOT / "installations"
NAMES = sorted(p.parent.name for p in INSTALLATIONS.glob("*/smoke.json"))
sys.path.insert(0, str(REPO_ROOT / "data"))


def csv_ids(installation: str) -> list[str]:
    """The adapter CSV's id column: generated from data/students.json for ait, the committed file otherwise."""
    if installation == "ait":
        import generate_csv as gc

        return [row["id"] for row in gc.build_rows(gc.load_students()["students"])]
    with open(INSTALLATIONS / installation / "adapter" / "student_identity_data.csv", newline="", encoding="utf-8") as f:
        return [row["id"] for row in csv.DictReader(f)]


def realm_usernames(installation: str) -> list[str]:
    realm = json.loads((INSTALLATIONS / installation / "keycloak-realm.json").read_text(encoding="utf-8"))
    return [user["username"] for user in realm["users"]]


def smoke_fixtures(installation: str) -> list[dict]:
    return json.loads((INSTALLATIONS / installation / "smoke.json").read_text(encoding="utf-8"))


def unknown_personas(installation: str) -> set[str]:
    return {fixture["unknown"] for fixture in smoke_fixtures(installation)}


def test_every_installation_is_found() -> None:
    assert {"ait", "hackathon"} <= set(NAMES), NAMES


def test_every_realm_user_but_the_smokes_unknown_persona_has_a_csv_row() -> None:
    for installation in NAMES:
        users = [u for u in realm_usernames(installation) if u not in unknown_personas(installation)]
        assert sorted(users) == sorted(csv_ids(installation)), installation


def test_the_hackathon_realm_holds_the_three_roster_personas_and_the_unknown_one() -> None:
    assert sorted(realm_usernames("hackathon")) == ["hack-2026-0001", "hack-2026-0002", "hack-2026-0003", "hack-2026-9999"]


def test_smoke_personas_can_sign_in() -> None:
    for installation in NAMES:
        users = set(realm_usernames(installation))
        for fixture in smoke_fixtures(installation):
            eligible = fixture["eligible"]  # one persona or a list
            eligible = [eligible] if isinstance(eligible, str) else eligible
            assert {*eligible, *fixture["refused"], fixture["unknown"]} <= users, (installation, fixture["scope"])


def test_the_unknown_smoke_persona_can_sign_in_but_has_no_record() -> None:
    """Each type's `unknown` persona gets a token, and the Adapter has no record of it: Certify answers `no_record`
    for it with the gate on or off, and so does the Gateway's 404."""
    for installation in NAMES:
        for fixture in smoke_fixtures(installation):
            assert isinstance(fixture["unknown"], str) and fixture["unknown"], (installation, fixture["scope"])
            assert fixture["unknown"] not in csv_ids(installation), (installation, fixture["scope"], fixture["unknown"])


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
