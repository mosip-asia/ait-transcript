"""The configuration contract page (wiki/project/issuer-v0.1/configuration-contract.md) against the Compose files.

Both directions: every service, image, environment variable, env file, mounted file, host port and Compose variable
of the folder files vc-stack/compose.yaml includes (vc-stack/<folder>/compose.yaml, each path relative to its own
folder) appears in the page's tables, in the section of the deployment whose folder defines it, and nothing in those
tables is absent from the Compose files. A deployment's section names its folder in a "**Deploy:** `vc-stack/<folder>/`"
line. The Gateway's variables come from its env_file, installations/<name>/gateway.env, which must name the same
variables in every installation. Every host port is named public or internal in the ingress allowlist, and each
server of the Servers section runs a Compose file that includes the deployments it lists.

Host only, no Docker. Needs PyYAML, which uvicorn[standard] (portal/requirements.txt) installs.
Run: python3 vc-stack/test_configuration_contract.py
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
STACK = REPO_ROOT / "vc-stack"
PAGE = REPO_ROOT / "wiki" / "project" / "issuer-v0.1" / "configuration-contract.md"
INSTALLATIONS = REPO_ROOT / "installations"
NAMES = sorted(p.parent.name for p in INSTALLATIONS.glob("*/gateway.env"))

SCOPES = {"installation", "shared", "environment"}
VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)")


# ---------- the Compose files ----------

def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def folders() -> list[str]:
    """The folders vc-stack/compose.yaml includes, each as its path from the repository root."""
    return [posixpath.dirname(f"vc-stack/{path}") for path in load(STACK / "compose.yaml")["include"]]


def services() -> dict[str, tuple[str, dict]]:
    """Every service of the folder files: its folder and its spec. A service is defined in one folder only."""
    found: dict[str, tuple[str, dict]] = {}
    for folder in folders():
        for service, spec in load(REPO_ROOT / folder / "compose.yaml")["services"].items():
            assert service not in found, f"{service} is in both {found[service][0]} and {folder}"
            found[service] = (folder, spec)
    return found


def repo_path(source: str, folder: str) -> str:
    """A Compose source path (relative to its folder) as a repository path, the installation written <name>."""
    source = re.sub(r"\$\{INSTALLATION[^}]*\}", "<name>", source)
    return posixpath.normpath(posixpath.join(folder, source))


def scope_of(text: str) -> str:
    if "${INSTALLATION" in text:
        return "installation"
    return "environment" if "${" in text else "shared"


def env_file_scopes(path: Path) -> tuple[tuple[str, str], ...]:
    """Each variable an env file sets, with its scope: environment when its value is a ${…} that .env can override,
    else installation, since the file is the installation's."""
    scopes = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            name, value = line.split("=", 1)
            scopes.append((name, "environment" if "${" in value else "installation"))
    return tuple(sorted(scopes))


def compose_rows() -> set[tuple[str, str, str, str, str, str]]:
    """(folder, service, kind, name, source, scope) for every env, env_file, mount and port in the Compose files."""
    rows = set()
    for service, (folder, spec) in services().items():
        for item in spec.get("environment", []):
            name, value = item.split("=", 1)
            rows.add((folder, service, "env", name, "", scope_of(value)))
        for env_file in spec.get("env_file", []):
            rows.add((folder, service, "env_file", repo_path(env_file, folder), "", "installation"))
            files = [Path(repo_path(env_file, folder).replace("<name>", n)) for n in NAMES]
            key_sets = {env_file_scopes(REPO_ROOT / f) for f in files}
            assert len(key_sets) == 1, f"{env_file} names different variables or scopes per installation: {key_sets}"
            for name, scope in key_sets.pop():
                rows.add((folder, service, "env", name, "", scope))
        for volume in spec.get("volumes", []):
            if isinstance(volume, dict):
                source, target = volume["source"], volume["target"]
            else:  # short form; ${INSTALLATION:?message} carries a colon of its own
                source, target = re.sub(r"\$\{INSTALLATION[^}]*\}", "${INSTALLATION}", volume).split(":")[:2]
            rows.add((folder, service, "mount", target, repo_path(source, folder), scope_of(source)))
        for port in spec.get("ports", []):
            rows.add((folder, service, "port", str(port), "", "shared"))
    return rows


