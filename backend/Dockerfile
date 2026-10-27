# ---- frontend build ----
FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- backend runtime ----
FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    BEAST_DATA_DIR=/data BEAST_FRONTEND_DIST=/app/frontend/dist
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core libsndfile1 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 1000 beast \
 && mkdir -p /data && chown beast:beast /data
WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install -r requirements.txt
COPY backend/ ./
COPY scripts/ /app/scripts/
COPY --from=web /web/dist /app/frontend/dist
# The entrypoint drops from root to the beast user after fixing /data ownership.
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=90s --retries=5 \
  CMD ["sh", "-c", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-8000}/api/health', timeout=4)\""]
ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
# PORT is set by hosts such as Render; defaults to 8000 for docker compose.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
