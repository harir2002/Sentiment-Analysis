import wave
from pathlib import Path

import pytest


@pytest.fixture
def sample_wav(tmp_path: Path) -> Path:
    """Minimal valid WAV (1s, 16 kHz mono) for validation tests."""
    path = tmp_path / "sample.wav"
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 16000)
    return path
