# Institutional Verifiable Credential Platform (AIT Issuer)

An enterprise Verifiable Credential (VC) platform built on **MOSIP Inji Certify**, issuing W3C VCDM 2.0 credentials (JSON-LD with Ed25519Signature2020) via OpenID4VCI.

The platform provides end-to-end credential lifecycle management: institutional clearance workflow, dynamic data resolution, cryptographic signing, credential design studio, and wallet issuance.

```mermaid
flowchart TD
    subgraph Client["Holder Wallets & Verifiers"]
        Wallet["Holder Wallet<br>(Inji Web :4004 / Mobile)"]
        Verifier["Inji Verify :4007"]
    end

    subgraph Platform["Institutional VC Platform (src/)"]
        Certify["Inji Certify Engine<br>(OpenID4VCI :9091)"]
        Plugin["IssuerDataProviderPlugin<br>(Java 21 SPI)"]
        Gateway["Institutional Clearance Workflow<br>(Gateway :8000)"]
        VCLab["VC Lab Registry<br>(Contexts, Schemas, Templates)"]
        Certify --- Plugin
        Plugin -->|1. POST /evaluations| Gateway
        Plugin -->|2. GET /student/{sub}/transcript| Adapter
    end

    subgraph Upstream["Institutional Systems & Ingress"]
        Adapter["SIS Data Adapter :8000"]
        Auth["Keycloak / OAuth Server :9080"]
    end

    Wallet -->|Bearer Token & Offer| Certify
    Wallet -.->|Auth Code Flow| Auth
    Wallet -->|Present Credential| Verifier
    Certify -.->|Fetch Schemas / Contexts| VCLab
```

---

## 1. Repository Architecture

The codebase is organized into modular components separating pure source code, container packaging, and deployment orchestration:

```
ait-transcript/
├── src/                                  # 100% PURE APPLICATION SOURCE CODE
│   ├── issuer/                           # Java 21 SPI Data-Provider Plugin (pom.xml + src/)
│   ├── gateway/                          # Institutional clearance & permission workflow engine
│   └── vc-lab/                           # VC Designer: W3C JSON-LD contexts, schemas, visual templates
│
├── docker/                               # CONTAINER PACKAGING RECIPES
│   ├── Dockerfile.certify                # Bakes src/issuer SPI plugin into Inji Certify
│   └── Dockerfile.gateway                # Packages src/gateway
│
├── compose.yaml                          # Local developer platform compose (builds from src/)
├── compose.dev.yaml                      # Loop 3: Hot JAR mount dev overlay (~3s reload)
├── .env.example                          # Root developer environment configuration
├── pyproject.toml / uv.lock              # Modern Python dependency management (uv)
│
├── deploy/                               # STANDALONE PRODUCTION / STAGING DEPLOYMENT
│   ├── compose.yaml                      # Pulls pre-built registry images (no source build)
│   ├── .env.example                      # Production environment template
│   ├── config/                           # Self-contained Inji Certify properties & SQL schemas
│   └── remote-deploy.sh                  # Automated VM deployment script used by CI/CD
│
├── installations/                        # MULTI-TENANT CONFIGURATION PROFILES
│   ├── ait/                              # Academic Transcript profile
│   └── hackathon/                        # Developer Passport & Achievement profile
│
└── vc-stack/                             # FULL DEMO STACK (Inji Web, Keycloak, Portal, Verify)
```

---

## 2. Prerequisites

