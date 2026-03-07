"""Tests for iNat API response parsers."""

import json
import pytest
from app.inat.parsers import (
    parse_observation,
    parse_identifications,
    parse_comments,
    parse_annotations,
)


def _make_obs(**overrides):
    """Build a minimal iNat observation dict."""
    obs = {
        "id": 12345,
        "observed_on": "2025-06-15",
        "quality_grade": "needs_id",
        "geojson": {"coordinates": [-1.5, 51.5]},
        "taxon": {
            "id": 47604,
            "name": "Ranunculus repens",
            "rank": "species",
        },
        "photos": [
            {"url": "https://inaturalist-open-data.s3.amazonaws.com/photos/12345/square.jpg"}
        ],
        "identifications": [],
        "comments": [],
        "annotations": [],
    }
    obs.update(overrides)
    return obs


class TestParseObservation:
    def test_basic_fields(self):
        obs = _make_obs()
        parsed = parse_observation(obs)
        assert parsed["obs_id"] == 12345
        assert parsed["observed_on"] == "2025-06-15"
        assert parsed["lat"] == 51.5
        assert parsed["lng"] == -1.5
        assert parsed["taxon_id"] == 47604
        assert parsed["taxon_name"] == "Ranunculus repens"
        assert parsed["quality_grade"] == "needs_id"

    def test_photo_url_upgrade(self):
        obs = _make_obs()
        parsed = parse_observation(obs)
        assert "medium" in parsed["photo_url"]
        assert "square" not in parsed["photo_url"]

    def test_no_photos(self):
        obs = _make_obs(photos=[])
        parsed = parse_observation(obs)
        assert parsed["photo_url"] is None

    def test_location_from_string(self):
        obs = _make_obs(geojson=None, location="52.0, -0.5")
        parsed = parse_observation(obs)
        assert parsed["lat"] == 52.0
        assert parsed["lng"] == -0.5

    def test_no_location(self):
        obs = _make_obs(geojson=None)
        parsed = parse_observation(obs)
        assert parsed["lat"] is None
        assert parsed["lng"] is None

    def test_ids_json_is_valid(self):
        obs = _make_obs(identifications=[
            {
                "id": 100,
                "taxon": {"id": 47604, "name": "Ranunculus repens", "rank": "species"},
                "user": {"login": "alice", "name": "Alice", "icon_url": ""},
                "current": True,
                "created_at": "2025-06-15T10:00:00Z",
                "category": "improving",
            }
        ])
        parsed = parse_observation(obs)
        ids = json.loads(parsed["ids_json"])
        assert len(ids) == 1
        assert ids[0]["user_login"] == "alice"
        assert ids[0]["taxon_name"] == "Ranunculus repens"

    def test_comments_json(self):
        obs = _make_obs(comments=[
            {
                "id": 200,
                "user": {"login": "bob", "name": "Bob", "icon_url": ""},
                "body": "Great find!",
                "created_at": "2025-06-15T11:00:00Z",
            }
        ])
        parsed = parse_observation(obs)
        comments = json.loads(parsed["comments_json"])
        assert len(comments) == 1
        assert comments[0]["body"] == "Great find!"

    def test_empty_comments_skipped(self):
        obs = _make_obs(comments=[
            {"id": 201, "user": {"login": "x"}, "body": ""},
            {"id": 202, "user": {"login": "y"}, "body": "   "},
        ])
        parsed = parse_observation(obs)
        comments = json.loads(parsed["comments_json"])
        assert len(comments) == 0


class TestParseAnnotations:
    def test_flowering_annotation(self):
        obs = _make_obs(annotations=[
            {
                "uuid": "ann-1",
                "controlled_attribute_id": 12,
                "controlled_value_id": 13,
                "user": {"login": "carol", "name": "Carol"},
            }
        ])
        annotations = parse_annotations(obs)
        assert len(annotations) == 1
        assert annotations[0]["attribute_label"] == "Plant Phenology"
        assert annotations[0]["value_label"] == "Flowering"
        assert annotations[0]["user_login"] == "carol"
