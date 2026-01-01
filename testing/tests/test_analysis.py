# tests/test_analysis.py
import pytest

@pytest.mark.asyncio
async def test_transient_analysis(client, sample_file_id):
    r = await client.get(f"/analyze/{sample_file_id}", timeout=20.0)
    assert r.status_code == 200
    data = r.json()
    assert "tokens" in data
    assert len(data["tokens"]) > 0


@pytest.mark.asyncio
async def test_persistent_analysis(client, sample_file_id):
    r = await client.post(f"/analyze-and-store/{sample_file_id}", timeout=20.0)
    assert r.status_code == 200

    # Retrieve
    r2 = await client.get(f"/analysis/{sample_file_id}")
    assert r2.status_code == 200
    data = r2.json()
    assert "tokens" in data
    assert isinstance(data["tokens"], list)


@pytest.mark.asyncio
async def test_download_analysis(client, sample_file_id):
    await client.post(f"/analyze-and-store/{sample_file_id}", timeout=20.0)

    r = await client.get(f"/download-analysis/{sample_file_id}.json")
    assert r.status_code == 200
    assert "application/json" in r.headers["content-type"]
