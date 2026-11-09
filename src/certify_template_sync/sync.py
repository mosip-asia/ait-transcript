#!/usr/bin/env python3
"""
certify-template-sync

GitOps Synchronizer for Inji Certify credential configurations and templates.

Maintains human-readable JSON files in Git as the single source of truth,
and idempotently synchronizes them with PostgreSQL.

Usage:
  # With root uv:
  uv run certify-template-sync --apply
  uv run certify-template-sync --generate-sql
  uv run certify-template-sync --check

  # With Docker Compose:
  docker compose run --rm template-sync

  # With standard Python:
  python3 -m certify_template_sync.sync --generate-sql
"""

import argparse
import base64
import json
import os
import subprocess
import sys
from pathlib import Path


def find_credentials_dir(custom_path=None):
    if custom_path:
        p = Path(custom_path)
        if p.exists():
            return p
    env_path = os.getenv("CREDENTIALS_DIR")
    if env_path and Path(env_path).exists():
        return Path(env_path)

    # Search common relative locations
    here = Path(__file__).resolve().parent
    candidates = [
        Path("/config"),                             # Docker container mount
        here.parent.parent / "config" / "credentials", # Relative to src/certify_template_sync
        here / "credentials",                        # Local folder
        Path.cwd() / "config" / "credentials",       # CWD relative
    ]
    for c in candidates:
        if c.exists():
            return c
    return here.parent.parent / "config" / "credentials"


def find_seed_sql_path():
    env_path = os.getenv("SEED_SQL_PATH")
    if env_path:
        return Path(env_path)
    here = Path(__file__).resolve().parent
    candidates = [
        here.parent.parent / "deploy" / "config" / "certify_seed.sql",
        Path.cwd() / "deploy" / "config" / "certify_seed.sql",
    ]
    for c in candidates:
        if c.parent.exists():
            return c
    return here.parent.parent / "deploy" / "config" / "certify_seed.sql"


