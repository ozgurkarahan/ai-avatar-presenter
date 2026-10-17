# Stage 1: Build React frontend
FROM node:20-slim AS frontend-build
WORKDIR /frontend
COPY demos/frontend/package.json demos/frontend/package-lock.json ./
RUN npm ci --no-audit
COPY demos/frontend/ ./
RUN npm run build

# Stage 2: Python backend + frontend static files
FROM python:3.12-slim

# System dependencies: LibreOffice for PPTX->PDF, poppler for PDF->PNG, fonts
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libreoffice-impress \
        poppler-utils \
        fonts-liberation \
        fonts-crosextra-carlito \
        fonts-crosextra-caladea \
        fonts-dejavu-core \
        ffmpeg \
        libass9 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN useradd -m -s /bin/bash appuser

WORKDIR /app

COPY demos/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Includes demos/backend/static/avatars/ (custom avatar thumbnails, gitignored, optional)
COPY demos/backend/ .

# Public AI enablement decks for the operator content CLI (python -m maintenance.content).
COPY content/ai-enablement/*.pptx ./maintenance/decks/

# Copy built frontend into backend static directory. COPY merges into the existing
# directory, so static/avatars/ from the previous step is preserved.
COPY --from=frontend-build /frontend/dist ./static

# Local data dirs for rendered slide images
RUN mkdir -p data/uploads data/slides slides_cache static/avatars && chown -R appuser:appuser data slides_cache

USER appuser

EXPOSE 8000

ENV WORKERS=1

# Local/docker-run health signal (Azure Container Apps uses its own probes and ignores this)
HEALTHCHECK --interval=60s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

CMD gunicorn -w ${WORKERS} -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 --timeout 300 app:app
