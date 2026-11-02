# TEMPORARY SIS bridge (ticket 08 of the issuer reshape; ticket 11 deletes it): the Adapter contract's record paths in
# front of the SIS Adapter's current route. data/ait_courses.py is copied in for the course listing.
FROM python:3.12-slim-bookworm

WORKDIR /bridge

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY sis-bridge/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY sis-bridge/bridge.py sis-bridge/sis_mapping.py data/ait_courses.py ./

EXPOSE 8000

# No access log: the request line carries the student's `sub`, which the contract keeps out of logs.
CMD ["uvicorn", "bridge:from_env", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
