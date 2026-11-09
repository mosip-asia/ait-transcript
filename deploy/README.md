# Verifiable Credential Platform Deployment

This directory contains deployment overlays and runtime configurations for staging and production environments.

---

## 1. Directory Structure

```
deploy/
├── base/                      # Common Inji platform defaults
│   ├── certify_init.sql       # Postgres schema initialization
│   ├── certify-default.properties # Base Inji Certify Spring properties
│   ├── certify-nginx.conf     # Nginx reverse proxy routing
│   └── vp_request_config.json # OpenID4VP request specifications
├── ait/                       # AIT Tenant profile (academic transcript)
│   ├── certify-installation.properties
│   ├── keycloak-realm.json
│   ├── mimoto-issuers-config.json.template
│   ├── gateway.env
│   ├── smoke.json
│   └── adapter/
├── hackathon/                 # Hackathon Tenant profile (developer passport & achievements)
│   ├── certify-installation.properties
│   ├── keycloak-realm.json
│   ├── mimoto-issuers-config.json.template
│   ├── gateway.env
│   ├── smoke.json
│   └── adapter/
├── remote-deploy.sh           # Automated VM deployment script used by CI/CD
└── smoke.sh                   # Pure Bash issuance smoke test
```

---

## 2. Quickstart: Deploying the Platform

From the repository root:

```bash
# 1. Configure environment
cp .env.example .env

# 2. Select target tenant (ait or hackathon) in .env:
# INSTALLATION=ait

# 3. Deploy services
docker compose up -d

# 4. Verify issuance
./deploy/smoke.sh
```
