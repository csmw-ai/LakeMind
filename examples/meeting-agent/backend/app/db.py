from __future__ import annotations
import aiosqlite
from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS meeting_tasks (
    task_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    owner_principal_id TEXT NOT NULL,
    title TEXT NOT NULL,
    participants TEXT NOT NULL DEFAULT '[]',
    source_type TEXT NOT NULL DEFAULT 'LIVE',
    status TEXT NOT NULL DEFAULT 'DRAFT',
    current_stage TEXT,
    template_id TEXT,
    template_snapshot TEXT NOT NULL DEFAULT '{}',
    language TEXT,
    started_at TEXT,
    stopped_at TEXT,
    duration_ms INTEGER DEFAULT 0,
    recording_artifact_id TEXT,
    transcript_artifact_id TEXT,
    minutes_artifact_id TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_owner ON meeting_tasks(tenant_id, owner_principal_id, status);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON meeting_tasks(owner_principal_id, created_at DESC);

CREATE TABLE IF NOT EXISTS meeting_audio_chunks (
    chunk_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    sequence_no INTEGER NOT NULL,
    duration_ms INTEGER,
    mime_type TEXT,
    size_bytes INTEGER,
    checksum TEXT NOT NULL,
    object_uri TEXT NOT NULL,
    upload_status TEXT DEFAULT 'UPLOADED',
    asr_status TEXT DEFAULT 'PENDING',
    created_at TEXT,
    UNIQUE(task_id, sequence_no)
);
CREATE INDEX IF NOT EXISTS idx_chunks_task ON meeting_audio_chunks(task_id, sequence_no);

CREATE TABLE IF NOT EXISTS meeting_stage_runs (
    stage_run_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    job_id TEXT,
    skill_version TEXT,
    model_profile TEXT,
    error_message TEXT,
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_stages_task ON meeting_stage_runs(task_id, stage);

CREATE TABLE IF NOT EXISTS meeting_transcript_segments (
    segment_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    chunk_sequence INTEGER,
    start_ms INTEGER,
    end_ms INTEGER,
    speaker_label TEXT,
    original_text TEXT NOT NULL,
    edited_text TEXT,
    confidence REAL,
    revision INTEGER DEFAULT 1,
    created_at TEXT,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_segments_task ON meeting_transcript_segments(task_id, start_ms);

CREATE TABLE IF NOT EXISTS meeting_minutes_versions (
    minutes_version_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    content_markdown TEXT NOT NULL,
    status TEXT DEFAULT 'PREVIEW',
    created_at TEXT,
    UNIQUE(task_id, version)
);

CREATE TABLE IF NOT EXISTS meeting_knowledge_items (
    item_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    item_type TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    tags TEXT DEFAULT '[]',
    evidence_segment_ids TEXT DEFAULT '[]',
    evidence_start_ms INTEGER,
    evidence_end_ms INTEGER,
    confidence REAL,
    review_status TEXT DEFAULT 'DRAFT',
    reviewed_at TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_knowledge_task ON meeting_knowledge_items(task_id, review_status);

CREATE TABLE IF NOT EXISTS meeting_templates (
    template_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    owner_principal_id TEXT,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'ACTIVE',
    current_version INTEGER DEFAULT 1,
    is_builtin INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS meeting_template_versions (
    template_version_id TEXT PRIMARY KEY,
    template_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    config_json TEXT NOT NULL,
    created_by TEXT,
    created_at TEXT,
    UNIQUE(template_id, version)
);

CREATE TABLE IF NOT EXISTS app_users (
    principal_id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    display_name TEXT,
    created_at TEXT NOT NULL
);
"""


async def init_db(path: str = DB_PATH):
    async with aiosqlite.connect(path) as db:
        await db.executescript(SCHEMA)
        try:
            await db.execute("ALTER TABLE meeting_tasks ADD COLUMN remarks TEXT DEFAULT ''")
        except Exception:
            pass
        await db.commit()


async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()
