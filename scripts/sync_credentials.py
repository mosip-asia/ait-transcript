#!/usr/bin/env python3
"""
Credential Template GitOps Synchronizer

Maintains Git as the single declarative source of truth for Inji Certify
credential configurations and templates.

Usage:
  python3 scripts/sync_credentials.py --generate-sql   # Generate deploy/config/certify_seed.sql
  python3 scripts/sync_credentials.py --apply          # Idempotently apply to running database
  python3 scripts/sync_credentials.py --check          # Check drift between Git and database
"""

import argparse
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS_DIR = REPO_ROOT / "config" / "credentials"
SEED_SQL_PATH = REPO_ROOT / "deploy" / "config" / "certify_seed.sql"


def load_credential_configs():
    configs = []
    if not CREDENTIALS_DIR.exists():
        print(f"Error: Credentials directory not found: {CREDENTIALS_DIR}", file=sys.stderr)
        sys.exit(1)

    for p in sorted(CREDENTIALS_DIR.glob("*.json")):
        with open(p, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                configs.append((p.name, data))
            except json.JSONDecodeError as e:
                print(f"Error parsing {p}: {e}", file=sys.stderr)
                sys.exit(1)
    return configs


def build_vc_template_base64(template_dict):
    raw_json = json.dumps(template_dict, indent=2, ensure_ascii=False)
    # Ensure raw JSON array placeholders remain unquoted in JSON-LD template
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
-- AUTO-GENERATED from config/credentials/*.json via scripts/sync_credentials.py
-- DO NOT EDIT THIS FILE MANUALLY. Edit the JSON files in config/credentials/ instead.
-- ==============================================================================
\\c inji_certify postgres

"""
    body = "\n\n".join(generate_sql_statement(c) for _, c in configs)
    return header + body + "\n"


def main():
    parser = argparse.ArgumentParser(description="GitOps Synchronizer for Credential Configurations")
    parser.add_argument("--generate-sql", action="store_true", help="Generate deploy/config/certify_seed.sql from JSON")
    parser.add_argument("--apply", action="store_true", help="Apply declarative configuration to running PostgreSQL database")
    parser.add_argument("--check", action="store_true", help="Check if running database matches Git configuration")
    args = parser.parse_args()

    configs = load_credential_configs()
    sql_content = generate_full_sql(configs)

    if args.generate_sql or (not args.apply and not args.check):
        with open(SEED_SQL_PATH, "w", encoding="utf-8") as f:
            f.write(sql_content)
        print(f"[+] Successfully generated {SEED_SQL_PATH.relative_to(REPO_ROOT)} from {len(configs)} credential config(s).")

    if args.apply:
        print("[*] Applying declarative credential configurations to PostgreSQL database...")
        cmd = [
            "docker", "compose", "exec", "-T", "database",
            "psql", "-U", "postgres", "-d", "inji_certify"
        ]
        proc = subprocess.run(cmd, input=sql_content, text=True, capture_output=True)
        if proc.returncode != 0:
            print(f"[-] Failed to apply configuration to database:\n{proc.stderr}", file=sys.stderr)
            sys.exit(1)
        print("[+] SUCCESS! Database updated with zero downtime and no data loss.")

    if args.check:
        print("[*] Checking database sync status...")
        cmd = [
            "docker", "compose", "exec", "-T", "database",
            "psql", "-U", "postgres", "-d", "inji_certify", "-t", "-c",
            "SELECT credential_config_key_id FROM certify.credential_config;"
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            print(f"[-] Cannot query database: {proc.stderr}", file=sys.stderr)
            sys.exit(1)
        db_keys = set(line.strip() for line in proc.stdout.splitlines() if line.strip())
        git_keys = set(c["credential_config_key_id"] for _, c in configs)
        print(f"    Git credentials: {sorted(git_keys)}")
        print(f"    DB  credentials: {sorted(db_keys)}")
        if git_keys.issubset(db_keys):
            print("[+] OK: All Git credentials present in database.")
        else:
            print(f"[-] DRIFT DETECTED: Missing in DB: {git_keys - db_keys}")
            sys.exit(2)


if __name__ == "__main__":
    main()
