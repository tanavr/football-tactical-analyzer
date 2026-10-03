"""Source-independent records. IDs are namespaced by provider."""

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class Record(BaseModel):
    model_config = ConfigDict(frozen=True)


class Provenance(Record):
    source: str
    data_kind: Literal["real", "sample"]
    url: str
    retrieved_at: datetime
    revision: str
    sha256: str


class Competition(Record):
    id: str
    name: str
    country: str
    gender: str
    provenance: Provenance


class Season(Record):
    id: str
    competition_id: str
    name: str
    provenance: Provenance


class Team(Record):
    id: str
    name: str
    provenance: Provenance


class Match(Record):
    id: str
    competition_id: str
    season_id: str
    date: date
    home_team: Team
    away_team: Team
    home_score: Optional[int] = Field(default=None, ge=0)
    away_score: Optional[int] = Field(default=None, ge=0)
    event_status: Optional[str] = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance


class Event(Record):
    id: str
    match_id: str
    index: int = Field(ge=1)
    type: str
    period: int = Field(ge=1, le=5)
    minute: int = Field(ge=0)
    second: int = Field(ge=0, lt=60)
    team_id: Optional[str] = None
    player_id: Optional[str] = None
    location: Optional[tuple[float, float]] = None
    # Optional semantic fields populated by source adapters, never inferred by analytics.
    coordinate_system: Optional[Literal["attacking_120x80"]] = None
    pass_end_location: Optional[tuple[float, float]] = None
    pass_completed: Optional[bool] = None
    shot_xg: Optional[float] = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    possession_id: Optional[str] = None
    possession_team_id: Optional[str] = None
    from_counterattack: Optional[bool] = None
    is_tackle: Optional[bool] = None
    # Preserve provider-specific attributes without claiming they are standardized.
    source_fields: dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance
