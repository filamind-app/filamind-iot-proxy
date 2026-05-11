# filamind-iot-proxy backend image
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps for psycopg + healthchecks + lego (Phase 2 ACME)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install lego (Let's Encrypt client used by api/services/acme.py).
# Pinned by checksum-checked tarball. Skipped at runtime when ACME envs
# are unset (api returns 503 acme_not_configured).
ARG LEGO_VERSION=4.18.0
RUN curl -fsSL "https://github.com/go-acme/lego/releases/download/v${LEGO_VERSION}/lego_v${LEGO_VERSION}_linux_amd64.tar.gz" \
        -o /tmp/lego.tgz \
    && tar -xzf /tmp/lego.tgz -C /usr/local/bin lego \
    && rm /tmp/lego.tgz \
    && chmod +x /usr/local/bin/lego

# Install Python deps first for layer caching
COPY backend/pyproject.toml backend/README.md ./
RUN pip install --upgrade pip wheel \
    && pip install -e .

# Source
COPY backend/api ./api
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./

# Non-root user
RUN useradd -u 1000 -m proxy && chown -R proxy:proxy /app
USER proxy

EXPOSE 9100

CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "9100"]
