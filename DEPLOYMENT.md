# Prescription Intelligence — Deployment Guide

This document describes how to deploy Prescription Intelligence in a production environment.

---

## Architecture Overview

```text
                    ┌─────────────────────────────┐
                    │       Reverse Proxy         │
                    │    (nginx / Caddy / ALB)    │
                    │      TLS termination        │
                    └──────────┬──────────┬───────┘
                               │          │
                    ┌──────────▼─┐   ┌───▼─────────────┐
                    │  Frontend  │   │     Backend      │
                    │ Next.js 16 │   │ FastAPI/uvicorn  │
                    │   :3000    │   │      :8000       │
                    └────────────┘   └─────┬──────┬─────┘
                                           │      │
                             ┌─────────────▼─┐  ┌─▼──────────┐
                             │  PostgreSQL   │  │  uploads/  │
                             │     :5432     │  │  (volume)  │
                             └───────────────┘  └────────────┘
```

In production, the reverse proxy should terminate HTTPS/TLS and expose only the public frontend and backend endpoints.

The PostgreSQL database and application containers should not be directly exposed to the public internet.

---

## Prerequisites

### Backend host

* Python 3.11+
* PostgreSQL 14+
* Tesseract OCR
* `libpq5` or the PostgreSQL client libraries required by the deployment environment

For Ubuntu/Debian:

```bash
apt-get update
apt-get install -y tesseract-ocr libpq5
```

### Frontend host

* Node.js 20+

### Docker deployment

Docker Desktop or Docker Engine with Docker Compose support.

The provided Docker configuration includes Tesseract and the required Python dependencies inside the backend image.

---

## Quick Start with Docker Compose

The Compose configuration supports local development and provides a production-oriented single-server reference.

### Local Docker environment

```bash
# 1. Copy the environment example
cp .env.example .env

# 2. Fill in the required local values.
#    At minimum:
#      DB_PASSWORD
#      SECRET_KEY
#      SMTP_* variables
#      FRONTEND_URL
#
#    For local testing, localhost URLs are acceptable.

# 3. Build and start all services
docker compose up --build
```

Services:

```text
http://localhost:3000          — Frontend
http://localhost:8000          — Backend API
http://localhost:8000/health   — Backend health check
```

The Docker Compose configuration binds these services to localhost by default.

**Do not expose the PostgreSQL port or application ports directly to the public internet in a hardened production deployment.**

---

## Production Docker Deployment

For a real production deployment:

1. Provide production environment variables through the hosting platform's secret/environment-variable system.
2. Do not commit `.env` or any file containing real secrets.
3. Use real HTTPS frontend and backend URLs.
4. Configure SMTP before enabling production registration.
5. Configure `CORS_ORIGINS` to contain only the required production frontend origins.
6. Place the application behind a reverse proxy or load balancer with TLS termination.
7. Use persistent storage for PostgreSQL and prescription uploads.
8. Run database migrations before starting application instances.
9. Configure regular database and upload backups.
10. Use a shared rate-limit store such as Redis when running multiple backend instances.

For a single-server Docker deployment, the included Compose configuration can be used as a starting point.

For multi-server deployments, move PostgreSQL to managed PostgreSQL and prescription uploads to object storage such as S3 or GCS.

---

## Manual Deployment

### Backend

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# Windows PowerShell:
# .venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env

# Edit .env with real production values.

# 4. Run database migrations
alembic upgrade head

# 5. Start the server
uvicorn backend.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 4
```

Use an appropriate process manager, container orchestrator, or service manager for production.

### Frontend

```bash
cd frontend

# 1. Install dependencies
npm ci

# 2. Configure the production API URL
#
# NEXT_PUBLIC_API_URL is a build-time variable.
# It must point to the publicly reachable backend API.

# Example:
# NEXT_PUBLIC_API_URL=https://api.yourdomain.com

# 3. Build
npm run build

