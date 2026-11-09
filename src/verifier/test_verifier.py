"""Plain-assert tests for Inji Verifier branding overlay and configuration contract.

Run: python3 src/verifier/test_verifier.py
"""

from __future__ import annotations

import json
from pathlib import Path
import xml.etree.ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VERIFIER_DIR = REPO_ROOT / "src" / "verifier"
DEPLOY_BASE = REPO_ROOT / "deploy" / "base"


def test_dockerfile_overlay() -> None:
    dockerfile = VERIFIER_DIR / "Dockerfile"
    assert dockerfile.is_file(), "Dockerfile must exist"
    content = dockerfile.read_text(encoding="utf-8")
    assert "FROM injistack/inji-verify-ui:0.17.0" in content
    assert "inji_verify.svg" in content
    assert "theme.css" in content


def test_theme_css_variables() -> None:
    theme_file = VERIFIER_DIR / "theme.css"
    assert theme_file.is_file(), "theme.css must exist"
    css = theme_file.read_text(encoding="utf-8")
    required_vars = [
        "--iv-primary-color",
        "--iv-logo-start-color",
        "--iv-header-background-color",
        "--iv-active-tab-background",
        "--iv-success",
        "--iv-invalid",
    ]
    for var in required_vars:
        assert var in css, f"Missing CSS variable {var} in theme.css"


def test_svg_logo() -> None:
    svg_file = VERIFIER_DIR / "assets" / "inji_verify.svg"
    assert svg_file.is_file(), "inji_verify.svg must exist"
    svg_text = svg_file.read_text(encoding="utf-8")
    # Parse as XML to verify syntax
    root = ET.fromstring(svg_text)
    assert root.tag.endswith("svg")
    assert "AIT" in svg_text
    assert "VERIFY" in svg_text


def test_verify_config_schema() -> None:
    config_file = DEPLOY_BASE / "verify-config.json"
    assert config_file.is_file(), "verify-config.json must exist in deploy/base"
    cfg = json.loads(config_file.read_text(encoding="utf-8"))
    assert "verifiableClaims" in cfg
    assert "VCRenderOrders" in cfg
    types = [c["type"] for c in cfg["verifiableClaims"]]
    assert "AitTranscriptCredential" in types
    assert "AitTranscriptCredentialRenderOrder" in cfg["VCRenderOrders"]


def test_compose_verify_manifest() -> None:
    compose_file = REPO_ROOT / "compose.verify.yaml"
    assert compose_file.is_file(), "compose.verify.yaml must exist"
    content = compose_file.read_text(encoding="utf-8")
    assert "verify-ui:" in content
    assert "verify-service:" in content
    assert "verify-database:" in content
    assert "4007:8000" in content
    assert "DEFAULT_TITLE" in content
    assert "DEFAULT_THEME" in content


def main() -> None:
    tests = [
        ("test_dockerfile_overlay", test_dockerfile_overlay),
        ("test_theme_css_variables", test_theme_css_variables),
        ("test_svg_logo", test_svg_logo),
        ("test_verify_config_schema", test_verify_config_schema),
        ("test_compose_verify_manifest", test_compose_verify_manifest),
    ]
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print(f"{len(tests)} tests passed")


if __name__ == "__main__":
    main()
