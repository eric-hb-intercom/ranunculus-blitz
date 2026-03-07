"""Tests for superlative award computation."""

import json
import pytest
import pytest_asyncio

from app.database import init_db, set_db_path, get_db
from app.workers.superlatives import (
    compute_superlatives,
    _compute_bonus_awards,
    _select_bonus_awards,
)


@pytest_asyncio.fixture
async def db(tmp_path):
    """Create a temporary database with test data."""
    db_path = str(tmp_path / "test_sup.db")
    set_db_path(db_path)
    await init_db()

    conn = await get_db()

    # Create teams
    await conn.execute("INSERT INTO teams (team_id, name, color) VALUES (1, 'Buttercups', '#d4a843')")
    await conn.execute("INSERT INTO teams (team_id, name, color) VALUES (2, 'Meadows', '#4a7c3f')")

    # Create participants
    await conn.execute("INSERT INTO participants (user_id, login, name, team_id) VALUES (1, 'alice', 'Alice', 1)")
    await conn.execute("INSERT INTO participants (user_id, login, name, team_id) VALUES (2, 'bob', 'Bob', 1)")
    await conn.execute("INSERT INTO participants (user_id, login, name, team_id) VALUES (3, 'carol', 'Carol', 2)")

    # Create observations with different dates and locations
    for i, (obs_date, lat, lng) in enumerate([
        ("2020-05-10", 51.5, -1.0),
        ("2024-07-20", 53.0, -2.0),
        ("2019-03-15", 55.0, -3.0),
    ]):
        await conn.execute(
            """INSERT INTO observations (obs_id, observed_on, lat, lng, taxon_id, quality_grade, resolved)
               VALUES (?, ?, ?, ?, 47604, 'needs_id', 0)""",
            (1000 + i, obs_date, lat, lng),
        )

    # Insert events
    events = [
        # Alice: 5 identifications (including on oldest obs), 2 flowering annotations
        ("identification", "alice", "Alice", "", 1, 1, 1000, "{}", "2025-06-15T10:01:00Z"),
        ("identification", "alice", "Alice", "", 1, 1, 1001, "{}", "2025-06-15T10:05:00Z"),
        ("identification", "alice", "Alice", "", 1, 1, 1002, "{}", "2025-06-15T10:10:00Z"),
        ("identification", "alice", "Alice", "", 1, 1, 1000, "{}", "2025-06-15T10:15:00Z"),
        ("identification", "alice", "Alice", "", 1, 1, 1001, "{}", "2025-06-15T10:20:00Z"),
        ("annotation_added", "alice", "Alice", "", 1, 1, 1000, '{"attribute": "Plant Phenology", "value": "Flowering"}', "2025-06-15T10:02:00Z"),
        ("annotation_added", "alice", "Alice", "", 1, 1, 1001, '{"attribute": "Plant Phenology", "value": "Flowering"}', "2025-06-15T10:06:00Z"),

        # Bob: 3 identifications, 4 comments (3 teaching-style repeats)
        ("identification", "bob", "Bob", "", 1, 1, 1000, "{}", "2025-06-15T10:30:00Z"),
        ("identification", "bob", "Bob", "", 1, 1, 1001, "{}", "2025-06-15T10:35:00Z"),
        ("identification", "bob", "Bob", "", 1, 1, 1002, "{}", "2025-06-15T10:40:00Z"),
        ("comment", "bob", "Bob", "", 1, 1, 1000, '{"body": "This looks like R. repens based on the stolons and leaf shape pattern"}', "2025-06-15T10:31:00Z"),
        ("comment", "bob", "Bob", "", 1, 1, 1001, '{"body": "This looks like R. repens based on the stolons and leaf shape pattern"}', "2025-06-15T10:36:00Z"),
        ("comment", "bob", "Bob", "", 1, 1, 1002, '{"body": "This looks like R. repens based on the stolons and leaf shape pattern"}', "2025-06-15T10:41:00Z"),
        ("comment", "bob", "Bob", "", 1, 1, 1000, '{"body": "Nice photo!"}', "2025-06-15T10:32:00Z"),

        # Carol: 2 identifications (first one at 10:00), 1 genus move
        ("identification", "carol", "Carol", "", 2, 1, 1000, "{}", "2025-06-15T10:00:00Z"),
        ("identification", "carol", "Carol", "", 2, 1, 1002, "{}", "2025-06-15T11:00:00Z"),
        ("taxon_move", "carol", "Carol", "", 2, 1, 1001, '{"to_taxon_name": "Ranunculus", "to_taxon_rank": "genus"}', "2025-06-15T10:45:00Z"),
    ]

    for e in events:
        await conn.execute(
            """INSERT INTO events (event_type, actor_login, actor_name, actor_icon_url,
                                   actor_team_id, is_participant, obs_id, detail_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            e,
        )

    await conn.commit()
    await conn.close()
    return db_path


@pytest.mark.asyncio
async def test_computes_superlatives(db):
    """Verify superlatives are computed correctly."""
    await compute_superlatives()

    conn = await get_db()
    cursor = await conn.execute("SELECT award_name, winner_login, team_name, scope FROM superlatives")
    awards = {row[0]: {"winner": row[1], "team": row[2], "scope": row[3]} for row in await cursor.fetchall()}
    await conn.close()

    # Alice identified the oldest obs (2019-03-15, obs 1002)
    assert awards.get("time_traveler", {}).get("winner") == "alice"

    # Alice has most flowering annotations (2)
    assert awards.get("flower_expert", {}).get("winner") == "alice"

    # Bob has most comments (4)
    assert awards.get("conversationalist", {}).get("winner") == "bob"

    # Bob has teaching comments (same body 3 times)
    assert awards.get("teaching_moment", {}).get("winner") == "bob"

    # Carol has most genus moves (1)
    assert awards.get("genus_whisperer", {}).get("winner") == "carol"

    # Carol was first on the scene (10:00:00)
    assert awards.get("first_on_scene", {}).get("winner") == "carol"

    # Alice has most identifications (5)
    assert awards.get("top_identifier", {}).get("winner") == "alice"


@pytest.mark.asyncio
async def test_team_superlatives(db):
    """Verify team awards."""
    await compute_superlatives()

    conn = await get_db()
    cursor = await conn.execute(
        "SELECT award_name, team_name FROM superlatives WHERE scope = 'team'"
    )
    team_awards = {row[0]: row[1] for row in await cursor.fetchall()}
    await conn.close()

    # Team Spirit and Most Ground Covered should be present
    assert "team_spirit" in team_awards or "most_ground_covered" in team_awards


@pytest.mark.asyncio
async def test_no_events_no_crash(tmp_path):
    """Compute superlatives with no events — should not crash."""
    db_path = str(tmp_path / "empty.db")
    set_db_path(db_path)
    await init_db()
    await compute_superlatives()  # Should complete without error


# ---------------------------------------------------------------------------
# Bonus geographic award tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bonus_awards_computed(db):
    """Bonus geographic awards are inserted into the database."""
    await compute_superlatives()

    conn = await get_db()
    cursor = await conn.execute(
        "SELECT award_name, scope FROM superlatives WHERE scope LIKE 'bonus_%'"
    )
    bonus = {row[0]: row[1] for row in await cursor.fetchall()}
    await conn.close()

    # Should have exactly 5 bonus awards (1 team or 0 + up to 5 individual)
    assert len(bonus) == 5

    # Compass extremes should be among candidates (obs at 51.5, 53.0, 55.0)
    # North Star winner identified obs at lat 55.0
    assert any(name in bonus for name in ["north_star", "gone_south", "far_east_feast", "wild_west"])


@pytest.mark.asyncio
async def test_bonus_awards_deterministic(db):
    """Same seed produces same bonus award selection."""
    await compute_superlatives()

    conn = await get_db()
    cursor = await conn.execute(
        "SELECT award_name FROM superlatives WHERE scope LIKE 'bonus_%' ORDER BY award_name"
    )
    first_run = [row[0] for row in await cursor.fetchall()]
    await conn.close()

    # Recompute — should produce identical result
    await compute_superlatives()

    conn = await get_db()
    cursor = await conn.execute(
        "SELECT award_name FROM superlatives WHERE scope LIKE 'bonus_%' ORDER BY award_name"
    )
    second_run = [row[0] for row in await cursor.fetchall()]
    await conn.close()

    assert first_run == second_run


def test_select_bonus_awards_diversity():
    """Selection prefers unique winners."""
    candidates = [
        {"scope": "bonus_individual", "award_name": f"award_{i}",
         "award_title": f"Award {i}", "winner_login": f"user_{i % 3}",
         "winner_name": f"User {i % 3}", "winner_team_id": None,
         "team_name": None, "detail": "test", "value": i}
        for i in range(8)
    ]
    selected = _select_bonus_awards(candidates, "test-seed", total=5)
    assert len(selected) == 5

    winners = [s["winner_login"] for s in selected]
    # With 3 unique users among 8 candidates, all 3 should appear
    assert len(set(winners)) == 3


def test_select_bonus_awards_empty():
    """No crash on empty candidates."""
    assert _select_bonus_awards([], "seed") == []


def test_select_bonus_awards_with_team():
    """Selects 1 team + 4 individual when both are available."""
    candidates = [
        {"scope": "bonus_team", "award_name": "united_kingdom",
         "award_title": "United Kingdom", "winner_login": None,
         "winner_name": None, "winner_team_id": 1,
         "team_name": "Team A", "detail": "test", "value": 3},
    ] + [
        {"scope": "bonus_individual", "award_name": f"award_{i}",
         "award_title": f"Award {i}", "winner_login": f"user_{i}",
         "winner_name": f"User {i}", "winner_team_id": None,
         "team_name": None, "detail": "test", "value": i}
        for i in range(6)
    ]
    selected = _select_bonus_awards(candidates, "test-seed")
    assert len(selected) == 5

    team_awards = [s for s in selected if s["scope"] == "bonus_team"]
    indiv_awards = [s for s in selected if s["scope"] == "bonus_individual"]
    assert len(team_awards) == 1
    assert len(indiv_awards) == 4


def test_compute_bonus_awards_no_geo_data():
    """No crash when observations lack coordinates."""
    obs_data = {1: {"lat": None, "lng": None, "observed_on": "2024-01-01"}}
    # Simulate minimal event tuples: (type, login, name, team_id, obs_id, detail, created)
    events = [("identification", "alice", "Alice", 1, 1, "{}", "2025-01-01T00:00:00Z")]
    id_events = events
    teams = {1: "Team A"}

    candidates = _compute_bonus_awards(events, id_events, obs_data, teams)
    # No candidates should be generated — no valid coordinates
    assert candidates == []
