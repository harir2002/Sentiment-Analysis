from pathlib import Path

import pytest

from app.core.exceptions import AudioValidationError
from app.services.audio_validation import get_mime_type, validate_audio_file


def test_get_mime_type_wav():
    assert get_mime_type("recording.wav") == "audio/wav"


def test_get_mime_type_mpeg():
    assert get_mime_type("recording.mpeg") == "audio/mpeg"


def test_get_mime_type_m4a():
    assert get_mime_type("Hinglish-Audio.m4a") == "audio/mp4"


def _minimal_m4a_bytes() -> bytes:
    # Minimal ISO BMFF header: size + 'ftyp' + brand 'M4A ' + padding
    return b"\x00\x00\x00\x20ftypM4A \x00\x00\x00\x00" + b"\x00" * 300


def test_validate_m4a_accepts_audio_mp4_mime(tmp_path: Path):
    m4a_file = tmp_path / "Hinglish-Audio.m4a"
    m4a_file.write_bytes(_minimal_m4a_bytes())
    meta = validate_audio_file(str(m4a_file), content_type="audio/mp4")
    assert meta["extension"] == ".m4a"
    assert meta["mime_type"] == "audio/mp4"


def test_validate_m4a_accepts_audio_x_m4a_mime(tmp_path: Path):
    m4a_file = tmp_path / "Hinglish-Audio.m4a"
    m4a_file.write_bytes(_minimal_m4a_bytes())
    meta = validate_audio_file(str(m4a_file), content_type="audio/x-m4a")
    assert meta["extension"] == ".m4a"
    assert meta["mime_type"] == "audio/mp4"


def test_validate_m4a_rejects_invalid_signature(tmp_path: Path):
    m4a_file = tmp_path / "bad.m4a"
    m4a_file.write_bytes(b"not an m4a file" + b"\x00" * 300)
    with pytest.raises(AudioValidationError, match="Invalid M4A file"):
        validate_audio_file(str(m4a_file), content_type="audio/x-m4a")


def test_validate_m4a_accepts_octet_stream_when_signature_valid(tmp_path: Path):
    m4a_file = tmp_path / "clip.m4a"
    m4a_file.write_bytes(_minimal_m4a_bytes())
    meta = validate_audio_file(str(m4a_file), content_type="application/octet-stream")
    assert meta["extension"] == ".m4a"


def test_validate_mpeg_accepts_audio_mime(tmp_path: Path):
    mpeg_file = tmp_path / "clip.mpeg"
    mpeg_file.write_bytes(b"fake mpeg audio content" + b"\x00" * 300)
    meta = validate_audio_file(
        str(mpeg_file),
        content_type="audio/mpeg",
    )
    assert meta["extension"] == ".mpeg"
    assert meta["mime_type"] == "audio/mpeg"


def test_validate_mpeg_rejects_video_mime(tmp_path: Path):
    mpeg_file = tmp_path / "clip.mpeg"
    mpeg_file.write_bytes(b"fake mpeg video content" + b"\x00" * 300)
    with pytest.raises(AudioValidationError, match="Expected an audio MIME type"):
        validate_audio_file(
            str(mpeg_file),
            content_type="video/mpeg",
        )


def test_validate_audio_file_success(sample_wav: Path):
    meta = validate_audio_file(str(sample_wav))
    assert meta["extension"] == ".wav"
    assert meta["sample_rate_hz"] == 16000
    assert meta["duration_seconds"] == 1.0
    assert meta["mime_type"] == "audio/wav"


def test_validate_audio_file_missing():
    with pytest.raises(AudioValidationError, match="not found"):
        validate_audio_file("/nonexistent/audio.wav")


def test_validate_audio_file_bad_extension(tmp_path: Path):
    bad = tmp_path / "audio.txt"
    bad.write_text("not audio")
    with pytest.raises(AudioValidationError, match="Unsupported format"):
        validate_audio_file(str(bad))
