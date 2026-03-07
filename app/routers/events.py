"""Events (activity feed) API endpoint."""

import json

from fastapi import APIRouter, Query

from ..database import get_db
from ..models import EventItem

router = APIRouter(prefix="/api", tags=["events"])


@router.get("/events", response_model=list[EventItem])
async def get_events(
    since: int = Query(0, description="Return events with ID > this value"),
    limit: int = Query(50, ge=1, le=200),
):
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT e.event_id, e.event_type, e.actor_login, e.actor_name,
                      e.actor_icon_url, e.actor_team_id, e.is_participant,
                      e.obs_id, e.detail_json, e.created_at,
                      o.species_group
               FROM events e
               LEFT JOIN observations o ON e.obs_id = o.obs_id
               WHERE e.event_id > ?
               ORDER BY e.event_id DESC
               LIMIT ?""",
            (since, limit),
        )
        rows = await cursor.fetchall()

        return [
            EventItem(
                event_id=r[0],
                event_type=r[1],
                actor_login=r[2],
                actor_name=r[3],
                actor_icon_url=r[4],
                actor_team_id=r[5],
                is_participant=bool(r[6]),
                obs_id=r[7],
                detail=json.loads(r[8] or "{}"),
                created_at=r[9],
                species_group=r[10],
            )
            for r in rows
        ]
    finally:
        await db.close()
