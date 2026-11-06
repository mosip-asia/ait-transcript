# Verifiable Credential Platform Deployment

This directory contains standalone deployment manifests and runtime configurations for staging and production environments.

Unlike root development (`compose.yaml`), the deployment compose manifest pulls pre-built immutable container images from the GitHub Container Registry and requires no local compilers, JDKs, or Python toolchains.

---

## 1. Directory Structure

```
deploy/
├── compose.yaml          # Deployment compose manifest (pulls registry images)
├── .env.example          # Environment template for deployments
├── config/               # Self-contained Inji Certify properties & SQL schemas
│   ├── certify_init.sql
│   ├── certify-default.properties
│   ├── certify-nginx.conf
│   └── vp_request_config.json
└── remote-deploy.sh      # Automated VM deployment script used by CI/CD
```

---

## 2. Quickstart: Deploying to a Server or VM

```bash
cd deploy

# 1. Configure deployment environment
cp .env.example .env

# 2. Deploy services
docker compose pull
docker compose up -d
```
