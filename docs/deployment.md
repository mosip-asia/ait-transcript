# CI/CD, Deployment & Network Ingress Architecture

This document describes the deployment architecture, continuous delivery (CD) pipeline, NetBird mesh VPN overlay, and remote host automation used across **dev**, **uat**, and **production** environments.

---

## 1. Branching & Promotion Lifecycle

```
[feature/xxx] ---> [dev] (tag vX.Y.Z -> CD deploys to Dev VM)
                    │
                    ▼ (scripts/release.sh promote uat)
                  [uat] (CD deploys to UAT VM)
                    │
                    ▼ (scripts/release.sh promote main)
                  [main] (CD deploys to Production VM)
```

1. **Development (`dev`)**:
   - Primary integration branch. Pushes directly to `dev` do not trigger deployments.
   - Run local validation and unit tests with `scripts/release-checks.sh` or individual test suites (`tests/test_*.py`).
2. **Release Tag (`v*`) & Dev Deployment**:
   - Cut release tag: `bash scripts/release.sh vX.Y.Z`.
   - Running `scripts/release.sh` executes pre-flight checks (data guard, Compose configs, JSON schemas, and host test suite), tags the tip of `origin/dev`, and pushes the tag to GitHub.
   - Pushing the tag triggers [`.github/workflows/cd.yml`](../.github/workflows/cd.yml), deploying automatically to the **dev** environment (VM `ait-itserv-dev`).
3. **UAT Promotion (`uat`)**:
   - Fast-forward branch: `bash scripts/release.sh promote uat [vX.Y.Z]`.
   - The push automatically deploys to the **uat** environment (VM `ait-itserv-uat`).
4. **Production Promotion (`main`)**:
   - Fast-forward branch: `bash scripts/release.sh promote main [vX.Y.Z]`.
   - The push automatically deploys to the **production** environment (campus VM `ait-itserv-vm`).

---

## 2. GitHub Environments & Credentials

Configure three environments in GitHub (**Settings > Environments**): `dev`, `uat`, and `production`. All three execute the unified deployment job in `.github/workflows/cd.yml`.

| Variable / Secret | Type | Scope | Description |
|---|---|---|---|
| `NETBIRD_SETUP_KEY` | Secret | Repo / Env | NetBird WireGuard mesh VPN setup key for runner access |
| `SSH_PRIVATE_KEY` | Secret | Environment | SSH private key to authenticate against deployment server |
| `SERVER_HOST` | Variable | Environment | Target server IP or NetBird mesh hostname (e.g. `ait-itserv-dev.netbird.selfhosted`) |
| `SERVER_USER` | Variable | Environment | Target server SSH user |
| `SERVER_PROJECT_DIR` | Variable | Environment | Target directory on host (e.g. `/opt/ait-transcript`) |
| `NETBIRD_MANAGEMENT_URL` | Variable | Repo / Env | *(Optional)* Self-hosted NetBird management URL |

---

## 3. Deployment Flow & Host Automation

Remote server deployment is executed via SSH over the secure NetBird mesh network without opening SSH ports to the public internet:

```
GitHub Actions Runner
       │ (NetBird VPN Mesh)
       ▼
Target VM (ait-itserv-*)
       ├── 1. Fetch tags and checkout release commit SHA
       ├── 2. Record current stable baseline (.deploy_success)
       ├── 3. Execute `bash scripts/deploy.sh <installation> [--wipe]`
       │      ├── Docker plugin jar build
       │      ├── Docker Compose stack bring-up (compose.yaml, overlays)
       │      └── Automatic health checks & template sync
       ├── 4. Execute post-deployment smoke test (`scripts/smoke-test.sh`)
       └── 5. On success: write commit SHA to `.deploy_success`
              On failure: automatic rollback to previous stable SHA
```

---

## 4. Ingress & Reverse Proxy Overlay

The deployment leverages layered Docker Compose configurations and a reverse proxy (Caddy / Traefik / Nginx) to enforce security boundaries between public endpoints and internal management APIs.

### Public Web Ingress (TLS / Caddy / Traefik)
Internet-facing endpoints accessible to students, holders, and verifiers:
- **Student & Registrar Portal**: `https://transcript-demo.ait-vc.dpi.ait.ac.th/`
- **Inji Web Wallet**: `https://wallet.transcript-demo.ait-vc.dpi.ait.ac.th/`
- **Credential Verifier**: `https://verify.transcript-demo.ait-vc.dpi.ait.ac.th/`
- **OpenID4VCI Issuer Metadata**: `https://api.transcript-demo.ait-vc.dpi.ait.ac.th/.well-known/openid-credential-issuer`

### Private Administrative & API Access via NetBird VPN
Internal ports and management interfaces are never exposed to the public internet. Only clients authenticated via the NetBird WireGuard network can reach:
- **Inji Certify Admin & Swagger UI**: `http://<vm-netbird-ip>:9091/v1/certify/swagger-ui/index.html`
- **Pre-Authorized Issuance API**: `POST http://<vm-netbird-ip>:9091/v1/certify/pre-authorized-data`
- **SIS Adapter Contract Endpoints**: `http://<vm-netbird-ip>:8000/student/{sub}/eligibility`
- **PostgreSQL Database**: Port `5432`
- **Keycloak Admin Console**: Port `9080`

---

## 5. Fail-Forward Policy & Automated Rollback

- **Sensitive Data Guard**: Pre-deployment check `bash scripts/check-data-guard.sh` prevents uncommitted secrets, CSV identity leaks, CRLF mismatches, or large binaries.
- **Smoke Testing**: Every deployment executes `scripts/smoke-test.sh` verifying real cryptographic token acquisition, credential issuance, signature verification, and ledger recording.
- **Persistent Baseline (`.deploy_success`)**: The deployed commit SHA is written to `.deploy_success` only after the deployment and smoke tests pass.
- **Zero-Touch Rollback**: If `scripts/deploy.sh` or post-deployment checks fail:
  1. The workflow checks out the previous verified SHA recorded in `.deploy_success`.
  2. Runs `bash scripts/deploy.sh "$INSTALLATION"` to restore the last known working stack.
  3. Fails the GitHub Actions run to alert operators while leaving the server in a stable, functioning state.
