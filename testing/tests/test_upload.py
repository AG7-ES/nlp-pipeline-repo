# tests/test_upload.py
import pytest

@pytest.mark.asyncio
async def test_upload_txt_file(client, reset_db):
    files = {
        "file": ("hello.txt", b"Hello world!", "text/plain")
    }
    r = await client.post("/upload", files=files)
    assert r.status_code == 201
    data = r.json()
    assert "id" in data
    assert data["filename"].endswith(".txt")


@pytest.mark.asyncio
async def test_upload_rejects_non_utf8(client, reset_db):
    files = {
        "file": ("bad.txt", b"\xff\xff\xff", "text/plain")
    }
    r = await client.post("/upload", files=files)
    assert r.status_code == 400
