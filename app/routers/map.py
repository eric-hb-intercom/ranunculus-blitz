"""Map data API endpoint."""

from typing import Optional

from fastapi import APIRouter, Query

from ..database import get_db
from ..models import MapMarker

router = APIRouter(prefix="/api", tags=["map"])


@router.get("/map-data", response_model=list[MapMarker])
async def get_map_data(
    since: Optional[str] = Query(None, description="ISO timestamp — only return obs updated after this"),
):
    db = await get_db()
    try:
        if since:
            cursor = await db.execute(
                """SELECT obs_id, lat, lng, photo_url, taxon_name,
                          quality_grade, species_group, species_color,
                          resolved, observed_on, updated_at
                   FROM observations
                   WHERE lat IS NOT NULL AND lng IS NOT NULL
                     AND updated_at > ?""",
                (since,),
            )
        else:
            cursor = await db.execute(
                """SELECT obs_id, lat, lng, photo_url, taxon_name,
                          quality_grade, species_group, species_color,
                          resolved, observed_on, updated_at
                   FROM observations
                   WHERE lat IS NOT NULL AND lng IS NOT NULL"""
            )
        rows = await cursor.fetchall()

        return [
            MapMarker(
                obs_id=r[0],
                lat=r[1],
                lng=r[2],
                photo_url=r[3],
                taxon_name=r[4],
                quality_grade=r[5],
                species_group=r[6],
                species_color=r[7],
                resolved=bool(r[8]),
                observed_on=r[9],
                updated_at=r[10],
            )
            for r in rows
        ]
    finally:
        await db.close()
