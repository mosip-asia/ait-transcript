---
title: SIS Adapter handover
description: What the AIT installation's Issuer needs from the SIS Adapter and the server's settings, in plain words, beside the two master files.
type: project
tags:
  - wiki
  - adapter
---

# SIS Adapter handover

Written 2026-11-03 for the infra team and the SIS Adapter's builders (Jo and Boss). The two master files are still [`adapter/openapi.yaml`](../../../adapter/openapi.yaml) and [`wiki/schemas/ait-transcript-credential.v2.schema.json`](../../schemas/ait-transcript-credential.v2.schema.json). This page says the same things in plain words, plus what the schemas can't say. If this page and the master files disagree, the master files win; tell Thas so the page gets fixed.

## What the Issuer asks for

When a student claims a transcript, the Issuer makes two calls to the SIS Adapter, both `GET`:

1. `/student/{sub}/eligibility`: whether the student may get a transcript today (holds, conferral, balance owed). This path doesn't exist yet: please add it. Until it does, the Issuer reads eligibility from its own CSV, as now, so a student the CSV doesn't list is refused.
2. `/student/{sub}/transcript`: the transcript itself.

The path uses `student`, singular. Both paths are only defaults: the server's settings below hold the whole URL, so a different path just means a different setting, with no code change.

## The one value both sides must agree on: `sub`

`{sub}` is the `sub` claim of the student's access token, passed on exactly as the sign-in server wrote it. The Issuer doesn't read, change or look up any other identifier.

- **What must match:** the `sub` the campus sign-in server puts in a student's token must be the key the SIS Adapter finds that student by. If they differ, every claim fails with "no record".
- Which value that is (a student number, an internal account id) is for campus IT and the SIS Adapter to decide together.
- **Find the student by `sub` exactly as sent.** Don't ignore case or trim spaces, and answer `404` for anything that isn't an exact match. Today's SIS route answers `ST123456` and `st123456 ` (with a trailing space) with `st123456`'s record. The Issuer signs whatever record comes back, so a near-miss `sub` would get another student's transcript signed. Campus IT, for its part, keeps every `sub` unique.
- One `sub` gives one transcript. A student with two degrees is still an open question in [`spec-part-2.md`](spec-part-2.md) ("Multi-degree students").

## The server's settings

The deployed server reads two settings from its `app.env`. Both were renamed on 2026-11-03.

| Setting | Replaces | Example |
|---|---|---|
| `CERTIFY_RECORD_URL` | `CERTIFY_ADAPTER_URL` | `http://<sis-adapter-host>:<port>/student/{sub}/transcript` |
| `GATEWAY_ELIGIBILITY_URL` | `GATEWAY_ADAPTER_URL` | `http://<sis-adapter-host>:<port>/student/{sub}/eligibility` |

What must match:

- **Write `{sub}` literally**, braces included. The Issuer replaces it on each request. A URL without `{sub}`, or one that doesn't start with `http://` or `https://` and name a host, stops the service at startup, and its log names the setting.
- **The old names do nothing.** A server that still sets only `CERTIFY_ADAPTER_URL` starts normally but quietly reads the built-in mock instead of the SIS. Remove the old lines when adding the new ones.
- **The path must be one the SIS Adapter serves**, and the host must be reachable from inside the Certify and Gateway containers.
- **Until the SIS serves eligibility**, leave `GATEWAY_ELIGIBILITY_URL` unset, so it stays on the mock's CSV.

## What a transcript answer looks like

A JSON object holding the 24 fields `TranscriptRecord` lists in `adapter/openapi.yaml`. The rules:

- **Every field is present, and none is `null`.** The Issuer refuses a record with a `null` among the 24 fields. A `null` inside `courses`, or a field missing altogether, is caught only by the contract check below, not at issuance (see "Known gaps"), so it is the Adapter's job never to send one.
- **Every value is a string, numbers included.** The only exception is `courses`, which is a list.
- **Dates** (`dateOfBirth`, `dateAdmitted`, `dateGraduation`, `issueDate`): year-month-day with dashes, like `2026-08-31`. No time, no time zone, no `31/08/2026`.
- **Year** (`yearAwarded`): four digits, like `2023`.
- **Numbers** (`courseworkCredits`, `thesisCredits`, `totalCredits`, and in `courses` each term's `credits`, `gpa` and `cumGpa`, and each course's `lec`, `lab` and `credits`):
  - write them as text with a point for decimals, like `27.0`, `3.67` or `45`;
  - no comma, no sign, no units such as "credits";
  - the Issuer prints the number exactly as sent, so send the decimals you want shown: GPAs on the 4.00 scale with two decimals, credits as the transcript prints them.
