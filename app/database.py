"""SQLite database setup and connection management."""

import aiosqlite
import json
from pathlib import Path

_db_path: str = "blitz.db"


def set_db_path(path: str) -> None:
    global _db_path
    _db_path = path
    Path(path).parent.mkdir(parents=True, exist_ok=True)


async def get_db() -> aiosqlite.Connection:
    """Get a database connection. Caller must close it."""
    db = await aiosqlite.connect(_db_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db() -> None:
    """Create all tables if they don't exist."""
    db = await get_db()
    try:
        await db.executescript(SCHEMA)
        await db.commit()
    finally:
        await db.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS blitz_config (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS teams (
    team_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT NOT NULL,
    color   TEXT NOT NULL DEFAULT '#4a7c3f'
);

CREATE TABLE IF NOT EXISTS participants (
    user_id  INTEGER PRIMARY KEY,
    login    TEXT NOT NULL UNIQUE,
    name     TEXT NOT NULL DEFAULT '',
    icon_url TEXT NOT NULL DEFAULT '',
    team_id  INTEGER REFERENCES teams(team_id)
);

CREATE TABLE IF NOT EXISTS observations (
    obs_id              INTEGER PRIMARY KEY,
    observed_on         TEXT,
    lat                 REAL,
    lng                 REAL,
    photo_url           TEXT,
    taxon_id            INTEGER,
    taxon_name          TEXT,
    taxon_rank          TEXT,
    quality_grade       TEXT,
    species_group       TEXT,
    species_color       TEXT,
    -- Snapshot state (frozen at blitz start)
    snapshot_taxon_id   INTEGER,
    snapshot_taxon_name TEXT,
    snapshot_taxon_rank TEXT,
    snapshot_quality    TEXT,
    snapshot_ids_json   TEXT DEFAULT '[]',
    snapshot_comments_json TEXT DEFAULT '[]',
    snapshot_annotations TEXT DEFAULT '[]',
    -- Current state (updated each diff)
    current_ids_json    TEXT DEFAULT '[]',
    current_comments_json TEXT DEFAULT '[]',
    current_annotations TEXT DEFAULT '[]',
    -- Tracking
    claimed_by          TEXT,
    resolved            INTEGER DEFAULT 0,
    updated_at          TEXT
);

CREATE TABLE IF NOT EXISTS events (
    event_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type     TEXT NOT NULL,
    actor_login    TEXT,
    actor_name     TEXT,
    actor_icon_url TEXT,
    actor_team_id  INTEGER,
    is_participant INTEGER DEFAULT 0,
    obs_id         INTEGER,
    detail_json    TEXT DEFAULT '{}',
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS superlatives (
    award_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    scope       TEXT NOT NULL DEFAULT 'individual',
    award_name  TEXT NOT NULL,
    award_title TEXT NOT NULL,
    winner_login TEXT,
    winner_name  TEXT,
    winner_team_id INTEGER,
    team_name    TEXT,
    detail       TEXT,
    value        REAL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_obs_resolved ON observations(resolved);
CREATE INDEX IF NOT EXISTS idx_obs_species ON observations(species_group);
CREATE INDEX IF NOT EXISTS idx_participants_login ON participants(login);
"""
