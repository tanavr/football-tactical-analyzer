"""API envelopes and independently reviewed coverage configuration."""

from typing import Literal, Optional

from pydantic import Field, PositiveInt

from app.models.football import Competition, Record, Season, Team


class CompetitionList(Record):
    competitions: list[Competition]


class SeasonList(Record):
    competition_id: str
    seasons: list[Season]


class TeamList(Record):
    competition_id: str
    season_id: str
    teams: list[Team]


class ErrorInfo(Record):
    code: str
    message: str


class ErrorResponse(Record):
    error: ErrorInfo


class SeasonCoverage(Record):
    competition_id: str
    season_id: str
    source: str
    data_kind: Literal["real", "sample"]
    match_data_sha256: str
    complete_event_sha256: dict[str, str] = Field(default_factory=dict)
    expected_matches: Optional[dict[str, PositiveInt]] = None
    evidence: str = Field(min_length=1)
