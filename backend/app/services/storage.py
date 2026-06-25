import uuid
import logging
import aiofiles
from pathlib import Path
from fastapi import UploadFile

from app.core.config import get_settings
from app.core.exceptions import AudioValidationError
from app.core.observability import metrics
from app.services.audio_validation import ALLOWED_EXTENSIONS, validate_audio_file

logger = logging.getLogger(__name__)


async def save_upload(file: UploadFile) -> tuple[str, str, str, dict]:
    settings = get_settings()

    if not file.filename:
        raise AudioValidationError("No filename provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise AudioValidationError(
            f"Unsupported file type '{ext}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise AudioValidationError(
            f"File exceeds maximum size of {settings.max_upload_size_mb}MB"
        )
    if len(content) == 0:
        raise AudioValidationError("Uploaded file is empty")

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_id = str(uuid.uuid4())
    safe_name = f"{file_id}{ext}"
    file_path = upload_dir / safe_name

    async with aiofiles.open(file_path, "wb") as out:
        await out.write(content)

    metadata = validate_audio_file(
        str(file_path),
        size_bytes=len(content),
        content_type=file.content_type,
    )
    if ext == ".m4a":
        logger.info(
            "M4A upload received filename=%s content_type=%s file_id=%s bytes=%s",
            file.filename,
            file.content_type,
            file_id,
            len(content),
        )
    metrics.record_upload(accepted=True)
    return file_id, file.filename, str(file_path), metadata


async def save_uploads(files: list[UploadFile]) -> tuple[list[dict], list[dict]]:
    """Save multiple uploads; failures are isolated per file."""
    uploaded: list[dict] = []
    failed: list[dict] = []

    for file in files:
        filename = file.filename or "unknown"
        try:
            file_id, orig_name, path, metadata = await save_upload(file)
            uploaded.append(
                {
                    "file_id": file_id,
                    "filename": orig_name,
                    "path": path,
                    "metadata": metadata,
                    "success": True,
                    "error": None,
                }
            )
        except AudioValidationError as exc:
            metrics.record_upload(accepted=False)
            failed.append(
                {
                    "file_id": None,
                    "filename": filename,
                    "path": None,
                    "metadata": {},
                    "success": False,
                    "error": str(exc),
                }
            )
        except Exception as exc:
            failed.append(
                {
                    "file_id": None,
                    "filename": filename,
                    "path": None,
                    "metadata": {},
                    "success": False,
                    "error": f"Upload failed: {exc}",
                }
            )

    return uploaded, failed


def resolve_audio_path(file_id: str | None) -> str | None:
    if not file_id:
        return None
    settings = get_settings()
    upload_dir = Path(settings.upload_dir)
    matches = list(upload_dir.glob(f"{file_id}.*"))
    return str(matches[0]) if matches else None


def delete_audio_file(path: str | None) -> None:
    if not path:
        return
    file_path = Path(path)
    if file_path.exists():
        file_path.unlink(missing_ok=True)
