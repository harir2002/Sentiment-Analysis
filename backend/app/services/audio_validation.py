import logging
import mimetypes
import wave
import contextlib
from pathlib import Path

from app.core.config import get_settings
from app.core.exceptions import AudioValidationError

logger = logging.getLogger(__name__)

# FINTECH: Restrict to WAV, MP3, M4A only (regulatory standard)
FINTECH_ALLOWED_EXTENSIONS = {".wav", ".mp3", ".mpeg", ".m4a"}
ALLOWED_EXTENSIONS = FINTECH_ALLOWED_EXTENSIONS  # Alias for backward compatibility

# FINTECH: Sample rate and channel requirements for compliance
FINTECH_SAMPLE_RATE_HZ = [8000, 16000]  # Standard for call recordings
FINTECH_MAX_CHANNELS = 2  # Mono or stereo only
FINTECH_MIN_DURATION_SECONDS = 0.5
FINTECH_MAX_DURATION_SECONDS = 4 * 3600  # 4 hours max

EXTENSION_MIME = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".mpeg": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".webm": "audio/webm",
    ".flac": "audio/flac",
}

# MIME types accepted per extension (browsers vary, especially for .m4a).
EXTENSION_ACCEPTED_MIMES: dict[str, frozenset[str]] = {
    ".wav": frozenset({"audio/wav", "audio/x-wav", "audio/wave"}),
    ".mp3": frozenset({"audio/mpeg", "audio/mp3", "audio/x-mpeg", "audio/x-mp3"}),
    ".mpeg": frozenset({"audio/mpeg", "audio/mp3", "audio/x-mpeg", "audio/x-mp3"}),
    ".m4a": frozenset({"audio/mp4", "audio/x-m4a", "audio/m4a"}),
    ".ogg": frozenset({"audio/ogg", "application/ogg"}),
    ".webm": frozenset({"audio/webm", "video/webm"}),
    ".flac": frozenset({"audio/flac", "audio/x-flac"}),
}

MIME_ALIASES = {
    "audio/mp3": "audio/mpeg",
    "audio/x-mpeg": "audio/mpeg",
    "audio/x-mp3": "audio/mpeg",
    "audio/x-m4a": "audio/mp4",
    "audio/m4a": "audio/mp4",
    "audio/x-wav": "audio/wav",
    "audio/wave": "audio/wav",
    "audio/x-flac": "audio/flac",
}

# Improve OS-level guessing for .m4a (notably on Windows).
mimetypes.add_type("audio/mp4", ".m4a")
mimetypes.add_type("audio/x-m4a", ".m4a")


def _normalize_mime_type(mime_type: str | None) -> str | None:
    if not mime_type:
        return None
    normalized = mime_type.split(";", 1)[0].strip().lower()
    return MIME_ALIASES.get(normalized, normalized)


def _accepted_mimes_for_extension(ext: str) -> frozenset[str]:
    accepted = EXTENSION_ACCEPTED_MIMES.get(ext, frozenset())
    if not accepted:
        canonical = EXTENSION_MIME.get(ext)
        return frozenset({canonical}) if canonical else frozenset()
    normalized = {_normalize_mime_type(m) or m for m in accepted}
    return accepted | normalized


def _mime_matches_extension(ext: str, mime_type: str | None) -> bool:
    normalized = _normalize_mime_type(mime_type)
    if not normalized:
        return False
    return normalized in _accepted_mimes_for_extension(ext)


def _read_file_header(path: Path, nbytes: int = 16) -> bytes:
    with path.open("rb") as handle:
        return handle.read(nbytes)


def _has_mp4_container_signature(data: bytes) -> bool:
    """Detect ISO BMFF containers used by .m4a / .mp4 audio (ftyp atom)."""
    return len(data) >= 8 and data[4:8] == b"ftyp"


def _validate_extension_mime(
    ext: str,
    *,
    content_type: str | None = None,
    path: str | None = None,
) -> str:
    canonical = EXTENSION_MIME.get(ext)
    if not canonical:
        raise AudioValidationError(f"Unsupported format '{ext}'.")

    observed: list[str] = []
    declared = _normalize_mime_type(content_type)
    if declared:
        observed.append(declared)
    if path:
        guessed = _normalize_mime_type(get_mime_type(path))
        if guessed:
            observed.append(guessed)

    if not observed:
        return canonical

    for mime in observed:
        if not mime or mime in {"application/octet-stream", "binary/octet-stream"}:
            continue
        if _mime_matches_extension(ext, mime):
            return canonical
        raise AudioValidationError(
            f"Unsupported file type for '{ext}'. "
            f"Expected an audio MIME type such as {', '.join(sorted(_accepted_mimes_for_extension(ext)))}, "
            f"got {mime}."
        )

    return canonical


