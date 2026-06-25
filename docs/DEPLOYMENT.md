# Deployment Guide

## Prerequisites

- Docker 24+ and Docker Compose v2, **or**
- Python 3.11+, Node 20+, reverse proxy (nginx/Caddy)

## Quick start (Docker)

```bash
cp .env.example .env
# Set SARVAM_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY, and change ADMIN_PASSWORD

docker compose up --build -d
```

- Frontend: http://localhost:5173  
- Backend API: http://localhost:8000  
- API docs: http://localhost:8000/docs  

## Production environment variables

| Variable | Production value | Notes |
|----------|------------------|-------|
| `APP_ENV` | `production` | Enables production-safe defaults |
| `LOG_FORMAT` | `json` | Structured logs for aggregation |
| `EXPOSE_ERROR_DETAILS` | `false` | Never leak stack traces to clients |
| `ADMIN_PASSWORD` | strong secret | Rotate regularly |
| `METRICS_ENABLED` | `true` | Enables `/metrics` endpoint |
| `DATABASE_URL` | PostgreSQL URL | Recommended for multi-instance deploys |

## Health probes

| Endpoint | Use | Expected |
|----------|-----|----------|
| `GET /live` | Liveness | Always 200 if process is up |
| `GET /ready` | Readiness | 200 when DB + upload dir + provider keys OK |
| `GET /health` | Detailed status | 200 with dependency breakdown |

## Rollback

1. Tag releases before deploy: `git tag v1.2.3`
2. On failure, redeploy previous image: `docker compose pull && docker compose up -d`
3. Database is forward-compatible via lightweight migrations in `init_db()`
4. Keep `data/uploads` volume if jobs are in-flight

## Scaling notes

- Background jobs use in-process tasks — for high volume, migrate to Celery/Redis or similar
- SQLite is fine for single-node; use PostgreSQL for HA
- Set `CORS_ORIGINS` to your production frontend URL only

## Secrets

Never commit `.env`. Use your platform's secret manager (AWS SSM, Azure Key Vault, etc.).
