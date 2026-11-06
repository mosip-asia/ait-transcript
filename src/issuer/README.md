# Inji Certify Issuer (Standalone Deployment)

This directory contains the standalone deployment manifests and custom container configuration for **Inji Certify** with the Data-Provider SPI Plugin.

---

## 1. Directory Structure

```
src/issuer/
├── .env.example          # Environment template for standalone Issuer deployment
├── compose.yaml          # Compose manifest (Certify + Postgres + Nginx Ingress + Mock VDR)
├── docker-compose.yml    # Symlink to compose.yaml
├── Dockerfile.certify    # Multi-stage Dockerfile baking the SPI plugin into Certify
└── plugin/               # Data-Provider Plugin Java source
```

---

## 2. Quickstart: Running the Standalone Issuer

To run Inji Certify without the demo portal or mock services:

```bash
cd src/issuer

# 1. Copy the standalone environment template
cp .env.example .env

# 2. Build the custom Certify image with the plugin pre-baked
docker compose build

# 3. Start the services
docker compose up -d
```

---

## 3. Services

| Service | Image / Build | Port | Role |
|---|---|---|---|
| `certify` | Built via `Dockerfile.certify` (`injistack/inji-certify-with-plugins:0.14.0`) | `9090` | Inji Certify core issuance engine |
| `database` | `postgres:15` | `6440` | Internal ledger, keystore, and credential configuration database |
| `certify-nginx` | `nginx:stable` | `9091` | Ingress router: rewrites `/.well-known/` discovery, handles CORS, proxies `/contexts/` |
| `vdr` | `nginx:stable` | internal | Static mock VDR serving authored JSON-LD schemas |

---

## 4. Key Endpoints

- OpenID4VCI Issuer Metadata: `http://localhost:9091/.well-known/openid-credential-issuer`
- DID Document: `http://localhost:9091/.well-known/did.json`
- Credential Offer / Issuance: `http://localhost:9091/v1/certify/...`
