---
title: Transcript Credential Design
description: AIT Transcript VC claim shape, the vendored physical-look PDF template, and gotchas to avoid re-discovering.
type: concept
tags:
  - wiki
  - concept
  - credential
  - transcript
---
# Transcript Credential Design

## Hard requirement: it must look like the physical transcript

The claimed VC, opened as a PDF/card in Inji Web, must replicate the **official AIT Master Transcript** layout — this is the design the user already built and approved in Credential Lab (the `aittranscript` preset), not a simplified card invented for this demo. See [PRD (stale) §7](../../PRD.stale.md).

To guarantee that, the two files that define the look and the course-table rendering logic are **vendored verbatim** into [design/](../../design/) from the upstream `inji` repo (not included here; read-only reference):

| File | Role |
|---|---|
| `design/pdf-ait-transcript-template.html` | Mimoto Velocity PDF template: A4 portrait, bordered student-info grid, semester course table, thesis/committee footer, verify QR |
| `design/ait_courses.py` | Parses/validates the semester-block `courses` JSON and renders an HTML course table from it (the runtime no longer uses the table) |

Building `portal/` and `vc-stack/` wires claims into this template — it does not restyle or re-derive it. If the upstream inji design changes and this demo should follow, re-copy both files rather than hand-patching drift.

**Known, deliberate exceptions:** the runtime copies (`data/ait_courses.py`, `vc-stack/config/AITUniversity-ait-transcript-template.html`) diverge from the frozen `design/` pair. Since 2026-09-18: QR moved to its own page and enlarged. Since ticket 06 (transcript context v1): the HTML course table is no longer rendered or carried in the credential, and the PDF's course body is `courseList` plus the credit totals (see Gotchas). User's explicit call: fix the runtime render, leave `design/` as the untouched upstream mirror. Port to `~/Developer/inji/credential-lab` by hand if wanted there; a future re-copy from upstream will silently undo these changes in `data/` unless they are re-applied.

Original design rationale: `inji/docs/superpowers/specs/2026-08-07-ait-transcript-preset-design.md`.

## Claim shape

| Claim | Type | Embed style in VC template | Notes |
|---|---|---|---|
| `fullName`, `dateOfBirth`, `country`, `registrationNo` | string | quoted | student identity block |
| `previousDegree`, `yearAwarded` | string | quoted | prior qualification |
| `dateAdmitted`, `option`, `degreeAwarded`, `dateGraduation` | string | quoted | admission/award |
| `faculty`, `academicProgram`, `areaOfSpecialization`, `notes` | string | quoted | program block |
| `issueDate` | string | quoted | printed top-right of the transcript |
| `courses` | JSON array | **unquoted** embed (`"courses": ${courses}`) | semester blocks: `{term, courses: [{no, title, lab, lec, credits, grade}], credits, gpa, cumGpa}`, every value a string; typed `@json` in the context, so signed as one value |
| `courseList` | string | quoted | newline `Course — Grade` summary, derived from `courses`, for wallet/list display and the PDF's course body |
| `thesisTitle`, `thesisGrade`, `programCommittee` | string | quoted | footer block |
| `courseworkCredits`, `thesisCredits`, `totalCredits`, `thesisExamination` | string | quoted | credit summary |

## Gotchas (already hit upstream — do not re-discover)

- Any multi-line string claim (`courseList`, `programCommittee`) must be JSON-escaped before going into the CSV/VC template, or embedded `"` / newlines break Certify's VC template substitution (`json_processing_error` / `Unterminated string`). The CSV holds every value verbatim and the adapter serves it verbatim; the Gateway escapes each string claim for Certify's Velocity template (`gateway/credential_types.py`, applied to every claim except `courses`, the one unquoted raw-JSON embed); see [VC download troubleshooting #4](../reference/vc-download-troubleshooting.md#4-unescaped-html-breaks-the-vc-templates-json) if it regresses.
- Mimoto's Velocity PDF template must use `#claimValue("<field>")` only — **no** `#while`, `#elseif`, or Velocity-side string splitting on course data. That path is a documented dead end upstream.
- **The PDF cannot render the semester table from `courses`.** Mimoto 0.21 hands every claim to Velocity as a string (`CredentialPDFGeneratorService.formatValue`), and a list of objects without `language`/`value` keys becomes `""`. With the HTML course table gone from the credential (it was unsigned presentation data), the PDF's course body is `courseList`, one `Title — Grade` line per course, followed by the credit totals; semester grouping, hours, credits and GPAs per course are not on the PDF. They are in the signed `courses` claim. See [transcript context](./transcript-context.md).
- The mock Adapter reads the CSV **by header name** (`csv.DictReader`, `adapter/main.py`) and the Gateway builds the claims from its answer (`gateway/credential_types.py`, handed to Certify by the plugin in `gateway/plugin/`), so each claim column must keep its header; the CSV also carries four adapter-only columns (`level`, `holds`, `conferralStatus`, `balance`) after the claim columns, which are not claims.
- Claims are baked at issuance. Changing the mock fixture after a VC was already issued requires deleting and re-downloading the credential in Inji Web, not just editing the fixture.
- `ait_courses.py` as vendored expects a `PackValidationError` import from Credential Lab's `pack` module — adapt that import when wiring it into `portal/`; keep the parsing/rendering logic unchanged.
- **iText's pdfHTML table layout ignores per-row CSS `height`.** Setting an explicit `height`/`min-height` on the outer `<table>` (to make its border fill leftover page space) makes iText distribute that *entire* forced height evenly across **every** row, regardless of any `height` set on individual `<tr>`/`<td>` elements — confirmed by measuring actual glyph y-positions in a real rendered PDF (`pdfplumber`), not by eyeballing a browser preview (plain browsers respect per-row height as a cap; iText does not, so a browser-only check will pass while the real render is still broken). The only mechanism that reliably worked: don't set any height on the table at all; give exactly **one** spacer `<tr>` an explicit height (computed in Python from the known row count × an empirical per-row pt estimate), and let every other row render at its natural content size. That was `render_course_table_html()` in `data/ait_courses.py`, removed with the HTML course table in ticket 06 (see git history); `design/ait_courses.py` keeps the original.
- **Inji Verify rejects uploads outside 10 KB–5 MB** ("File size not supported"), checked in the UI before any verification. The two-page text-only transcript renders at ~8 KB, so it fails on the low side. The runtime template `vc-stack/config/AITUniversity-ait-transcript-template.html` ends with an invisible 1 px random-data PNG (~12 KB, incompressible) to stay above the floor; keep it, and keep the padding out of the frozen `design/` copy. Re-claim a VC to get a padded PDF; already-downloaded ones stay small.

Full upstream detail: `inji/wiki/guides/credential-lab-pdf-csv-gotchas.md`.

## Related

- [PRD (stale) §7, §9](../../PRD.stale.md)
- [Transcript context](./transcript-context.md)
- [Approval gate (stale)](./approval-gate.stale.md)
- [Local stack](../architecture/vc-stack.md)
