# The Gateway: POST /evaluations and the old POST /issuances (contracts.md section 2a), the Approval gate's checklist runner.
FROM python:3.12-slim-bookworm

WORKDIR /gateway

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY gateway/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY gateway/main.py gateway/credential_types.py gateway/store.py ./

EXPOSE 8000

CMD ["uvicorn", "main:from_env", "--factory", "--host", "0.0.0.0", "--port", "8000"]
