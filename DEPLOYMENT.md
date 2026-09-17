# Prescription Intelligence — Deployment Guide

This document describes how to deploy Prescription Intelligence in a
production environment.

---

## Architecture Overview

```
                    ┌─────────────────────────────┐
                    │        Reverse Proxy         │
                    │    (nginx / Caddy / ALB)     │
                    │     TLS termination          │
                    └──────────┬──────────┬────────┘
                               │          │
                  ┌────────────▼─┐   ┌───▼─────────────┐
                  │   Frontend   │   │     Backend      │
                  │  Next.js 15  │   │  FastAPI/uvicorn │
                  │  :3000       │   │  :8000           │
                  └──────────────┘   └─────┬──────┬─────┘
                                           │      │
                             ┌─────────────▼─┐  ┌─▼──────────┐
                             │  PostgreSQL   │  │  uploads/  │
                             │  :5432        │  │  (volume)  │
                             └───────────────┘  └────────────┘
```

---

## Prerequisites

### Backend host
- Python 3.11+
- PostgreSQL 14+
- Tesseract OCR: `apt-get install tesseract-ocr`
- `libpq5` (PostgreSQL client)

### Frontend host
- Node.js 20+

---

## Quick Start with Docker Compose

```bash
# 1. Copy environment files
cp .env.example .env
cp frontend/.env.example frontend/.env.local

# 2. Fill in required values in .env:
#    DB_PASSWORD, SECRET_KEY, SMTP_* variables, FRONTEND_URL

# 3. Build and start all services
docker compose up --build

# Services:
#   http://localhost:3000  — Frontend
#   http://localhost:8000  — Backend API
#   http://localhost:8000/health  — Health check
```

---

## Manual Deployment

### Backend

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\Activate.ps1  # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with real values

# 4. Run database migrations
alembic upgrade head

# 5. Start the server
uvicorn backend.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 4
```

### Frontend

```bash
cd frontend

# 1. Install dependencies
npm ci

# 2. Configure environment
cp .env.example .env.local
# Set NEXT_PUBLIC_API_URL=https://api.yourdomain.com

# 3. Build
npm run build

# 4. Start
npm start
```

---

## Environment Variables

### Backend (`.env`)

| Variable | Required | Description |
|---|---|---|
| `DB_USER` | ✅ | PostgreSQL username |
| `DB_PASSWORD` | ✅ | PostgreSQL password |
| `DB_HOST` | ✅ | PostgreSQL hostname |
| `DB_PORT` | ✅ | PostgreSQL port (default: `5432`) |
| `DB_NAME` | ✅ | Database name |
| `SECRET_KEY` | ✅ (prod) | JWT signing secret — generate with `python -c "import secrets; print(secrets.token_hex(64))"` |
| `ENVIRONMENT` | recommended | `development` or `production` (enforces `SECRET_KEY`) |
| `CORS_ORIGINS` | ✅ (prod) | Comma-separated allowed origins (e.g. `https://app.yourdomain.com`) |
| `SMTP_HOST` | optional | SMTP server for email verification |
| `SMTP_PORT` | optional | SMTP port (default: `587`) |
| `SMTP_USERNAME` | optional | SMTP login |
| `SMTP_PASSWORD` | optional | SMTP password |
| `SMTP_FROM_EMAIL` | optional | From address in verification emails |
| `FRONTEND_URL` | optional | Frontend base URL used in verification email links |

> **Note:** If SMTP variables are not set, email verification emails will not be sent. Registration still works — users can be manually verified via the admin interface.

### Frontend (`.env.local`)

| Variable | Required | Description |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | ✅ | Backend API URL (e.g. `https://api.yourdomain.com`) |

---

## Production Checklist

### Security

- [ ] `SECRET_KEY` is a strong, unique random value (not the example placeholder)
- [ ] `SECRET_KEY` is different in production vs development
- [ ] `ENVIRONMENT=production` is set on the backend
- [ ] `CORS_ORIGINS` contains only the production frontend domain
- [ ] PostgreSQL is not exposed to the public internet
- [ ] HTTPS/TLS is enforced on the reverse proxy
- [ ] `uploads/` directory is not served as a public static path

### Database

- [ ] `alembic upgrade head` has been run against the production database
- [ ] PostgreSQL data volume is backed up regularly
- [ ] Database password is strong and not the example placeholder

### File Storage

- [ ] `uploads/` is on a persistent volume (not ephemeral container storage)
- [ ] Upload volume is included in backup strategy
- [ ] **Future:** Migrate to object storage (S3/GCS) by replacing the upload path logic in `backend/main.py` and the image serving endpoint

### Application

- [ ] Health endpoint responds: `GET /health` returns `{"status": "healthy"}`
- [ ] Email verification works (SMTP configured or manually tested)
- [ ] Frontend can reach the backend API (`NEXT_PUBLIC_API_URL` is correct)

---

## File Storage Notes

Currently, prescription images are stored on the local filesystem in `./uploads/`.

**This is suitable for single-server deployments.**

For multi-server or cloud deployments, migrate to object storage:

1. Replace the `open(file_path, "wb")` write in `backend/main.py` with an S3/GCS `put_object` call
2. Replace the `FileResponse(path=...)` in the image endpoint with a presigned URL or streaming proxy
3. The security model (auth check before any image is served) must be preserved regardless of storage backend
4. Update `UPLOAD_DIR` handling in `backend/main.py`

---

## Health Monitoring

The backend exposes a health endpoint:

```
GET /health

# Healthy (HTTP 200):
{"status": "healthy", "database": "connected", "version": "1.0.0"}

# Degraded (HTTP 503):
{"status": "degraded", "database": "unavailable", "version": "1.0.0"}
```

Configure your load balancer or orchestrator to use `/health` as the health check path.

---

## Database Migrations

Migrations are managed with Alembic.

```bash
# Apply all pending migrations
alembic upgrade head

# Check current migration state
alembic current

# View migration history
alembic history
```

**In Docker Compose**, the `migrate` service runs `alembic upgrade head` automatically before the backend starts.

---

## Tesseract OCR

Tesseract must be installed on the backend host:

```bash
# Ubuntu/Debian
apt-get install tesseract-ocr

# macOS
brew install tesseract

# Windows
# Download installer from: https://github.com/UB-Mannheim/tesseract/wiki
```

The application does not invoke Tesseract in the frontend — it is a backend-only dependency.

---

## Logging

The backend uses Python's `logging` module throughout.

To configure log level in production:

```bash
# Via environment variable (uvicorn)
UVICORN_LOG_LEVEL=info uvicorn backend.main:app ...

# Or in code, configure logging before app startup
```

OCR candidate scoring and text extraction metrics are logged at `DEBUG` level only.
No prescription text content is written to logs (only character counts at debug level).

---

## Startup Order

1. PostgreSQL must be healthy
2. `alembic upgrade head` must complete successfully
3. Backend (uvicorn) starts
4. Frontend (Next.js) starts

---

## Recommended Hosting

| Component | Suitable Hosting |
|---|---|
| Backend | Any Python 3.11 host with Tesseract: EC2, Render, Railway, Fly.io, VPS |
| Frontend | Vercel (native Next.js), Netlify, or any Node.js host |
| Database | Managed PostgreSQL: RDS, Neon, Supabase, Railway, Render |
| File storage | Local volume (single server) → S3/GCS (multi-server) |

> **Note:** Vercel deployment of the frontend requires `NEXT_PUBLIC_API_URL` to be set in the Vercel project environment, pointing to the backend API. The backend cannot run on Vercel due to Tesseract dependency.
