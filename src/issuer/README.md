# Inji Certify Issuer Module

This directory contains the custom **Inji Certify** engine module, containing the Data-Provider SPI Plugin (`IssuerDataProviderPlugin`) and its multi-stage Docker build recipe.

---

## 1. Directory Structure

```
src/issuer/
├── plugin/               # Java 21 SPI DataProvider plugin source & pom.xml
│   ├── src/main/java/    #   - IssuerDataProviderPlugin implementation
│   └── src/test/java/    #   - Comprehensive JUnit test suite
├── Dockerfile            # Multi-stage image build (bakes plugin into Inji Certify)
└── README.md
```

---

## 2. Developer Experience (DX) & Inner Loops

When developing or modifying the DataProvider SPI plugin (`plugin/src/main/java/...`), choose the feedback loop that fits your task:

### Loop 1: Fast Inner Loop — Unit Testing (~3s)
Run JUnit tests in CLI without running Docker or spinning up any databases:
```bash
cd src/issuer/plugin
mvn test
```
*(Or in Docker if Maven is not installed locally):*
```bash
docker run --rm -v "$PWD/src/issuer/plugin:/src" -w /src maven:3.9-eclipse-temurin-21 mvn test
```
Tests in-memory HTTP responses, error mappings, and JSON escaping in **~3 seconds**.

---

### Loop 2: Live Testing with Root Compose (~7s)
Test your changes inside the full Inji Certify container runtime from the repo root:
```bash
# From repository root:
docker compose up -d --build
```
Builds and restarts the container with the updated image in **~7 seconds** via Docker BuildKit caching.

---

### Loop 3: Hot JAR Mount Mode (~3s Reload)
For rapid local iteration without rebuilding Docker images:

1. **Option A: Control via root `.env`:**
   In your root `.env` file, toggle `COMPOSE_FILE`:
   ```env
   # Merge compose.dev.yaml to mount the local JAR
   COMPOSE_FILE=compose.yaml:compose.dev.yaml
   ```
   Now all standard Docker Compose commands automatically mount your local plugin JAR directly into `/home/inji/additional_jars/`.

2. **Option B: One-Command Recompile & Update (`./dev-reload.sh`)**
   ```bash
   ./dev-reload.sh
   ```
   *Compiles the plugin JAR and updates Inji Certify with the fresh JAR in **~3 seconds flat**.*

---

## 3. Building Container Images

To build the standalone Certify image manually:

```bash
docker build -t ghcr.io/mosip-asia/ait-certify:latest src/issuer
```

---

## 4. Production Deployment

Production and staging deployments are orchestrated independently via `deploy/compose.yaml`, pulling release images from GitHub Container Registry without needing local build tools or source code.
