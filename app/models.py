"""Pydantic response models for API endpoints."""

from typing import Dict, List, Optional

from pydantic import BaseModel


class SpeciesBreakdown(BaseModel):
    name: str
    common: str = ""
    color: str = "#888888"
    total: int = 0
    resolved: int = 0


class OverviewResponse(BaseModel):
    total_observations: int = 0
    resolved_count: int = 0
    pct_complete: float = 0.0
    elapsed_seconds: int = 0
    blitz_status: str = "setup"  # setup | ready | live | ended
    species: List[SpeciesBreakdown] = []


class ParticipantStats(BaseModel):
    login: str
    name: str
    icon_url: str
    team_id: Optional[int] = None
    team_name: Optional[str] = None
    team_color: Optional[str] = None
    identifications: int = 0
    comments: int = 0
    taxon_moves: int = 0
    annotations: int = 0
    total: int = 0


class TeamStats(BaseModel):
    team_id: int
    name: str
    color: str
    identifications: int = 0
    comments: int = 0
    taxon_moves: int = 0
    annotations: int = 0
    total: int = 0
    members: List[ParticipantStats] = []


class ObservationSummary(BaseModel):
    obs_id: int
    observed_on: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    photo_url: Optional[str] = None
    taxon_name: Optional[str] = None
    taxon_rank: Optional[str] = None
    quality_grade: Optional[str] = None
    species_group: Optional[str] = None
    species_color: Optional[str] = None
    resolved: bool = False


class EventItem(BaseModel):
    event_id: int
    event_type: str
    actor_login: Optional[str] = None
    actor_name: Optional[str] = None
    actor_icon_url: Optional[str] = None
    actor_team_id: Optional[int] = None
    is_participant: bool = False
    obs_id: Optional[int] = None
    detail: Dict = {}
    created_at: str = ""
    species_group: Optional[str] = None


class SuperlativeAward(BaseModel):
    scope: str
    award_name: str
    award_title: str
    winner_login: Optional[str] = None
    winner_name: Optional[str] = None
    winner_team_id: Optional[int] = None
    team_name: Optional[str] = None
    detail: Optional[str] = None
    value: float = 0


class MapMarker(BaseModel):
    obs_id: int
    lat: float
    lng: float
    photo_url: Optional[str] = None
    taxon_name: Optional[str] = None
    quality_grade: Optional[str] = None
    species_group: Optional[str] = None
    species_color: Optional[str] = None
    resolved: bool = False
    observed_on: Optional[str] = None
    updated_at: Optional[str] = None


class BlitzStatus(BaseModel):
    status: str  # setup | ready | live | ended
    species: List[SpeciesBreakdown] = []
    place_id: int = 6857
    total_observations: int = 0
    started_at: Optional[str] = None
    ended_at: Optional[str] = None


