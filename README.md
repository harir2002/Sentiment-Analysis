# Call Analytics | Dr. Mohan's

Client-facing call transcription and sentiment analysis platform. Compares four real STT+LLM pipelines in parallel and presents a polished, business-ready result to end users.

| Pipeline | STT | LLM |
|----------|-----|-----|
| 1 | Sarvam (`saaras:v3`) | Sarvam (`sarvam-30b`) |
| 2 | Sarvam | OpenRouter Gemma 4 26B |
| 3 | Groq Whisper large-v3 | Sarvam |
| 4 | Groq Whisper | OpenRouter Gemma 4 26B |

## Features

- **Client UI** — premium layout, light/dark mode, processing steps, skeleton loading
- **Production backend** — validation, guardrails, PII masking, audit trail, metrics
- **Real APIs only** — no mock mode; English translation before analysis
- **Formats** — M4A, MP3, WAV, MPEG, FLAC, OGG, WebM (max 25 MB)
- **Exports** — Word, PDF, Excel, CSV, JSON
- **Observability** — `/live`, `/ready`, `/health`, `/metrics`

## Quick start (local)

```bash
cp .env.example .env
# Set SARVAM_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY

cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

cd frontend && npm install && npm run dev
```

Open http://localhost:5173 — default credentials: change `ADMIN_PASSWORD` in `.env`.

## Docker (production)

```bash
docker compose up --build -d
```

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) and [docs/OPERATIONS.md](docs/OPERATIONS.md).

## API endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/live` | No | Liveness probe |
| GET | `/ready` | No | Readiness (DB, upload dir, keys) |
| GET | `/health` | No | Detailed health status |
| GET | `/metrics` | Yes | Operational metrics snapshot |
| POST | `/upload` | Yes | Batch audio upload |
| POST | `/run-comparison` | Yes | Start analysis job |
| GET | `/results/{job_id}` | Yes | Poll results |
| GET | `/results/{job_id}/export/*` | Yes | Download report |

## Production configuration

Key `.env` settings for production:

```env
APP_ENV=production
LOG_FORMAT=json
EXPOSE_ERROR_DETAILS=false
METRICS_ENABLED=true
ADMIN_PASSWORD=<strong-secret>
GUARDRAILS_PII_MASKING_ENABLED=true
SARVAM_LLM_PLAN_TIER=starter
SARVAM_LLM_MAX_TOKENS=4096
```

## Testing & regression

```bash
cd backend
pytest tests/ -q
python eval/runner.py
```

Eval fixtures cover positive, neutral, negative, mixed, noisy, and injection scenarios offline.

## Security

- HTTP Basic auth on all API routes (except health probes)
- PII masked in client responses and safe logs
- Prompt-injection detection and delimiter wrapping
- No raw provider payloads or internal model names in client UI
- Error details hidden in production (`EXPOSE_ERROR_DETAILS=false`)

## Documentation

- [Deployment](docs/DEPLOYMENT.md) — Docker, env vars, rollback
- [Operations](docs/OPERATIONS.md) — monitoring, alerts, incidents, audit trail
