"""Mock data adapter: contracts.md section 2b over HTTP, read-only, from a mounted CSV.

The CSV is read again on every request, so editing the mounted file changes what is served
(restarting the container is not even needed). A `sub` is the CSV's `id` column; one row is
one sign-in identity and so one degree. A missing row is a 404, nothing else is an error.

It is column-driven, so the same image serves every installation's CSV. On the AIT transcript CSV the record
path serves the record and the eligibility path contract 2b's eligibility attributes; a CSV without those
attributes (the hackathon roster) is served whole on both paths.
"""

from __future__ import annotations

import csv
import json
import os

from fastapi import FastAPI, HTTPException

app = FastAPI(title="Mock data adapter")

# Stored as JSON text (data/generate_csv.py) and served decoded.
JSON_COLUMNS = {"courses", "holds"}
# The generator escapes every other transcript claim for Certify's quoted Velocity substitution; these it
# stores as they are.
RAW_COLUMNS = {"id", "level", "conferralStatus", "balance", *JSON_COLUMNS}
# contracts.md section 2b's eligibility attributes: on the eligibility path only.
ELIGIBILITY_COLUMNS = {"holds", "conferralStatus", "balance"}
# Not in the record: the identity, the generator's rendering of `courses` and the eligibility attributes.
NOT_IN_RECORD = {"id", "courseList", *ELIGIBILITY_COLUMNS}
DEGREE_COLUMNS = ("level", "degreeAwarded", "dateGraduation")


def find_row(sub: str, degree_id: str | None = None) -> dict:
    with open(os.environ.get("ADAPTER_CSV", "/data/student_identity_data.csv"), newline="", encoding="utf-8") as f:
        row = next((r for r in csv.DictReader(f) if r["id"] == sub), None)
    if row is None or degree_id not in (None, sub):  # degreeId is the row's id
        raise HTTPException(404, "no such student or degree")
    return {k: json.loads(v) if k in JSON_COLUMNS else v if k in RAW_COLUMNS else json.loads(f'"{v}"')
            for k, v in row.items()}


@app.get("/students/{sub}/degrees")
def degrees(sub: str) -> list[dict]:
    row = find_row(sub)
    return [{"degreeId": row["id"], **{k: row[k] for k in DEGREE_COLUMNS if k in row}}]


@app.get("/students/{sub}/transcript")
def transcript(sub: str, degreeId: str | None = None) -> dict:
    row = find_row(sub, degreeId)
    return {"degreeId": row["id"], **{k: v for k, v in row.items() if k not in NOT_IN_RECORD}}


@app.get("/students/{sub}/eligibility")
def eligibility(sub: str, degreeId: str | None = None) -> dict:
    row = find_row(sub, degreeId)
    served = ELIGIBILITY_COLUMNS & row.keys() or row.keys() - {"id"}
    return {k: v for k, v in row.items() if k in served}
