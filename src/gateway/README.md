# Institutional Clearance & Permission Workflow Engine (Gateway)

The **Gateway** is the institutional business logic and clearance engine. It evaluates whether a subject (student, employee, participant) is cleared and authorized to receive a Verifiable Credential.

It enforces institutional policies such as:
- **No Active Holds:** Subject must be free of library fines, disciplinary holds, or administrative locks.
- **Degree Conferred:** Academic senate has officially conferred the degree.
- **Zero Balance:** Student tuition and university fees must be fully settled.

Per [ADR 0001](../../docs/adr/0001-approval-gate-beside-the-data-path.md), the Gateway sits **beside the data path**: it evaluates eligibility attributes via `POST /evaluations` and never proxies or intercepts private transcript claim records.

---

## 1. Directory Structure

```
src/gateway/
├── main.py               # FastAPI application exposing POST /evaluations
├── credential_types.py   # Registry of credential clearance predicates
├── requirements.txt      # Module dependencies (also managed in root pyproject.toml)
└── tests/                # In-process and host verification tests
    ├── test_credential_types.py
    └── test_evaluations.py
```

*(Note: Container build recipes are located in `docker/Dockerfile.gateway`)*

---

## 2. Running Locally with `uv`

To run the workflow engine on your host machine:

```bash
# Start the FastAPI server on port 8000:
uv run uvicorn main:from_env --factory --host 0.0.0.0 --port 8000 --app-dir src/gateway
```

---

## 3. Running Tests

Run the test suite directly with `uv`:

```bash
uv run python src/gateway/tests/test_credential_types.py
uv run python src/gateway/tests/test_evaluations.py
```

---

## 4. API Specification

### `POST /evaluations`
Evaluates whether a token subject meets the clearance criteria for a specific credential scope.

**Request:**
```json
{
  "sub": "st125001",
  "scope": "AitTranscript"
}
```

**Response (HTTP 200 - Cleared):**
```json
{
  "passed": true,
  "checks": [
    {"name": "no_holds", "passed": true},
    {"name": "conferred", "passed": true},
    {"name": "zero_balance", "passed": true}
  ]
}
```

**Response (HTTP 403 - Clearance Refused):**
```json
{
  "passed": false,
  "error": "checklist_failed",
  "checks": [
    {"name": "no_holds", "passed": false, "reason": "Holds on record: Library fine"},
    {"name": "conferred", "passed": true},
    {"name": "zero_balance", "passed": true}
  ]
}
```