- **Dates and numbers can't be empty.** Text fields may be empty strings. If the SIS has no value for a date or a number, tell Thas before go-live rather than sending `""`.
- **`courses`** is the terms in order. Each term is `{ term, courses, credits, gpa, cumGpa }`, with `term` the semester's name, like `August Semester 2024`. Its `courses` are in order, each `{ no, title, lec, lab, credits, grade }`. `lec` and `lab` are lecture and lab hours. `grade` is the letter as printed (`A`, `B+`, `S`).
- **`courseList`** is the short version a wallet card shows: one line per course, `<title> — <grade>` (with an em dash), lines separated by a newline. Use the title alone when there is no grade.
- **`programCommittee`** holds one member per line, the chair first, marked `(Chair)`.
- **`notes`** is `-` when there are none.
- **Text fields:** `fullName` is the whole name in one string. `country` is a country name, like `Thailand`, not a code.
- **`registrationNo` can't be empty**, though it is text: Certify's ledger indexes it, and revocation finds an issued credential by it. It is the SIS's `studentId` today, and `faculty` is its `schoolName` (the school, like `School of Engineering and Technology`).
- **Extra fields** beyond the 24 are allowed if each is a plain string, number or true/false. The Issuer passes them on unused.
- **Forbidden keys:** a record must never carry `id`, `_holderId`, `_issuer`, `validFrom`, `validUntil`, `credentialStatus`, `tokenSub` or `tokenClientId`. Certify and the Issuer set those themselves, and they refuse a record that has one.

**Today's gaps** in the current SIS route, seen through the temporary bridge (`sis-bridge/`). The route has no field for any of these, so the bridge sends each as an empty string, for every student:

- **dates and numbers:** the year awarded, the issue date, the coursework and thesis credits, lecture and lab hours, and each term's credits, GPA and cumulative GPA. These fail the contract check until the SIS fills them in.
- **text:** `country`, `previousDegree`, `option`, `areaOfSpecialization`, `notes`, `programCommittee` and `thesisExamination`. Empty text passes the contract check, so nothing flags these, and the transcript prints them blank. `notes` should be `-` when there are none.

## What an eligibility answer looks like

`{ "holds": [...], "conferralStatus": "...", "balance": "..." }`:

- `holds` is a list with one readable line per hold, empty when there are none.
- `conferralStatus` is `Conferred` or `Pending`.
- `balance` is the amount owed, written as text like `0.00` or `1250.00`.

The student passes when there are no holds, the degree is conferred, and the balance is zero.

## Answers, errors and time

- **Unknown student:** answer `404`. The Issuer doesn't read the body and tells the wallet "no record".
- **The Issuer refuses the claim** for another status, no answer at all, or a body that isn't one strict JSON object (no single quotes, no trailing comma, nothing after the closing brace).
- **Time:** the transcript's whole answer, body included, must arrive within 10 seconds. For eligibility, the Gateway waits at most 3 seconds to connect and at most 3 seconds for each next piece of the answer. Slower than that, and the claim is refused.
- **Security:** there is no password or key on these calls. The private network (NetBird) is the only boundary, so the SIS Adapter must not be reachable from anywhere else.

## Privacy: the Issuer stores `sub`

Campus asked consumers not to store its `sub` during the PoC. Three things to know:

- **The SIS Adapter** should keep `sub` out of its own storage and access logs.
- **The Issuer itself stores it.** Certify keeps every issued credential in its ledger, and the Issuer records the token's `sub` there as `tokenSub`. That is how a credential can later be traced to the sign-in that claimed it. Revocation itself goes by `registrationNo`.
- **Certify also logs it, and more.** For each issued credential, `io.mosip.certify.utils.LedgerUtils` writes one INFO line per value the ledger indexes, in plain text: `fullName`, `academicProgram`, `registrationNo`, `tokenSub` and `tokenClientId`. So the log holds the student's name and programme too, and the `sub` twice when the `sub` is the student number (`registrationNo` is then the same value). The logging is Certify's own code. Which claims get indexed is the Issuer's choice, the `mosip.certify.indexed-mappings.*` lines in the Installation's `certify-installation.properties`.

If campus's `sub` is an internal account id they don't want stored, they need to say so before go-live. The fix on Thas's side is small: trace by `registrationNo` from the record instead of `sub`. The question is in [`spec-part-2.md`](spec-part-2.md) under "If campus picks (b)".

## How to check an Adapter

Run the contract check against the real Adapter. It needs Python 3 with the packages in `portal/requirements.txt`:

```sh
python3 adapter/test_adapter.py --contract 'http://<sis-adapter-host>:<port>/student/{sub}/transcript' <a real sub> ait_transcript_vc_ldp
```

It fetches that student's record and checks every rule above that a schema can state: fields, types, dates, numbers, forbidden keys. It also checks that an unknown `sub` gets a `404`. It can't check meaning, such as whether a GPA is right or the course order matches the printed transcript.

## Known gaps on the Issuer's side

- The Issuer doesn't check the rules above when it issues: a date written `31/08/2026`, a number sent as a JSON number, an empty name or a wrong key inside `courses` would be signed exactly as sent. Only the contract check catches them, so run it before go-live and after every change to the Adapter.
- The Issuer can't tell when a field is missing altogether: Certify's template knows the field list, and the Issuer's plugin doesn't. A missing field would be signed as the literal placeholder (`${thesisGrade}`). The guard is the Adapter always sending every field, and the contract check above proving it before go-live.
