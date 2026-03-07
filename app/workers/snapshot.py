"""Snapshot worker: fetches all needs_id observations for target species."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from ..config import SpeciesConfig
from ..database import get_db
from ..inat.client import get_paged, lookup_taxon
from ..inat.parsers import parse_observation

logger = logging.getLogger(__name__)


async def run_snapshot(species_list: list[SpeciesConfig], place_id: int) -> dict:
    """Fetch all needs_id observations for each target species and store in DB.

    Can be run hours before the blitz to pre-warm the database.
    Returns summary stats.
    """
    total_count = 0
    species_results = []

    for sp in species_list:
        logger.info(f"Looking up taxon: {sp.name}")
        taxon = await lookup_taxon(sp.name, rank="species")
        if not taxon:
            logger.warning(f"Could not find taxon: {sp.name}, skipping")
            continue

        taxon_id = taxon["id"]
        taxon_actual_name = taxon.get("name", sp.name)
        sp.taxon_id = taxon_id
        logger.info(f"Found {taxon_actual_name} (ID: {taxon_id})")

        # Fetch all needs_id observations for this species
        logger.info(f"Fetching needs_id observations for {taxon_actual_name}...")
        observations = await get_paged(
            "observations",
            {
                "taxon_id": taxon_id,
                "place_id": place_id,
                "quality_grade": "needs_id",
                "per_page": 200,
                "order_by": "id",
                "order": "asc",
            },
            max_results=10000,
        )

        logger.info(f"Fetched {len(observations)} observations for {taxon_actual_name}")

        # Store in database
        db = await get_db()
        try:
            count = 0
            for obs in observations:
                parsed = parse_observation(obs)
                await db.execute(
                    """INSERT OR REPLACE INTO observations
                    (obs_id, observed_on, lat, lng, photo_url,
                     taxon_id, taxon_name, taxon_rank, quality_grade,
                     species_group, species_color,
                     snapshot_taxon_id, snapshot_taxon_name, snapshot_taxon_rank,
                     snapshot_quality, snapshot_ids_json, snapshot_comments_json,
                     snapshot_annotations,
                     current_ids_json, current_comments_json, current_annotations,
                     resolved, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)""",
                    (
                        parsed["obs_id"],
                        parsed["observed_on"],
                        parsed["lat"],
                        parsed["lng"],
                        parsed["photo_url"],
                        parsed["taxon_id"],
                        parsed["taxon_name"],
                        parsed["taxon_rank"],
                        parsed["quality_grade"],
                        # Species group info
                        taxon_actual_name,
                        sp.color,
                        # Snapshot (frozen)
                        parsed["taxon_id"],
                        parsed["taxon_name"],
                        parsed["taxon_rank"],
                        parsed["quality_grade"],
                        parsed["ids_json"],
                        parsed["comments_json"],
                        parsed["annotations_json"],
                        # Current (will be updated by differ)
                        parsed["ids_json"],
                        parsed["comments_json"],
                        parsed["annotations_json"],
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                count += 1

            await db.commit()
            logger.info(f"Stored {count} observations for {taxon_actual_name}")
        finally:
            await db.close()

        total_count += count
        species_results.append({
            "name": taxon_actual_name,
            "common": sp.common,
            "taxon_id": taxon_id,
            "color": sp.color,
            "count": count,
        })

    # Store config
    db = await get_db()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO blitz_config (key, value) VALUES (?, ?)",
            ("species_json", json.dumps(species_results)),
        )
        await db.execute(
            "INSERT OR REPLACE INTO blitz_config (key, value) VALUES (?, ?)",
            ("place_id", str(place_id)),
        )
        await db.execute(
            "INSERT OR REPLACE INTO blitz_config (key, value) VALUES (?, ?)",
            ("snapshot_at", datetime.now(timezone.utc).isoformat()),
        )
        await db.execute(
            "INSERT OR REPLACE INTO blitz_config (key, value) VALUES (?, ?)",
            ("snapshot_count", str(total_count)),
        )
        await db.commit()
    finally:
        await db.close()

    return {
        "species": species_results,
        "total_observations": total_count,
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
    }
