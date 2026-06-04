"""
storage.py
Handles all PostgreSQL database operations for the Attributed Knowledge Store (AKS).
Falls back to SQLite when PostgreSQL is unavailable (e.g. on Render without a
local DB, or when DATABASE_URL / DB_HOST are not configured).
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

from schema import ClassifiedChunk, SignalLabel

from dotenv import load_dotenv

# Load .env from the same directory as this script
_HERE = Path(__file__).parent
load_dotenv(_HERE / ".env")

# ---------------------------------------------------------------------------
# Database connection configuration
# ---------------------------------------------------------------------------
# Render (and many PaaS providers) expose a single DATABASE_URL env var.
# Support it first, then fall back to individual DB_* vars, then localhost.
_DATABASE_URL = os.getenv("DATABASE_URL")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "hackfest_aks")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "postgres")

# Path for the SQLite fallback database (next to this file)
_SQLITE_PATH = os.path.join(_HERE, "aks_storage.db")


def get_connection():
    """Returns (conn, db_type) where db_type is 'postgres' or 'sqlite'."""
    # Try DATABASE_URL first (Render-style postgres:// URL)
    if _DATABASE_URL:
        try:
            conn = psycopg2.connect(_DATABASE_URL, connect_timeout=3)
            return conn, "postgres"
        except Exception:
            pass  # fall through to individual vars / SQLite

    # Try individual DB_* env vars
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
            connect_timeout=3,
        )
        return conn, "postgres"
    except Exception:
        pass  # fall through to SQLite

    # Fallback to SQLite
    conn = sqlite3.connect(_SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn, "sqlite"


def _adapt_query(query: str, db_type: str) -> str:
    """Translate PostgreSQL placeholders / syntax for SQLite if needed."""
    if db_type == "sqlite":
        query = query.replace("%s", "?")
        # SQLite doesn't support UUID / JSONB types or jsonb_set / execute_values
        query = query.replace("JSONB", "TEXT")
        query = query.replace("UUID", "TEXT")
        query = query.replace("TIMESTAMP WITH TIME ZONE", "TIMESTAMP")
        query = query.replace("ON CONFLICT (chunk_id) DO NOTHING", "")
    return query


def execute_query(conn, db_type, query, params=None, fetch=False):
    """Abstraction to handle parameter naming differences and cursor behavior."""
    query = _adapt_query(query, db_type)

    if db_type == "postgres" and fetch:
        cur = conn.cursor(cursor_factory=RealDictCursor)
    else:
        cur = conn.cursor()

    try:
        cur.execute(query, params or ())
        if fetch:
            if db_type == "sqlite":
                return [dict(row) for row in cur.fetchall()]
            return cur.fetchall()
        if db_type == "postgres":
            conn.commit()
    finally:
        cur.close()
    return None


def init_db():
    """Creates the necessary tables using a compatible schema for both PG and SQLite."""
    conn, db_type = get_connection()
    try:
        json_type = "JSONB" if db_type == "postgres" else "TEXT"
        uuid_type = "UUID" if db_type == "postgres" else "TEXT"

        queries = [
            f"""
                CREATE TABLE IF NOT EXISTS classified_chunks (
                    chunk_id {uuid_type} PRIMARY KEY,
                    session_id VARCHAR(255),
                    source_ref VARCHAR(255),
                    label VARCHAR(50),
                    suppressed BOOLEAN,
                    manually_restored BOOLEAN,
                    flagged_for_review BOOLEAN,
                    created_at TIMESTAMP,
                    data {json_type}
                );
            """,
            "CREATE INDEX IF NOT EXISTS idx_classified_chunks_label ON classified_chunks(label);",
            "CREATE INDEX IF NOT EXISTS idx_classified_chunks_suppressed ON classified_chunks(suppressed);",
            "CREATE INDEX IF NOT EXISTS idx_classified_chunks_session ON classified_chunks(session_id);",
            "CREATE INDEX IF NOT EXISTS idx_classified_chunks_source_ref ON classified_chunks(source_ref);",
            "CREATE INDEX IF NOT EXISTS idx_classified_chunks_flagged ON classified_chunks(flagged_for_review);",
            f"""
                CREATE TABLE IF NOT EXISTS brd_snapshots (
                    snapshot_id {uuid_type} PRIMARY KEY,
                    session_id VARCHAR(255),
                    created_at TIMESTAMP,
                    chunk_ids {json_type}
                );
            """,
            f"""
                CREATE TABLE IF NOT EXISTS brd_sections (
                    section_id {uuid_type} PRIMARY KEY,
                    session_id VARCHAR(255),
                    snapshot_id {uuid_type},
                    section_name VARCHAR(100),
                    version_number INTEGER DEFAULT 1,
                    content TEXT,
                    source_chunk_ids {json_type},
                    is_locked BOOLEAN DEFAULT FALSE,
                    human_edited BOOLEAN DEFAULT FALSE,
                    generated_at TIMESTAMP,
                    data {json_type}
                );
            """,
            f"""
                CREATE TABLE IF NOT EXISTS brd_validation_flags (
                    flag_id {uuid_type} PRIMARY KEY,
                    session_id VARCHAR(255),
                    section_name VARCHAR(100),
                    flag_type VARCHAR(50),
                    description TEXT,
                    severity VARCHAR(20),
                    auto_resolvable BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP
                );
            """,
            "CREATE INDEX IF NOT EXISTS idx_brd_sections_session ON brd_sections(session_id);",
            "CREATE INDEX IF NOT EXISTS idx_brd_snapshots_session ON brd_snapshots(session_id);",
        ]

        for q in queries:
            execute_query(conn, db_type, q)

    finally:
        conn.close()


def store_chunks(chunks: List[ClassifiedChunk]):
    """Batch inserts a list of ClassifiedChunk objects into the database."""
    if not chunks:
        return

    conn, db_type = get_connection()
    try:
        if db_type == "postgres":
            insert_query = """
                INSERT INTO classified_chunks (
                    chunk_id, session_id, source_ref, label, suppressed,
                    manually_restored, flagged_for_review, created_at, data
                ) VALUES %s
                ON CONFLICT (chunk_id) DO NOTHING
            """
            values = []
            for c in chunks:
                data_json = c.model_dump(mode="json")
                values.append((
                    c.chunk_id,
                    c.session_id,
                    c.source_ref,
                    c.label.value,
                    c.suppressed,
                    c.manually_restored,
                    c.flagged_for_review,
                    c.created_at,
                    json.dumps(data_json),
                ))
            with conn.cursor() as cur:
                execute_values(cur, insert_query, values)
            conn.commit()
        else:
            # SQLite — fallback to executemany
            query = """
                INSERT OR IGNORE INTO classified_chunks (
                    chunk_id, session_id, source_ref, label, suppressed,
                    manually_restored, flagged_for_review, created_at, data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            values = []
            for c in chunks:
                data_json = c.model_dump(mode="json")
                values.append((
                    str(c.chunk_id),
                    c.session_id,
                    c.source_ref,
                    c.label.value,
                    c.suppressed,
                    c.manually_restored,
                    c.flagged_for_review,
                    c.created_at.isoformat() if hasattr(c.created_at, 'isoformat') else str(c.created_at),
                    json.dumps(data_json),
                ))
            conn.executemany(query, values)
    finally:
        conn.close()


def get_active_signals(session_id: str = None) -> List[ClassifiedChunk]:
    """Retrieves active signals, optionally filtered by session_id at DB level."""
    conn, db_type = get_connection()
    results = []
    try:
        # Use 0/1 for cross-DB boolean compatibility (SQLite has no TRUE/FALSE keyword)
        if session_id:
            query = "SELECT data FROM classified_chunks WHERE session_id = %s AND (suppressed = 0 OR manually_restored = 1) ORDER BY created_at ASC"
            params = (session_id,)
        else:
            query = "SELECT data FROM classified_chunks WHERE suppressed = 0 OR manually_restored = 1 ORDER BY created_at ASC"
            params = None

        query = _adapt_query(query, db_type)
        rows = execute_query(conn, db_type, query, params=params, fetch=True)
        for row in rows:
            raw = row['data']
            results.append(ClassifiedChunk.model_validate(json.loads(raw) if isinstance(raw, str) else raw))
    finally:
        conn.close()
    return results


def get_noise_items(session_id: str = None) -> List[ClassifiedChunk]:
    """Retrieves noise chunks, optionally filtered by session_id at DB level."""
    conn, db_type = get_connection()
    results = []
    try:
        if session_id:
            query = "SELECT data FROM classified_chunks WHERE session_id = %s AND suppressed = 1 AND manually_restored = 0 ORDER BY created_at ASC"
            params = (session_id,)
        else:
            query = "SELECT data FROM classified_chunks WHERE suppressed = 1 AND manually_restored = 0 ORDER BY created_at ASC"
            params = None

        query = _adapt_query(query, db_type)
        rows = execute_query(conn, db_type, query, params=params, fetch=True)
        for row in rows:
            raw = row['data']
            results.append(ClassifiedChunk.model_validate(json.loads(raw) if isinstance(raw, str) else raw))
    finally:
        conn.close()
    return results


def restore_noise_item(chunk_id: str):
    """
    Manually restores a misclassified noise chunk back to an active signal.
    Updates both the indexed columns and the serialized payload.
    Supports both PostgreSQL and SQLite.
    """
    conn, db_type = get_connection()
    try:
        query = "SELECT data FROM classified_chunks WHERE chunk_id = %s"
        query = _adapt_query(query, db_type)
        rows = execute_query(conn, db_type, query, params=(chunk_id,), fetch=True)
        if not rows:
            raise ValueError(f"Chunk {chunk_id} was not found.")

        row = rows[0]
        raw_data = row['data'] if isinstance(row, dict) else row.get("data")
        payload = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        payload["suppressed"] = False
        payload["manually_restored"] = True

        update_query = """
            UPDATE classified_chunks
            SET suppressed = %s,
                manually_restored = %s,
                data = %s
            WHERE chunk_id = %s
        """
        update_query = _adapt_query(update_query, db_type)
        execute_query(conn, db_type, update_query, params=(0, 1, json.dumps(payload), chunk_id))
    finally:
        conn.close()


def create_snapshot(session_id: str) -> str:
    """
    Creates a frozen snapshot of all active signals from AKS via get_active_signals().
    Records their chunk IDs in brd_snapshots and returns the snapshot_id.
    """
    snapshot_id = str(uuid.uuid4())
    active_signals = get_active_signals(session_id=session_id)
    chunk_ids = [c.chunk_id for c in active_signals]

    conn, db_type = get_connection()
    try:
        query = """
            INSERT INTO brd_snapshots (snapshot_id, session_id, created_at, chunk_ids)
            VALUES (%s, %s, %s, %s)
        """
        query = _adapt_query(query, db_type)
        execute_query(conn, db_type, query, params=(snapshot_id, session_id, datetime.now(timezone.utc), json.dumps(chunk_ids)))
    finally:
        conn.close()

    return snapshot_id


def get_signals_for_snapshot(snapshot_id: str, label_filter: str = None) -> List[ClassifiedChunk]:
    """
    Queries AKS for chunks whose IDs are in the snapshot's chunk_ids array,
    optionally filtered by label.
    """
    conn, db_type = get_connection()
    results = []
    try:
        query = "SELECT chunk_ids FROM brd_snapshots WHERE snapshot_id = %s"
        query = _adapt_query(query, db_type)
        rows = execute_query(conn, db_type, query, params=(snapshot_id,), fetch=True)
        if not rows:
            return []

        row = rows[0]
        raw_ids = row['chunk_ids']
        chunk_ids = json.loads(raw_ids) if isinstance(raw_ids, str) else raw_ids
        if not chunk_ids:
            return []

        # Build IN (...) query for cross-platform compatibility
        placeholders = ",".join(["?" if db_type == "sqlite" else "%s"] * len(chunk_ids))
        query = f"SELECT data FROM classified_chunks WHERE chunk_id IN ({placeholders})"
        params = list(chunk_ids)

        if label_filter:
            query += " AND label = " + ("?" if db_type == "sqlite" else "%s")
            params.append(label_filter)

        rows = execute_query(conn, db_type, query, params=tuple(params), fetch=True)
        for r in rows:
            data = r['data'] if isinstance(r['data'], str) else r.get("data")
            results.append(ClassifiedChunk.model_validate(json.loads(data) if isinstance(data, str) else data))
    finally:
        conn.close()
    return results


def store_brd_section(session_id: str, snapshot_id: str, section_name: str, content: str, source_chunk_ids: List[str]):
    """Stores a generated BRD section with automatic version incrementing."""
    conn, db_type = get_connection()
    try:
        query = """
            SELECT COALESCE(MAX(version_number), 0) + 1
            FROM brd_sections
            WHERE session_id = %s AND section_name = %s
        """
        query = _adapt_query(query, db_type)
        rows = execute_query(conn, db_type, query, params=(session_id, section_name), fetch=True)
        version_number = rows[0][list(rows[0].keys())[0]] if rows else 1

        section_id = str(uuid.uuid4())
        query = """
            INSERT INTO brd_sections (
                section_id, session_id, snapshot_id, section_name,
                version_number, content, source_chunk_ids, generated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        query = _adapt_query(query, db_type)
        execute_query(conn, db_type, query, params=(
            section_id, session_id, snapshot_id, section_name,
            version_number, content, json.dumps(source_chunk_ids), datetime.now(timezone.utc)
        ))
    finally:
        conn.close()


def get_latest_brd_sections(session_id: str) -> Dict[str, str]:
    """Returns the latest generated content for each section name in a session."""
    conn, db_type = get_connection()
    sections = {}
    try:
        query = """
            SELECT section_name, content
            FROM brd_sections
            WHERE session_id = %s
            ORDER BY version_number DESC
        """
        query = _adapt_query(query, db_type)
        rows = execute_query(conn, db_type, query, params=(session_id,), fetch=True)
        for r in rows:
            name = r['section_name'] if isinstance(r, dict) else r.get("section_name")
            content = r['content'] if isinstance(r, dict) else r.get("content")
            if name not in sections:
                sections[name] = content
    finally:
        conn.close()
    return sections


def copy_session_chunks(src_session_id: str, dst_session_id: str) -> int:
    """
    Copy all classified chunks from src_session_id into dst_session_id.
    Clears dst_session_id first so repeated calls don't accumulate duplicates.
    Updates the session_id field inside the stored JSON data blob too.
    Returns the number of chunks copied.
    """
    conn, db_type = get_connection()
    copied = 0
    try:
        # Clear destination first
        delete_q = _adapt_query("DELETE FROM classified_chunks WHERE session_id = %s", db_type)
        execute_query(conn, db_type, delete_q, params=(dst_session_id,))

        # Get source chunks
        select_q = _adapt_query(
            "SELECT chunk_id, source_ref, label, suppressed, manually_restored, "
            "flagged_for_review, created_at, data FROM classified_chunks WHERE session_id = %s",
            db_type,
        )
        rows = execute_query(conn, db_type, select_q, params=(src_session_id,), fetch=True)
        for row in rows:
            new_id = str(uuid.uuid4())
            raw_data = row['data'] if isinstance(row['data'], str) else str(row['data'])
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
            data['session_id'] = dst_session_id
            data['chunk_id'] = new_id

            insert_q = _adapt_query(
                """
                INSERT INTO classified_chunks
                    (chunk_id, session_id, source_ref, label, suppressed,
                     manually_restored, flagged_for_review, created_at, data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (chunk_id) DO NOTHING
                """,
                db_type,
            )
            # Remove the ON CONFLICT clause which isn't in SQLite INSERT OR IGNORE
            if db_type == "sqlite":
                insert_q = insert_q.replace(
                    "INSERT INTO classified_chunks",
                    "INSERT OR IGNORE INTO classified_chunks"
                )

            execute_query(conn, db_type, insert_q, params=(
                new_id,
                dst_session_id,
                row['source_ref'],
                row['label'],
                row['suppressed'],
                row['manually_restored'],
                row['flagged_for_review'],
                datetime.now(timezone.utc),
                json.dumps(data),
            ))
            copied += 1
    finally:
        conn.close()
    return copied
