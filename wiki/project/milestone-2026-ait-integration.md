---
title: "Milestone (2026): AIT Institutional Integration"
description: First project milestone focusing on Integration Boundary 2 with the Asian Institute of Technology (AIT) — data model, registrar workflows, and visual transcript fidelity.
type: project
tags:
  - wiki
  - project
  - milestone
  - 2026
  - ait
  - boundary-2
---
# Milestone (2026): AIT Institutional Integration

## 1. Milestone Strategic Intent

As established in [The Role & Functionality of a Complete University VC Issuer](./README.md), an academic issuer must bridge two worlds:
1. **Integration Boundary 1**: The Decentralized Identity & VC Ecosystem (VCGA, VDR, Wallets, Verifiers).
2. **Integration Boundary 2**: Institutional / University Systems (SIS, IdP, Registrar Workflows, Document Branding).

### Why Focus on Boundary 2 in 2026?

Decentralized standards and wallet protocols (OpenID4VCI, W3C VCs) are already implemented by open-source engines like MOSIP Inji. However, **a Verifiable Credential is only as useful as the institutional reality it represents**. 

For universities like AIT, the most critical hurdles are internal:
- How does the transcript data model accurately reflect complex academic careers, semester course tables, and cumulative GPAs?
- How do academic registrars maintain review, approval, and revocation governance over issued credentials?
- How does the student experience feel, and does the final rendered document honor the visual authority of the official university transcript?

Therefore, **Milestone (2026)** focuses squarely on **Integration Boundary 2 (University / AIT Systems)**, keeping Boundary 1 in a controlled, vendored local stack.

---

## 2. Core Pillars in Milestone (2026)

### Pillar 1: AIT Master Transcript Data Model & Visual Fidelity
- **Data Model**: Modeled on the official AIT Master Transcript schema (`registrationNo`, `fullName`, `dateOfBirth`, `country`, `degreeAwarded`, `faculty`, `academicProgram`, `option`, semester course arrays, credit summaries, and thesis details).
- **Physical Fidelity**: The digital credential, when opened or printed, must look indistinguishable from the physical paper transcript. The official Credential Lab `aittranscript` layout is vendored into `design/` and rendered via Mimoto Velocity templates into an A4 PDF.
- **Embedded Verification QR**: Every generated PDF embeds an on-document QR code for instant offline-to-online presentation and verification.

### Pillar 2: Data Sources & Campus Identity
- **Student Data Fixtures**: Canonical student records defined in `data/students.json` dynamically synced to Inji Certify's data provider (`vc-stack/config/student_identity_data.csv`).
- **Campus Authentication**: Keycloak instance pre-configured with realm `inji` and mock student accounts, providing the OIDC authentication layer simulating AIT's campus SSO.
- **Zero Host Dependencies**: Python scripts run inside Docker containers; the entire data generation and sync process requires zero host-installed Python runtimes.

### Pillar 3: Registrar Governance & Lifecycle Workflows
- **Student Request Experience**: Self-service portal (`app/`) allowing student personas to log in, review their academic profile, and submit a formal transcript VC request.
- **Registrar Review & Approval Gate**: Registrar portal allowing academic officers to review pending requests, inspect student records, and approve or reject issuance.
- **Cryptographic Revocation (VCDM 2.0)**: Registrar revocation dashboard connected to Certify's W3C Bitstring Status List registry, ensuring revocation is cryptographically verifiable by Inji Verify in real time.

---

## 3. Deployment Architecture: "Issuer in a Box" on GCE VM

For the 2026 milestone, the system runs as a self-contained, low-cost **"Issuer in a Box"** on a single Google Compute Engine (GCE) VM (`e2-standard-2`) without Kubernetes:

```
[Internet] ──> Traefik / Caddy (Auto-TLS) ──> Docker Compose Stack:
                                            ├── Inji Certify (Stateless Issuer Engine)
                                            ├── Local PostgreSQL (Operational Cache on Persistent Disk)
                                            ├── Mimoto + Inji Web (Browser Wallet)
                                            ├── Inji Verify (Verification Service)
                                            └── Keycloak (Mock Campus IdP / Broker)
```

