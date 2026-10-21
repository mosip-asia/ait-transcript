# AIT Issuer

The institutional issuer that both AIT's transcript service and the sandbox hackathon deploy. Terms agreed on 2026-10-19; Hard copy, Pilot and Adapter added 2026-10-20.

## Language

**Issuer**:
The product: one codebase of components (Certify, Gateway, Admin Portal, Verifier, VC Lab) that turns an organisation's records into verifiable credentials, configured per installation.
_Avoid_: issuing engine, institutional issuer, Certify (when the whole product is meant)

**Installation**:
One deployment of the Issuer for one organisation, such as AIT or the hackathon. Installations differ only in configuration.
_Avoid_: project (when the deployment is meant), profile, tenant

**Certify**:
Inji Certify, the signing engine inside the Issuer. It signs credentials and keeps the ledger and the status lists.
_Avoid_: issuer (when the engine is meant), signing service

**Gateway**:
The Issuer's own service around Certify: the data-provider plugin, the checklist runner and the admin API.
_Avoid_: middleware, policy engine, adapter (when the gateway is meant)

**Checklist**:
The ordered list of checks an organisation sets per credential type, evaluated when a credential is requested, that decides whether it may be issued.
_Avoid_: workflow, approval process, approval queue, prerequisite checklist, Function 1

**Check**:
One entry in a checklist. Its kind says what evidence it needs: a predicate over the record, or a required presentation.
_Avoid_: rule, step, policy

**Approval gate**:
The point in the issuance protocol where a failed checklist stops the credential from being released.
_Avoid_: UI-gated approval, approval enforcement

**Admin Portal**:
The Issuer's web application for the organisation's staff: review, search, revoke and print.
_Avoid_: registrar portal, demo-app, OSA console, management portal, Function 2

**Verifier**:
The stock Inji Verify deployed with the Issuer as the reference way to check its credentials. Any standards-conformant verifier may stand in for it.
_Avoid_: web verifier, universal verifier, Cloud Run verifier

**VC Lab**:
The Issuer's template authoring and publishing: the files and the publish step that change how a credential is shaped, printed and displayed.
_Avoid_: Card Display Lab, presentation template designer

**Adapter**:
The read-only service that serves an organisation's records and eligibility attributes to the Gateway under the adapter contract; one per installation. The CSV-backed mock stands in until the organisation's own adapter exists.
_Avoid_: data source, SIS integration (that is what the real adapter wraps), plugin (that is the Gateway's piece inside Certify)

**VDR**:
The public host, owned by Track 3, for the DID document, status lists and JSON-LD contexts that verifiers fetch, and for the templates the Portal fetches. Verifiers never use its templates.
_Avoid_: public registry, registry host, CDN, trust registry (that is the trusted-issuer list, a different thing)

**Wallet**:
Any OpenID4VCI-conformant holder application. The Issuer promises a valid credential offer and nothing about the wallet; Inji Web is used only to test issuance.
_Avoid_: web wallet (as a deliverable), student catalog, walletless mode

**Hard copy**:
The PDF the Portal renders from the VC Lab template, carrying a credential in its QR code, verifiable online by the Verifier. The Portal obtains and redeems the credential for it and stores nothing.
_Avoid_: walletless PDF, printed credential, paper transcript (when the PDF is meant)

**Pilot**:
The first issuance to real people: a small group of students chosen by the registrar's office, given a wallet claim and a hard copy from real records. Pilot credentials carry no compatibility promise and may be revoked.
_Avoid_: mid-December issuance, POC, UAT (that is an environment, not the pilot)
