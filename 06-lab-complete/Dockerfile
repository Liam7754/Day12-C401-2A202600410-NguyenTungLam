# ============================================================
# Production Dockerfile — Multi-stage, non-root, Railway-ready
# ============================================================

# Stage 1: Builder — install deps to /install
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# Stage 2: Runtime — copy only what's needed
FROM python:3.11-slim AS runtime

# Non-root user
RUN groupadd -r agent && useradd -r -g agent -d /app agent

WORKDIR /app

# Copy installed packages into system Python path (uvicorn at /usr/local/bin)
COPY --from=builder /install /usr/local

# Copy application
COPY app/ ./app/
COPY utils/ ./utils/

RUN chown -R agent:agent /app

USER agent

ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
        CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1


# Shell form so ${PORT} is expanded at container start (Railway sets PORT dynamically)
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
