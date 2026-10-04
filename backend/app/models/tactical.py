"""Inspectable scores and rule-based descriptions."""

from typing import Literal, Optional

from pydantic import Field

from app.models.football import Record


class TacticalConfig(Record):
    min_teams: int = Field(default=10, ge=3)
    min_matches: int = Field(default=10, ge=1)
    min_match_coverage: float = Field(default=.8, gt=0, le=1)
    min_roster_coverage: float = Field(default=.8, gt=0, le=1)


class TacticalScore(Record):
    value: Optional[float] = Field(default=None, ge=0, le=100)
    proxy: bool = False
    interpretation: str
    components: dict[str, float] = Field(default_factory=dict)
    raw_values: dict[str, float] = Field(default_factory=dict)
    cohort_team_ids: list[str] = Field(default_factory=list)
    eligible_match_ids: list[str] = Field(default_factory=list)
    excluded_teams: dict[str, str] = Field(default_factory=dict)
    constant_components: list[str] = Field(default_factory=list)
    reason: Optional[str] = None


class TacticalProfile(Record):
    team_id: str
    competition_id: str
    season_id: str
    model_version: str = "1.0.0"
    metrics_version: str
    source: str
    data_kind: Literal["real", "sample"]
    scores: dict[str, TacticalScore]
    primary_identity: str
    secondary_traits: list[str]
    explanation: str
    config: TacticalConfig
    expected_matches: dict[str, int]
    limitations: list[str]
