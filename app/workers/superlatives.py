"""Compute superlative awards from event data."""

import json
import logging
import math
import random
from collections import Counter, defaultdict
from datetime import datetime

from ..database import get_db
from .uk_geo import classify_observations

logger = logging.getLogger(__name__)


async def compute_superlatives() -> None:
    """Recompute all superlative awards from event data."""
    db = await get_db()
    try:
        # Clear existing superlatives
        await db.execute("DELETE FROM superlatives")

        # Load all participant events
        cursor = await db.execute(
            """SELECT event_type, actor_login, actor_name, actor_team_id,
                      obs_id, detail_json, created_at
               FROM events WHERE is_participant = 1
               ORDER BY created_at ASC"""
        )
        events = await cursor.fetchall()

        if not events:
            await db.commit()
            return

        # Load team info
        cursor = await db.execute("SELECT team_id, name FROM teams")
        teams = {row[0]: row[1] for row in await cursor.fetchall()}

        # Load observations for date/location data
        cursor = await db.execute(
            "SELECT obs_id, observed_on, lat, lng FROM observations"
        )
        obs_data = {
            row[0]: {"observed_on": row[1], "lat": row[2], "lng": row[3]}
            for row in await cursor.fetchall()
        }

        # --- Individual superlatives ---

        # Time Traveler: resolved the observation with the oldest observed_on
        id_events = [e for e in events if e[0] == "identification"]
        oldest_obs_date = None
        oldest_login = None
        oldest_name = None
        for e in id_events:
            obs_info = obs_data.get(e[4], {})
            obs_date = obs_info.get("observed_on")
            if obs_date:
                if oldest_obs_date is None or obs_date < oldest_obs_date:
                    oldest_obs_date = obs_date
                    oldest_login = e[1]
                    oldest_name = e[2]
        if oldest_login:
            await _insert_award(
                db, "individual", "time_traveler", "Time Traveler",
                oldest_login, oldest_name, None, None,
                f"Identified an observation from {oldest_obs_date}", 0,
            )

        # Flower Expert: most "Flowering" annotations
        annotation_events = [e for e in events if e[0] == "annotation_added"]
        flowering_counts: Counter = Counter()
        for e in annotation_events:
            detail = json.loads(e[5] or "{}")
            if detail.get("value") == "Flowering":
                flowering_counts[e[1]] += 1
        if flowering_counts:
            winner, count = flowering_counts.most_common(1)[0]
            name = _find_name(events, winner)
            await _insert_award(
                db, "individual", "flower_expert", "Flower Expert",
                winner, name, None, None,
                f"{count} flowering annotations", count,
            )

        # Leaf Expert: most "Budding" or other leaf annotations
        leaf_counts: Counter = Counter()
        for e in annotation_events:
            detail = json.loads(e[5] or "{}")
            if detail.get("value") in ("Budding", "Fruiting"):
                leaf_counts[e[1]] += 1
        if leaf_counts:
            winner, count = leaf_counts.most_common(1)[0]
            name = _find_name(events, winner)
            await _insert_award(
                db, "individual", "leaf_expert", "Leaf Expert",
                winner, name, None, None,
                f"{count} phenology annotations", count,
            )

        # Conversationalist: most comments
        comment_events = [e for e in events if e[0] == "comment"]
        comment_counts: Counter = Counter()
        for e in comment_events:
            comment_counts[e[1]] += 1
        if comment_counts:
            winner, count = comment_counts.most_common(1)[0]
            name = _find_name(events, winner)
            await _insert_award(
                db, "individual", "conversationalist", "Conversationalist",
                winner, name, None, None,
                f"{count} comments posted", count,
            )

        # Teaching Moment: most repeated comments (same body 3+ times)
        comment_bodies: dict[str, Counter] = defaultdict(Counter)
        for e in comment_events:
            detail = json.loads(e[5] or "{}")
            body = detail.get("body", "").strip()
            if len(body) > 10:  # Ignore very short comments
                comment_bodies[e[1]][body] += 1
        teaching_counts: Counter = Counter()
        for login, bodies in comment_bodies.items():
            teaching_counts[login] = sum(
                c for body, c in bodies.items() if c >= 3
            )
        teaching_counts = +teaching_counts  # Remove zeros
        if teaching_counts:
            winner, count = teaching_counts.most_common(1)[0]
            name = _find_name(events, winner)
            await _insert_award(
                db, "individual", "teaching_moment", "Teaching Moment",
                winner, name, None, None,
                f"{count} teaching comments (repeated 3+ times)", count,
            )

        # Genus Whisperer: most genus-level moves
        move_events = [e for e in events if e[0] == "taxon_move"]
        genus_counts: Counter = Counter()
        for e in move_events:
            detail = json.loads(e[5] or "{}")
            if detail.get("to_taxon_rank") == "genus":
                genus_counts[e[1]] += 1
        if genus_counts:
            winner, count = genus_counts.most_common(1)[0]
            name = _find_name(events, winner)
            await _insert_award(
                db, "individual", "genus_whisperer", "Genus Whisperer",
                winner, name, None, None,
                f"{count} genus-level moves", count,
            )

        # First on the Scene: first participant ID after blitz start
        if id_events:
            first = id_events[0]
            await _insert_award(
                db, "individual", "first_on_scene", "First on the Scene",
                first[1], first[2], None, None,
                f"First identification at {first[6][:19]}", 0,
            )

        # Most Identifications (bonus)
        id_counts: Counter = Counter()
        for e in id_events:
            id_counts[e[1]] += 1
        if id_counts:
            winner, count = id_counts.most_common(1)[0]
            name = _find_name(events, winner)
            await _insert_award(
                db, "individual", "top_identifier", "Top Identifier",
                winner, name, None, None,
                f"{count} identifications", count,
            )

        # --- Team superlatives ---

        # Team Spirit: most even distribution of contributions
        team_member_counts: dict[int, Counter] = defaultdict(Counter)
        for e in events:
            if e[3]:  # has team_id
                team_member_counts[e[3]][e[1]] += 1

        best_evenness = -1.0
        best_team_id = None
        for team_id, member_counts in team_member_counts.items():
            if len(member_counts) < 2:
                continue
            # Use normalized entropy as evenness measure (0 = one person did everything, 1 = perfectly even)
            total = sum(member_counts.values())
            n = len(member_counts)
            entropy = -sum(
                (c / total) * math.log(c / total) for c in member_counts.values()
            )
            max_entropy = math.log(n)
            evenness = entropy / max_entropy if max_entropy > 0 else 0
            if evenness > best_evenness:
                best_evenness = evenness
                best_team_id = team_id

        if best_team_id:
            await _insert_award(
                db, "team", "team_spirit", "Team Spirit",
                None, None, best_team_id, teams.get(best_team_id, ""),
                f"Most even contribution distribution ({best_evenness:.0%} evenness)", best_evenness,
            )

        # Most Ground Covered: team whose IDs span largest geographic area
        team_coords: dict[int, list[tuple[float, float]]] = defaultdict(list)
        for e in id_events:
            if e[3]:  # has team_id
                obs_info = obs_data.get(e[4], {})
                lat, lng = obs_info.get("lat"), obs_info.get("lng")
                if lat and lng:
                    team_coords[e[3]].append((lat, lng))

        best_area = 0.0
        best_area_team = None
        for team_id, coords in team_coords.items():
            if len(coords) < 2:
                continue
            # Bounding box area as proxy for geographic spread
            lats = [c[0] for c in coords]
            lngs = [c[1] for c in coords]
            area = (max(lats) - min(lats)) * (max(lngs) - min(lngs))
            if area > best_area:
                best_area = area
                best_area_team = team_id

        if best_area_team:
            await _insert_award(
                db, "team", "most_ground_covered", "Most Ground Covered",
                None, None, best_area_team, teams.get(best_area_team, ""),
                f"Identifications spanning the largest area", best_area,
            )

        # --- Bonus geographic awards ---
        cursor = await db.execute(
            "SELECT value FROM blitz_config WHERE key = 'started_at'"
        )
        row = await cursor.fetchone()
        seed_str = row[0] if row else "default"

        candidates = _compute_bonus_awards(
            events, id_events, obs_data, teams,
        )
        selected = _select_bonus_awards(candidates, seed_str)
        for award in selected:
            await _insert_award(
                db,
                award["scope"],
                award["award_name"],
                award["award_title"],
                award.get("winner_login"),
                award.get("winner_name"),
                award.get("winner_team_id"),
                award.get("team_name"),
                award["detail"],
                award["value"],
            )

        await db.commit()
    finally:
        await db.close()


