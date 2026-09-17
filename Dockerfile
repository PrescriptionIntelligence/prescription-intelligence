# ============================================================
# Prescription Intelligence — Backend Dockerfile
#
# Multi-stage build:
#   1. builder  — install Python dependencies
#   2. runtime  — minimal production image
#
# Tesseract OCR is installed from OS packages.
# ============================================================

# -----------------------------------------------------------
# Stage 1: dependency installation
# -----------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements to benefit from layer caching
COPY requirements.txt .

# Install Python dependencies into a virtualenv so they can be
# copied cleanly into the runtime stage without layout issues.
RUN python -m venv /app/venv && \
    /app/venv/bin/pip install --no-cache-dir -r requirements.txt


# -----------------------------------------------------------
# Stage 2: runtime image
# -----------------------------------------------------------
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install runtime OS packages:
#   tesseract-ocr  — OCR engine required by pytesseract
#   libpq5         — PostgreSQL client library (psycopg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy virtualenv from builder stage
COPY --from=builder /app/venv /app/venv

# Use the virtualenv's Python and pip
ENV PATH="/app/venv/bin:$PATH"

# PYTHONPATH ensures `import backend.*` resolves from /app
ENV PYTHONPATH=/app

# Copy application source
COPY backend ./backend
COPY migrations ./migrations
COPY alembic.ini .

# Create upload directory.
# In production, mount a persistent volume at /app/uploads.
RUN mkdir -p /app/uploads

# Run as a non-root user
RUN useradd --no-create-home --shell /bin/false appuser && \
    chown -R appuser:appuser /app
USER appuser

# Port exposed by uvicorn
EXPOSE 8000

# Healthcheck: poll /health every 30 s.
# urllib raises HTTPError for non-2xx, so a degraded (503) response
# correctly reports the container as unhealthy.
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Default command.
# CORS_ORIGINS, DB_*, and SECRET_KEY must be set via environment variables.
CMD ["uvicorn", "backend.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2"]
