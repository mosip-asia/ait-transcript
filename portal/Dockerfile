# Demo app — repo root is WORKDIR so portal/fixtures.py REPO_ROOT and portal/db.py paths match.
FROM python:3.12-slim-bookworm

WORKDIR /demo

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY portal/requirements.txt portal/requirements.txt
RUN pip install --no-cache-dir -r portal/requirements.txt

# Fallback when bind mounts are not used (e.g. image-only smoke). Dev uses compose bind mounts.
COPY portal/ portal/
COPY data/ data/

EXPOSE 4100

CMD ["uvicorn", "portal.main:app", "--host", "0.0.0.0", "--port", "4100", "--reload"]
