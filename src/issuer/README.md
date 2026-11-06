# Inji Certify Issuer (Standalone Module)

This directory contains the standalone issuance engine for **Inji Certify**, bundling the custom Data-Provider SPI Plugin, standalone multi-stage container build, and isolated runtime configuration.

---

## 1. Directory Structure

```
src/issuer/
├── plugin/                                 # Java 21 SPI DataProvider plugin source & pom.xml
├── Dockerfile.certify                      # Multi-stage image build (bakes plugin into Certify)
├── compose.yaml                            # Standalone Compose manifest (Certify + Postgres + Ingress + VDR)
├── docker-compose.override.yml.example     # Loop 3: Dev override for hot JAR mounting
├── dev-reload.sh                           # Loop 3: Fast recompile & container restart script (~3s)
├── .env.example                            # Dedicated standalone Issuer environment template
├── config/                                 # Self-contained Certify properties & SQL init
└── README.md
```

---

## 2. Developer Experience (DX) & Inner Loops

When developing or modifying the DataProvider SPI plugin (`plugin/src/main/java/...`), choose the feedback loop that fits your task:

### Loop 1: Fast Inner Loop — Unit Testing (~3s)
Run JUnit tests in CLI without running Docker or spinning up any databases:
```bash
cd plugin
mvn test
```
*(Or in Docker if Maven is not installed locally):*
```bash
docker run --rm -v "$PWD/plugin:/src" -w /src maven:3.9-eclipse-temurin-21 mvn test
```
Tests in-memory HTTP responses, error mappings, and JSON escaping in **~3 seconds**.

---

### Loop 2: Live Testing in Docker (~7s)
Test your changes inside the full Inji Certify container runtime. Thanks to Docker BuildKit layer caching, Maven packages are cached, so rebuilding compiles only your modified code:
```bash
docker compose up -d --build
```
Builds and restarts the container with the updated image in **~7 seconds**.

---

### Loop 3: Even Faster "Hot JAR Mount" Mode (~3s Reload)
For rapid local iteration without rebuilding Docker images:

1. **Enable the local override once:**
   ```bash
   cp docker-compose.override.yml.example docker-compose.override.yml
   ```
   *This instructs Docker Compose to mount the local JAR directly into `/home/inji/additional_jars/`, overriding the baked JAR inside the container.*

2. **Recompile and restart in one command:**
   ```bash
   ./dev-reload.sh
   ```
   *Compiles the JAR and restarts Inji Certify in **~3 seconds flat**.*

---

## 3. Quickstart: Running the Standalone Issuer

To run Inji Certify in isolation (without demo portal, mock Keycloak, or external test harnesses):

```bash
cd src/issuer

# 1. Copy the standalone environment template
cp .env.example .env

# 2. Build and start the services
docker compose build
docker compose up -d
```

---

## 4. Services

| Service | Image / Build | Port | Role |
|---|---|---|---|
| `certify` | Built via `Dockerfile.certify` (`injistack/inji-certify-with-plugins:0.14.0`) | `9090` | Inji Certify core issuance engine |
| `database` | `postgres:15` | `6440` | Internal ledger, keystore, and credential configuration database |
| `certify-nginx` | `nginx:stable` | `9091` | Ingress router: rewrites `/.well-known/` discovery, handles CORS, proxies `/contexts/` |
| `vdr` | `nginx:stable` | internal | Static mock VDR serving authored JSON-LD schemas |

---

## 5. Production & CI/CD Release Flow

When cutting a release:
1. **CI Pipeline:** Runs `docker build -t ghcr.io/mosip-asia/ait-certify:<tag> -f Dockerfile.certify .` from `src/issuer/`.
2. **Push:** Pushes the verified immutable image to GitHub Container Registry.
3. **Deploy:** Production environments pull `ghcr.io/mosip-asia/ait-certify:<tag>` via `.env` (`CERTIFY_IMAGE=...`) without needing Java, Maven, or source code.
