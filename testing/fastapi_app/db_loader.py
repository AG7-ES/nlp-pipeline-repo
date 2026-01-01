# db_loader.py
"""
Async DB loader and initializer using SQLAlchemy async engine (asyncpg).
- Creates tables if missing.
- Loads .txt files from TEXT_DIR into documents (upserts by filename).
- Aligns documents.id sequence.
- Uses pg_try_advisory_lock to ensure only one process initializes DB.
"""

import os
import logging
import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

TEXT_DIR = Path("/app/texts")
DB_INIT_ADVISORY_LOCK_KEY = 1234567890

_engine: AsyncEngine | None = None

def set_engine(engine: AsyncEngine):
    """Called by main to provide the shared async engine."""
    global _engine
    _engine = engine

async def _set_documents_sequence(conn):
    res = await conn.execute(text("SELECT COALESCE(MAX(id), 0) FROM documents;"))
    max_id_row = res.fetchone()
    max_id = max_id_row[0] if max_id_row and max_id_row[0] is not None else 0
    await conn.execute(
        text("SELECT setval(pg_get_serial_sequence('documents', 'id'), :val, true);"),
        {"val": max_id}
    )

async def load_txt_files_to_db():
    if _engine is None:
        raise RuntimeError("DB engine not set. Call set_engine(engine) before load_txt_files_to_db().")

    async with _engine.begin() as conn:
        # Try to acquire advisory lock (non-blocking)
        res = await conn.execute(text("SELECT pg_try_advisory_lock(:k);"), {"k": DB_INIT_ADVISORY_LOCK_KEY})
        locked_row = res.fetchone()
        locked = bool(locked_row[0]) if locked_row and locked_row[0] is not None else False

        if not locked:
            logger.info("✅ Another worker already initialized the DB, skipping.")
            return

        # Create documents table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                filename TEXT UNIQUE,
                content TEXT
            );
        """))

        # Create analyses table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS analyses (
                id SERIAL PRIMARY KEY,
                document_id INTEGER UNIQUE REFERENCES documents(id) ON DELETE CASCADE,
                tokens JSONB,
                lemmas JSONB,
                morphs JSONB,
                dependencies JSONB,
                entities JSONB,
                word_vectors JSONB
            );
        """))

        # Index
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_analyses_document_id
            ON analyses(document_id);
        """))

        # Load .txt files
        if not TEXT_DIR.exists() or not TEXT_DIR.is_dir():
            logger.warning("Text directory %s does not exist or is not a directory.", TEXT_DIR)
        else:
            for file in sorted(TEXT_DIR.glob("*.txt")):
                try:
                    with file.open("r", encoding="utf-8") as fh:
                        content = fh.read()
                except UnicodeDecodeError:
                    logger.warning("Skipping non-UTF-8 file: %s", file)
                    continue

                # upsert by filename
                await conn.execute(
                    text("""
                        INSERT INTO documents (filename, content)
                        VALUES (:fn, :content)
                        ON CONFLICT (filename) DO UPDATE
                        SET content = EXCLUDED.content;
                    """),
                    {"fn": file.name, "content": content}
                )

        # Align sequence
        await _set_documents_sequence(conn)

    logger.info("✅ Database initialized and TXT files loaded successfully.")

if __name__ == "__main__":
    load_txt_files_to_db()
