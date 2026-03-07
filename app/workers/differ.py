"""Diff worker: detects changes between stored and current observation state."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from ..database import get_db
from ..inat.client import fetch_observations_by_ids
from ..inat.parsers import parse_observation

logger = logging.getLogger(__name__)


async def run_diff_cycle() -> list[dict]:
    """Run a single diff cycle. Returns list of new events detected."""
    db = await get_db()
    try:
        # Get all unresolved observation IDs
        cursor = await db.execute(
            "SELECT obs_id FROM observations WHERE resolved = 0"
        )
        rows = await cursor.fetchall()
        obs_ids = [row[0] for row in rows]
    finally:
        await db.close()

    if not obs_ids:
        logger.info("No unresolved observations to diff")
        return []

    logger.info(f"Diffing {len(obs_ids)} unresolved observations")
    all_events: list[dict] = []

    # Process in chunks of 200 (iNat API limit)
    for i in range(0, len(obs_ids), 200):
        chunk = obs_ids[i : i + 200]
        try:
            api_obs = await fetch_observations_by_ids(chunk)
        except Exception as e:
            logger.error(f"Error fetching observations batch: {e}")
            continue

        # Index fetched observations by ID
        fetched = {obs["id"]: obs for obs in api_obs}

        db = await get_db()
        try:
            for obs_id in chunk:
                if obs_id not in fetched:
                    # Observation was deleted or obscured
                    await db.execute(
                        "UPDATE observations SET resolved = 1, updated_at = ? WHERE obs_id = ?",
                        (datetime.now(timezone.utc).isoformat(), obs_id),
                    )
                    continue

                api_data = fetched[obs_id]
                parsed = parse_observation(api_data)

                # Load stored state
                cursor = await db.execute(
                    """SELECT current_ids_json, current_comments_json,
                              current_annotations, taxon_id, taxon_name,
                              taxon_rank, quality_grade
                       FROM observations WHERE obs_id = ?""",
                    (obs_id,),
                )
                row = await cursor.fetchone()
                if not row:
                    continue

                old_ids = json.loads(row[0] or "[]")
                old_comments = json.loads(row[1] or "[]")
                old_annotations = json.loads(row[2] or "[]")
                old_taxon_id = row[3]
                old_quality = row[6]

                new_ids = json.loads(parsed["ids_json"])
                new_comments = json.loads(parsed["comments_json"])
                new_annotations = json.loads(parsed["annotations_json"])

                # Detect new identifications
                old_id_set = {i["id"] for i in old_ids if i.get("id")}
                for ident in new_ids:
                    if ident.get("id") and ident["id"] not in old_id_set and ident.get("current"):
                        event = _make_event(
                            "identification",
                            ident.get("user_login"),
                            ident.get("user_name", ""),
                            ident.get("user_icon", ""),
                            obs_id,
                            {
                                "taxon_name": ident.get("taxon_name"),
                                "taxon_rank": ident.get("taxon_rank"),
                                "category": ident.get("category", ""),
                            },
                        )
                        all_events.append(event)

                # Detect new comments
                old_comment_ids = {c["id"] for c in old_comments if c.get("id")}
                for comment in new_comments:
                    if comment.get("id") and comment["id"] not in old_comment_ids:
                        event = _make_event(
                            "comment",
                            comment.get("user_login"),
                            comment.get("user_name", ""),
                            comment.get("user_icon", ""),
                            obs_id,
                            {"body": comment.get("body", "")[:200]},
                        )
                        all_events.append(event)

                # Detect taxon moves
                if parsed["taxon_id"] and parsed["taxon_id"] != old_taxon_id:
                    # Find the latest identification that caused the move
                    latest_ident = new_ids[-1] if new_ids else {}
                    event = _make_event(
                        "taxon_move",
                        latest_ident.get("user_login"),
                        latest_ident.get("user_name", ""),
                        latest_ident.get("user_icon", ""),
                        obs_id,
                        {
                            "from_taxon": old_taxon_id,
                            "to_taxon_name": parsed["taxon_name"],
                            "to_taxon_rank": parsed["taxon_rank"],
                        },
                    )
                    all_events.append(event)

                # Detect new annotations
                old_ann_ids = {a["id"] for a in old_annotations if a.get("id")}
                for ann in new_annotations:
                    if ann.get("id") and ann["id"] not in old_ann_ids:
                        event = _make_event(
                            "annotation_added",
                            ann.get("user_login"),
                            ann.get("user_name", ""),
                            ann.get("user_icon", ""),
                            obs_id,
                            {
                                "attribute": ann.get("attribute_label"),
                                "value": ann.get("value_label"),
                            },
                        )
                        all_events.append(event)

                # Detect quality grade change
                if parsed["quality_grade"] != old_quality:
                    event = _make_event(
                        "quality_change",
                        None,
                        "",
                        "",
                        obs_id,
                        {
                            "from": old_quality,
                            "to": parsed["quality_grade"],
                        },
                    )
                    all_events.append(event)

                # Update stored state
                resolved = 1 if parsed["quality_grade"] == "research" else 0
                await db.execute(
                    """UPDATE observations SET
                        taxon_id = ?, taxon_name = ?, taxon_rank = ?,
                        quality_grade = ?,
                        current_ids_json = ?, current_comments_json = ?,
                        current_annotations = ?,
                        resolved = ?, updated_at = ?
                       WHERE obs_id = ?""",
                    (
                        parsed["taxon_id"],
                        parsed["taxon_name"],
                        parsed["taxon_rank"],
                        parsed["quality_grade"],
                        parsed["ids_json"],
                        parsed["comments_json"],
                        parsed["annotations_json"],
                        resolved,
                        datetime.now(timezone.utc).isoformat(),
                        obs_id,
                    ),
                )

            await db.commit()
        finally:
            await db.close()

    # Now store events with participant attribution
    if all_events:
        await _store_events(all_events)

    logger.info(f"Diff cycle complete: {len(all_events)} events detected")
    return all_events


async def _store_events(events: list[dict]) -> None:
    """Store events in the database with participant attribution.

    Any user who appears in an event is automatically registered as a
    participant (no pre-registration required).
    """
    db = await get_db()
    try:
        # Load known participants
        cursor = await db.execute("SELECT login, team_id FROM participants")
        rows = await cursor.fetchall()
        participants = {row[0].lower(): row[1] for row in rows}

        for event in events:
            login = (event.get("actor_login") or "").lower()
            if not login:
                # System events (quality_change) have no actor
                await _insert_event(db, event, team_id=None, is_participant=0)
                continue

            # Auto-register new participants
            if login not in participants:
                await db.execute(
                    """INSERT OR IGNORE INTO participants (user_id, login, name, icon_url)
                       VALUES (
                           (SELECT COALESCE(MAX(user_id), 0) + 1 FROM participants),
                           ?, ?, ?
                       )""",
                    (login, event.get("actor_name", ""), event.get("actor_icon_url", "")),
                )
                participants[login] = None  # No team

            team_id = participants.get(login)
            await _insert_event(db, event, team_id=team_id, is_participant=1)

        await db.commit()
    finally:
        await db.close()


async def _insert_event(db, event: dict, team_id, is_participant: int) -> None:
    await db.execute(
        """INSERT INTO events
           (event_type, actor_login, actor_name, actor_icon_url,
            actor_team_id, is_participant, obs_id, detail_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event["event_type"],
            event.get("actor_login"),
            event.get("actor_name", ""),
            event.get("actor_icon_url", ""),
            team_id,
            is_participant,
            event.get("obs_id"),
            json.dumps(event.get("detail", {})),
            event["created_at"],
        ),
    )


def _make_event(
    event_type: str,
    actor_login: str | None,
    actor_name: str,
    actor_icon_url: str,
    obs_id: int,
    detail: dict,
) -> dict:
    return {
        "event_type": event_type,
        "actor_login": actor_login,
        "actor_name": actor_name,
        "actor_icon_url": actor_icon_url,
        "obs_id": obs_id,
        "detail": detail,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
