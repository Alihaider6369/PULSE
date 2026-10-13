# PULSE Production Deployment Guide

This guide details the architecture, configuration, hosting options, migration safety protocols, and operational procedures for deploying the **PULSE API backend**, **Web Dashboard**, and **Managed PostgreSQL Database** under HTTPS.

---

## 1. Architecture Overview & Security Perimeter

```
[PySide6 Windows Desktop App] ---> HTTPS (REST API) ---> [Cloud Reverse Proxy / PaaS (TLS/HTTPS)]
[Browser Web Dashboard User]  ---> HTTPS (HTML/JS)  --->           |
                                                                [FastAPI Backend: Uvicorn]
                                                                        |
                                                             (Private Network / TLS)
                                                                        v
                                                         [Managed PostgreSQL Database]
```

### Non-Negotiable Security & Privacy Rules
1. **Zero Camera Stream Exfiltration:** Webcam frames are processed strictly in-memory on the local desktop device via OpenCV and MediaPipe. Raw video or images are **never** stored, streamed, or uploaded. Only numerical session telemetry (posture classifications, time spent in good/poor posture, warning counts) is transmitted.
2. **Per-User Isolation:** Every database row (`sessions`, `posture_events`, `settings`) is scoped to `current_user.id` verified by cryptographic JWT signature.
3. **Database Isolation:** PostgreSQL must **never** be exposed directly to the public internet without SSL/TLS restrictions. In PaaS setups (e.g. Render, Railway), connections utilize internal private networking.
4. **HTTPS Enforcement:** All production communication must use TLS 1.3 / HTTPS. Plain HTTP traffic is automatically redirected or rejected.

---

## 2. Production Environment Variables Reference