- **Docker Desktop** (Compose v2) with Linux containers or WSL2 (on Windows).
- **Python 3.11+** and [`uv`](https://github.com/astral-sh/uv) (recommended for running tests and scripts).
- `jq`, `curl`, `awk` on the host.
- **Windows:** Run commands inside WSL2, not Git Bash, to avoid path-mangling issues on volume bind-mounts.

---

## 3. Deploy locally

Run every command from the repository root. Depending on your task, you can start the **Core Issuer Platform** (fast, focused) or the **Full End-to-End Demo** (with wallet, registrar portal, and verifier).

### Mode A: Core Issuer Platform (Developer Fast-Track)

Spins up the core Verifiable Credential Platform (`certify`, `gateway`, `vdr`, `database`, `adapter`):

```bash
# 1. Setup local environment
cp .env.example .env

# 2. Build the SPI plugin via the compiler container (no host Maven/Java needed)
docker compose run --rm plugin-builder

# 3. Start the platform
docker compose up -d
```

#### Fast Inner Loops for SPI Plugin Development:
- **Compiler Container Build & Reload (~2s):**
  Recompile the JAR into `src/issuer/target/` and reload Certify without rebuilding the image:
  ```bash
  docker compose run --rm plugin-builder && docker compose restart certify
  ```
- **In-Memory Unit Tests (~3s):**
  ```bash
  cd src/issuer && mvn test
  # Or via Docker:
  docker run --rm -v "$PWD/src/issuer:/src" -w /src maven:3.9-eclipse-temurin-21 mvn test
  ```
- **Multi-Stage Production Image Build:**
  To build the standalone release image using the 2-stage Dockerfile:
  ```bash
  docker build -f docker/Dockerfile.certify -t ghcr.io/mosip-asia/ait-certify:local .
  ```

---

### Mode B: Full End-to-End Demo (Stakeholder Journey)

Brings up the complete multi-service demonstration journey (Inji Web Wallet, Keycloak OAuth Server, Registrar Portal, and Inji Verify):

```bash
chmod +x run-demo.sh vc-stack/bootstrap.sh vc-stack/smoke.sh vc-stack/issuer-smoke.sh
INSTALLATION=ait ./run-demo.sh
```

`run-demo.sh` prepares the database, generates mock student data, renders Mimoto issuer configurations, compiles the plugin JAR, brings up the containers in order, and verifies health. A successful start ends with `Stack is healthy.`

#### To Reset or Switch Installation:
```bash
INSTALLATION=ait ./run-demo.sh --wipe          # Reset AIT stack
INSTALLATION=hackathon ./run-demo.sh --wipe    # Switch to Hackathon profile
```

---

## 4. How to test

All test suites are automated and runnable locally on your host or in CI.

### Unit & Host Tests (Run without Docker)

Using `uv` (or `.venv`):

```bash
# Run all host verification tests:
uv run python data/test_generate_csv.py
uv run python vc-stack/test_installation_guard.py
uv run python vc-stack/test_installations.py
uv run python vc-stack/test_authorization_server.py
uv run python vc-stack/test_configuration_contract.py
uv run python adapter/test_adapter.py
uv run python src/gateway/tests/test_credential_types.py
uv run python src/gateway/tests/test_evaluations.py
uv run python sis-bridge/test_bridge.py

# Run Java plugin unit tests:
cd src/issuer && mvn test
```

| Module | Test Target | What It Verifies |
|---|---|---|
| **Gateway** | `src/gateway/tests/test_credential_types.py` | Credential clearance rules, hold checks, zero balance, conferral predicates |
| **Gateway** | `src/gateway/tests/test_evaluations.py` | In-process evaluation of `POST /evaluations` across all installation personas |
| **Issuer Plugin** | `src/issuer/` (`mvn test`) | SPI `fetchData()` contract, HTTP retry/timeouts, strict JSON escaping, trace keys |
| **Adapter** | `adapter/test_adapter.py` | Validates OpenAPI contracts (`adapter/openapi.yaml`) against VCDM 2.0 schemas |
| **Contract** | `vc-stack/test_configuration_contract.py` | Holds Compose files and architecture documentation in sync |
| **Auth Server** | `vc-stack/test_authorization_server.py` | Validates OIDC issuer URLs, Keycloak realm mappings, and public endpoints |

---

### Integration Smoke Tests (Requires Running Stack)

A smoke test verifies real cryptographic issuance, signature verification, and ledger recording.

| Smoke Suite | Pre-requisite | Command | Expected Output |
|---|---|---|---|
| **Issuer Smoke** | Core platform up | `./vc-stack/issuer-smoke.sh` | `All Issuer-only smoke checks passed.` |
| **Full Stack Smoke** | Demo stack up | `./vc-stack/smoke.sh` | `All smoke checks passed.` |

---

## 5. Local Access & Stakeholder Walkthrough

When running the Full Demo Stack (`./run-demo.sh`):

### Local Port Endpoints

| Service | Local URL | Role |
|---|---|---|
| **Student Portal** | [http://localhost:4100/student/login](http://localhost:4100/student/login) | Student requests transcript |
| **Registrar Portal** | [http://localhost:4100/registrar/login](http://localhost:4100/registrar/login) | Registrar approves or revokes issuance |
| **Inji Web Wallet** | [http://localhost:4004](http://localhost:4004) | Digital wallet to claim & store credentials |
| **Inji Verify** | [http://localhost:4007](http://localhost:4007) | Verifier to validate credential signatures & status |
| **Inji Certify** | [http://localhost:9091](http://localhost:9091) | OpenID4VCI credential issuer & metadata |
| **Keycloak Admin** | [http://localhost:9080/admin/](http://localhost:9080/admin/) | Identity provider (`admin` / `admin`) |

### Stakeholder Walkthrough:
1. Open **Student Portal** ([http://localhost:4100/student/login](http://localhost:4100/student/login)) $\rightarrow$ Select `Nara Wattanakul` (`ait-2026-0001`) $\rightarrow$ Click **Request my transcript VC**.
2. Open **Registrar Portal** ([http://localhost:4100/registrar/login](http://localhost:4100/registrar/login)) $\rightarrow$ Sign in as Academic Registrar $\rightarrow$ Click **Approve**.
3. Return to Student Portal $\rightarrow$ Click **Claim your credential** $\rightarrow$ Redirects to **Inji Web**.
4. In Inji Web, sign in (`ait-2026-0001` / `inji`), select **AIT University**, and download the **AIT Transcript**.
5. Open **Inji Verify** ([http://localhost:4007](http://localhost:4007)) $\rightarrow$ Upload the downloaded credential JSON $\rightarrow$ Verdict reports **`allChecksSuccessful: true`**.

---

## 6. Deploying to GCP

The demonstration environment is continuously deployed to a Google Compute Engine VM behind Caddy (TLS):

- **Student Portal:** `https://transcript-demo.ait-vc.dpi.ait.ac.th/student/login`
- **Registrar Portal:** `https://transcript-demo.ait-vc.dpi.ait.ac.th/registrar/login`
- **Inji Web Wallet:** `https://wallet.transcript-demo.ait-vc.dpi.ait.ac.th`
- **Inji Verify:** `https://verify.transcript-demo.ait-vc.dpi.ait.ac.th`

Deployments are triggered via GitHub Actions: **Actions $\rightarrow$ Deploy $\rightarrow$ Run workflow**.

---

## 7. Documentation & References

- [Architecture & Topology (`wiki/architecture/vc-stack.md`)](./wiki/architecture/vc-stack.md)
- [ADR 0001: Approval Gate Beside the Data Path](./docs/adr/0001-approval-gate-beside-the-data-path.md)
- [Inji Certify Standalone Deployment (`deploy/README.md`)](./deploy/README.md)
- [Gateway Workflow Engine (`src/gateway/README.md`)](./src/gateway/README.md)
- [VC Lab Designer (`src/vc-lab/README.md`)](./src/vc-lab/README.md)
- [Inji Mobile Wallet Guide (`wallet/README.md`)](./wallet/README.md)
