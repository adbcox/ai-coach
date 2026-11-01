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
ARG GIT_SHA=dev
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    AEC_DATA_DIR=/data \
    AEC_STATIC_DIR=/app/static \
    PORT=26219 \
    AEC_BUILD=${GIT_SHA}
WORKDIR /app
COPY backend/ /app/backend/
RUN pip install /app/backend && rm -rf /app/backend
COPY --from=web /web/dist /app/static
# Starts as root only to fix ownership of the /data volume, then drops to
# PUID:PGID (default 10001; Unraid users set PUID=99 PGID=100). See app/__main__.py.
RUN mkdir -p /data
VOLUME /data
EXPOSE 26219
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:%s/api/health'%os.environ.get('PORT','26219'),timeout=4)"
CMD ["python", "-m", "app"]

# Future: a `full` target extending `slim` with heavier converters (OCR via Docling,
# YouTube transcripts; CPU-only PyTorch). The slim image already converts PDFs, web
# pages, Markdown and text (pypdf, trafilatura) since v0.6.0.
