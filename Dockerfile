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
        ffmpeg \
        libass9 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN useradd -m -s /bin/bash appuser

WORKDIR /app

COPY demos/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY demos/backend/ .

# Copy built frontend into backend static directory
COPY --from=frontend-build /frontend/dist ./static

# Local data dirs for rendered slide images
RUN mkdir -p data/uploads data/slides slides_cache && chown -R appuser:appuser data slides_cache

USER appuser

EXPOSE 8000

ENV WORKERS=1

CMD gunicorn -w ${WORKERS} -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 --timeout 300 app:app
