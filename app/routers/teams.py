"""Teams API endpoint."""

from fastapi import APIRouter

from ..database import get_db
from ..models import TeamStats, ParticipantStats

router = APIRouter(prefix="/api", tags=["teams"])


@router.get("/teams", response_model=list[TeamStats])
async def get_teams():
    db = await get_db()
    try:
        # Load all teams
        cursor = await db.execute("SELECT team_id, name, color FROM teams ORDER BY team_id")
        team_rows = await cursor.fetchall()

        results = []
        for t in team_rows:
            team_id = t[0]

            # Get team members
            cursor = await db.execute(
                """SELECT p.login, p.name, p.icon_url
                   FROM participants p WHERE p.team_id = ?
                   ORDER BY p.login""",
                (team_id,),
            )
            member_rows = await cursor.fetchall()

            members = []
            team_ids = team_comments = team_moves = team_annotations = 0

            for m in member_rows:
                login = m[0]
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

                team_ids += ids
                team_comments += comments
                team_moves += moves
                team_annotations += annotations

                members.append(
                    ParticipantStats(
                        login=login,
                        name=m[1] or login,
                        icon_url=m[2] or "",
                        team_id=team_id,
                        team_name=t[1],
                        team_color=t[2],
                        identifications=ids,
                        comments=comments,
                        taxon_moves=moves,
                        annotations=annotations,
                        total=ids + comments + moves + annotations,
                    )
                )

            members.sort(key=lambda x: x.total, reverse=True)

            results.append(
                TeamStats(
                    team_id=team_id,
                    name=t[1],
                    color=t[2],
                    identifications=team_ids,
                    comments=team_comments,
                    taxon_moves=team_moves,
                    annotations=team_annotations,
                    total=team_ids + team_comments + team_moves + team_annotations,
                    members=members,
                )
            )

        return results
    finally:
        await db.close()
