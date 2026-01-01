# tests/conftest.py
import asyncio
import httpx
import pytest
import pytest_asyncio
import asyncpg
import os
import time

TEST_API_URL = "http://nlp_test_fastapi:8001"

TEST_DB_HOST = os.getenv("DB_HOST", "test_db")
TEST_DB_NAME = os.getenv("DB_NAME", "test_db")
TEST_DB_USER = os.getenv("DB_USER", "test_user")
TEST_DB_PASS = os.getenv("DB_PASSWORD", "test_pass")


# ---------------------------
# Wait until FastAPI test service is up
# ---------------------------
@pytest.fixture(scope="session", autouse=True)
def wait_for_api():
    print("Waiting for FastAPI…")
    for _ in range(40):
        try:
            r = httpx.get(f"{TEST_API_URL}/", timeout=2)
            if r.status_code == 200:
                print("FastAPI is ready.")
                return
        except Exception:
            pass
        time.sleep(1)

    raise RuntimeError("FastAPI did not start.")


# ---------------------------
# Async HTTP client
# ---------------------------
@pytest_asyncio.fixture
async def client():
    async with httpx.AsyncClient(
        base_url=TEST_API_URL,
        timeout=30.0  # <-- increased global timeout
    ) as c:
        yield c



# ---------------------------
# Reset DB
# ---------------------------
@pytest_asyncio.fixture
async def reset_db():
    conn = await asyncpg.connect(
        user=TEST_DB_USER,
        password=TEST_DB_PASS,
        host=TEST_DB_HOST,
        database=TEST_DB_NAME,
    )

    await conn.execute("TRUNCATE analyses RESTART IDENTITY CASCADE;")
    await conn.execute("TRUNCATE documents RESTART IDENTITY CASCADE;")

    await conn.close()


# ---------------------------
# Upload a sample file
# ---------------------------
@pytest_asyncio.fixture
async def sample_file_id(client, reset_db):
    files = {
        "file": ("sample.txt", b"Hello world. This is a test.", "text/plain")
    }
    r = await client.post("/upload", files=files)
    assert r.status_code == 201
    return r.json()["id"]
