"""The configuration contract page (wiki/project/issuer-v0.1/configuration-contract.md) against the Compose file.

Both directions: every service, image, environment variable, env file, mounted file, host port and Compose variable
of vc-stack/docker-compose.yaml appears in the page's tables, and nothing in those tables is absent from the Compose
file. The Gateway's variables come from its env_file, installations/<name>/gateway.env, which must name the same
variables in every installation. Every host port is named public or internal in the ingress allowlist.

Host only, no Docker. Needs PyYAML, which uvicorn[standard] (portal/requirements.txt) installs.
Run: python3 vc-stack/test_configuration_contract.py
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE = REPO_ROOT / "vc-stack" / "docker-compose.yaml"
PAGE = REPO_ROOT / "wiki" / "project" / "issuer-v0.1" / "configuration-contract.md"
INSTALLATIONS = REPO_ROOT / "installations"
NAMES = sorted(p.parent.name for p in INSTALLATIONS.glob("*/gateway.env"))

SCOPES = {"installation", "shared", "environment"}
VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)")


# ---------- the Compose file ----------

def compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def repo_path(source: str) -> str:
    """A Compose source path (relative to vc-stack/) as a repository path, the installation written <name>."""
    source = re.sub(r"\$\{INSTALLATION[^}]*\}", "<name>", source)
    if source.startswith("../"):
        return source[3:]
    if source.startswith("./"):
        return "vc-stack/" + source[2:]
    return source


def scope_of(text: str) -> str:
    if "${INSTALLATION" in text:
        return "installation"
    return "environment" if "${" in text else "shared"


def env_file_keys(path: Path) -> list[str]:
    keys = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            keys.append(line.split("=", 1)[0])
    return keys


def compose_rows() -> set[tuple[str, str, str, str, str]]:
    """(service, kind, name, source, scope) for every env, env_file, mount and port in the Compose file."""
    rows = set()
    for service, spec in compose()["services"].items():
        for item in spec.get("environment", []):
            name, value = item.split("=", 1)
            rows.add((service, "env", name, "", scope_of(value)))
        for env_file in spec.get("env_file", []):
            rows.add((service, "env_file", repo_path(env_file), "", "installation"))
            files = [Path(repo_path(env_file).replace("<name>", n)) for n in NAMES]
            key_sets = {tuple(sorted(env_file_keys(REPO_ROOT / f))) for f in files}
            assert len(key_sets) == 1, f"{env_file} names different variables per installation: {key_sets}"
            for name in key_sets.pop():
                rows.add((service, "env", name, "", "installation"))
        for volume in spec.get("volumes", []):
            if isinstance(volume, dict):
                source, target = volume["source"], volume["target"]
            else:  # short form; ${INSTALLATION:?message} carries a colon of its own
                source, target = re.sub(r"\$\{INSTALLATION[^}]*\}", "${INSTALLATION}", volume).split(":")[:2]
            rows.add((service, "mount", target, repo_path(source), scope_of(source)))
        for port in spec.get("ports", []):
            rows.add((service, "port", str(port), "", "shared"))
    return rows


def compose_variables() -> set[str]:
    """Every ${VARIABLE} Compose interpolates from vc-stack/.env or the environment, in the file or its env files."""
    found: set[str] = set()
    for spec in compose()["services"].values():
        for env_file in spec.get("env_file", []):
            for name in NAMES:
                found.update(VARIABLE.findall((REPO_ROOT / repo_path(env_file).replace("<name>", name))
                                              .read_text(encoding="utf-8")))

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, str):
            found.update(VARIABLE.findall(node))

    walk(compose()["services"])
    return found


def host_port(binding: object) -> str:
    """The published host port of a short-form binding, [ip:]host:container[/protocol]."""
    parts = str(binding).split("/")[0].rsplit(":", 2)
    return parts[-2] if len(parts) > 1 else parts[0]


def compose_ports() -> dict[str, str]:
    return {host_port(port): service
            for service, spec in compose()["services"].items() for port in spec.get("ports", [])}


# ---------- the page ----------

def section(heading: str) -> str:
    text = PAGE.read_text(encoding="utf-8").replace("\r\n", "\n")
    start = text.index(f"\n## {heading}\n")
    end = text.find("\n## ", start + 1)
    return text[start:] if end == -1 else text[start:end]


def cells(line: str) -> list[str]:
    return [cell.strip().replace("`", "") for cell in line.strip().strip("|").split("|")]


def tables(text: str) -> list[list[dict[str, str]]]:
    """Every Markdown table in the text, each a list of rows keyed by the header's cells."""
    found, lines = [], text.split("\n")
    i = 0
    while i < len(lines):
        if lines[i].startswith("|") and i + 1 < len(lines) and lines[i + 1].startswith("|---"):
            header, rows, i = cells(lines[i]), [], i + 2
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(dict(zip(header, cells(lines[i]))))
                i += 1
            found.append(rows)
        else:
            i += 1
    return found


