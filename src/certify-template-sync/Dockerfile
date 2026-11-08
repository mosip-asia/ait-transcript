FROM ghcr.io/astral-sh/uv:python3.11-alpine

WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy root pyproject and lockfile
COPY pyproject.toml uv.lock* /app/

# Synchronize dependencies (bake into image for fast offline startup)
RUN uv sync --no-install-project

# Copy sync script and default credentials
COPY src/certify-template-sync/ /app/src/certify-template-sync/
COPY config/credentials/ /app/config/credentials/

ENV POSTGRES_HOST=database \
    POSTGRES_PORT=5432 \
    POSTGRES_USER=postgres \
    POSTGRES_PASSWORD=postgres \
    CREDENTIALS_DIR=/app/config/credentials

ENTRYPOINT ["uv", "run", "--no-project", "src/certify-template-sync/sync.py"]
CMD ["--apply"]
