# main.py
"""
Async FastAPI application for the NLP pipeline using SQLAlchemy async engine (asyncpg).
- Uses a connection pool.
- Async endpoints.
- spaCy model loaded once per process (threadsafe via threading.Lock).
- CPU-bound spaCy work executed in threadpool (asyncio.to_thread).
"""

import os
import json
import logging
import threading
import asyncio
from io import BytesIO
from pathlib import Path
from typing import Optional

import spacy
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy import text

#from fastapi_app import db_loader

import db_loader  # async db loader module

logger = logging.getLogger("nlp_pipeline")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="NLP Pipeline API", version="3.0")

# ---------------------------
# spaCy model: single load
# ---------------------------
nlp_model = None
nlp_lock = threading.Lock()


def get_nlp():
    """
    Ensure spaCy model is loaded once per process.
    Thread lock is fine here because loading is CPU-bound and synchronous.
    """
    global nlp_model
    with nlp_lock:
        if nlp_model is None:
            logger.info("Loading spaCy model en_core_web_lg ...")
            nlp_model = spacy.load("en_core_web_lg")
            logger.info("spaCy model loaded.")
    return nlp_model


def run_nlp_analysis_sync(text: str):
    """Synchronous spaCy analysis (keeps shape similar to original)."""
    nlp = get_nlp()
    doc = nlp(text)

    word_vectors = []
    for token in doc:
        word_vectors.append({
            "token": token.text,
            "has_vector": bool(token.has_vector),
            "vector_norm": float(token.vector_norm) if token.has_vector else None,
            "is_oov": bool(token.is_oov),
        })

    return {
        "tokens": [token.text for token in doc],
        "lemmas": [(token.text, token.lemma_) for token in doc],
        "morphs": [(token.text, token.morph.to_dict()) for token in doc],
        "dependencies": [(token.text, token.dep_, token.head.text) for token in doc],
        "entities": [(ent.text, ent.label_) for ent in doc.ents],
        "word_vectors": word_vectors,
    }


async def run_nlp_analysis(text: str):
    """
    Run blocking spaCy analysis in a threadpool so the async event loop isn't blocked.
    """
    return await asyncio.to_thread(run_nlp_analysis_sync, text)


# ---------------------------
# DB (SQLAlchemy async engine)
# ---------------------------
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")

if not all([DB_USER, DB_PASSWORD, DB_HOST, DB_NAME]):
    logger.warning("One or more DB env variables are missing (DB_USER/DB_PASSWORD/DB_HOST/DB_NAME).")

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"

# tune pool size to your expected concurrency
engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
)

# Make engine available to db_loader
db_loader.set_engine(engine)


# ---------------------------
# Startup: wait for DB and initialize
# ---------------------------

async def wait_for_db_ready():
    """
    Try connecting until DB is ready. This is async (non-blocking).
    """
    # use engine.connect within try/except
    while True:
        try:
            async with engine.connect() as conn:
                # a lightweight check
                await conn.execute(text("SELECT 1"))
                return
        except Exception:
            logger.info("⏳ Waiting for database (async)...")
            await asyncio.sleep(1)


@app.on_event("startup")
async def startup_event():
    """
    - Wait for DB
    - Run db_loader.load_txt_files_to_db() (async). The db_loader uses pg_try_advisory_lock
      so only one process will initialize the DB.
    """
    await wait_for_db_ready()

    try:
        # initialize schema and load .txt files (db_loader is async)
        await db_loader.load_txt_files_to_db()
    except Exception:
        logger.exception("DB initialization failed on startup. Endpoints may fail if DB not ready.")


# ---------------------------
# Utility helpers (async)
# ---------------------------

async def fetch_all_files():
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT id, filename FROM documents ORDER BY id;"))
        rows = result.fetchall()
    return [{"id": r[0], "filename": r[1]} for r in rows]


async def fetch_document(doc_id: int):
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT id, filename, content FROM documents WHERE id = :id;"), {"id": doc_id})
        row = result.fetchone()
    return row


# ---------------------------
# Endpoints (async)
# ---------------------------

@app.get("/", response_class=JSONResponse)
async def index():
    return {
        "service": "NLP Pipeline API",
        "version": app.version,
        "endpoints": {
            "GET /files": "List documents (id, filename)",
            "GET /files/{doc_id}": "View document content (JSON)",
            "POST /upload": "Upload a UTF-8 .txt file (form field 'file', optional 'filename')",
            "DELETE /files/{doc_id}": "Delete document (and its analysis via cascade)",
            "GET /download/{doc_id}.txt": "Download raw .txt file for document",
            "GET /analyze/{doc_id}": "Run transient analysis and return results (not stored)",
            "POST /analyze-and-store/{doc_id}": "Run analysis and store results in DB",
            "GET /analysis/{doc_id}": "Retrieve stored analysis (JSON)",
            "GET /download-analysis/{doc_id}.json": "Download stored analysis as .json file",
            "DELETE /analysis/{doc_id}": "Delete stored analysis for document",
        }
    }