def subsections(text: str) -> dict[str, str]:
    parts = re.split(r"\n### (.+)\n", text)
    return {parts[i].replace("`", "").strip(): parts[i + 1] for i in range(1, len(parts), 2)}


def page_rows() -> set[tuple[str, str, str, str, str]]:
    rows = set()
    for title, body in subsections(section("Per service: environment, files and ports")).items():
        if title == "Compose variables":
            continue
        for table in tables(body):
            for row in table:
                rows.add((title, row["Kind"], row["Name"],
                          row["Source"] if row["Kind"] == "mount" else "", row["Scope"]))
    return rows


def page_variables() -> set[str]:
    body = subsections(section("Per service: environment, files and ports"))["Compose variables"]
    return {row["Variable"] for table in tables(body) for row in table}


# ---------- the checks ----------

def test_both_installations_are_found() -> None:
    assert {"ait", "hackathon"} <= set(NAMES), NAMES


def test_the_service_set_is_the_compose_file_with_its_images() -> None:
    services = compose()["services"]
    rows = [row for table in tables(section("Service set and images")) for row in table]
    listed = {row["Compose service"]: row["Image"] for row in rows}
    assert set(listed) == set(services), sorted(set(listed) ^ set(services))
    for service, spec in services.items():
        expected = spec["image"] if "image" in spec else "built from " + repo_path("../" + spec["build"]["dockerfile"])
        assert listed[service] == expected, (service, listed[service], expected)


def test_every_env_file_mount_and_port_is_in_the_page_and_nothing_else() -> None:
    expected, listed = compose_rows(), page_rows()
    assert all(row[4] in SCOPES for row in listed), [row for row in listed if row[4] not in SCOPES]
    missing, extra = sorted(expected - listed), sorted(listed - expected)
    assert not missing and not extra, f"in Compose, not in the page: {missing}\nin the page, not in Compose: {extra}"


def test_every_compose_variable_is_in_the_page_and_nothing_else() -> None:
    expected, listed = compose_variables(), page_variables()
    assert expected == listed, f"in Compose only: {sorted(expected - listed)}; in the page only: {sorted(listed - expected)}"


def test_the_host_port_is_read_from_every_binding_form() -> None:
    for binding in ("9080:8080", "9080:8080/tcp", "127.0.0.1:9080:8080", "127.0.0.1:9080:8080/udp", "[::1]:9080:8080"):
        assert host_port(binding) == "9080", (binding, host_port(binding))


def test_every_host_port_is_public_or_internal_in_the_allowlist() -> None:
    rows = [row for table in tables(section("Ingress allowlist")) for row in table if row.get("Host port")]
    listed = {row["Host port"]: (row["Service"], row["Exposure"]) for row in rows}
    ports = compose_ports()
    assert set(listed) == set(ports), sorted(set(listed) ^ set(ports))
    for port, service in ports.items():
        assert listed[port][0] == service, (port, listed[port], service)
        assert listed[port][1] in {"public", "internal"}, (port, listed[port])


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
