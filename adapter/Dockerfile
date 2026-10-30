# Mock data adapter: read-only, serves contracts.md section 2b from a mounted CSV.
FROM python:3.12-slim-bookworm

WORKDIR /adapter

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY adapter/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY adapter/main.py main.py

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