A template file is provided at [`backend/.env.production.example`](file:///D:/PULSE/backend/.env.production.example).

| Variable | Type | Required | Description | Example Value |
| :--- | :--- | :--- | :--- | :--- |
| `DATABASE_URL` | String | Yes | PostgreSQL connection URI with SSL mode enabled | `postgresql+psycopg://pulse_admin:PASSWORD@db.region.render.com:5432/pulse_prod?sslmode=require` |
| `SECRET_KEY` | String | Yes | Cryptographically secure random JWT signing secret | Generate with: `openssl rand -hex 32` |
| `ALGORITHM` | String | Yes | JWT algorithm (HS256) | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Integer | Yes | Token validity window (in minutes) | `10080` (7 days) |
| `CORS_ORIGINS` | String | Yes | Comma-separated list of approved web dashboard HTTPS domains | `https://pulse.example.com,https://dashboard.pulse.example.com` |
| `COOKIE_SECURE` | Boolean | Yes | Ensures authentication cookies are only transmitted over HTTPS | `true` |
| `ENVIRONMENT` | String | Yes | Runtime environment flag | `production` |
| `APP_BASE_URL` | String | No | Public web dashboard origin for generating reset links (default: `http://127.0.0.1:8000`) | `https://pulse.example.com` |
| `SMTP_HOST` | String | No | Outbound SMTP relay hostname (if empty, reset links log to stdout) | `smtp.sendgrid.net` |
| `SMTP_PORT` | Integer | No | SMTP relay port (default: `587`) | `587` |
| `SMTP_USER` | String | Conditional | SMTP username (required if `SMTP_HOST` is configured) | `apikey` |
| `SMTP_PASSWORD` | String | Conditional | SMTP password or API token (required if `SMTP_HOST` is configured) | Configured in cloud secrets |
| `SMTP_FROM` | String | No | Sender address in From header (defaults to `SMTP_USER` if omitted) | `noreply@pulse.example.com` |

> [!WARNING]
> Never commit real production `.env` files or hardcoded credentials to Git. Inject environment variables using your cloud provider's encrypted secrets manager.
>
> **Mandatory Secrets:** `SECRET_KEY` and `POSTGRES_PASSWORD` are mandatory and must be set in `.env` (generate secure values with: `openssl rand -hex 32`). The backend and compose services will refuse to start if these are missing.

### Password reset email (SMTP)

PULSE supports self-service password recovery via cryptographically hashed tokens dispatched to user email addresses:

- **Development / Local Fallback:** When `SMTP_HOST` is unset, outbound email sending is skipped and generated reset links are safely logged to backend stdout for local development and verification.
- **Production Configuration:** To deliver emails in production, set `SMTP_HOST`, `SMTP_PORT` (typically 587 with STARTTLS), `SMTP_USER`, and `SMTP_PASSWORD` using your transactional email provider (such as SendGrid, AWS SES, Mailgun, Postmark, or Google Workspace).
- **Public Domain Linkage:** Set `APP_BASE_URL` to your production HTTPS domain (e.g. `https://pulse.example.com`). The password reset email includes a link formatted as `${APP_BASE_URL}/reset-password.html?token=<token>`.
- **Security Protections:** Raw tokens are 32-byte cryptographically secure random values with a 1-hour expiration. Only SHA-256 hashes are persisted in the `password_reset_tokens` table. Each token is strictly single-use (`used_at` timestamp). Both user enumeration protection and endpoint rate limiting (3 requests/hour per email) are active.

---

## 3. Recommended Cloud Hosting Options

### Option A: Render.com (Recommended for Simplicity & Zero-Maintenance)
* **Components:**
  1. **Render Web Service:** Runs Docker or native Python runtime using `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 4`.
  2. **Render Managed PostgreSQL:** Provides daily automated backups, SSL/TLS by default, and private internal DNS (`db.internal`).
* **Health Check Path:** `/api/health`
* **SSL/TLS:** Automated free Let's Encrypt certificates managed by Render.
* **Estimated Cost:** ~$7/mo for Web Service + ~$7/mo for PostgreSQL Starter tier.

### Option B: Railway.app (Recommended for Developer Agility & Micro-Services)
* **Components:**
  1. **Railway Service:** Deploys directly from Git branch with zero configuration using the included [`Dockerfile`](file:///D:/PULSE/Dockerfile).
  2. **Railway PostgreSQL Plugin:** One-click managed Postgres provisioning with private service mesh connectivity.
* **SSL/TLS:** Automatic HTTPS domain generation (`*.up.railway.app`) or custom domain mapping.
* **Estimated Cost:** Usage-based (typically $5–$10/mo).

### Option C: Fly.io + Supabase (Recommended for Global Latency Optimization)
* **Components:**
  1. **Fly.io App:** Deploys container to global edge regions close to users.
  2. **Supabase Managed Postgres:** Enterprise-grade PostgreSQL with pooled connections (PgBouncer) and point-in-time recovery.
* **Estimated Cost:** Generous free tiers available; ~$5–$25/mo for production workloads.

### Option D: Self-Hosted Linux VPS (Ubuntu 24.04 + Docker + Caddy)
* **Components:**
  1. [`docker-compose.prod.yml`](file:///D:/PULSE/docker-compose.prod.yml) running containerized FastAPI and Postgres.
  2. **Caddy Web Server:** Reverse proxy providing automated HTTPS certificates.
* **Estimated Cost:** ~$6–$12/mo on Hetzner or DigitalOcean.

---

## 4. Database Migration Runbook & Rollback Strategy

### A. Pre-Deployment Migration Testing (Dry Run)
Before running migrations on production data, verify migrations against a disposable staging database:

```bash
# 1. Export test database URI
export DATABASE_URL="postgresql+psycopg://test_user:test_pass@localhost:5432/pulse_staging"

# 2. Run migration upgrade to head
alembic upgrade head

# 3. Test downgrade to verify rollback safety
alembic downgrade -1

# 4. Re-upgrade to head
alembic upgrade head
```

### B. Production Migration Execution
When deploying a new backend release:
```bash
# In the application directory:
cd /app/backend
alembic upgrade head
```

### C. Emergency Rollback Procedure
If a database migration causes errors or application incompatibility:
```bash
# Roll back the single most recent migration:
alembic downgrade -1

# Or roll back to a specific known-good revision:
alembic downgrade 395fc3a2bf5d
```

---

## 5. Automated Backups & Disaster Recovery

### Daily Automated Backup Script
```bash
#!/bin/bash
set -euo pipefail

BACKUP_DIR="/var/backups/pulse"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/pulse_backup_${TIMESTAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"

# Dump database through SSL-secured connection
pg_dump "${DATABASE_URL}" | gzip > "${BACKUP_FILE}"
chmod 600 "${BACKUP_FILE}"

# Retain backups for 30 days
find "${BACKUP_DIR}" -type f -name "pulse_backup_*.sql.gz" -mtime +30 -delete

echo "Backup completed successfully: ${BACKUP_FILE}"
```

### Disaster Restoration Command
```bash
gunzip < /var/backups/pulse/pulse_backup_20261013_120000.sql.gz | psql "${DATABASE_URL}"
```

---

## 6. Desktop Application Configuration for Cloud HTTPS

The PULSE Windows Desktop application does **not** need to be recompiled when deploying to production:

1. Launch **PULSE** on Windows.
2. Navigate to the **Settings** view (Screen 3).
3. Under **Backend API Base URL**, enter your production HTTPS endpoint:
   ```
   https://api.pulse.yourdomain.com/api
   ```
4. Click **Save Settings**.
5. Navigate to **Cloud Sync** (Screen 4) and click **Test Connection**. A green `● Online (XX ms)` badge confirms successful HTTPS communication.
6. Click **Sign In / Register** to connect your desktop app to your authenticated cloud account.

---

## 7. User Explicit Approval Gate (Checklist)

Before performing any external operations, the user must review and explicitly authorize the following steps:

- [ ] **Cloud Provider Selection:** Approve preferred hosting platform (Render, Railway, Fly.io, or VPS).
- [ ] **Account Creation & Billing:** Creating the cloud provider account and configuring payment methods (agent will never request or process payment information).
- [ ] **Domain & DNS Provisioning:** Approving custom domain name and setting up DNS CNAME / A records.
- [ ] **Production Credentials Generation:** Generating and storing the live `SECRET_KEY` and database master password in provider secrets manager.
- [ ] **Live Migration Approval:** Executing `alembic upgrade head` against a live hosted PostgreSQL database.
