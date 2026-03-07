"""Configuration from environment variables."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


# Default target species with their display colors
DEFAULT_SPECIES = [
    {"name": "Ranunculus repens", "common": "Creeping Buttercup", "color": "#d4a843"},
    {"name": "Ranunculus acris", "common": "Meadow Buttercup", "color": "#e6c832"},
    {"name": "Ranunculus bulbosus", "common": "Bulbous Buttercup", "color": "#c46a2b"},
]


@dataclass
class SpeciesConfig:
    name: str       # Scientific name
    common: str     # Common name
    color: str      # Hex color for map/UI
    taxon_id: int | None = None  # Resolved during snapshot


@dataclass
class TeamConfig:
    name: str
    color: str
    members: list[str]


@dataclass
class Settings:
    db_path: str = "blitz.db"
    place_id: int = 6857
    diff_interval: int = 90
    auto_snapshot: bool = False
    species: list[SpeciesConfig] = field(default_factory=list)
    teams: list[TeamConfig] = field(default_factory=list)


def load_settings() -> Settings:
    teams_json = os.environ.get("BLITZ_TEAMS", "[]")
    try:
        raw_teams = json.loads(teams_json)
    except json.JSONDecodeError:
        raw_teams = []

    teams = [
        TeamConfig(
            name=t.get("name", f"Team {i+1}"),
            color=t.get("color", "#4a7c3f"),
            members=[m.lower() for m in t.get("members", [])],
        )
        for i, t in enumerate(raw_teams)
    ]

    # Parse species config from env or use defaults
    species_json = os.environ.get("BLITZ_SPECIES", "")
    if species_json:
        try:
            raw_species = json.loads(species_json)
        except json.JSONDecodeError:
            raw_species = DEFAULT_SPECIES
    else:
        raw_species = DEFAULT_SPECIES

    species = [
        SpeciesConfig(
            name=s.get("name", ""),
            common=s.get("common", ""),
            color=s.get("color", "#888888"),
        )
        for s in raw_species
    ]

    return Settings(
        db_path=os.environ.get("BLITZ_DB_PATH", "blitz.db"),
        place_id=int(os.environ.get("BLITZ_PLACE_ID", "6857")),
        diff_interval=int(os.environ.get("BLITZ_DIFF_INTERVAL", "90")),
        auto_snapshot=os.environ.get("BLITZ_AUTO_SNAPSHOT", "").lower() == "true",
        species=species,
        teams=teams,
    )
