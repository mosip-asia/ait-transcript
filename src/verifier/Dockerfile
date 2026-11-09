FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

COPY src/verifier/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src/verifier/ src/verifier/

EXPOSE 4007

CMD ["uvicorn", "src.verifier.main:app", "--host", "0.0.0.0", "--port", "4007"]
