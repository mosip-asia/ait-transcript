"""Mock data adapter: the Adapter contract (adapter/openapi.yaml) over HTTP, read-only, from a mounted CSV.

The CSV is read again on every request, so editing the mounted file changes what is served
(restarting the container is not even needed). A `sub` is the CSV's `id` column, and so is a `recordId`: one row is
one sign-in identity and so one degree. A missing row is a 404, nothing else is an error. The same row is served for
every scope: `scope` is required, as the contract says, and otherwise ignored.

It is column-driven, so the same image serves every installation's CSV. On the AIT transcript CSV the record
path serves every column but `id` and the eligibility columns, and the eligibility path those columns; a CSV without
them (the hackathon roster) is served whole on both paths.
"""

from __future__ import annotations

import csv
import json
import os

from fastapi import FastAPI, HTTPException

app = FastAPI(title="Mock data adapter")

# Stored as JSON text (data/generate_csv.py) and served decoded; every other cell is served verbatim, a cell the
# row lacks as null. Escaping for Certify's template is the reader's (the Data-provider plugin).
JSON_COLUMNS = {"courses", "holds"}
# The transcript's eligibility attributes: on the eligibility path only.
ELIGIBILITY_COLUMNS = {"holds", "conferralStatus", "balance"}
# Not in the record: the identity and the eligibility attributes.
NOT_IN_RECORD = {"id", *ELIGIBILITY_COLUMNS}
DEGREE_COLUMNS = ("level", "degreeAwarded", "dateGraduation")


def find_row(row_id: str) -> dict:
    with open(os.environ.get("ADAPTER_CSV", "/data/student_identity_data.csv"), newline="", encoding="utf-8") as f:
        row = next((r for r in csv.DictReader(f) if r["id"] == row_id), None)
    if row is None:
        raise HTTPException(404, "no such student or record")
    return {k: json.loads(v) if k in JSON_COLUMNS and v is not None else v for k, v in row.items()}


def degree_summary(row: dict) -> dict:
    return {k: row[k] for k in DEGREE_COLUMNS if k in row}


def eligibility_of(row: dict) -> dict:
    served = ELIGIBILITY_COLUMNS & row.keys() or row.keys() - {"id"}
    return {k: v for k, v in row.items() if k in served}


@app.get("/records")
def records(sub: str, scope: str) -> list[dict]:
    row = find_row(sub)
    return [{"recordId": row["id"], **degree_summary(row)}]


@app.get("/records/{recordId}")
def record(recordId: str, scope: str) -> dict:
    return {k: v for k, v in find_row(recordId).items() if k not in NOT_IN_RECORD}


@app.get("/records/{recordId}/eligibility")
def record_eligibility(recordId: str, scope: str) -> dict:
    return eligibility_of(find_row(recordId))
