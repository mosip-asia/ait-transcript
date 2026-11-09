# VC Lab: Credential Designer & Schema Registry

**VC Lab** is the design studio and schema registry for the Verifiable Credential Platform. It is the single source of truth for:
1. **W3C JSON-LD Contexts** (`contexts/`): Machine-readable semantic definitions required by W3C VCDM 2.0.
2. **Credential Schemas** (`schemas/`): JSON Schemas defining required attributes, types, and constraints.
3. **Visual Templates** (`templates/`): Print-accurate HTML/CSS designs for generating verifiable A4 PDFs.

---

## 1. Directory Structure

```
src/vc-lab/
├── contexts/                 # Versioned W3C JSON-LD Contexts
│   ├── transcript/v1.json    #   - AIT Academic Transcript context
│   ├── developer-passport/   #   - Hackathon Developer Passport context
│   └── achievement/          #   - Hackathon Achievement Badge context
├── schemas/                  # Credential JSON Schemas
│   └── ait-transcript-credential.v2.schema.json
├── templates/                # Visual PDF Rendering Templates
│   ├── pdf-ait-transcript-template.html
│   └── ait_courses.py
└── README.md
```

---

## 2. How VC Lab "Runs" in the Architecture

VC Lab is not a heavy background server. It operates in two ways:

### A. In the Docker Stack (The Mock VDR)
In Compose (`src/issuer/compose.yaml` or `vc-stack/issuer/compose.yaml`), the `vdr` service runs a lightweight static Nginx container mounting `src/vc-lab/contexts`:

```yaml
vdr:
  image: nginx:stable
  volumes:
    - ../../src/vc-lab/contexts:/usr/share/nginx/html/contexts:ro
```

- When **Inji Certify** issues a credential, or **Inji Verify** validates one, their cryptographic engines resolve the `@context` URL by fetching from the VDR (via `certify-nginx` on port `9091`):
  ```
  GET http://localhost:9091/contexts/transcript/v1.json
  ```
- Nginx reads files live from disk, so any schema or context edit takes effect immediately without restarting containers.

### B. Running a Local Context Preview Server (Host Mode)
If you are developing or testing new credential contexts locally without running Docker:

```bash
# Start a simple HTTP server from the contexts folder:
cd src/vc-lab/contexts
python3 -m http.server 9091
```

Now you can curl and inspect the context at:
```bash
curl http://localhost:9091/transcript/v1.json | jq .
```

---

## 3. Designing a New Credential Type

To introduce a new credential into the institution:
1. **Define Schema:** Add `src/vc-lab/schemas/<credential-name>.schema.json`.
2. **Author JSON-LD Context:** Add `src/vc-lab/contexts/<credential-name>/v1.json` mapping each claim to a URI or `@json` literal.
3. **Add Clearance Rules:** In `src/gateway/credential_types.py`, add the scope and checklist rules (e.g. holds, eligibility).
4. **Configure Certify Seed:** Add the credential type row to `deploy/<name>/certify_seed.sql` (or `deploy/<name>/credentials/`).
