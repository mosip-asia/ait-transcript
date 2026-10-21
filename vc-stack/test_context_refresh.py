"""Checks vc-stack/context_refresh.sql against a throwaway Postgres loaded with the real seed.

Needs only Docker (postgres:16-alpine). Run: python3 vc-stack/test_context_refresh.py
"""

from __future__ import annotations

import base64
import subprocess
import sys
import time
import uuid
from pathlib import Path

STACK = Path(__file__).parent
LOCAL = "http://host.docker.internal:9098/contexts/transcript/v1.json"
PUBLIC = "https://api.demo.example/contexts/transcript/v1.json"
W3C = "https://www.w3.org/ns/credentials/v2"


def psql(name: str, *args: str, stdin: str | None = None, db: str = "inji_certify") -> str:
    cmd = ["docker", "exec", "-i", name, "psql", "-U", "postgres", "-d", db, "-tAq", "-v", "ON_ERROR_STOP=1", *args]
    return subprocess.run(cmd, input=stdin, capture_output=True, text=True, check=True).stdout.strip()


def refresh(name: str, url: str) -> str:
    return psql(name, "-v", f"new_url={url}", stdin=(STACK / "context_refresh.sql").read_text())


def row(name: str) -> tuple[str, str]:
    ctx = psql(name, "-c", "select context from certify.credential_config where credential_config_key_id='ait-transcript'")
    b64 = psql(name, "-c", "select vc_template from certify.credential_config where credential_config_key_id='ait-transcript'")
    assert "\n" not in b64, "vc_template must stay a single line"
    # Not valid JSON until Certify fills the ${...} placeholders, so compare as text.
    return ctx, base64.b64decode(b64).decode()


def main() -> None:
    name = f"ctxrefresh-{uuid.uuid4().hex[:8]}"
    subprocess.run(["docker", "run", "-d", "--rm", "--name", name, "-e", "POSTGRES_PASSWORD=x", "postgres:16-alpine"],
                   check=True, capture_output=True)
    try:
        for _ in range(30):
            if subprocess.run(["docker", "exec", name, "pg_isready", "-U", "postgres"], capture_output=True).returncode == 0:
                break
            time.sleep(1)
        time.sleep(2)
        # The schema and the AIT rows each connect to inji_certify themselves, in the stack's init order.
        for seed in (STACK / "certify_init.sql", STACK.parent / "installations" / "ait" / "certify_seed.sql"):
            psql(name, stdin=seed.read_text(), db="postgres")

        ctx, tpl = row(name)
        assert ctx == f"{LOCAL},{W3C}" and f'"{LOCAL}"' in tpl, "seed no longer matches the local default"

        assert refresh(name, PUBLIC) == "1", "first switch must update the row"
        ctx, tpl = row(name)
        assert ctx == f"{PUBLIC},{W3C}", ctx
        assert f'"{PUBLIC}"' in tpl and LOCAL not in tpl
        assert f'"{W3C}"' in tpl and "ed25519-2020/v1" in tpl  # other contexts untouched
        assert "${_issuer}" in tpl and "${credentialStatus.id}" in tpl, "template placeholders must survive"

        assert refresh(name, PUBLIC) == "", "second run must be a no-op"
        assert refresh(name, LOCAL) == "1", "switching back must work"
        ctx, tpl = row(name)
        assert ctx == f"{LOCAL},{W3C}" and f'"{LOCAL}"' in tpl and PUBLIC not in tpl
        print("PASS context_refresh.sql: switch, no-op, switch back")
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


if __name__ == "__main__":
    sys.exit(main())
