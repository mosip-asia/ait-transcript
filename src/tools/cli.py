"""Unified Typer CLI for AIT Issuer Platform Developer & Operational Tools."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated, Optional

import typer

from tools import generate_csv as gc_mod
from tools import issue_and_verify as iv_mod
from tools import render_mimoto_issuers_config as rmc_mod

app = typer.Typer(
    name="tools",
    help="AIT Issuer Platform Operational & Developer Tools.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# ------------------------------------------------------------------------------
# 1. generate-csv Subcommand
# ------------------------------------------------------------------------------
generate_csv_app = typer.Typer(
    name="generate-csv",
    help="Generate student identity CSV from persona fixtures.",
    no_args_is_help=False,
)


@generate_csv_app.callback(invoke_without_command=True)
def generate_csv_cmd(
    ctx: typer.Context,
    students: Annotated[
        Path,
        typer.Option("--students", "-s", help="Path to students.json persona fixture"),
    ] = gc_mod.STUDENTS_JSON,
    out: Annotated[
        Path,
        typer.Option("--out", "-o", help="Output path for student_identity_data.csv"),
    ] = gc_mod.OUT_CSV,
) -> None:
    """Generate student identity CSV for Inji Certify from persona fixtures."""
    if ctx.invoked_subcommand is not None:
        return
    data = gc_mod.load_students(students)
    rows = gc_mod.build_rows(data["students"])
    gc_mod.write_csv(rows, out)
    typer.echo(f"Wrote {len(rows)} rows, {len(gc_mod.CSV_COLUMNS)} columns to {out}")


# ------------------------------------------------------------------------------
# 2. render-mimoto Subcommand
# ------------------------------------------------------------------------------
render_mimoto_app = typer.Typer(
    name="render-mimoto",
    help="Render Mimoto issuers config and gateway configurations from templates.",
    no_args_is_help=False,
)


@render_mimoto_app.callback(invoke_without_command=True)
def render_mimoto_cmd(
    ctx: typer.Context,
    installation: Annotated[
        Optional[str],
        typer.Option("--installation", "-i", help="Target installation tenant (e.g. ait, hackathon)"),
    ] = None,
) -> None:
    """Render Mimoto issuers config from installation template."""
    if ctx.invoked_subcommand is not None:
        return
    env = dict(os.environ)
    if installation:
        env["INSTALLATION"] = installation
    elif "INSTALLATION" not in env:
        env["INSTALLATION"] = "ait"

    for path, content in rmc_mod.render(env).items():
        path.write_text(content, encoding="utf-8")
        typer.echo(f"Wrote {path}")


# ------------------------------------------------------------------------------
# 3. issue-and-verify Subcommand (with subcommands: issue, verify, refused)
# ------------------------------------------------------------------------------
issue_verify_app = typer.Typer(
    name="issue-and-verify",
    help="Scripted issuance and verification without a browser or a wallet.",
    no_args_is_help=True,
)


@issue_verify_app.command("issue")
def issue_cmd(
    installation: Annotated[str, typer.Argument(help="Target installation (e.g. ait, hackathon)")],
    persona: Annotated[str, typer.Argument(help="Keycloak username, e.g. ait-2026-0001")],
    scope: Annotated[str, typer.Option("--scope", "-s", help="Credential scope")] = "ait_transcript_vc_ldp",
    out: Annotated[
        Path,
        typer.Option("--out", "-o", help="Output path for credential JSON"),
    ] = Path(".demo-state/smoke-credential.json"),
    certify_url: Annotated[str, typer.Option("--certify-url", help="Certify base URL")] = iv_mod.CERTIFY,
) -> None:
    """Issue a credential directly and write it to OUT."""
    import httpx

    old_certify = iv_mod.CERTIFY
    iv_mod.CERTIFY = certify_url
    try:
        with httpx.Client(timeout=60) as client:
            credential = iv_mod.issue(client, installation, persona, scope)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(credential, indent=2), encoding="utf-8")
            typer.echo(f"OK: issued {scope} for {persona} -> {out}")
    finally:
        iv_mod.CERTIFY = old_certify


@issue_verify_app.command("verify")
def verify_cmd(
    credential: Annotated[Path, typer.Argument(help="Path to credential JSON file")],
    claims: Annotated[
        Optional[list[str]],
        typer.Argument(help="Claim paths to tamper, e.g. fullName courses[0].courses[0].grade"),
    ] = None,
    verify_url: Annotated[str, typer.Option("--verify-url", help="Verify service URL")] = iv_mod.VERIFY_SERVICE,
) -> None:
    """Verify a credential file, then test that tampered copies fail verification."""
    import httpx

    claims = claims or []
    old_verify = iv_mod.VERIFY_SERVICE
    iv_mod.VERIFY_SERVICE = verify_url
    try:
        with httpx.Client(timeout=60) as client:
            cred_data = json.loads(credential.read_text(encoding="utf-8"))
            problems = iv_mod.verify_step(client, cred_data, claims)
            if problems:
                for problem in problems:
                    typer.secho(f"FAIL: {problem}", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1)
            tamper_list = ", ".join(["id", *claims])
            typer.echo(
                f"OK: credential verifies (SUCCESS); tampered {tamper_list} each fail (ERR_SIGNATURE_VERIFICATION_FAILED)"
            )
    finally:
        iv_mod.VERIFY_SERVICE = old_verify


@issue_verify_app.command("refused")
def refused_cmd(
    installation: Annotated[str, typer.Argument(help="Target installation (e.g. ait, hackathon)")],
    persona: Annotated[str, typer.Argument(help="Keycloak username, e.g. ait-2026-0002")],
    code: Annotated[str, typer.Argument(help="Expected OpenID4VCI error code, e.g. checklist_failed")],
    scope: Annotated[str, typer.Option("--scope", "-s", help="Credential scope")] = "ait_transcript_vc_ldp",
    certify_url: Annotated[str, typer.Option("--certify-url", help="Certify base URL")] = iv_mod.CERTIFY,
) -> None:
    """Verify that a credential request is refused with CODE."""
    import httpx

    old_certify = iv_mod.CERTIFY
    iv_mod.CERTIFY = certify_url
    try:
        with httpx.Client(timeout=60) as client:
            resp = iv_mod.credential_request(client, installation, persona, scope)
            actual_code = iv_mod.refusal_code(resp)
            if actual_code != code:
                typer.secho(
                    f"FAIL: {persona}: expected error {code}, got {actual_code!r}",
                    fg=typer.colors.RED,
                    err=True,
                )
                raise typer.Exit(code=1)
            typer.echo(f"OK: {scope} for {persona} refused with {actual_code}")
    finally:
        iv_mod.CERTIFY = old_certify


# Register submenus under the main tools CLI
app.add_typer(generate_csv_app, name="generate-csv")
app.add_typer(render_mimoto_app, name="render-mimoto")
app.add_typer(issue_verify_app, name="issue-and-verify")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