### Operational & Cost Controls:
- **Zero-Idle Compute via Hibernation (Interim 2026 Pattern)**: The VM uses GCP's native **VM Suspend / Resume (`gcloud compute instances suspend/resume`)** rather than full shutdown. This freezes RAM to disk, cuts compute billing to **$0**, and allows the VM to wake up in **~10 seconds with the JVM already hot**. *(Note: This is an interim pattern for 2026; architecture must be further optimized before Q3 2027).*
- **Postgres as Local Cache**: Co-located on the VM's persistent disk. Avoids the $55/month cost of an external 24/7 Cloud SQL instance while hibernating for free alongside Certify.
- **Always-Active Front Gateway**: The lightweight Python FastAPI app handles user sessions and triggers VM wake-up during the request/approval workflow.

---

## 4. Disaster Recovery & Persistence Plan

To prevent the **"Lost Control / Orphaned Credential"** disaster (losing the index mapping between students and their status list bits), the 2026 milestone establishes a 4-tier persistence hierarchy:

1. **Tier 1: Hot Local Persistence (Dev, Stage, Prod)**: PostgreSQL data directory stored on a dedicated GCP Persistent Disk (`pd-balanced`). Survives reboots, container recreations, and VM hibernation.
2. **Tier 1.5: Fast-Rollback VM Snapshots (Production Only)**: Automated GCP Disk Snapshot schedule (7-day rolling window) providing 3-minute emergency rollback against bad deployments.
3. **Tier 2: Warm Cloud Backup (Stage & Prod)**: Scheduled `pg_dump` pushed to a dedicated Google Cloud Storage (GCS) bucket with 30-day versioned retention.
4. **Tier 3: Annual Permanent Cold Archive (Production Only)**: End-of-academic-year database freeze stored in immutable, WORM-locked multi-region archive storage for 50+ year compliance.

---

## 5. Key Deliverables & Validation Criteria

- [x] **Self-Contained Local Stack**: Single-command startup (`./run-demo.sh` or `docker compose -f vc-stack/docker-compose.yaml up -d`).
- [x] **Full User Journey Walkthrough**:
  1. Student requests transcript in Demo App (`:4100`).
  2. Registrar approves request in Demo App (`:4100`).
  3. Student claims VC into Inji Web (`:4004`) via Keycloak OIDC and OpenID4VCI.
  4. PDF download matches official AIT Master Transcript layout.
  5. Inji Verify (`:4007`) successfully verifies the presented credential.
  6. Registrar revokes credential; Inji Verify confirms revoked status.
- [x] **Public Demo Deployment**: GCE VM deployment behind Caddy TLS for live stakeholder demonstrations.
- [ ] **VM Suspend / Resume Validation**: Confirm stack resumes from GCE `suspend` within 15 seconds with verified database connectivity and warm JVM.
- [ ] **Automated GCS Backup Pipeline**: Verify automated `pg_dump` export to GCS bucket for staging and production disaster recovery.

---

## 6. Transition to Future Milestones

Milestone (2026) completes the foundation for AIT. Subsequent milestones will expand and optimize the architecture:

- **Q3 2027 Optimization Target (Serverless Cloud Run & Decoupled Database)**:
  - Migrate the interim hibernating VM to a truly stateless, serverless Cloud Run microservice to eliminate the VM and JVM operational footprint entirely.
  - Decouple PostgreSQL from the VM disk into a managed, external database (Google Cloud SQL or central AIT PostgreSQL cluster), allowing horizontal autoscaling and multi-department issuer reuse.
- **Boundary 1 Expansion**: Transitioning to production `did:web`, VCGA trust integration, and multi-wallet interoperability testing.
- **Boundary 2 Deepening**: Direct live API adapters to AIT's central Student Information System (SIS) and enterprise single sign-on (SSO).

## Related Documentation

- [Complete University VC Issuer Functionality](./README.md)
- [Project Scope & Objectives](./scope.md)
- [PRD.md](../../PRD.md)
- [Local stack architecture](../architecture/vc-stack.md)
- [Transcript credential design](../concepts/transcript-credential.md)
- [Approval gate](../concepts/approval-gate.md)
- [VC revocation](../concepts/vc-revocation.md)
