from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import verify_admin
from app.core.config import get_settings
from app.core.exceptions import AudioValidationError
from app.models.schemas import (
    UploadItemResult,
    BatchUploadResponse,
    RunComparisonRequest,
    RetryProvidersRequest,
    JobResponse,
    CallsListResponse,
    CallListItem,
    HealthResponse,
)
from app.core.observability import metrics
from app.services.health import health_report, readiness_report
from app.services.storage import save_uploads, resolve_audio_path
from app.services.jobs import (
    create_job,
    get_job,
    list_jobs,
    run_job_background,
    retry_job_background,
    job_to_response,
)
from app.services.export import (
    export_job_csv,
    export_job_excel,
    export_job_json,
    export_job_pdf,
    export_job_word,
)

router = APIRouter()


async def _list_calls(db: AsyncSession) -> CallsListResponse:
    jobs = await list_jobs(db)
    calls: list[CallListItem] = []
    for job in jobs:
        response = job_to_response(job)
        calls.append(
            CallListItem(
                job_id=response.job_id,
                status=response.status,
                audio_filename=response.audio_filename,
                call_reference=response.call_reference,
                created_at=response.created_at,
                completed_at=response.completed_at,
                aggregate_status=response.aggregate_status,
                results_ready=response.results_ready,
            )
        )
    return CallsListResponse(calls=calls, total=len(calls))


@router.get("/calls", response_model=CallsListResponse, tags=["calls"])
@router.get("/api/calls", response_model=CallsListResponse, tags=["calls"])
async def list_calls(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin),
):
    return await _list_calls(db)


@router.get("/live")
async def liveness():
    """Process is running (for orchestrator liveness probes)."""
    return {"status": "alive"}


@router.get("/ready")
async def readiness():
    """Dependency readiness (DB, upload dir, provider keys)."""
    report = await readiness_report()
    status_code = 200 if report["ready"] else 503
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=status_code, content=report)


@router.get("/metrics")
async def get_metrics(_: str = Depends(verify_admin)):
    """Operational metrics snapshot for monitoring dashboards."""
    settings = get_settings()
    if not settings.metrics_enabled:
        raise HTTPException(status_code=404, detail="Metrics disabled")
    return metrics.snapshot()


@router.get("/health", response_model=HealthResponse)
async def health():
    report = await health_report()
    return HealthResponse(
        status=report["status"],
        database=report["database"],
        version=report["version"],
        providers=report["providers"],
        models=report["models"],
    )


@router.post("/upload", response_model=BatchUploadResponse)
async def upload_audio(
    files: list[UploadFile] = File(...),
    _: str = Depends(verify_admin),
):
    if not files:
        raise HTTPException(status_code=400, detail="At least one audio file is required")

    uploaded_raw, failed_raw = await save_uploads(files)
    uploaded = [UploadItemResult(**item) for item in uploaded_raw]
    failed = [UploadItemResult(**item) for item in failed_raw]

    if not uploaded and failed:
        raise HTTPException(
            status_code=400,
            detail=f"All {len(failed)} file(s) failed validation",
        )

    return BatchUploadResponse(
        uploaded=uploaded,
        failed=failed,
        total=len(files),
        success_count=len(uploaded),
        failed_count=len(failed),
    )


@router.post("/run-comparison", response_model=JobResponse)
async def run_comparison(
    request: RunComparisonRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin),
):
    if not request.file_id:
        raise HTTPException(status_code=400, detail="file_id is required — upload a real audio file first")

    audio_path = resolve_audio_path(request.file_id)
    if not audio_path:
        raise HTTPException(status_code=404, detail="Uploaded audio file not found")

    try:
        job = await create_job(
            db,
            request.file_id,
            request.call_reference,
        )
    except (AudioValidationError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    background_tasks.add_task(run_job_background, job.id)
    return job_to_response(job)


@router.post("/results/{job_id}/retry", response_model=JobResponse)
async def retry_failed_providers(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin),
):
    job = await get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.result:
        raise HTTPException(status_code=400, detail="No results to retry")

    if not job.audio_path:
        raise HTTPException(
            status_code=400,
            detail="Audio file no longer available — re-upload and run a new analysis",
        )

    background_tasks.add_task(retry_job_background, job_id)
    job.status = "running"
    await db.commit()
    await db.refresh(job)
    return job_to_response(job)


@router.get("/results/{job_id}", response_model=JobResponse)
async def get_results(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin),
):
    job = await get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job_to_response(job)


@router.get("/results/{job_id}/export/json")
async def export_results_json(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin),
):
    job = await get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    response = job_to_response(job)
    content = export_job_json(response)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="analysis-{job_id}.json"'},
    )


@router.get("/results/{job_id}/export/csv")
async def export_results_csv(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin),
):
    job = await get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    response = job_to_response(job)
    content = export_job_csv(response)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="analysis-{job_id}.csv"'},
    )


@router.get("/results/{job_id}/export/xlsx")
async def export_results_excel(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin),
):
    job = await get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    response = job_to_response(job)
    content = export_job_excel(response)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="analysis-{job_id}.xlsx"'},
    )


@router.get("/results/{job_id}/export/pdf")
async def export_results_pdf(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin),
):
    job = await get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    response = job_to_response(job)
    content = export_job_pdf(response)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="analysis-{job_id}.pdf"'},
    )


@router.get("/results/{job_id}/export/docx")
async def export_results_word(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin),
):
    job = await get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    response = job_to_response(job)
    content = export_job_word(response)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="analysis-{job_id}.docx"'},
    )


@router.post("/results/{job_id}/sync-odoo")
async def sync_results_to_odoo(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_admin),
):
    from app.services.odoo_crm import sync_to_odoo
    
    job = await get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if not job.result:
        raise HTTPException(status_code=400, detail="No analysis results to sync")
    
    response = job_to_response(job)
    if not response.result:
        raise HTTPException(status_code=400, detail="No analysis data available")
    
    # Sync to Odoo
    crm_sync = await sync_to_odoo(
        call_reference=job.call_reference or job.id,
        transcript=response.result.get('transcript') or '',
        analysis=response.result,
        customer_phone=None,
        customer_email=None,
        customer_name=None,
        agent_name=None,
    )
    
    return crm_sync
