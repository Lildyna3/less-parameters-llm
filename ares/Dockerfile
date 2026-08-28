# ARES — single-image production build.
#
# Stage 1 builds the frontend; stage 2 runs the FastAPI backend, which serves
# both the API and the built SPA. One process, one port, one URL for phone,
# laptop and desktop.

FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build


FROM python:3.11-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
COPY --from=frontend /build/dist ./frontend/dist

# Writable location for the SQLite journal; mount a volume to persist it.
RUN mkdir -p /app/backend/data

ENV ARES_SYSTEM__HOST=0.0.0.0 \
    ARES_SYSTEM__PORT=8000 \
    ARES_SYSTEM__SERVE_FRONTEND=true \
    ARES_SYSTEM__FRONTEND_DIST=/app/frontend/dist \
    ARES_SYSTEM__DATABASE_URL=sqlite+aiosqlite:////app/backend/data/ares.db

EXPOSE 8000

# Container-native health check hits the public, unauthenticated endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status==200 else 1)"

WORKDIR /app/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
