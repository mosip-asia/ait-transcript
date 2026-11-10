# VC Lab: Drag-and-Drop Visual Credential Studio (Planned)

**VC Lab** is the visual design studio for the Verifiable Credential Platform. It allows institutional administrators and credential designers to visually compose, preview, and export W3C VCDM 2.0 Verifiable Credentials.

---

## 1. Planned Capabilities

1. **Visual Schema & Claim Designer (Drag-and-Drop):**
   - Add, reorder, and configure credential subject claims (e.g., student name, degree, GPA, honors, conferral date).
   - Specify claim data types (strings, dates, structured objects) and required validations.
2. **Visual Card & Certificate Layout Designer:**
   - Drag-and-drop canvas to design credential cards and printable PDF diplomas/transcripts.
   - Institutional branding, logos, security watermarks, and QR code placement.
3. **Automated Export & Multi-Tenant Deployment:**
   - **W3C JSON-LD Contexts:** Generates versioned `@context` JSON definitions, saved to `deploy/<tenant>/contexts/<credential-name>/v1.json`.
   - **Inji Certify Configurations:** Generates credential configuration JSON, saved to `deploy/<tenant>/credentials/<credential-name>.json` for GitOps template sync.
   - **Verification Rules:** Generates verification rules and claim display definitions for Inji Verify.

---

## 2. Multi-Tenant VDR Architecture

Static W3C JSON-LD contexts are served per installation tenant by the `vdr` service in `compose.yaml`:
- **AIT Tenant:** `deploy/ait/contexts/` $\rightarrow$ served at `http://host.docker.internal:9098/contexts/`
- **Hackathon Tenant:** `deploy/hackathon/contexts/` $\rightarrow$ served at `http://host.docker.internal:9098/contexts/`

Inji Certify and Inji Verify resolve the `@context` URLs over HTTP from `vdr` live at runtime.
