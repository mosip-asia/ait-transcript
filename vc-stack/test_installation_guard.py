"""The INSTALLATION guard: run-demo.sh, bootstrap.sh and smoke.sh refuse to start
unless INSTALLATION names a directory under installations/, before Docker is touched.

Runs the scripts from a throwaway copy of the repo layout with docker, jq and curl
replaced by stubs that only record their calls. No Docker needed.
Run: python3 vc-stack/test_installation_guard.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ["run-demo.sh", "vc-stack/bootstrap.sh", "vc-stack/smoke.sh"]
STUBS = ["docker", "jq", "curl"]


def run(script: str, installation: str | None, dot_env: str = "") -> tuple[int, str, str]:
    """Run one script from a fresh copy; return (exit code, stderr, recorded stub calls)."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "vc-stack").mkdir()
        (root / "installations" / "ait").mkdir(parents=True)
        for path in REPO_ROOT.glob("*.sh"):
            shutil.copy(path, root / path.name)
        for path in (REPO_ROOT / "vc-stack").glob("*.sh"):
            shutil.copy(path, root / "vc-stack" / path.name)
        if dot_env:
            (root / "vc-stack" / ".env").write_text(dot_env, newline="\n")
        stubs = root / "stubs"
        stubs.mkdir()
        log = root / "calls.log"
        log.touch()
        for name in STUBS:
            stub = stubs / name
            stub.write_text('#!/usr/bin/env bash\necho "$(basename "$0") $*" >> "$STUB_LOG"\n', newline="\n")
            stub.chmod(0o755)
        env = {k: v for k, v in os.environ.items() if k != "INSTALLATION"}
        env["PATH"] = f"{stubs}{os.pathsep}{env['PATH']}"
        env["STUB_LOG"] = str(log)
        if installation is not None:
            env["INSTALLATION"] = installation
        proc = subprocess.run([shutil.which("bash"), str(root / script)], env=env, capture_output=True,
                              text=True, timeout=60, stdin=subprocess.DEVNULL)
        return proc.returncode, proc.stderr, log.read_text()


def test_unset_installation_stops_before_docker() -> None:
    for script in SCRIPTS:
        code, err, calls = run(script, installation=None)
        assert code != 0, f"{script} started with INSTALLATION unset"
        assert "INSTALLATION" in err, f"{script} gave no message: {err!r}"
        assert "docker" not in calls, f"{script} called docker before refusing: {calls!r}"


def test_missing_directory_stops_before_docker() -> None:
    for script in SCRIPTS:
        # The environment wins over vc-stack/.env, so a valid .env does not rescue a bad name.
        code, err, calls = run(script, installation="nope", dot_env="INSTALLATION=ait\n")
        assert code != 0, f"{script} started with INSTALLATION naming no directory"
        assert "'nope'" in err, f"{script} did not name the bad value: {err!r}"
        assert "docker" not in calls, f"{script} called docker before refusing: {calls!r}"


def test_installation_from_dot_env_passes_the_guard() -> None:
    _, err, calls = run("run-demo.sh", installation=None, dot_env="INSTALLATION=ait\n")
    assert "INSTALLATION must name" not in err, err
    assert "docker" in calls, "run-demo.sh never reached Docker with INSTALLATION=ait in vc-stack/.env"


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"{len(tests)} tests passed")
