# tests/test_files.py
import pytest

@pytest.mark.asyncio
async def test_list_files_empty(client, reset_db):
    r = await client.get("/files")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_upload_and_retrieve(client, reset_db):
    files = { "file": ("x.txt", b"ABC", "text/plain") }
    r = await client.post("/upload", files=files)
    file_id = r.json()["id"]

    # Get file info
    r2 = await client.get(f"/files/{file_id}")
    assert r2.status_code == 200
    assert r2.json()["content"] == "ABC"


@pytest.mark.asyncio
async def test_download_raw_text(client, sample_file_id):
    r = await client.get(f"/download/{sample_file_id}.txt")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]


@pytest.mark.asyncio
async def test_delete_file(client, sample_file_id):
    r = await client.delete(f"/files/{sample_file_id}")
    assert r.status_code == 200

    # Ensure gone
    r2 = await client.get(f"/files/{sample_file_id}")
    assert r2.status_code == 404