def _find_name(events: list, login: str) -> str:
    """Find the display name for a login from event data."""
    for e in events:
        if e[1] == login and e[2]:
            return e[2]
    return login or ""


async def _insert_award(
    db, scope, award_name, award_title,
    winner_login, winner_name, winner_team_id, team_name,
    detail, value,
) -> None:
    await db.execute(
        """INSERT INTO superlatives
           (scope, award_name, award_title, winner_login, winner_name,
            winner_team_id, team_name, detail, value)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (scope, award_name, award_title, winner_login, winner_name,
         winner_team_id, team_name, detail, value),
    )


# ---------------------------------------------------------------------------
# Bonus geographic awards
# ---------------------------------------------------------------------------

def _compute_bonus_awards(
    events: list,
    id_events: list,
    obs_data: dict,
    teams: dict,
) -> list[dict]:
    """Compute all candidate bonus awards from geographic data.

    Returns a list of candidate dicts, each with keys:
      scope, award_name, award_title, winner_login, winner_name,
      winner_team_id, team_name, detail, value
    """
    geo = classify_observations(obs_data)
    candidates: list[dict] = []

    # --- Compass extremes (individual) ---
    # Find the observation at each extreme and who identified it
    best_north = (None, None, None, -90.0)   # (login, name, obs_id, lat)
    best_south = (None, None, None, 90.0)
    best_east = (None, None, None, -180.0)   # (login, name, obs_id, lng)
    best_west = (None, None, None, 180.0)

    for e in id_events:
        obs_info = obs_data.get(e[4], {})
        lat, lng = obs_info.get("lat"), obs_info.get("lng")
        if lat is None or lng is None:
            continue
        if lat > best_north[3]:
            best_north = (e[1], e[2], e[4], lat)
        if lat < best_south[3]:
            best_south = (e[1], e[2], e[4], lat)
        if lng > best_east[3]:
            best_east = (e[1], e[2], e[4], lng)
        if lng < best_west[3]:
            best_west = (e[1], e[2], e[4], lng)

    if best_north[0]:
        candidates.append({
            "scope": "bonus_individual", "award_name": "north_star",
            "award_title": "North Star",
            "winner_login": best_north[0], "winner_name": best_north[1],
            "winner_team_id": None, "team_name": None,
            "detail": f"ID'd the most northerly observation ({best_north[3]:.2f}°N)",
            "value": best_north[3],
        })
    if best_south[0]:
        candidates.append({
            "scope": "bonus_individual", "award_name": "gone_south",
            "award_title": "Gone South",
            "winner_login": best_south[0], "winner_name": best_south[1],
            "winner_team_id": None, "team_name": None,
            "detail": f"ID'd the most southerly observation ({best_south[3]:.2f}°N)",
            "value": best_south[3],
        })
    if best_east[0]:
        candidates.append({
            "scope": "bonus_individual", "award_name": "far_east_feast",
            "award_title": "Far East Feast",
            "winner_login": best_east[0], "winner_name": best_east[1],
            "winner_team_id": None, "team_name": None,
            "detail": f"ID'd the most easterly observation ({best_east[3]:.2f}°)",
            "value": best_east[3],
        })
    if best_west[0]:
        candidates.append({
            "scope": "bonus_individual", "award_name": "wild_west",
            "award_title": "Wild Wild West",
            "winner_login": best_west[0], "winner_name": best_west[1],
            "winner_team_id": None, "team_name": None,
            "detail": f"ID'd the most westerly observation ({best_west[3]:.2f}°)",
            "value": best_west[3],
        })

    # --- City / Park / Territory specialists (individual) ---
    city_counts: Counter = Counter()
    park_counts: Counter = Counter()
    territory_counts: dict[str, Counter] = {
        "England": Counter(),
        "Scotland": Counter(),
        "Wales": Counter(),
        "Northern Ireland": Counter(),
    }
    # Per-individual territory set
    individual_territories: dict[str, set] = defaultdict(set)
    # Per-team territory set
    team_territories: dict[int, set] = defaultdict(set)

    for e in id_events:
        obs_geo = geo.get(e[4], {})
        if obs_geo.get("is_city"):
            city_counts[e[1]] += 1
        if obs_geo.get("is_national_park"):
            park_counts[e[1]] += 1
        territory = obs_geo.get("territory")
        if territory and territory in territory_counts:
            territory_counts[territory][e[1]] += 1
            individual_territories[e[1]].add(territory)
            if e[3]:  # has team_id
                team_territories[e[3]].add(territory)

    if city_counts:
        winner, count = city_counts.most_common(1)[0]
        candidates.append({
            "scope": "bonus_individual", "award_name": "city_slicker",
            "award_title": "City Slicker",
            "winner_login": winner, "winner_name": _find_name(events, winner),
            "winner_team_id": None, "team_name": None,
            "detail": f"{count} IDs on city observations",
            "value": count,
        })

    if park_counts:
        winner, count = park_counts.most_common(1)[0]
        candidates.append({
            "scope": "bonus_individual", "award_name": "park_life",
            "award_title": "Park Life",
            "winner_login": winner, "winner_name": _find_name(events, winner),
            "winner_team_id": None, "team_name": None,
            "detail": f"{count} IDs on national park observations",
            "value": count,
        })

    territory_awards = [
        ("England", "england_expects", "England Expects"),
        ("Scotland", "braveheart", "Braveheart"),
        ("Wales", "dragon_tamer", "Dragon Tamer"),
        ("Northern Ireland", "giants_cause", "Giant's Cause"),
    ]
    for territory, award_name, award_title in territory_awards:
        counts = territory_counts[territory]
        if counts:
            winner, count = counts.most_common(1)[0]
            candidates.append({
                "scope": "bonus_individual", "award_name": award_name,
                "award_title": award_title,
                "winner_login": winner, "winner_name": _find_name(events, winner),
                "winner_team_id": None, "team_name": None,
                "detail": f"{count} IDs on {territory} observations",
                "value": count,
            })

    # --- Border Hopper (individual) — most distinct territories ---
    if individual_territories:
        best_login = max(individual_territories, key=lambda k: len(individual_territories[k]))
        n_territories = len(individual_territories[best_login])
        if n_territories >= 2:
            candidates.append({
                "scope": "bonus_individual", "award_name": "border_hopper",
                "award_title": "Border Hopper",
                "winner_login": best_login,
                "winner_name": _find_name(events, best_login),
                "winner_team_id": None, "team_name": None,
                "detail": f"IDs spanning {n_territories} territories",
                "value": n_territories,
            })

    # --- United Kingdom (team) — most distinct territories ---
    if team_territories:
        best_team = max(team_territories, key=lambda k: len(team_territories[k]))
        n_territories = len(team_territories[best_team])
        if n_territories >= 2:
            candidates.append({
                "scope": "bonus_team", "award_name": "united_kingdom",
                "award_title": "United Kingdom",
                "winner_login": None, "winner_name": None,
                "winner_team_id": best_team,
                "team_name": teams.get(best_team, ""),
                "detail": f"IDs spanning {n_territories} territories",
                "value": n_territories,
            })

    return candidates


def _select_bonus_awards(
    candidates: list[dict],
    seed_str: str,
    total: int = 5,
) -> list[dict]:
    """Select bonus awards from candidates with seeded randomness.

    Picks 1 team + up to 4 individual awards (or fewer if not enough
    candidates).  Prefers unique winners for diversity.
    """
    if not candidates:
        return []

    rng = random.Random(seed_str)

    team_candidates = [c for c in candidates if c["scope"] == "bonus_team"]
    indiv_candidates = [c for c in candidates if c["scope"] == "bonus_individual"]

    selected: list[dict] = []
    winners_seen: set[str] = set()

    # Pick 1 team award
    if team_candidates:
        rng.shuffle(team_candidates)
        selected.append(team_candidates[0])

    # Pick up to (total - len(selected)) individual awards with diversity
    want_indiv = total - len(selected)
    rng.shuffle(indiv_candidates)

    # First pass: prefer unique winners
    for c in indiv_candidates:
        if len(selected) - len([s for s in selected if s["scope"] == "bonus_team"]) >= want_indiv:
            break
        login = c.get("winner_login", "")
        if login not in winners_seen:
            selected.append(c)
            winners_seen.add(login)

    # Second pass: fill remaining slots regardless of winner uniqueness
    for c in indiv_candidates:
        if len(selected) - len([s for s in selected if s["scope"] == "bonus_team"]) >= want_indiv:
            break
        if c not in selected:
            selected.append(c)

    return selected
