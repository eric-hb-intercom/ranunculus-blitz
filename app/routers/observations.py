"""Observations API endpoint with pagination, sorting, filtering, and claims."""

from fastapi import APIRouter, Query

from ..database import get_db
from ..models import ObservationSummary, ClaimRequest

router = APIRouter(prefix="/api", tags=["observations"])


@router.get("/observations", response_model=dict)
async def get_observations(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    sort: str = Query("obs_id"),
    order: str = Query("asc"),
    filter: str = Query("all"),  # all | unresolved | resolved | claimed
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
        elif filter == "claimed":
            where_parts.append("claimed_by IS NOT NULL")

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
                       claimed_by, resolved
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
                claimed_by=r[10],
                resolved=bool(r[11]),
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


@router.post("/observations/{obs_id}/claim")
async def claim_observation(obs_id: int, body: ClaimRequest):
    db = await get_db()
    try:
        await db.execute(
            "UPDATE observations SET claimed_by = ? WHERE obs_id = ? AND claimed_by IS NULL",
            (body.login, obs_id),
        )
        await db.commit()
        cursor = await db.execute(
            "SELECT claimed_by FROM observations WHERE obs_id = ?", (obs_id,)
        )
        row = await cursor.fetchone()
        return {"obs_id": obs_id, "claimed_by": row[0] if row else None}
    finally:
        await db.close()


@router.delete("/observations/{obs_id}/claim")
async def release_claim(obs_id: int):
    db = await get_db()
    try:
        await db.execute(
            "UPDATE observations SET claimed_by = NULL WHERE obs_id = ?",
            (obs_id,),
        )
        await db.commit()
        return {"obs_id": obs_id, "claimed_by": None}
    finally:
        await db.close()
