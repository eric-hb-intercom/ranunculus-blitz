"""Admin/blitz control API endpoints."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from ..config import Settings
from ..database import get_db
from ..models import BlitzStatus, SpeciesBreakdown
from ..workers.snapshot import run_snapshot
from ..workers import poller

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["admin"])

# Reference to app settings — set by main.py during startup
_settings: Settings | None = None
_broadcast_fn = None


def configure(settings: Settings, broadcast_fn) -> None:
    global _settings, _broadcast_fn
    _settings = settings
    _broadcast_fn = broadcast_fn


@router.get("/blitz/status", response_model=BlitzStatus)
async def get_blitz_status():
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT key, value FROM blitz_config"
        )
        config = {row[0]: row[1] for row in await cursor.fetchall()}

        cursor = await db.execute("SELECT COUNT(*) FROM observations")
        total = (await cursor.fetchone())[0]

        if config.get("ended_at"):
            status = "ended"
        elif config.get("started_at"):
            status = "live"
        elif config.get("snapshot_at"):
            status = "ready"
        else:
            status = "setup"

        # Parse species from config
        species = []
        if config.get("species_json"):
            import json
            for sp in json.loads(config["species_json"]):
                species.append(SpeciesBreakdown(
                    name=sp.get("name", ""),
                    common=sp.get("common", ""),
                    color=sp.get("color", "#888888"),
                    total=sp.get("count", 0),
                ))

        return BlitzStatus(
            status=status,
            species=species,
            place_id=int(config.get("place_id", "6857")),
            total_observations=total,
            started_at=config.get("started_at"),
            ended_at=config.get("ended_at"),
        )
    finally:
        await db.close()


_snapshot_task = None


@router.post("/blitz/snapshot")
async def trigger_snapshot():
    global _snapshot_task
    if not _settings:
        raise HTTPException(500, "Settings not configured")

    # If snapshot is already running, report that
    if _snapshot_task and not _snapshot_task.done():
        return {"status": "running", "message": "Snapshot already in progress"}

    async def _run():
        try:
            result = await run_snapshot(_settings.species, _settings.place_id)
            logger.info(f"Snapshot complete: {result}")
        except Exception as e:
            logger.error(f"Snapshot failed: {e}", exc_info=True)

    _snapshot_task = asyncio.create_task(_run())
    return {"status": "started", "message": "Snapshot started in background. Poll GET /api/blitz/status to track progress."}


@router.post("/blitz/start")
async def start_blitz():
    if not _settings or not _broadcast_fn:
        raise HTTPException(500, "Settings not configured")

    db = await get_db()
    try:
        # Check that snapshot exists
        cursor = await db.execute(
            "SELECT value FROM blitz_config WHERE key = 'snapshot_at'"
        )
        if not await cursor.fetchone():
            raise HTTPException(400, "No snapshot taken yet. Run POST /api/blitz/snapshot first.")

        # Check not already started
        cursor = await db.execute(
            "SELECT value FROM blitz_config WHERE key = 'started_at'"
        )
        if await cursor.fetchone():
            raise HTTPException(400, "Blitz already started")

        # Record start time
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT OR REPLACE INTO blitz_config (key, value) VALUES (?, ?)",
            ("started_at", now),
        )
        await db.commit()
    finally:
        await db.close()

    # Start the diff poller
    asyncio.create_task(
        poller.start_poller(_settings.diff_interval, _broadcast_fn)
    )

    return {"status": "live", "started_at": now}


@router.post("/blitz/end")
async def end_blitz():
    db = await get_db()
    try:
        # Check that blitz is running
        cursor = await db.execute(
            "SELECT value FROM blitz_config WHERE key = 'started_at'"
        )
        if not await cursor.fetchone():
            raise HTTPException(400, "Blitz not started")

        cursor = await db.execute(
            "SELECT value FROM blitz_config WHERE key = 'ended_at'"
        )
        if await cursor.fetchone():
            raise HTTPException(400, "Blitz already ended")

        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT OR REPLACE INTO blitz_config (key, value) VALUES (?, ?)",
            ("ended_at", now),
        )
        await db.commit()
    finally:
        await db.close()

    # Stop the poller
    await poller.stop_poller()

    # Run one final diff + superlatives computation
    from ..workers.differ import run_diff_cycle
    from ..workers.superlatives import compute_superlatives
    await run_diff_cycle()
    await compute_superlatives()

    return {"status": "ended", "ended_at": now}