@app.get("/files", response_class=JSONResponse)
async def list_txt_files():
    try:
        return await fetch_all_files()
    except Exception:
        logger.exception("DB error while listing files.")
        raise HTTPException(status_code=500, detail="Database error while listing files.")


@app.get("/files/{doc_id}")
async def view_text(doc_id: int):
    try:
        row = await fetch_document(doc_id)
    except Exception:
        logger.exception("DB error while fetching document id %s", doc_id)
        raise HTTPException(status_code=500, detail="Database error while fetching document.")

    if not row:
        raise HTTPException(status_code=404, detail="Document not found.")

    return {"id": row[0], "filename": row[1], "content": row[2]}


@app.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_text(file: UploadFile = File(...), filename: Optional[str] = Form(None)):
    orig_name = file.filename or "upload.txt"

    if filename:
        if not filename.lower().endswith(".txt"):
            raise HTTPException(status_code=400, detail="Provided filename must end with .txt")
        safe_filename = filename
    else:
        safe_filename = orig_name if orig_name.lower().endswith(".txt") else orig_name + ".txt"

    try:
        content_bytes = await file.read()
        content_str = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Uploaded file must be UTF-8 encoded .txt")
    except Exception:
        logger.exception("Error reading uploaded file.")
        raise HTTPException(status_code=500, detail="Failed to read uploaded file.")

    # Perform transactional insert with explicit id assignment and sequence alignment.
    async with engine.begin() as conn:
        # get next logical id
        result = await conn.execute(text("SELECT COALESCE(MAX(id), 0) FROM documents;"))
        max_id_row = result.fetchone()
        next_id = (max_id_row[0] if max_id_row and max_id_row[0] is not None else 0) + 1

        base_name = safe_filename.rsplit("/", 1)[-1]
        candidate = base_name
        suffix = 0
        # check collisions
        while True:
            res = await conn.execute(text("SELECT 1 FROM documents WHERE filename = :fn;"), {"fn": candidate})
            if not res.fetchone():
                break
            suffix += 1
            candidate = f"{Path(base_name).stem}_{suffix}.txt"

        stored_filename = candidate

        # insert explicit id
        await conn.execute(
            text("""
                INSERT INTO documents (id, filename, content)
                VALUES (:id, :filename, :content)
            """),
            {"id": next_id, "filename": stored_filename, "content": content_str}
        )
        # align sequence
        await conn.execute(
            text("SELECT setval(pg_get_serial_sequence('documents','id'), :val, true);"),
            {"val": next_id}
        )

    return {"id": next_id, "filename": stored_filename}


@app.delete("/files/{doc_id}")
async def delete_text(doc_id: int):
    async with engine.begin() as conn:
        res = await conn.execute(text("SELECT filename FROM documents WHERE id = :id;"), {"id": doc_id})
        row = res.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Document not found.")
        filename = row[0]
        await conn.execute(text("DELETE FROM documents WHERE id = :id;"), {"id": doc_id})
    return {"message": f"Document {doc_id} ({filename}) deleted (analysis removed via cascade if present)."}


@app.get("/download/{doc_id}.txt")
async def download_text(doc_id: int):
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT filename, content FROM documents WHERE id = :id;"), {"id": doc_id})
        row = res.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Document not found.")

    filename, content = row[0], row[1]
    buffer = BytesIO(content.encode("utf-8"))

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": "text/plain; charset=utf-8",
    }
    return StreamingResponse(buffer, headers=headers)


@app.get("/analyze/{doc_id}")
async def analyze_file(doc_id: int):
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT content FROM documents WHERE id = :id;"), {"id": doc_id})
        row = res.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Document not found.")

    analysis = await run_nlp_analysis(row[0])
    return analysis

