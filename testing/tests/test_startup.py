# tests/test_startup.py
import httpx
import pytest

@pytest.mark.asyncio
async def test_index_available(client):
    r = await client.get("/")
    assert r.status_code == 200
    assert "service" in r.json()
    assert r.json()["service"] == "NLP Pipeline API"


@pytest.mark.asyncio
async def test_tables_exist(client):
    # indirectly check table existence via /files
    r = await client.get("/files")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
