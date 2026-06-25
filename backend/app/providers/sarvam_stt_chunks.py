"""Chunk long WAV files into REST-sized segments for Sarvam real-time STT."""
from __future__ import annotations

import logging
import tempfile
import wave
from pathlib import Path

logger = logging.getLogger(__name__)


def can_chunk_audio(audio_path: str) -> bool:
    return Path(audio_path).suffix.lower() == ".wav"


def split_wav_chunks(audio_path: str, chunk_seconds: float) -> list[str]:
    """Split a WAV into temporary chunk files. Caller must delete temps."""
    paths: list[str] = []
    with wave.open(audio_path, "rb") as wf:
        channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        rate = wf.getframerate()
        frames_per_chunk = int(rate * chunk_seconds)
        total_frames = wf.getnframes()

        index = 0
        while index * frames_per_chunk < total_frames:
            wf.setpos(index * frames_per_chunk)
            frames = wf.readframes(frames_per_chunk)
            if not frames:
                break

            tmp = tempfile.NamedTemporaryFile(
                suffix=f"_chunk_{index}.wav", delete=False, prefix="sarvam_stt_"
            )
            tmp_path = tmp.name
            tmp.close()

            with wave.open(tmp_path, "wb") as out:
                out.setnchannels(channels)
                out.setsampwidth(sample_width)
                out.setframerate(rate)
                out.writeframes(frames)

            paths.append(tmp_path)
            index += 1

    return paths


def cleanup_chunk_files(paths: list[str]) -> None:
    for path in paths:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not delete temp chunk %s", path)