@app.post("/analyze-and-store/{doc_id}")
async def analyze_and_store(doc_id: int):
    # fetch content
    async with engine.connect() as conn:
        res = await conn.execute(
            text("SELECT content FROM documents WHERE id = :id;"),
            {"id": doc_id}
        )
        row = res.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found.")

    analysis = await run_nlp_analysis(row[0])

    # store analysis
    async with engine.begin() as conn:
        await conn.execute(
            text("""
            INSERT INTO analyses (
                document_id, tokens, lemmas, morphs, dependencies, entities, word_vectors
            )
            VALUES (
                :document_id,
                CAST(:tokens AS jsonb),
                CAST(:lemmas AS jsonb),
                CAST(:morphs AS jsonb),
                CAST(:dependencies AS jsonb),
                CAST(:entities AS jsonb),
                CAST(:word_vectors AS jsonb)
            )
            ON CONFLICT (document_id) DO UPDATE
            SET tokens = EXCLUDED.tokens,
                lemmas = EXCLUDED.lemmas,
                morphs = EXCLUDED.morphs,
                dependencies = EXCLUDED.dependencies,
                entities = EXCLUDED.entities,
                word_vectors = EXCLUDED.word_vectors;
            """),
            {
                "document_id": doc_id,
                "tokens": json.dumps(analysis["tokens"], ensure_ascii=False),
                "lemmas": json.dumps(analysis["lemmas"], ensure_ascii=False),
                "morphs": json.dumps(analysis["morphs"], ensure_ascii=False),
                "dependencies": json.dumps(analysis["dependencies"], ensure_ascii=False),
                "entities": json.dumps(analysis["entities"], ensure_ascii=False),
                "word_vectors": json.dumps(analysis["word_vectors"], ensure_ascii=False),
            }
        )

    return {"message": "Full NLP analysis (with simplified vectors) stored successfully"}

@app.get("/analysis/{doc_id}")
async def get_analysis(doc_id: int):
    async with engine.connect() as conn:
        res = await conn.execute(text("""
            SELECT tokens, lemmas, morphs, dependencies, entities, word_vectors
            FROM analyses
            WHERE document_id = :id;
        """), {"id": doc_id})
        row = res.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Analysis not found for this document.")

    # row values are JSON strings (because we inserted as jsonb). AsyncPG should return them decoded,
    # but to be robust, ensure they are Python objects.
    def _maybe_load(val):
        if val is None:
            return None
        if isinstance(val, (dict, list)):
            return val
        try:
            return json.loads(val)
        except Exception:
            return val

    return {
        "tokens": _maybe_load(row[0]),
        "lemmas": _maybe_load(row[1]),
        "morphs": _maybe_load(row[2]),
        "dependencies": _maybe_load(row[3]),
        "entities": _maybe_load(row[4]),
        "word_vectors": _maybe_load(row[5]),
    }


@app.get("/download-analysis/{doc_id}.json")
async def download_analysis(doc_id: int):
    async with engine.connect() as conn:
        res = await conn.execute(text("""
            SELECT tokens, lemmas, morphs, dependencies, entities, word_vectors
            FROM analyses
            WHERE document_id = :id;
        """), {"id": doc_id})
        row = res.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Analysis not found for this document.")

    def _maybe_load(val):
        if val is None:
            return None
        if isinstance(val, (dict, list)):
            return val
        try:
            return json.loads(val)
        except Exception:
            return val

    analysis_obj = {
        "document_id": doc_id,
        "tokens": _maybe_load(row[0]),
        "lemmas": _maybe_load(row[1]),
        "morphs": _maybe_load(row[2]),
        "dependencies": _maybe_load(row[3]),
        "entities": _maybe_load(row[4]),
        "word_vectors": _maybe_load(row[5]),
    }

    data_bytes = json.dumps(analysis_obj, ensure_ascii=False, indent=2).encode("utf-8")
    buffer = BytesIO(data_bytes)
    headers = {
        "Content-Disposition": f'attachment; filename="analysis_{doc_id}.json"',
        "Content-Type": "application/json; charset=utf-8",
    }
    return StreamingResponse(buffer, headers=headers)


@app.delete("/analysis/{doc_id}")
async def delete_analysis(doc_id: int):
    async with engine.begin() as conn:
        res = await conn.execute(text("SELECT 1 FROM analyses WHERE document_id = :id;"), {"id": doc_id})
        if not res.fetchone():
            raise HTTPException(status_code=404, detail="Analysis not found for this document")
        await conn.execute(text("DELETE FROM analyses WHERE document_id = :id;"), {"id": doc_id})
    return {"message": f"Analysis for document {doc_id} deleted successfully."}

@app.on_event("shutdown")
async def shutdown_event():
    """
    Triggered on SIGTERM / SIGINT (e.g., when Docker stops the container).
    Cleans up DB connections and optionally NLP resources.
    """
    logger.info("Shutting down FastAPI gracefully...")

    # Dispose async SQLAlchemy engine (closes all connections in pool)
    if 'engine' in globals() and engine is not None:
        await engine.dispose()
        logger.info("Async DB engine disposed.")

    # Clear spaCy model from memory
    global nlp_model
    if nlp_model is not None:
        del nlp_model
        nlp_model = None
        logger.info("spaCy model cleared from memory.")

    logger.info("Shutdown cleanup complete.")
