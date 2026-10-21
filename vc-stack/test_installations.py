"""Every installation's sign-in identities match its adapter CSV: one Keycloak user per CSV row, with the row's `id`
as username, and the smoke personas among them (smoke.sh checks the same against the running stack).

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


def test_every_installation_is_found() -> None:
    assert {"ait", "hackathon"} <= set(NAMES), NAMES


def test_realm_users_match_the_csv_row_for_row() -> None:
    for installation in NAMES:
        assert sorted(realm_usernames(installation)) == sorted(csv_ids(installation)), installation


def test_the_hackathon_realm_holds_the_three_roster_personas() -> None:
    assert sorted(realm_usernames("hackathon")) == ["hack-2026-0001", "hack-2026-0002", "hack-2026-0003"]


def test_smoke_personas_can_sign_in() -> None:
    for installation in NAMES:
        fixtures = json.loads((INSTALLATIONS / installation / "smoke.json").read_text(encoding="utf-8"))
        users = set(realm_usernames(installation))
        assert {fixtures["eligible"], *fixtures["refused"]} <= users, installation


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
