"""Overview and superlatives API endpoints."""

import json
from datetime import datetime, timezone

from fastapi import APIRouter

from ..database import get_db
from ..models import OverviewResponse, SuperlativeAward

router = APIRouter(prefix="/api", tags=["overview"])


@router.get("/overview", response_model=OverviewResponse)
async def get_overview():
    db = await get_db()
    try:
        # Total observations
        cursor = await db.execute("SELECT COUNT(*) FROM observations")
        total = (await cursor.fetchone())[0]

        # Resolved count
        cursor = await db.execute(
            "SELECT COUNT(*) FROM observations WHERE resolved = 1"
        )
        resolved = (await cursor.fetchone())[0]

        # Blitz status and timing
        status = await _get_blitz_status(db)
        elapsed = 0
        if status == "live":
            cursor = await db.execute(
                "SELECT value FROM blitz_config WHERE key = 'started_at'"
            )
            row = await cursor.fetchone()
            if row:
                started = datetime.fromisoformat(row[0])
                elapsed = int((datetime.now(timezone.utc) - started).total_seconds())
        elif status == "ended":
            cursor = await db.execute(
                "SELECT value FROM blitz_config WHERE key = 'started_at'"
            )
            start_row = await cursor.fetchone()
            cursor = await db.execute(
                "SELECT value FROM blitz_config WHERE key = 'ended_at'"
            )
            end_row = await cursor.fetchone()
            if start_row and end_row:
                started = datetime.fromisoformat(start_row[0])
                ended = datetime.fromisoformat(end_row[0])
                elapsed = int((ended - started).total_seconds())

        pct = round(100 * resolved / total, 1) if total > 0 else 0.0

        # Species breakdown
        cursor = await db.execute(
            """SELECT species_group, species_color,
                      COUNT(*) as total,
                      SUM(CASE WHEN resolved = 1 THEN 1 ELSE 0 END) as resolved_count
               FROM observations
               GROUP BY species_group, species_color
               ORDER BY species_group"""
        )
        species_rows = await cursor.fetchall()

        # Fetch common names from config
        cursor = await db.execute(
            "SELECT value FROM blitz_config WHERE key = 'species_json'"
        )
        config_row = await cursor.fetchone()
        common_names = {}
        if config_row:
            import json
            for sp in json.loads(config_row[0]):
                common_names[sp["name"]] = sp.get("common", "")

        from ..models import SpeciesBreakdown
        species = [
            SpeciesBreakdown(
                name=row[0] or "Unknown",
                common=common_names.get(row[0], ""),
                color=row[1] or "#888888",
                total=row[2],
                resolved=row[3],
            )
            for row in species_rows
        ]

        return OverviewResponse(
            total_observations=total,
            resolved_count=resolved,
            pct_complete=pct,
            elapsed_seconds=elapsed,
            blitz_status=status,
            species=species,
        )
    finally:
        await db.close()


@router.get("/superlatives", response_model=list[SuperlativeAward])
async def get_superlatives():
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT scope, award_name, award_title, winner_login,
                      winner_name, winner_team_id, team_name, detail, value
               FROM superlatives ORDER BY scope, award_name"""
        )
        rows = await cursor.fetchall()
        return [
            SuperlativeAward(
                scope=row[0],
                award_name=row[1],
                award_title=row[2],
                winner_login=row[3],
                winner_name=row[4],
                winner_team_id=row[5],
                team_name=row[6],
                detail=row[7],
                value=row[8] or 0,
            )
            for row in rows
        ]
    finally:
        await db.close()


async def _get_blitz_status(db) -> str:
    cursor = await db.execute(
        "SELECT key, value FROM blitz_config WHERE key IN ('started_at', 'ended_at', 'snapshot_at')"
    )
    config = {row[0]: row[1] for row in await cursor.fetchall()}

    if config.get("ended_at"):
        return "ended"
    if config.get("started_at"):
        return "live"
    if config.get("snapshot_at"):
        return "ready"
    return "setup"