def compose_variables(wanted: str) -> set[str]:
    """Every ${VARIABLE} Compose interpolates from vc-stack/.env or the environment, in the folder's file or its env files."""
    found: set[str] = set()
    for folder, spec in services().values():
        if folder != wanted:
            continue
        for env_file in spec.get("env_file", []):
            for name in NAMES:
                found.update(VARIABLE.findall((REPO_ROOT / repo_path(env_file, folder).replace("<name>", name))
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

    walk([spec for folder, spec in services().values() if folder == wanted])
    return found


def host_port(binding: object) -> str:
    """The published host port of a short-form binding, [ip:]host:container[/protocol]."""
    parts = str(binding).split("/")[0].rsplit(":", 2)
    return parts[-2] if len(parts) > 1 else parts[0]


def compose_ports() -> dict[str, str]:
    return {host_port(port): service
            for service, (_, spec) in services().items() for port in spec.get("ports", [])}


# ---------- the page ----------

def sections() -> dict[str, str]:
    """Every "## Heading" of the page: its text, from the heading line to the next one."""
    text = PAGE.read_text(encoding="utf-8").replace("\r\n", "\n")
    parts = re.split(r"\n## (.+)\n", "\n" + text)
    return {parts[i].strip(): f"\n## {parts[i]}\n{parts[i + 1]}" for i in range(1, len(parts), 2)}


def section(heading: str) -> str:
    return sections()[heading]


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


def deployments() -> dict[str, str]:
    """The deployment sections: each folder (as its path from the repository root) to the section that names it."""
    found: dict[str, str] = {}
    for heading, text in sections().items():
        match = re.search(r"\*\*Deploy:\*\* `([^`]+)`", text)
        if match:
            folder = match.group(1).rstrip("/")
            assert folder not in found, f"{folder} is deployed by both {found[folder]} and {heading}"
            found[folder] = heading
    return found


def header_tables(heading: str, column: str) -> list[list[dict[str, str]]]:
    """The tables of a section with a column of that name, whatever subsection they sit in."""
    return [rows for table in tables(sections()[heading]) for rows in [table] if rows and column in rows[0]]


def page_rows() -> set[tuple[str, str, str, str, str, str]]:
    """The per-service tables (a Kind column) of each deployment section, under the heading of their service."""
    rows = set()
    for folder, heading in deployments().items():
        for title, body in subsections(section(heading)).items():
            for table in tables(body):
                if not table or "Kind" not in table[0]:
                    continue
                assert title in services() and services()[title][0] == folder, \
                    f"the table under '{title}' in {heading} is not a service of {folder}"
                for row in table:
                    rows.add((folder, title, row["Kind"], row["Name"],
                              row["Source"] if row["Kind"] == "mount" else "", row["Scope"]))
    return rows


def page_variables(heading: str) -> set[str]:
    return {row["Variable"] for table in header_tables(heading, "Variable") for row in table}


# ---------- the checks ----------

def test_both_installations_are_found() -> None:
    assert {"ait", "hackathon"} <= set(NAMES), NAMES


def test_every_folder_but_demo_runs_alone() -> None:
    """Every service a folder's services depend on is in that folder, its database included; demo/ needs the Issuer."""
    for service, (folder, spec) in services().items():
        if folder == "vc-stack/demo":
            continue
        for needed in spec.get("depends_on", []):
            assert services()[needed][0] == folder, f"{service} in {folder} depends on {needed} in {services()[needed][0]}"


def test_mimoto_config_comes_from_demo() -> None:
    """Both of Mimoto's config-server URIs name a demo/ service that mounts its files; the Issuer mounts none."""
    mounts = {}
    for _, service, kind, _, source, _ in compose_rows():
        if kind == "mount":
            mounts.setdefault(service, set()).add(source)
    props = dict(line.split("=", 1) for line in (STACK / "config/mimoto-bootstrap.properties").read_text(
        encoding="utf-8").splitlines() if "=" in line and not line.startswith("#"))
    hosts = {re.match(r"http://([^:/]+)", props[key]).group(1)
             for key in ("spring.cloud.config.uri", "config.server.file.storage.uri")}
    assert len(hosts) == 1, hosts
    host = hosts.pop()
    assert services()[host][0] == "vc-stack/demo", (host, services()[host][0])
    assert {"vc-stack/config", "installations/<name>/mimoto-issuers-config.json"} <= mounts[host], mounts[host]
    for service, (folder, _) in services().items():
        if folder == "vc-stack/issuer":
            found = {s for s in mounts.get(service, set()) if s == "vc-stack/config" or "mimoto" in s}
            assert not found, f"{service} in the Issuer mounts Mimoto's files: {found}"


def test_every_folder_has_one_section_that_says_what_it_needs() -> None:
    """The page has a section per folder, naming it in its Deploy line and what it needs from the other deployments."""
    assert set(deployments()) == set(folders()), sorted(set(deployments()) ^ set(folders()))
    for folder, heading in deployments().items():
        assert "**Needs from the other deployments:**" in section(heading), f"{heading} does not say what it needs"
        assert f"`{folder}/compose.yaml`" in section(heading), f"{heading} does not name {folder}/compose.yaml"


def test_each_section_lists_the_services_of_its_folder_with_their_images() -> None:
    for folder, heading in deployments().items():
        listed = {row["Compose service"]: row["Image"]
                  for table in header_tables(heading, "Compose service") for row in table}
        found = {service: spec for service, (f, spec) in services().items() if f == folder}
        assert set(listed) == set(found), (heading, sorted(set(listed) ^ set(found)))
        for service, spec in found.items():
            build = spec.get("build", {})
            expected = spec["image"] if "image" in spec else \
                "built from " + repo_path(posixpath.join(build["context"], build["dockerfile"]), folder)
            assert listed[service] == expected, (service, listed[service], expected)


def test_every_env_file_mount_and_port_is_in_the_page_and_nothing_else() -> None:
    expected, listed = compose_rows(), page_rows()
    assert all(row[5] in SCOPES for row in listed), [row for row in listed if row[5] not in SCOPES]
    missing, extra = sorted(expected - listed), sorted(listed - expected)
    assert not missing and not extra, f"in Compose, not in the page: {missing}\nin the page, not in Compose: {extra}"


def test_each_section_lists_the_compose_variables_of_its_folder_and_nothing_else() -> None:
    for folder, heading in deployments().items():
        expected, listed = compose_variables(folder), page_variables(heading)
        assert expected == listed, \
            f"{heading}: in Compose only: {sorted(expected - listed)}; in the page only: {sorted(listed - expected)}"


def test_each_server_runs_a_compose_file_that_includes_the_deployments_it_lists() -> None:
    """The Servers table: the Compose file exists, and the deployments it includes are the ones the row names."""
    by_heading = {heading: folder for folder, heading in deployments().items()}
    rows = [row for table in header_tables("Servers", "Compose file") for row in table]
    assert {row["Server"] for row in rows} >= {"transcript-demo", "issuer-dev"}, rows
    for row in rows:
        path = REPO_ROOT / row["Compose file"]
        assert path.is_file(), f"{row['Server']} runs {row['Compose file']}, which does not exist"
        included = {posixpath.dirname(posixpath.normpath(posixpath.join(posixpath.dirname(row["Compose file"]), inc)))
                    for inc in load(path)["include"]}
        named = {by_heading[name.strip()] for name in row["Deployments"].split(",")}
        assert included == named, (row["Server"], sorted(included), sorted(named))


def test_the_host_port_is_read_from_every_binding_form() -> None:
    for binding in ("9080:8080", "9080:8080/tcp", "127.0.0.1:9080:8080", "127.0.0.1:9080:8080/udp", "[::1]:9080:8080"):
        assert host_port(binding) == "9080", (binding, host_port(binding))


def test_every_host_port_is_public_or_internal_in_the_allowlist() -> None:
    rows = [row for table in tables(section("Ingress allowlist")) for row in table if row.get("Host port")]
    listed = {row["Host port"]: (row["Service"], row["Exposure"]) for row in rows}
    by_deployment = {row["Host port"]: row["Deployment"] for row in rows}
    ports = compose_ports()
    assert set(listed) == set(ports), sorted(set(listed) ^ set(ports))
    for port, service in ports.items():
        assert listed[port][0] == service, (port, listed[port], service)
        assert deployments()[services()[service][0]] == by_deployment[port], (port, by_deployment[port])
        assert listed[port][1] in {"public", "internal"}, (port, listed[port])


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