def load_credential_configs(creds_dir):
    configs = []
    if not creds_dir.exists():
        print(f"[-] Error: Credentials directory not found: {creds_dir}", file=sys.stderr)
        sys.exit(1)

    for p in sorted(creds_dir.glob("*.json")):
        with open(p, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                configs.append((p.name, data))
            except json.JSONDecodeError as e:
                print(f"[-] Error parsing {p}: {e}", file=sys.stderr)
                sys.exit(1)

    if not configs:
        print(f"[-] Warning: No .json credential files found in {creds_dir}", file=sys.stderr)
    return configs


def build_vc_template_base64(template_dict):
    raw_json = json.dumps(template_dict, indent=2, ensure_ascii=False)
    # Ensure unquoted raw JSON expressions (like courses array) are preserved
    raw_json = raw_json.replace('"courses": "${courses}"', '"courses": ${courses}')
    return base64.b64encode(raw_json.encode("utf-8")).decode("ascii")


def escape_sql_str(val):
    if val is None:
        return "NULL"
    return "'" + str(val).replace("'", "''") + "'"


def escape_sql_jsonb(val):
    if val is None:
        return "NULL"
    raw = json.dumps(val, ensure_ascii=False)
    return f"{escape_sql_str(raw)}::JSONB"


def escape_sql_text_array(val):
    if val is None:
        return "NULL"
    items = [escape_sql_str(x) for x in val]
    return f"ARRAY[{', '.join(items)}]::TEXT[]"


def generate_sql_statement(config):
    key_id = config["credential_config_key_id"]
    status = config.get("status", "active")
    b64_template = build_vc_template_base64(config["vc_template"])
    context_str = ",".join(config.get("context", []))
    cred_type = config.get("credential_type", "AitTranscriptCredential,VerifiableCredential")
    cred_format = config.get("credential_format", "ldp_vc")
    did_url = config.get("did_url", "did:key:z6MkpPLACEHOLDERreplaceMeViaBootstrapDidRefreshScript1")
    key_mgr_app = config.get("key_manager_app_id", "CERTIFY_VC_SIGN_ED25519")
    key_mgr_ref = config.get("key_manager_ref_id", "ED25519_SIGN")
    sig_algo = config.get("signature_algo", "EdDSA")
    sig_suite = config.get("signature_crypto_suite", "Ed25519Signature2020")
    scope = config.get("scope", "ait_transcript_vc_ldp")
    qr_algo = config.get("qr_signature_algo", "EdDSA")

    display_jsonb = escape_sql_jsonb(config.get("display"))
    display_order_arr = escape_sql_text_array(config.get("display_order"))
    binding_methods_arr = escape_sql_text_array(config.get("cryptographic_binding_methods_supported"))
    signing_algs_arr = escape_sql_text_array(config.get("credential_signing_alg_values_supported"))
    proof_types_jsonb = escape_sql_jsonb(config.get("proof_types_supported"))
    cred_subject_jsonb = escape_sql_jsonb(config.get("credential_subject"))
    plugin_configs_jsonb = escape_sql_jsonb(config.get("plugin_configurations"))
    status_purpose_arr = escape_sql_text_array(config.get("credential_status_purpose"))
    qr_settings_jsonb = escape_sql_jsonb(config.get("qr_settings"))

    sql = f"""-- Credential: {key_id}
INSERT INTO certify.credential_config (
    credential_config_key_id, config_id, status, vc_template, doctype, sd_jwt_vct, context,
    credential_type, credential_format, did_url, key_manager_app_id, key_manager_ref_id,
    signature_algo, signature_crypto_suite, sd_claim, display, display_order, scope,
    cryptographic_binding_methods_supported, credential_signing_alg_values_supported,
    proof_types_supported, credential_subject, mso_mdoc_claims, plugin_configurations,
    credential_status_purpose, qr_settings, qr_signature_algo, cr_dtimes, upd_dtimes
) VALUES (
    {escape_sql_str(key_id)},
    gen_random_uuid()::VARCHAR(255),
    {escape_sql_str(status)},
    {escape_sql_str(b64_template)},
    NULL,
    NULL,
    {escape_sql_str(context_str)},
    {escape_sql_str(cred_type)},
    {escape_sql_str(cred_format)},
    {escape_sql_str(did_url)},
    {escape_sql_str(key_mgr_app)},
    {escape_sql_str(key_mgr_ref)},
    {escape_sql_str(sig_algo)},
    {escape_sql_str(sig_suite)},
    NULL,
    {display_jsonb},
    {display_order_arr},
    {escape_sql_str(scope)},
    {binding_methods_arr},
    {signing_algs_arr},
    {proof_types_jsonb},
    {cred_subject_jsonb},
    NULL,
    {plugin_configs_jsonb},
    {status_purpose_arr},
    {qr_settings_jsonb},
    {escape_sql_str(qr_algo)},
    NOW(),
    NULL
)
ON CONFLICT (credential_config_key_id) DO UPDATE SET
    vc_template = EXCLUDED.vc_template,
    context = EXCLUDED.context,
    credential_type = EXCLUDED.credential_type,
    credential_format = EXCLUDED.credential_format,
    did_url = EXCLUDED.did_url,
    signature_algo = EXCLUDED.signature_algo,
    signature_crypto_suite = EXCLUDED.signature_crypto_suite,
    display = EXCLUDED.display,
    display_order = EXCLUDED.display_order,
    scope = EXCLUDED.scope,
    cryptographic_binding_methods_supported = EXCLUDED.cryptographic_binding_methods_supported,
    credential_signing_alg_values_supported = EXCLUDED.credential_signing_alg_values_supported,
    proof_types_supported = EXCLUDED.proof_types_supported,
    credential_subject = EXCLUDED.credential_subject,
    plugin_configurations = EXCLUDED.plugin_configurations,
    credential_status_purpose = EXCLUDED.credential_status_purpose,
    qr_settings = EXCLUDED.qr_settings,
    qr_signature_algo = EXCLUDED.qr_signature_algo,
    upd_dtimes = NOW();"""
    return sql


def generate_full_sql(configs):
    header = """-- ==============================================================================
-- Inji Certify Credential Configurations & Templates
-- AUTO-GENERATED from config/credentials/*.json via certify-template-sync
-- DO NOT EDIT THIS FILE MANUALLY. Edit the JSON files in config/credentials/ instead.
-- ==============================================================================
\\c inji_certify postgres

"""
    body = "\n\n".join(generate_sql_statement(c) for _, c in configs)
    return header + body + "\n"


def execute_sql(sql_content):
    """Executes SQL using psycopg if available, otherwise falls back to docker compose exec psql."""
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    dbname = os.getenv("POSTGRES_DB", "inji_certify")
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")

    # Try psycopg (standard uv / pip library)
    try:
        import psycopg
        conn = psycopg.connect(
            host=host, port=port, dbname=dbname, user=user, password=password, autocommit=True
        )
        with conn.cursor() as cur:
            # Strip \c inji_certify postgres for direct psycopg connection
            executable_sql = "\n".join(
                line for line in sql_content.splitlines() if not line.strip().startswith("\\c")
            )
            cur.execute(executable_sql)
        conn.close()
        return True
    except ImportError:
        pass
    except Exception as e:
        print(f"[-] Direct database connection to {host}:{port} failed: {e}", file=sys.stderr)
        print("[*] Attempting fallback via docker compose exec...", file=sys.stderr)

    # Fallback: docker compose exec database psql
    cmd = [
        "docker", "compose", "exec", "-T", "database",
        "psql", "-U", user, "-d", dbname
    ]
    proc = subprocess.run(cmd, input=sql_content, text=True, capture_output=True)
    if proc.returncode != 0:
        print(f"[-] Execution via docker compose failed:\n{proc.stderr}", file=sys.stderr)
        return False
    return True


def query_db_keys():
    """Queries existing credential keys from the database."""
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    dbname = os.getenv("POSTGRES_DB", "inji_certify")
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")

    try:
        import psycopg
        conn = psycopg.connect(
            host=host, port=port, dbname=dbname, user=user, password=password
        )
        with conn.cursor() as cur:
            cur.execute("SELECT credential_config_key_id FROM certify.credential_config;")
            rows = [r[0] for r in cur.fetchall()]
        conn.close()
        return set(rows)
    except ImportError:
        pass
    except Exception:
        pass

    # Fallback to docker compose
    cmd = [
        "docker", "compose", "exec", "-T", "database",
        "psql", "-U", user, "-d", dbname, "-t", "-c",
        "SELECT credential_config_key_id FROM certify.credential_config;"
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    return set(line.strip() for line in proc.stdout.splitlines() if line.strip())


def main():
    parser = argparse.ArgumentParser(description="GitOps Synchronizer for Inji Certify Credential Configurations")
    parser.add_argument("--dir", help="Path to credentials directory (defaults to auto-detection)")
    parser.add_argument("--generate-sql", action="store_true", help="Generate deploy/config/certify_seed.sql")
    parser.add_argument("--apply", action="store_true", help="Idempotently apply templates to PostgreSQL")
    parser.add_argument("--check", action="store_true", help="Check drift between Git and live database")
    args = parser.parse_args()

    creds_dir = find_credentials_dir(args.dir)
    seed_sql_path = find_seed_sql_path()

    print(f"[*] Reading credential definitions from: {creds_dir}")
    configs = load_credential_configs(creds_dir)
    print(f"    Loaded {len(configs)} configuration(s): {[c[0] for c in configs]}")
    sql_content = generate_full_sql(configs)

    if args.generate_sql:
        with open(seed_sql_path, "w", encoding="utf-8") as f:
            f.write(sql_content)
        print(f"[+] Generated seed SQL at: {seed_sql_path}")

    # Default action is --apply if not --check and not --generate-sql
    if args.apply or (not args.generate_sql and not args.check):
        print("[*] Synchronizing templates to PostgreSQL database...")
        success = execute_sql(sql_content)
        if not success:
            sys.exit(1)
        print("[+] SUCCESS! All credential templates synchronized in database (zero downtime, no data loss).")

    if args.check:
        print("[*] Checking configuration drift against database...")
        db_keys = query_db_keys()
        if db_keys is None:
            print("[-] Error: Could not query database to check drift.", file=sys.stderr)
            sys.exit(1)
        git_keys = set(c["credential_config_key_id"] for _, c in configs)
        print(f"    Git credentials: {sorted(git_keys)}")
        print(f"    DB  credentials: {sorted(db_keys)}")
        if git_keys.issubset(db_keys):
            print("[+] OK: All Git credentials present in database.")
        else:
            print(f"[-] DRIFT DETECTED: Missing in DB: {git_keys - db_keys}", file=sys.stderr)
            sys.exit(2)


if __name__ == "__main__":
    main()