def get_mime_type(path: str) -> str:
    ext = Path(path).suffix.lower()
    return EXTENSION_MIME.get(ext) or mimetypes.guess_type(path)[0] or "application/octet-stream"


def get_audio_duration_seconds(path: str) -> float | None:
    file_path = Path(path)
    if not file_path.exists():
        return None

    ext = file_path.suffix.lower()
    if ext == ".wav":
        try:
            with contextlib.closing(wave.open(str(file_path), "rb")) as wf:
                rate = wf.getframerate()
                if rate:
                    return wf.getnframes() / float(rate)
        except wave.Error:
            return None

    try:
        from mutagen import File as MutagenFile

        audio = MutagenFile(str(file_path))
        if audio is not None and audio.info is not None and hasattr(audio.info, "length"):
            length = float(audio.info.length)
            if length > 0:
                return length
    except Exception:
        return None

    return None


def validate_audio_file(
    path: str,
    size_bytes: int | None = None,
    *,
    content_type: str | None = None,
) -> dict:
    settings = get_settings()
    file_path = Path(path)

    if not file_path.exists():
        raise AudioValidationError(f"Audio file not found: {path}")

    ext = file_path.suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise AudioValidationError(
            f"Unsupported format '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    mime_type = _validate_extension_mime(ext, content_type=content_type, path=path)

    actual_size = size_bytes if size_bytes is not None else file_path.stat().st_size
    if actual_size <= 0:
        raise AudioValidationError("Audio file is empty")
    if actual_size > settings.max_upload_bytes:
        raise AudioValidationError(
            f"File size {actual_size / (1024 * 1024):.1f}MB exceeds "
            f"limit of {settings.max_upload_size_mb}MB"
        )

    if ext == ".m4a":
        header = _read_file_header(file_path)
        if header and not _has_mp4_container_signature(header):
            raise AudioValidationError(
                "Invalid M4A file: file does not appear to be a valid MP4/M4A audio container"
            )

    metadata = {
        "filename": file_path.name,
        "extension": ext,
        "size_bytes": actual_size,
        "mime_type": mime_type,
        "sample_rate_hz": None,
        "duration_seconds": None,
    }

    if ext == ".wav":
        metadata.update(_read_wav_metadata(file_path, settings))
    else:
        duration = get_audio_duration_seconds(path)
        if duration is not None:
            metadata["duration_seconds"] = round(duration, 2)
            if duration < 0.5:
                raise AudioValidationError("Audio must be at least 0.5 seconds long")
        elif actual_size < 256 and ext != ".m4a":
            raise AudioValidationError("Audio file appears corrupted or too small")
        elif ext == ".m4a" and actual_size < 256:
            raise AudioValidationError("M4A file appears corrupted or too small")

    if ext == ".m4a":
        logger.info(
            "M4A audio validated filename=%s mime_type=%s size_bytes=%s duration_seconds=%s",
            metadata["filename"],
            metadata["mime_type"],
            metadata["size_bytes"],
            metadata["duration_seconds"],
        )

    return metadata


def _read_wav_metadata(file_path: Path, settings) -> dict:
    try:
        with contextlib.closing(wave.open(str(file_path), "rb")) as wf:
            sample_rate = wf.getframerate()
            frames = wf.getnframes()
            channels = wf.getnchannels()
    except wave.Error as e:
        raise AudioValidationError(f"Invalid WAV file: {e}") from e

    if sample_rate < settings.min_sample_rate_hz:
        raise AudioValidationError(
            f"Sample rate {sample_rate}Hz is below minimum {settings.min_sample_rate_hz}Hz"
        )
    if sample_rate > settings.max_sample_rate_hz:
        raise AudioValidationError(
            f"Sample rate {sample_rate}Hz exceeds maximum {settings.max_sample_rate_hz}Hz"
        )

    duration = frames / float(sample_rate) if sample_rate else 0
    if duration < 0.5:
        raise AudioValidationError("Audio must be at least 0.5 seconds long")

    return {
        "sample_rate_hz": sample_rate,
        "channels": channels,
        "duration_seconds": round(duration, 2),
    }
