# tests/test_shutdown.py
import pytest

@pytest.mark.asyncio
async def test_service_alive_before_shutdown(client):
    r = await client.get("/")
    assert r.status_code == 200
