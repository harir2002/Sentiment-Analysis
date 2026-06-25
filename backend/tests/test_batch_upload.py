import io
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import UploadFile

from app.core.exceptions import AudioValidationError
from app.services.storage import save_uploads


def _upload_file(name: str, content: bytes = b"audio") -> UploadFile:
    return UploadFile(filename=name, file=io.BytesIO(content))


@pytest.mark.asyncio
async def test_save_uploads_processes_each_file_independently():
    files = [_upload_file("a.wav"), _upload_file("b.wav"), _upload_file("bad.txt")]

    async def fake_save(file):
        if file.filename == "bad.txt":
            raise AudioValidationError("Unsupported file type")
        return f"id-{file.filename}", file.filename, f"/tmp/{file.filename}", {"duration_seconds": 1.0}

    with patch("app.services.storage.save_upload", side_effect=fake_save):
        uploaded, failed = await save_uploads(files)

    assert len(uploaded) == 2
    assert len(failed) == 1
    assert uploaded[0]["success"] is True
    assert failed[0]["filename"] == "bad.txt"
    assert "Unsupported" in failed[0]["error"]
