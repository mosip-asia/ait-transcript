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

The claimed VC, opened as a PDF/card in Inji Web, must replicate the **official AIT Master Transcript** layout — this is the design the user already built and approved in Credential Lab (the `aittranscript` preset), not a simplified card invented for this demo. See [PRD.md §7](../../PRD.md).

To guarantee that, the two files that define the look and the course-table rendering logic are **vendored verbatim** into [design/](../../design/) from the upstream `inji` repo (not included here; read-only reference):

| File | Role |
|---|---|
| `design/pdf-ait-transcript-template.html` | Mimoto Velocity PDF template: A4 portrait, bordered student-info grid, semester course table, thesis/committee footer, verify QR |
| `design/ait_courses.py` | Parses/validates the semester-block `courses` JSON and renders `courseTableHtml` from it |

Building `app/` and `vc-stack/` wires claims into this template — it does not restyle or re-derive it. If the upstream inji design changes and this demo should follow, re-copy both files rather than hand-patching drift.

**Known, deliberate exception (2026-09-18):** the runtime copies (`data/ait_courses.py`, `vc-stack/config/AITUniversity-ait-transcript-template.html`) diverge from the frozen `design/` pair — QR moved to its own page and enlarged, course-table row spacing reworked. User's explicit call: fix the runtime render, leave `design/` as the untouched upstream mirror. Port to `~/Developer/inji/credential-lab` by hand if wanted there; a future re-copy from upstream will silently drop this fix from `data/` unless it's re-applied.

Original design rationale: `inji/docs/superpowers/specs/2026-08-07-ait-transcript-preset-design.md`.

## Claim shape

| Claim | Type | Embed style in VC template | Notes |
|---|---|---|---|
| `fullName`, `dateOfBirth`, `country`, `registrationNo` | string | quoted | student identity block |
| `previousDegree`, `yearAwarded` | string | quoted | prior qualification |
| `dateAdmitted`, `option`, `degreeAwarded`, `dateGraduation` | string | quoted | admission/award |
| `faculty`, `academicProgram`, `areaOfSpecialization`, `notes` | string | quoted | program block |
| `issueDate` | string | quoted | printed top-right of the transcript |
| `courses` | JSON array | **unquoted** embed (`"courses": ${courses}`) | semester blocks: `{term, courses: [{no, title, lab, lec, credits, grade}], credits, gpa, cumGpa}` |
| `courseTableHtml` | string | **quoted**, JSON-escaped | Python-rendered `<table>` from `courses`; the PDF renders this and only this for the course body |
| `courseList` | string | quoted | newline `Course — Grade` summary, derived from `courses`, for wallet/list display |
| `thesisTitle`, `thesisGrade`, `programCommittee` | string | quoted | footer block |
| `courseworkCredits`, `thesisCredits`, `totalCredits`, `thesisExamination` | string | quoted | credit summary |

## Gotchas (already hit upstream — do not re-discover)

- `courseTableHtml` and any other multi-line/HTML string claim must be JSON-escaped before going into the CSV/VC template, or embedded `"` / newlines break Certify's VC template substitution (`json_processing_error` / `Unterminated string`). Enforced by `escape_vc_quoted_claim()` in `data/generate_csv.py` (applied to every claim except `courses`, the one unquoted raw-JSON embed) — this rule was documented here but not actually implemented until 2026-09-18; see [VC download troubleshooting #4](../guides/vc-download-troubleshooting.md#4-unescaped-html-breaks-the-vc-templates-json) if it regresses.
- Mimoto's Velocity PDF template must use `#claimValue("courseTableHtml")` / `#claimValue("<field>")` only — **no** `#while`, `#elseif`, or Velocity-side string splitting on course data. That path is a documented dead end upstream.
- Certify's CSV data-provider maps columns **by position** (`data-columns` property) — the CSV header and that property must stay the same width, or values shift between claims.
- Claims are baked at issuance. Changing the mock fixture after a VC was already issued requires deleting and re-downloading the credential in Inji Web, not just editing the fixture.
- `ait_courses.py` as vendored expects a `PackValidationError` import from Credential Lab's `pack` module — adapt that import when wiring it into `app/`; keep the parsing/rendering logic unchanged.
- **iText's pdfHTML table layout ignores per-row CSS `height`.** Setting an explicit `height`/`min-height` on the outer `<table>` (to make its border fill leftover page space) makes iText distribute that *entire* forced height evenly across **every** row, regardless of any `height` set on individual `<tr>`/`<td>` elements — confirmed by measuring actual glyph y-positions in a real rendered PDF (`pdfplumber`), not by eyeballing a browser preview (plain browsers respect per-row height as a cap; iText does not, so a browser-only check will pass while the real render is still broken). The only mechanism that reliably worked: don't set any height on the table at all; give exactly **one** spacer `<tr>` an explicit height (computed in Python from the known row count × an empirical per-row pt estimate), and let every other row render at its natural content size. See `render_course_table_html()` in `data/ait_courses.py`.

Full upstream detail: `inji/wiki/guides/credential-lab-pdf-csv-gotchas.md`.

## Related

- [PRD.md §7, §9](../../PRD.md)
- [Approval gate](./approval-gate.md)
- [Local stack](../architecture/vc-stack.md)
