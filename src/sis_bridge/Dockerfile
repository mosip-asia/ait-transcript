# TEMPORARY SIS bridge, deleted once the SIS Adapter serves the contract itself (ticket 11): the Adapter contract's
# transcript path in front of the SIS Adapter's current route. src/adapter/ait_courses.py is copied in for the course listing.
FROM python:3.12-slim-bookworm

WORKDIR /bridge

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY src/sis_bridge/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src/sis_bridge/bridge.py src/sis_bridge/sis_mapping.py src/adapter/ait_courses.py ./

EXPOSE 8000

# No access log: the request line carries the student's `sub`, which the contract keeps out of logs.
CMD ["uvicorn", "bridge:from_env", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