# 4. Start
npm start
```

For Next.js, `NEXT_PUBLIC_API_URL` is embedded into the production frontend during the build. Changing only the runtime container environment after the build does not change the already-built frontend bundle.

---

## Environment Variables

### Backend (`.env`)

| Variable          | Required          | Description                                              |
| ----------------- | ----------------- | -------------------------------------------------------- |
| `DB_USER`         | Yes               | PostgreSQL username                                      |
| `DB_PASSWORD`     | Yes               | PostgreSQL password                                      |
| `DB_HOST`         | Yes               | PostgreSQL hostname                                      |
| `DB_PORT`         | Yes               | PostgreSQL port, normally `5432`                         |
| `DB_NAME`         | Yes               | Database name                                            |
| `SECRET_KEY`      | Yes in production | Strong random JWT signing secret                         |
| `ENVIRONMENT`     | Yes               | Use `development` locally and `production` in production |
| `CORS_ORIGINS`    | Yes in production | Comma-separated allowed frontend origins                 |
| `SMTP_HOST`       | Yes in production | SMTP server hostname                                     |
| `SMTP_PORT`       | Yes in production | SMTP server port, normally `587` for STARTTLS            |
| `SMTP_USERNAME`   | Yes in production | SMTP login username                                      |
| `SMTP_PASSWORD`   | Yes in production | SMTP password or application password                    |
| `SMTP_FROM_EMAIL` | Yes in production | Sender address used by verification/reset emails         |
| `FRONTEND_URL`    | Yes in production | Public frontend base URL used in email links             |

Generate a strong secret with:

```bash
python -c "import secrets; print(secrets.token_hex(64))"
```

### Email verification

Email verification is part of the production authentication flow.

Configure all of the following together:

```text
SMTP_HOST
SMTP_PORT
SMTP_USERNAME
SMTP_PASSWORD
SMTP_FROM_EMAIL
FRONTEND_URL
```

Production registration should not be enabled without working email delivery.

Do not rely on manual verification as a production fallback.

---

## Frontend Environment

The frontend uses:

| Variable              | Required | Description            |
| --------------------- | -------- | ---------------------- |
| `NEXT_PUBLIC_API_URL` | Yes      | Public backend API URL |

Example:

```text
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
```

`NEXT_PUBLIC_API_URL` is a **build-time** variable.

For Docker Compose, it is passed as a Docker build argument:

```yaml
build:
  args:
    NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL}
