"""Mock data adapter: contracts.md section 2b over HTTP, read-only, from a mounted CSV.

The CSV is read again on every request, so editing the mounted file changes what is served
(restarting the container is not even needed). A `sub` is the CSV's `id` column; one row is
one sign-in identity and so one degree. A missing row is a 404, nothing else is an error.
"""

from __future__ import annotations

import csv
import json
import os

from fastapi import FastAPI, HTTPException

app = FastAPI(title="Mock data adapter")

# The generator escapes every claim for Certify's quoted Velocity substitution (data/generate_csv.py);
# `courses` and the adapter columns are stored as they are.
RAW_COLUMNS = {"id", "courses", "level", "holds", "conferralStatus", "balance"}
# Not in the section 2b record: the generator's rendering of `courses`, and the adapter's own columns.
NOT_IN_RECORD = {"id", "courseList", "level", "holds", "conferralStatus", "balance"}


def find_row(sub: str, degree_id: str | None = None) -> dict:
    with open(os.environ.get("ADAPTER_CSV", "/data/student_identity_data.csv"), newline="", encoding="utf-8") as f:
        row = next((r for r in csv.DictReader(f) if r["id"] == sub), None)
    if row is None or degree_id not in (None, sub):  # degreeId is the row's id
        raise HTTPException(404, "no such student or degree")
    return row


def plain(row: dict) -> dict:
    return {k: v if k in RAW_COLUMNS else json.loads(f'"{v}"') for k, v in row.items()}


@app.get("/students/{sub}/degrees")
def degrees(sub: str) -> list[dict]:
    row = plain(find_row(sub))
    return [{"degreeId": row["id"], **{k: row[k] for k in ("level", "degreeAwarded", "dateGraduation")}}]


@app.get("/students/{sub}/transcript")
def transcript(sub: str, degreeId: str | None = None) -> dict:
    row = plain(find_row(sub, degreeId))
    record = {k: v for k, v in row.items() if k not in NOT_IN_RECORD}
    return {"degreeId": row["id"], "level": row["level"], **record, "courses": json.loads(row["courses"])}


@app.get("/students/{sub}/eligibility")
def eligibility(sub: str, degreeId: str | None = None) -> dict:
    row = find_row(sub, degreeId)
    return {"holds": json.loads(row["holds"]), "conferralStatus": row["conferralStatus"], "balance": row["balance"]}
