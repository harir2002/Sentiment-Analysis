# Operations Runbook

## Monitoring

### Metrics endpoint

`GET /metrics` (authenticated) returns:

- Request counts, 4xx/5xx rates, slow requests, average latency
- Job started/completed/failed counts
- Upload accept/reject counts
- Provider error counts by pipeline

Wire this to your dashboard (Grafana, Datadog, etc.) via periodic polling.

### Recommended alerts

| Alert | Condition | Action |
|-------|-----------|--------|
| High 5xx rate | `requests.5xx / requests.total > 0.05` over 5m | Check logs, provider status |
| Slow processing | `requests.slow` increasing | Review audio length, provider latency |
| Job failures | `jobs.failed` spike | Inspect audit events, provider keys |
| Not ready | `/ready` returns 503 | Check DB, upload dir, API keys |
| Provider errors | `provider_errors.*` spike | Retry failed jobs, check Sarvam/Groq status |

### Logs

Production: set `LOG_FORMAT=json`. Logs include:

- `request_completed` with `request_id`, latency
- `job_audit` events with `job_id`, `event_type` (no transcript/PII)
- `provider_pipeline_failed` / `provider_pipeline_completed`
- `slow_request` warnings

Search by `request_id` (returned in error responses as `X-Request-ID`).

## Audit trail

Every job writes events to `job_audit_events` table:

- `job_created`, `job_started`, `job_results_saved`, `job_finished`, `job_failed`

Metadata is PII-safe (filename, counts, status only — no transcript).

## Incident response

### Upload failures

1. Check `/ready` → `upload_dir` writable
2. Verify file type in allowed list (M4A, MP3, WAV, etc.)
3. Check `MAX_UPLOAD_SIZE_MB` vs file size
4. Review logs for `audio_validation_failed`

### Analysis stuck

1. Poll `GET /results/{job_id}` — check `pending_providers`
2. Sarvam batch STT may take up to `SARVAM_BATCH_MAX_WAIT_SECONDS`
3. Use `POST /results/{job_id}/retry` for failed providers

### Provider outage

1. `/health` shows which keys are configured
2. Pipelines fail independently — partial results still returned
3. HTTP retries handle transient 429/502/503 automatically

### Security incident (prompt injection / PII)

1. Guardrails log `prompt-injection patterns detected`
2. PII masked in all client responses when `GUARDRAILS_PII_MASKING_ENABLED=true`
3. Rotate API keys if exposure suspected

## Regression testing

Before each release:

```bash
cd backend
pytest tests/ -q
python eval/runner.py
```

Eval suite covers positive/neutral/negative/mixed/noisy transcripts and injection cases offline.

## Backup

- SQLite: copy `data/app.db` while app stopped, or use volume snapshots
- Uploads: backup `data/uploads/` if retention required (`CLEANUP_AUDIO_AFTER_JOB=false`)

## Rollback

See [DEPLOYMENT.md](./DEPLOYMENT.md#rollback).
