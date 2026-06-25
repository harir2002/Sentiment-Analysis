import uuid
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.observability import metrics
from app.services.audit import record_audit_event
from app.models.db_models import ComparisonJob
from app.models.schemas import JobStatus, JobResponse, ProviderResult
from app.services.comparison import run_single_solution
from app.services.storage import resolve_audio_path, delete_audio_file
from app.services.audio_validation import validate_audio_file
from app.services.sarvam_batch_worker import schedule_sarvam_batch_followups
from app.providers.sarvam_stt_coordinator import clear_shared_state
from app.services.stt_english import sanitize_provider_result_for_client
from app.services.odoo_crm import sync_to_odoo


async def create_job(
    db: AsyncSession,
    file_id: str,
    call_reference: str | None,
    original_filename: str | None = None,
) -> ComparisonJob:
    audio_path = resolve_audio_path(file_id)
    if not audio_path:
        raise ValueError("Uploaded audio file not found")

    validate_audio_file(audio_path)

    job = ComparisonJob(
        id=str(uuid.uuid4()),
        status=JobStatus.PENDING.value,
        audio_filename=original_filename or file_id,
        audio_path=audio_path,
        call_reference=call_reference,
        stt_language_code=None,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    metrics.record_job_started()
    await record_audit_event(
        db,
        job_id=job.id,
        event_type="job_created",
        message="Comparison job created",
        metadata={
            "filename": original_filename or file_id,
            "status": job.status,
        },
    )
    return job


async def get_job(db: AsyncSession, job_id: str) -> ComparisonJob | None:
    result = await db.execute(select(ComparisonJob).where(ComparisonJob.id == job_id))
    return result.scalar_one_or_none()


async def list_jobs(db: AsyncSession, *, limit: int = 100) -> list[ComparisonJob]:
    result = await db.execute(
        select(ComparisonJob).order_by(ComparisonJob.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def _save_job_results(
    db: AsyncSession,
    job: ComparisonJob,
    result: ProviderResult,
    audio_path: str | None,
) -> None:
    settings = get_settings()
    # Store single result
    job.result = result.model_dump()
    job.error = None
    job.stt_language_code = result.stt_language_code
    job.completed_at = datetime.utcnow()
    job.total_runtime_seconds = result.total_runtime_seconds
    
    job.status = JobStatus.COMPLETED.value if result.status == "completed" else JobStatus.FAILED.value
    await db.commit()

    await record_audit_event(
        db,
        job_id=job.id,
        event_type="job_results_saved",
        message="Analysis result persisted",
        metadata={
            "status": job.status,
            "result_status": result.status,
            "runtime_seconds": job.total_runtime_seconds,
        },
    )

    # Sync to Odoo CRM if enabled and analysis is successful
    if result.status == "completed" and result.analysis and settings.odoo_enabled:
        crm_sync = await sync_to_odoo(
            call_reference=job.call_reference or job.id,
            transcript=result.transcript or "",
            analysis=result.analysis,
            customer_phone=None,  # Could extract from transcript/analysis if needed
            customer_email=None,
            customer_name=None,
            agent_name=None,
        )
        
        await record_audit_event(
            db,
            job_id=job.id,
            event_type="odoo_sync",
            message=crm_sync.get("message", "Odoo sync completed"),
            metadata={
                "crm_status": crm_sync.get("status"),
                "crm_record_id": crm_sync.get("crm_record_id"),
                "error": crm_sync.get("error"),
            },
        )

    if settings.cleanup_audio_after_job and audio_path and result.status == "completed":
        delete_audio_file(audio_path)
        refreshed = await get_job(db, job.id)
        if refreshed:
            refreshed.audio_path = None
            await db.commit()

    clear_shared_state(audio_path or "")


async def run_job_background(job_id: str):
    from app.core.database import AsyncSessionLocal

    audio_path = None

    async with AsyncSessionLocal() as db:
        job = await get_job(db, job_id)
        if not job:
            return

        job.status = JobStatus.RUNNING.value
        await db.commit()
        await record_audit_event(
            db,
            job_id=job_id,
            event_type="job_started",
            message="Analysis started",
        )

        try:
            audio_path = job.audio_path
            if not audio_path:
                raise ValueError("No audio file associated with this job")

            validate_audio_file(audio_path)
            result = await run_single_solution(audio_path)
            await _save_job_results(db, job, result, audio_path)

        except Exception as e:
            job.status = JobStatus.FAILED.value
            job.error = str(e)
            job.completed_at = datetime.utcnow()
            await db.commit()
            metrics.record_job_finished(success=False)
            await record_audit_event(
                db,
                job_id=job_id,
                event_type="job_failed",
                message="Job failed during processing",
                level="error",
                metadata={"error_type": type(e).__name__},
            )


async def retry_job_background(job_id: str):
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        job = await get_job(db, job_id)
        if not job:
            return

        if not job.audio_path:
            job.error = "Audio file no longer available — re-upload and run analysis"
            await db.commit()
            return

        job.status = JobStatus.RUNNING.value
        await db.commit()

        try:
            validate_audio_file(job.audio_path)
            clear_shared_state(job.audio_path)
            result = await run_single_solution(job.audio_path)
            await _save_job_results(db, job, result, job.audio_path)
        except Exception as e:
            job.status = JobStatus.FAILED.value
            job.error = str(e)
            job.completed_at = datetime.utcnow()
            await db.commit()
            metrics.record_job_finished(success=False)
            await record_audit_event(
                db,
                job_id=job_id,
                event_type="job_retry_failed",
                message="Job retry failed",
                level="error",
                metadata={"error_type": type(e).__name__},
            )


def job_to_response(job: ComparisonJob) -> JobResponse:
    result = None
    if job.result:
        provider_result = ProviderResult(**job.result)
        # Extract the analysis from provider result (already an AnalysisResult)
        if provider_result.analysis and provider_result.status == "completed":
            result = provider_result.analysis

    ready = result is not None

    return JobResponse(
        job_id=job.id,
        status=JobStatus(job.status),
        created_at=job.created_at,
        completed_at=job.completed_at,
        total_runtime_seconds=job.total_runtime_seconds,
        call_reference=job.call_reference,
        stt_language_code=job.stt_language_code,
        audio_filename=job.audio_filename,
        result=result,
        error=job.error,
        pending_providers=0,
        results_ready=ready,
        aggregate_status=job.status,
    )
