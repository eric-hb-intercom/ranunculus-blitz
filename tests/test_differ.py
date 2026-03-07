"""Tests for the diff worker logic."""

import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch

from app.database import init_db, set_db_path, get_db


@pytest_asyncio.fixture
async def db(tmp_path):
    """Create a temporary database for testing."""
    db_path = str(tmp_path / "test.db")
    set_db_path(db_path)
    await init_db()

    # Seed a participant
    conn = await get_db()
    await conn.execute(
        "INSERT INTO teams (team_id, name, color) VALUES (1, 'Test Team', '#ff0000')"
    )
    await conn.execute(
        "INSERT INTO participants (user_id, login, name, team_id) VALUES (1, 'alice', 'Alice', 1)"
    )
    await conn.commit()
    await conn.close()

    return db_path


async def _insert_obs(obs_id, ids_json="[]", comments_json="[]", annotations_json="[]",
                       taxon_id=47604, quality_grade="needs_id"):
    """Insert a test observation."""
    conn = await get_db()
    await conn.execute(
        """INSERT INTO observations
           (obs_id, taxon_id, taxon_name, taxon_rank, quality_grade,
            snapshot_taxon_id, snapshot_quality,
            current_ids_json, current_comments_json, current_annotations,
            lat, lng, resolved, updated_at)
           VALUES (?, ?, 'Ranunculus', 'genus', ?, ?, ?, ?, ?, ?, 51.5, -1.5, 0, '')""",
        (obs_id, taxon_id, quality_grade, taxon_id, quality_grade,
         ids_json, comments_json, annotations_json),
    )
    await conn.commit()
    await conn.close()


@pytest.mark.asyncio
async def test_detect_new_identification(db):
    """Diff should detect a new identification."""
    await _insert_obs(100)

    api_response = [{
        "id": 100,
        "quality_grade": "needs_id",
        "taxon": {"id": 47604, "name": "Ranunculus", "rank": "genus"},
        "geojson": {"coordinates": [-1.5, 51.5]},
        "photos": [],
        "identifications": [{
            "id": 999,
            "taxon": {"id": 47604, "name": "Ranunculus repens", "rank": "species"},
            "user": {"login": "alice", "name": "Alice", "icon_url": ""},
            "current": True,
            "created_at": "2025-06-15T10:00:00Z",
            "category": "improving",
        }],
        "comments": [],
        "annotations": [],
    }]

    with patch("app.workers.differ.fetch_observations_by_ids", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = api_response

        from app.workers.differ import run_diff_cycle
        events = await run_diff_cycle()

    assert len(events) >= 1
    id_events = [e for e in events if e["event_type"] == "identification"]
    assert len(id_events) == 1
    assert id_events[0]["actor_login"] == "alice"

    # Alice should have been auto-registered as a participant
    conn = await get_db()
    cursor = await conn.execute("SELECT login FROM participants WHERE login = 'alice'")
    assert await cursor.fetchone() is not None
    await conn.close()


@pytest.mark.asyncio
async def test_detect_new_comment(db):
    """Diff should detect a new comment."""
    await _insert_obs(101)

    api_response = [{
        "id": 101,
        "quality_grade": "needs_id",
        "taxon": {"id": 47604, "name": "Ranunculus", "rank": "genus"},
        "geojson": {"coordinates": [-1.5, 51.5]},
        "photos": [],
        "identifications": [],
        "comments": [{
            "id": 555,
            "user": {"login": "alice", "name": "Alice", "icon_url": ""},
            "body": "Looks like R. repens based on the leaf shape.",
            "created_at": "2025-06-15T11:00:00Z",
        }],
        "annotations": [],
    }]

    with patch("app.workers.differ.fetch_observations_by_ids", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = api_response

        from app.workers.differ import run_diff_cycle
        events = await run_diff_cycle()

    comment_events = [e for e in events if e["event_type"] == "comment"]
    assert len(comment_events) == 1
    assert "leaf shape" in comment_events[0]["detail"]["body"]


@pytest.mark.asyncio
async def test_detect_taxon_move(db):
    """Diff should detect when the community taxon changes."""
    await _insert_obs(102, taxon_id=47604)

    api_response = [{
        "id": 102,
        "quality_grade": "needs_id",
        "taxon": {"id": 77777, "name": "Ranunculus acris", "rank": "species"},
        "geojson": {"coordinates": [-1.5, 51.5]},
        "photos": [],
        "identifications": [{
            "id": 1001,
            "taxon": {"id": 77777, "name": "Ranunculus acris", "rank": "species"},
            "user": {"login": "alice", "name": "Alice", "icon_url": ""},
            "current": True,
            "created_at": "2025-06-15T12:00:00Z",
            "category": "improving",
        }],
        "comments": [],
        "annotations": [],
    }]

    with patch("app.workers.differ.fetch_observations_by_ids", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = api_response

        from app.workers.differ import run_diff_cycle
        events = await run_diff_cycle()

    move_events = [e for e in events if e["event_type"] == "taxon_move"]
    assert len(move_events) == 1
    assert move_events[0]["detail"]["to_taxon_name"] == "Ranunculus acris"


@pytest.mark.asyncio
async def test_detect_quality_change(db):
    """Diff should detect quality grade changes."""
    await _insert_obs(103, quality_grade="needs_id")

    api_response = [{
        "id": 103,
        "quality_grade": "research",
        "taxon": {"id": 47604, "name": "Ranunculus", "rank": "genus"},
        "geojson": {"coordinates": [-1.5, 51.5]},
        "photos": [],
        "identifications": [],
        "comments": [],
        "annotations": [],
    }]

    with patch("app.workers.differ.fetch_observations_by_ids", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = api_response

        from app.workers.differ import run_diff_cycle
        events = await run_diff_cycle()

    quality_events = [e for e in events if e["event_type"] == "quality_change"]
    assert len(quality_events) == 1
    assert quality_events[0]["detail"]["to"] == "research"

    # Verify observation is marked resolved
    conn = await get_db()
    cursor = await conn.execute(
        "SELECT resolved FROM observations WHERE obs_id = 103"
    )
    row = await cursor.fetchone()
    await conn.close()
    assert row[0] == 1


@pytest.mark.asyncio
async def test_detect_annotation(db):
    """Diff should detect new annotations."""
    await _insert_obs(104)

    api_response = [{
        "id": 104,
        "quality_grade": "needs_id",
        "taxon": {"id": 47604, "name": "Ranunculus", "rank": "genus"},
        "geojson": {"coordinates": [-1.5, 51.5]},
        "photos": [],
        "identifications": [],
        "comments": [],
        "annotations": [{
            "uuid": "ann-new",
            "controlled_attribute_id": 12,
            "controlled_value_id": 13,
            "user": {"login": "alice", "name": "Alice"},
        }],
    }]

    with patch("app.workers.differ.fetch_observations_by_ids", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = api_response

        from app.workers.differ import run_diff_cycle
        events = await run_diff_cycle()

    ann_events = [e for e in events if e["event_type"] == "annotation_added"]
    assert len(ann_events) == 1
    assert ann_events[0]["detail"]["value"] == "Flowering"


@pytest.mark.asyncio
async def test_deleted_observation(db):
    """Diff should mark observation resolved if missing from API response."""
    await _insert_obs(105)

    with patch("app.workers.differ.fetch_observations_by_ids", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = []

        from app.workers.differ import run_diff_cycle
        events = await run_diff_cycle()

    conn = await get_db()
    cursor = await conn.execute(
        "SELECT resolved FROM observations WHERE obs_id = 105"
    )
    row = await cursor.fetchone()
    await conn.close()
    assert row[0] == 1
