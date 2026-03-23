"""Observations API endpoint with pagination, sorting, and filtering."""

from fastapi import APIRouter, Query

from ..database import get_db
from ..models import ObservationSummary

router = APIRouter(prefix="/api", tags=["observations"])


@router.get("/observations", response_model=dict)
async def get_observations(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    sort: str = Query("obs_id"),
    order: str = Query("asc"),
    filter: str = Query("all"),  # all | unresolved | resolved
    species: str = Query(""),  # filter by species_group name
):
    db = await get_db()
    try:
        # Build WHERE clause
        where_parts = []
        if filter == "unresolved":
            where_parts.append("resolved = 0")
        elif filter == "resolved":
            where_parts.append("resolved = 1")
        params = []
        if species:
            where_parts.append("species_group = ?")
            params.append(species)

        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        # Validate sort column
        allowed_sorts = {"obs_id", "observed_on", "taxon_name", "quality_grade", "updated_at"}
        if sort not in allowed_sorts:
            sort = "obs_id"
        order_dir = "DESC" if order.lower() == "desc" else "ASC"

        # Count total
        cursor = await db.execute(f"SELECT COUNT(*) FROM observations {where_sql}", params)
        total = (await cursor.fetchone())[0]

        # Fetch page
        offset = (page - 1) * per_page
        cursor = await db.execute(
            f"""SELECT obs_id, observed_on, lat, lng, photo_url,
                       taxon_name, taxon_rank, quality_grade,
                       species_group, species_color,
                       resolved
                FROM observations {where_sql}
                ORDER BY {sort} {order_dir}
                LIMIT ? OFFSET ?""",
            (*params, per_page, offset),
        )
        rows = await cursor.fetchall()

        items = [
            ObservationSummary(
                obs_id=r[0],
                observed_on=r[1],
                lat=r[2],
                lng=r[3],
                photo_url=r[4],
                taxon_name=r[5],
                taxon_rank=r[6],
                quality_grade=r[7],
                species_group=r[8],
                species_color=r[9],
                resolved=bool(r[10]),
            )
            for r in rows
        ]

        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
        }
    finally:
        await db.close()
