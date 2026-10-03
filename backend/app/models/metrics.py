"""Inputs and outputs for deterministic raw metrics, not tactical scores."""

from typing import Literal, Optional

from pydantic import Field

from app.models.football import Event, Provenance, Record


class MatchEvents(Record):
    events: list[Event]
    complete: bool = False
    # The caller must attest that this is a full match event feed, not a filtered slice.


class Metric(Record):
    value: Optional[float] = None
    unit: str
    numerator: float = 0
    denominator: float = 0
    eligible_match_ids: list[str] = Field(default_factory=list)
    excluded_matches: dict[str, str] = Field(default_factory=dict)
    status: Literal["available", "partial", "unavailable"]
    reason: Optional[str] = None


class TeamSeasonProfile(Record):
    team_id: str
    competition_id: str
    season_id: str
    matches_played: int
    match_ids: list[str]
    metrics_version: str = "1.0.0"
    metrics: dict[str, Metric]
    provenance: list[Provenance]
    notes: list[str]
