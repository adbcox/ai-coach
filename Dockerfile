# syntax=docker/dockerfile:1

# ---- web build (Node is only needed at build time) ----
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- slim runtime: sync + dashboard (+ agent access later) ----
FROM python:3.13-slim AS slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    AEC_DATA_DIR=/data \
    AEC_STATIC_DIR=/app/static \
    PORT=26219
WORKDIR /app
COPY backend/ /app/backend/
RUN pip install /app/backend && rm -rf /app/backend
COPY --from=web /web/dist /app/static
RUN useradd --system --uid 10001 --home-dir /app coach \
    && mkdir -p /data && chown coach /data
USER coach
VOLUME /data
EXPOSE 26219
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:%s/api/health'%os.environ.get('PORT','26219'),timeout=4)"
CMD ["python", "-m", "app"]

# Future: a `full` target extending `slim` with the ingest converters
# (Docling etc., CPU-only PyTorch). Not built yet (roadmap v0.3).
