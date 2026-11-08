# certify-template-sync

Declarative GitOps Synchronizer for Inji Certify Credential Configurations & Templates.

Maintains human-readable JSON files in Git as the **single source of truth** and idempotently synchronizes them into PostgreSQL.

---

## Why this exists

Inji Certify stores credential configurations and W3C VC templates inside PostgreSQL table `certify.credential_config`.

Traditional seed SQL scripts:
- Require manual base64 encoding of VC templates.
- Only run on a fresh empty volume (`/docker-entrypoint-initdb.d/`).
- Make review in Git PRs nearly impossible.

`certify-template-sync`:
- Lets you write clean, human-readable JSON in `config/credentials/*.json`.
- Idempotently updates the running database via `ON CONFLICT (credential_config_key_id) DO UPDATE`.
- Preserves all runtime keys, status lists, and audit ledger entries.
- Runs with `uv`, plain Python, or via Docker Compose.

---

## Usage

### 1. With `uv` (Host / Local from root project)
```bash
# Apply templates directly to PostgreSQL:
uv run certify-template-sync --apply

# Generate fresh deploy/config/certify_seed.sql:
uv run certify-template-sync --generate-sql

# Check for configuration drift:
uv run certify-template-sync --check
```

### 2. With Docker Compose (Containerized via `docker/Dockerfile.template-sync`)
```bash
# Apply templates:
docker compose run --rm template-sync

# Check for drift:
docker compose run --rm template-sync --check
```

### 3. With standard Python (zero external dependencies)
```bash
python3 src/certify_template_sync/sync.py --generate-sql
python3 src/certify_template_sync/sync.py --apply
```

---

## Configuration

| Environment Variable | Default (Local / Docker) | Description |
| :--- | :--- | :--- |
| `CREDENTIALS_DIR` | `./config/credentials` or `/config` | Directory containing credential JSON files |
| `POSTGRES_HOST` | `localhost` (or `database` in Docker) | PostgreSQL hostname |
| `POSTGRES_PORT` | `6440` (or `5432` in Docker) | PostgreSQL port |
| `POSTGRES_DB` | `inji_certify` | Inji Certify database name |
| `POSTGRES_USER` | `postgres` | Database username |
| `POSTGRES_PASSWORD` | `postgres` | Database password |
| `SEED_SQL_PATH` | `deploy/config/certify_seed.sql` | Output path for generated seed SQL |