```

For Vercel or another frontend hosting platform, configure the variable in the platform's build environment.

---

## Production URL Requirements

For a real production deployment, do not leave production URLs pointing to `localhost`.

The following values must use the actual publicly reachable HTTPS URLs:

```text
CORS_ORIGINS=https://app.yourdomain.com
FRONTEND_URL=https://app.yourdomain.com
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
```

These are examples only. Replace `yourdomain.com` with the actual production domain.

### Meaning of each URL

* `CORS_ORIGINS` — frontend origin(s) allowed to call the backend.
* `FRONTEND_URL` — frontend base URL used when generating email verification and password-reset links.
* `NEXT_PUBLIC_API_URL` — backend API URL embedded into the frontend during the Next.js build.

In production, HTTPS should be enforced at the reverse proxy/load balancer.

---

## Production Secrets

Never commit real credentials or secrets to source control.

The following must be supplied through a secure environment/secrets mechanism:

* `SECRET_KEY`
* `DB_PASSWORD`
* `SMTP_PASSWORD`
* other provider credentials or API keys

For local Docker development, `.env` may be used and must remain untracked.

For cloud production, prefer the hosting provider's secret/environment-variable management rather than committing or distributing `.env` files.

---

## Production Checklist

### Security

* [ ] `SECRET_KEY` is a strong, unique random value.
* [ ] `SECRET_KEY` is different between development and production.
* [ ] `ENVIRONMENT=production` is set on the backend.
* [ ] `CORS_ORIGINS` contains only the required production frontend origins.
* [ ] `FRONTEND_URL` uses the real production HTTPS frontend URL.
* [ ] `NEXT_PUBLIC_API_URL` uses the real production HTTPS backend URL.
* [ ] PostgreSQL is not exposed to the public internet.
* [ ] HTTPS/TLS is enforced on the reverse proxy.
* [ ] `uploads/` is not served as a public static path.
* [ ] Real secrets are not committed to Git.
* [ ] SMTP credentials are stored securely.
* [ ] Production rate limiting uses shared storage such as Redis when multiple backend instances are deployed.

### Database

* [ ] `alembic upgrade head` has been run against the production database.
* [ ] PostgreSQL data is backed up regularly.
* [ ] Database backups are tested periodically.
* [ ] Database password is strong and not the example placeholder.
* [ ] Database is accessible only from the required application/network layer.

### File Storage

* [ ] `uploads/` is on persistent storage.
* [ ] Upload storage is included in the backup strategy.
* [ ] Upload storage is not publicly exposed.
* [ ] For multi-server/cloud deployments, migrate prescription images to object storage such as S3 or GCS.

### Application

* [ ] `GET /health` returns HTTP 200 when the database is healthy.
* [ ] Email verification works with the production SMTP configuration.
* [ ] Password reset email delivery works.
* [ ] Frontend can reach the backend API.
* [ ] `NEXT_PUBLIC_API_URL` points to the correct production API.
* [ ] Prescription upload and OCR work in the production environment.
* [ ] Medicine vocabulary data is present in the backend runtime.
* [ ] Pharmacist review workflow works.
* [ ] PDF report generation works when enabled by the organization's plan.
* [ ] Customer prescription visibility is tenant-safe.

---

## File Storage Notes

Currently, prescription images are stored on the local filesystem in `./uploads/`.

This is suitable for a **single-server deployment** when the upload volume is persistent and included in backups.

For multi-server or cloud deployments, migrate prescription images to object storage such as S3 or GCS.

The storage implementation must preserve the existing authorization model.

Conceptually:

1. Replace the local file write with an object-storage upload.
2. Replace direct local file serving with a presigned URL or authenticated streaming proxy.
3. Preserve authorization checks before any prescription image is returned.
4. Preserve tenant isolation.
5. Update `UPLOAD_DIR` handling if local storage remains supported.

The security model must remain unchanged regardless of the storage backend.

---

## Health Monitoring

The backend exposes:

```text
GET /health
```

### Healthy

HTTP `200`:

```json
{
  "status": "healthy",
  "database": "connected",
  "version": "1.0.0"
}
```

### Degraded

HTTP `503`:

```json
{
  "status": "degraded",
  "database": "unavailable",
  "version": "1.0.0"
}
```

Configure the load balancer, reverse proxy, container orchestrator, or monitoring system to use `/health` as the backend health-check path.

A production deployment should alert on repeated health-check failures rather than relying only on manual monitoring.

---

## Database Migrations

Migrations are managed with Alembic.

Apply all pending migrations:

```bash
alembic upgrade head
```

Check the current migration state:

```bash
alembic current
```

View migration history:

```bash
alembic history
```

In Docker Compose, the `migrate` service runs:

```text
alembic upgrade head
```

before the backend starts.

Do not delete the PostgreSQL volume during normal deployments.

For production migrations:

1. Back up the database.
2. Apply the migration.
3. Verify the migration reaches `head`.
4. Start or restart application instances.
5. Verify `/health`.
6. Run an application smoke test.

---

## Tesseract OCR

Tesseract is a backend-only dependency.

For a manual Ubuntu/Debian installation:

```bash
apt-get update
apt-get install -y tesseract-ocr
```

For macOS:

```bash
brew install tesseract
```

For Windows development, install Tesseract separately and ensure it is available to the backend process.

The Docker backend image includes the required OCR runtime dependency.

The frontend does not invoke Tesseract.

---

## Logging

The backend uses Python's `logging` module.

To configure the Uvicorn log level:

```bash
UVICORN_LOG_LEVEL=info uvicorn backend.main:app ...
```

or configure logging through the production process manager/container environment.

OCR candidate scoring and text extraction metrics are logged at `DEBUG` level only.

Prescription text content should not be written to application logs.

Avoid logging:

* passwords
* JWTs
* SMTP passwords
* API keys
* password-reset tokens
* email-verification tokens
* prescription image contents
* other sensitive customer information

---

## Rate Limiting

The application includes authentication endpoint rate limiting.

The default rate-limit storage is in-memory, which is suitable for a single backend instance.

For multiple backend instances, configure a shared rate-limit store such as Redis using:

```text
RATELIMIT_STORAGE_URL
```

The shared store is required so that rate limits are enforced consistently across all backend instances.

---

## Startup Order

For Docker Compose:

1. PostgreSQL starts.
2. PostgreSQL health check passes.
3. Alembic migrations run.
4. Backend starts.
5. Backend health check passes.
6. Frontend starts.

The backend depends on successful completion of the migration service.

---

## Recommended Hosting

| Component          | Suitable Hosting                                                               |
| ------------------ | ------------------------------------------------------------------------------ |
| Backend            | EC2, Render, Railway, Fly.io, VPS, or another Python 3.11+ host with Tesseract |
| Frontend           | Vercel, Netlify, or another Node.js/Next.js host                               |
| Database           | Managed PostgreSQL such as RDS, Neon, Supabase, Railway, or Render             |
| File storage       | Persistent local volume for single server; S3/GCS for multi-server             |
| Rate-limit storage | In-memory for single instance; Redis for multi-instance                        |

### Vercel frontend

Vercel can host the Next.js frontend.

Configure:

```text
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
```

in the Vercel project environment before building the frontend.

The backend should run on infrastructure that supports Python, FastAPI, and the Tesseract OCR dependency.

---

## Production Smoke Test

After deployment, verify the following in order:

### 1. Backend health

```bash
curl -i https://api.yourdomain.com/health
```

Expected HTTP status:

```text
200
```

### 2. Frontend

Open:

```text
https://app.yourdomain.com
```

### 3. Authentication

Verify:

* registration
* verification email
* email verification
* login
* logout/session behavior
* password reset

### 4. Prescription workflow

Verify:

* prescription upload
* OCR processing
* medicine resolution
* safety analysis
* pharmacist review
* PDF report generation

### 5. Customer workflow

Verify:

* customer profile
* prescription assignment
* customer prescription visibility
* tenant isolation

### 6. Operational checks

Verify:

* health monitoring
* database migration state
* persistent uploads
* backup configuration
* application logs
* rate limiting

---

## Deployment Principles

Production deployments should follow these principles:

* Secrets belong in secure environment/secrets management.
* Production URLs must use HTTPS.
* PostgreSQL must not be publicly exposed.
* Prescription uploads must remain protected by authentication and tenant authorization.
* Email verification must remain enabled for production registration.
* Database migrations must be applied before application instances use the new schema.
* Persistent data must have a tested backup strategy.
* Multi-instance deployments require shared rate-limit storage.
* Multi-server deployments should use object storage for prescription images.
* AI analysis remains decision support and does not replace pharmacist review or clinical judgment.
