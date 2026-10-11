"""SQLite persistence for NOOBZY AI STUDIO.

Pragmatic design: each domain entity (Project, SourceMedia, TimelineDocument,
SkillManifest, MemoryRecord, ...) is a Pydantic model. Rather than hand-roll a
full relational schema for deeply nested JSON documents, each table stores
`id` (indexed, primary key) plus the model's JSON serialization. This keeps
the TimelineDocument (the source of truth per spec section 3) trivially
round-trippable while still being real, queryable, persistent SQLite -- not
an in-memory mock. Simple rules (projects, skills, memory) get real indexed
columns used for filtering.

Migrations: `schema_migrations` records which numbered migration has run.
Each migration is a plain SQL script applied once, in order. This is a real
(if minimal) migration mechanism, not a destructive create-all.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DATA_DIR = Path(os.environ.get("NOOBZY_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "noobzy.db"

MIGRATIONS: list[str] = [
    # 0001: initial tables
    """
    CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        preset TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        data_json TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS source_media (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        data_json TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS timeline_documents (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        data_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS skills (
        id TEXT PRIMARY KEY,
        version TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        data_json TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS skill_versions (
        skill_id TEXT NOT NULL,
        version TEXT NOT NULL,
        data_json TEXT NOT NULL,
        saved_at TEXT NOT NULL,
        PRIMARY KEY (skill_id, version)
    );
    CREATE TABLE IF NOT EXISTS memory_records (
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        key TEXT NOT NULL,
        version INTEGER NOT NULL,
        data_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS export_jobs (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        status TEXT NOT NULL,
        data_json TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS compute_jobs (
        id TEXT PRIMARY KEY,
        provider TEXT NOT NULL,
        status TEXT NOT NULL,
        data_json TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS audio_assets (
        id TEXT PRIMARY KEY,
        category TEXT,
        license TEXT NOT NULL,
        data_json TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS creative_feedback (
        id TEXT PRIMARY KEY,
        project_id TEXT,
        created_at TEXT NOT NULL,
        data_json TEXT NOT NULL
    );
    """,
]


_schema_ready = False


def _raw_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    # Lazily guarantee the schema exists before any query runs, so this
    # module is safe to use standalone (scripts, tests) as well as behind
    # the FastAPI startup hook that calls init_db() explicitly -- a fresh
    # or wiped DB file never surfaces "no such table" just because some
    # caller forgot to call init_db() first.
    global _schema_ready
    if not _schema_ready:
        run_migrations()
        _schema_ready = True
    conn = _raw_connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def run_migrations() -> None:
    conn = _raw_connect()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (n INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        applied = {row[0] for row in conn.execute("SELECT n FROM schema_migrations")}
        for i, script in enumerate(MIGRATIONS):
            if i in applied:
                continue
            conn.executescript(script)
            conn.execute(
                "INSERT INTO schema_migrations (n, applied_at) VALUES (?, datetime('now'))", (i,)
            )
        conn.commit()
    finally:
        conn.close()


def dumps(model) -> str:
    return model.model_dump_json()


def init_db() -> None:
    global _schema_ready
    run_migrations()
    _schema_ready = True


# ---- generic repository helpers ----


def upsert_project(project) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO projects (id, name, preset, status, created_at, updated_at, data_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET name=excluded.name, preset=excluded.preset,
                 status=excluded.status, updated_at=excluded.updated_at, data_json=excluded.data_json""",
            (
                project.id,
                project.name,
                project.preset.value,
                project.status.value,
                project.created_at.isoformat(),
                project.updated_at.isoformat(),
                dumps(project),
            ),
        )


def get_project(project_id: str) -> str | None:
    with connect() as conn:
        row = conn.execute("SELECT data_json FROM projects WHERE id=?", (project_id,)).fetchone()
        return row["data_json"] if row else None


def list_projects() -> list[str]:
    with connect() as conn:
        rows = conn.execute("SELECT data_json FROM projects ORDER BY created_at DESC").fetchall()
        return [r["data_json"] for r in rows]


def upsert_source_media(media) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO source_media (id, project_id, data_json) VALUES (?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET data_json=excluded.data_json""",
            (media.id, media.project_id, dumps(media)),
        )


def list_source_media(project_id: str) -> list[str]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT data_json FROM source_media WHERE project_id=?", (project_id,)
        ).fetchall()
        return [r["data_json"] for r in rows]


def upsert_timeline(doc) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO timeline_documents (id, project_id, data_json, updated_at) VALUES (?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET data_json=excluded.data_json, updated_at=excluded.updated_at""",
            (doc.id, doc.project_id, dumps(doc), doc.updated_at.isoformat()),
        )


def get_timeline_for_project(project_id: str) -> str | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT data_json FROM timeline_documents WHERE project_id=? ORDER BY updated_at DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        return row["data_json"] if row else None


def upsert_skill(manifest, keep_history: bool = True) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO skills (id, version, enabled, data_json) VALUES (?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET version=excluded.version, enabled=excluded.enabled,
                 data_json=excluded.data_json""",
            (manifest.id, manifest.version, int(manifest.enabled), dumps(manifest)),
        )
        if keep_history:
            conn.execute(
                """INSERT INTO skill_versions (skill_id, version, data_json, saved_at)
                   VALUES (?, ?, ?, datetime('now'))
                   ON CONFLICT(skill_id, version) DO UPDATE SET data_json=excluded.data_json""",
                (manifest.id, manifest.version, dumps(manifest)),
            )


def get_skill(skill_id: str) -> str | None:
    with connect() as conn:
        row = conn.execute("SELECT data_json FROM skills WHERE id=?", (skill_id,)).fetchone()
        return row["data_json"] if row else None


def list_skills(enabled_only: bool = False) -> list[str]:
    with connect() as conn:
        q = "SELECT data_json FROM skills"
        if enabled_only:
            q += " WHERE enabled=1"
        rows = conn.execute(q).fetchall()
        return [r["data_json"] for r in rows]


def list_skill_versions(skill_id: str) -> list[str]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT data_json FROM skill_versions WHERE skill_id=? ORDER BY saved_at", (skill_id,)
        ).fetchall()
        return [r["data_json"] for r in rows]


def set_skill_enabled(skill_id: str, enabled: bool) -> None:
    with connect() as conn:
        row = conn.execute("SELECT data_json FROM skills WHERE id=?", (skill_id,)).fetchone()
        if row is None:
            return
        data = json.loads(row["data_json"])
        data["enabled"] = enabled
        conn.execute(
            "UPDATE skills SET enabled=?, data_json=? WHERE id=?",
            (int(enabled), json.dumps(data), skill_id),
        )


def upsert_memory(record) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO memory_records (id, kind, key, version, data_json, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET version=excluded.version, data_json=excluded.data_json,
                 updated_at=excluded.updated_at""",
            (
                record.id,
                record.kind.value,
                record.key,
                record.version,
                dumps(record),
                record.updated_at.isoformat(),
            ),
        )


def list_memory(kind: str | None = None) -> list[str]:
    with connect() as conn:
        if kind:
            rows = conn.execute("SELECT data_json FROM memory_records WHERE kind=?", (kind,)).fetchall()
        else:
            rows = conn.execute("SELECT data_json FROM memory_records").fetchall()
        return [r["data_json"] for r in rows]


def search_memory(query: str) -> list[str]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT data_json FROM memory_records WHERE key LIKE ? OR data_json LIKE ?",
            (f"%{query}%", f"%{query}%"),
        ).fetchall()
        return [r["data_json"] for r in rows]


def upsert_audio_asset(asset) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO audio_assets (id, category, license, data_json) VALUES (?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET data_json=excluded.data_json""",
            (asset.id, asset.category.value if asset.category else None, asset.license.value, dumps(asset)),
        )


def list_audio_assets() -> list[str]:
    with connect() as conn:
        rows = conn.execute("SELECT data_json FROM audio_assets").fetchall()
        return [r["data_json"] for r in rows]


def insert_feedback(record) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO creative_feedback (id, project_id, created_at, data_json) VALUES (?, ?, ?, ?)",
            (record.id, record.project_id, record.created_at.isoformat(), dumps(record)),
        )


def list_feedback(project_id: str | None = None) -> list[str]:
    with connect() as conn:
        if project_id:
            rows = conn.execute(
                "SELECT data_json FROM creative_feedback WHERE project_id=?", (project_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT data_json FROM creative_feedback").fetchall()
        return [r["data_json"] for r in rows]
