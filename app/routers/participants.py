"""Participants API endpoint."""

from fastapi import APIRouter

from ..database import get_db
from ..models import ParticipantStats

router = APIRouter(prefix="/api", tags=["participants"])


@router.get("/participants", response_model=list[ParticipantStats])
async def get_participants():
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT p.login, p.name, p.icon_url, p.team_id,
                      t.name AS team_name, t.color AS team_color
               FROM participants p
               LEFT JOIN teams t ON p.team_id = t.team_id
               ORDER BY p.login"""
        )
        participants = await cursor.fetchall()

        results = []
        for p in participants:
            login = p[0]

            # Count events by type for this participant
            cursor = await db.execute(
                """SELECT event_type, COUNT(*) FROM events
                   WHERE actor_login = ? AND is_participant = 1
                   GROUP BY event_type""",
                (login,),
            )
            counts = {row[0]: row[1] for row in await cursor.fetchall()}

            ids = counts.get("identification", 0)
            comments = counts.get("comment", 0)
            moves = counts.get("taxon_move", 0)
            annotations = counts.get("annotation_added", 0)

            results.append(
                ParticipantStats(
                    login=login,
                    name=p[1] or login,
                    icon_url=p[2] or "",
                    team_id=p[3],
                    team_name=p[4],
                    team_color=p[5],
                    identifications=ids,
                    comments=comments,
                    taxon_moves=moves,
                    annotations=annotations,
                    total=ids + comments + moves + annotations,
                )
            )

        # Sort by total contributions descending
        results.sort(key=lambda x: x.total, reverse=True)
        return results
    finally:
        await db.close()
