from __future__ import annotations

ACTIVE_JOB_STATES = {"pending", "probing", "recording", "stopping"}
FINAL_JOB_STATES = {"completed", "interrupted", "failed"}
JOB_STATES = ACTIVE_JOB_STATES | FINAL_JOB_STATES

TEMP_SUFFIXES = {".tmp", ".part", ".download", ".crdownload"}
VIDEO_SUFFIXES = {".mp4", ".mkv", ".flv", ".ts", ".mov", ".webm"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL DEFAULT 'unknown',
    quality TEXT NOT NULL DEFAULT '原画',
    enabled INTEGER NOT NULL DEFAULT 1,
    source TEXT NOT NULL DEFAULT 'api',
    deleted_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recording_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT,
    error_message TEXT NOT NULL DEFAULT '',
    config_snapshot TEXT NOT NULL DEFAULT '{}',
    worker_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(room_id) REFERENCES rooms(id)
);

CREATE INDEX IF NOT EXISTS idx_recording_jobs_room_status ON recording_jobs(room_id, status);
CREATE INDEX IF NOT EXISTS idx_recording_jobs_status_id ON recording_jobs(status, id DESC);
CREATE INDEX IF NOT EXISTS idx_recording_jobs_room_id ON recording_jobs(room_id, id DESC);

CREATE TABLE IF NOT EXISTS recorded_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER,
    room_id INTEGER,
    local_path TEXT NOT NULL,
    file_identity TEXT NOT NULL UNIQUE,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    format TEXT NOT NULL DEFAULT '',
    segment_index INTEGER NOT NULL DEFAULT 0,
    duration_seconds REAL,
    checksum TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'recording',
    status TEXT NOT NULL DEFAULT 'ready',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(job_id) REFERENCES recording_jobs(id),
    FOREIGN KEY(room_id) REFERENCES rooms(id)
);

CREATE INDEX IF NOT EXISTS idx_recorded_files_created_at ON recorded_files(created_at);
CREATE INDEX IF NOT EXISTS idx_recorded_files_room_id ON recorded_files(room_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_recorded_files_job_id ON recorded_files(job_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_recorded_files_status_id ON recorded_files(status, id DESC);

CREATE TABLE IF NOT EXISTS download_watch_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_dir TEXT NOT NULL,
    local_path TEXT NOT NULL,
    file_identity TEXT NOT NULL UNIQUE,
    observed_size INTEGER NOT NULL DEFAULT 0,
    observed_mtime REAL NOT NULL DEFAULT 0,
    stable_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'candidate',
    encoding_status TEXT NOT NULL DEFAULT 'not_required',
    recorded_file_id INTEGER,
    error_message TEXT NOT NULL DEFAULT '',
    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    registered_at TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(recorded_file_id) REFERENCES recorded_files(id)
);

CREATE INDEX IF NOT EXISTS idx_download_watch_status_id ON download_watch_records(status, id DESC);
CREATE INDEX IF NOT EXISTS idx_download_watch_updated_at ON download_watch_records(updated_at);

CREATE TABLE IF NOT EXISTS douyin_collection_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL,
    input_url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    max_items INTEGER NOT NULL DEFAULT 1,
    progress_total INTEGER NOT NULL DEFAULT 0,
    progress_done INTEGER NOT NULL DEFAULT 0,
    error_message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TEXT,
    ended_at TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_douyin_tasks_status_id ON douyin_collection_tasks(status, id DESC);

CREATE TABLE IF NOT EXISTS douyin_downloaded_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    aweme_id TEXT NOT NULL,
    author TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    local_path TEXT NOT NULL DEFAULT '',
    file_identity TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT NOT NULL DEFAULT '',
    recorded_file_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(task_id, aweme_id),
    FOREIGN KEY(task_id) REFERENCES douyin_collection_tasks(id),
    FOREIGN KEY(recorded_file_id) REFERENCES recorded_files(id)
);

CREATE INDEX IF NOT EXISTS idx_douyin_items_task_id_id ON douyin_downloaded_items(task_id, id ASC);
CREATE INDEX IF NOT EXISTS idx_douyin_items_status_id ON douyin_downloaded_items(status, id DESC);

CREATE TABLE IF NOT EXISTS upload_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_file_id INTEGER,
    downloaded_item_id INTEGER,
    file_identity TEXT NOT NULL UNIQUE,
    local_path TEXT NOT NULL,
    youtube_video_id TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    privacy_status TEXT NOT NULL DEFAULT 'private',
    status TEXT NOT NULL DEFAULT 'pending',
    failure_reason TEXT NOT NULL DEFAULT '',
    retry_count INTEGER NOT NULL DEFAULT 0,
    upload_config_version TEXT NOT NULL DEFAULT 'v1',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(recorded_file_id) REFERENCES recorded_files(id),
    FOREIGN KEY(downloaded_item_id) REFERENCES douyin_downloaded_items(id)
);

CREATE INDEX IF NOT EXISTS idx_upload_records_status_id ON upload_records(status, id ASC);
CREATE INDEX IF NOT EXISTS idx_upload_records_youtube_status ON upload_records(status, youtube_video_id);

CREATE TABLE IF NOT EXISTS youtube_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    youtube_video_id TEXT NOT NULL,
    metric_date TEXT NOT NULL,
    view_count INTEGER NOT NULL DEFAULT 0,
    like_count INTEGER NOT NULL DEFAULT 0,
    comment_count INTEGER NOT NULL DEFAULT 0,
    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(youtube_video_id, metric_date)
);

CREATE INDEX IF NOT EXISTS idx_youtube_metrics_date_id ON youtube_metrics(metric_date DESC, id DESC);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'general',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS task_commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    command_type TEXT NOT NULL,
    room_id INTEGER,
    job_id INTEGER,
    upload_id INTEGER,
    payload TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    result_message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TEXT,
    FOREIGN KEY(room_id) REFERENCES rooms(id),
    FOREIGN KEY(job_id) REFERENCES recording_jobs(id),
    FOREIGN KEY(upload_id) REFERENCES upload_records(id)
);

CREATE INDEX IF NOT EXISTS idx_task_commands_status_id ON task_commands(status, id ASC);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    job_id INTEGER,
    file_id INTEGER,
    upload_id INTEGER,
    douyin_task_id INTEGER,
    level TEXT NOT NULL DEFAULT 'info',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_events_created_at_id ON events(created_at DESC, id DESC);
"""
