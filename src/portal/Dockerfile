# Demo app — repo root is WORKDIR so src/portal/fixtures.py REPO_ROOT and src/portal/db.py paths match.
FROM python:3.12-slim-bookworm

WORKDIR /demo

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/demo/src

COPY src/portal/requirements.txt src/portal/requirements.txt
RUN pip install --no-cache-dir -r src/portal/requirements.txt

# Fallback when bind mounts are not used (e.g. image-only smoke). Dev uses compose bind mounts.
COPY src/portal/ src/portal/

EXPOSE 4100

CMD ["uvicorn", "portal.main:app", "--host", "0.0.0.0", "--port", "4100", "--reload"]
