# Demo app — repo root is WORKDIR so app/fixtures.py REPO_ROOT and app/db.py paths match.
FROM python:3.12-slim-bookworm

WORKDIR /demo

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY app/requirements.txt app/requirements.txt
RUN pip install --no-cache-dir -r app/requirements.txt

# Fallback when bind mounts are not used (e.g. image-only smoke). Dev uses compose bind mounts.
COPY app/ app/
COPY data/ data/

EXPOSE 4100

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "4100", "--reload"]
