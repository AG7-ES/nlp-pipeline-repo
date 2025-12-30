"""
# =====================================
# About the "db_loader.py" script
# =====================================

***Author***

- Nicolas DAVID <nldlee@hotmail.com>

***Description***

`Database Initialization and Corpus Loader for the NLPipeline API`

This module is responsible for one-time database initialization and
bootstrap loading of text documents into PostgreSQL.

Responsibilities:
- Create required database schema (documents, analyses)
- Load UTF-8 `.txt` files from a mounted directory into the database
- Ensure idempotent execution under concurrent startup scenarios
- Safely align auto-increment sequences after manual inserts

Concurrency & deployment guarantees:
- Uses PostgreSQL advisory locks to ensure only one process performs
  schema creation and initial data loading
- Designed for multi-replica Docker / Kubernetes deployments
- Intended to be triggered during FastAPI startup

This module does NOT expose HTTP endpoints and is not intended to be
used directly by request handlers.
"""

import os
import logging
import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Directory containing initial .txt documents (typically Docker-mounted)
TEXT_DIR = Path("/app/texts")

# Fixed advisory lock key to serialize DB initialization across replicas
DB_INIT_ADVISORY_LOCK_KEY = 1234567890

# Shared async SQLAlchemy engine injected at runtime
_engine: AsyncEngine | None = None


def set_engine(engine: AsyncEngine):
    """
    Inject the shared async SQLAlchemy engine.

    This function must be called exactly once during application startup
    before invoking any database initialization routines.

    The engine is intentionally stored as a module-level singleton to
    avoid circular imports and ensure consistent connection pooling.
    """
    global _engine
    _engine = engine


async def _set_documents_sequence(conn):
    """
    Align the documents.id sequence with the current maximum ID.

    This is required because documents may be inserted with explicit IDs
    or via upserts, which can desynchronize PostgreSQL sequences and
    cause primary key collisions on subsequent inserts.
    """
    res = await conn.execute(text("SELECT COALESCE(MAX(id), 0) FROM documents;"))
    
    max_id_row = res.fetchone()
    
    max_id = max_id_row[0] if max_id_row and max_id_row[0] is not None else 0
    
    await conn.execute(
        text("SELECT setval(pg_get_serial_sequence('documents', 'id'), :val, true);"),
        {"val": max_id}
    )


async def load_txt_files_to_db():
    """
    Initialize database schema and load text corpus into PostgreSQL.

    Execution model:
    - Acquires a PostgreSQL advisory lock (non-blocking)
    - If lock is unavailable, exits immediately (another worker won)
    - Creates required tables and indexes if missing
    - Loads UTF-8 `.txt` files from TEXT_DIR using filename-based upserts
    - Realigns auto-increment sequences for consistency

    This function is safe to call concurrently from multiple processes
    and is designed to run during application startup.
    """
    if _engine is None:
        raise RuntimeError("DB engine not set. Call set_engine(engine) before load_txt_files_to_db().")

    async with _engine.begin() as conn:
        # Attempt to acquire advisory lock to serialize initialization
        res = await conn.execute(text("SELECT pg_try_advisory_lock(:k);"), {"k": DB_INIT_ADVISORY_LOCK_KEY})
        
        locked_row = res.fetchone()
        
        locked = bool(locked_row[0]) if locked_row and locked_row[0] is not None else False

        if not locked:
            logger.info("✅ Another worker already initialized the DB, skipping.")
            return

        # Create primary documents table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                filename TEXT UNIQUE,
                content TEXT
            );
        """))

        # Create analyses table with cascade semantics
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

        # Index for fast document (analysis lookup)
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_analyses_document_id
            ON analyses(document_id);
        """))

        # Load text corpus from mounted directory
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

                # Idempotent upsert by filename
                await conn.execute(
                    text("""
                        INSERT INTO documents (filename, content)
                        VALUES (:fn, :content)
                        ON CONFLICT (filename) DO UPDATE
                        SET content = EXCLUDED.content;
                    """),
                    {"fn": file.name, "content": content}
                )

        # Ensure sequence consistency after bulk inserts
        await _set_documents_sequence(conn)

    logger.info("✅ Database initialized and TXT files loaded successfully.")


if __name__ == "__main__":
    """
    Optional execution entrypoint.

    This is primarily intended for local debugging or manual invocation.
    In production, this module is executed via FastAPI startup hooks.
    """
    load_txt_files_to_db()
