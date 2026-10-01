"""Tiny synthetic dataset for offline development; not real football statistics."""

from datetime import datetime, timezone

from app.data.provider import DataNotFoundError, FootballDataProvider
from app.models.football import Competition, Event, Match, Provenance, Season, Team


class FixtureFootballDataProvider(FootballDataProvider):
    def __init__(self) -> None:
        provenance = Provenance(source="fixture", data_kind="sample", url="fixture://demo",
                                retrieved_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                                revision="1", sha256="not-applicable-synthetic")
        self._competition = Competition(id="fixture:competition:1", name="Sample League",
                                        country="Sample", gender="unspecified", provenance=provenance)
        self._season = Season(id="fixture:season:1", competition_id=self._competition.id,
                              name="Sample Season", provenance=provenance)
        home = Team(id="fixture:team:1", name="Sample North", provenance=provenance)
        away = Team(id="fixture:team:2", name="Sample South", provenance=provenance)
        self._match = Match(id="fixture:match:1", competition_id=self._competition.id,
                            season_id=self._season.id, date="2026-01-01", home_team=home,
                            away_team=away, home_score=1, away_score=0,
                            event_status="sample", provenance=provenance)
        self._event = Event(id="fixture:event:1", match_id=self._match.id, index=1,
                            type="Pass", period=1, minute=0, second=1, team_id=home.id,
                            provenance=provenance)

    def get_competitions(self) -> list[Competition]:
        return [self._competition.model_copy(deep=True)]

    def get_seasons(self, competition: str) -> list[Season]:
        if competition != self._competition.id:
            raise DataNotFoundError(f"Unknown fixture competition: {competition}")
        return [self._season.model_copy(deep=True)]

    def get_matches(self, competition: str, season: Season) -> list[Match]:
        self.validate_season(competition, season)
        return [self._match.model_copy(deep=True)]

    def get_match_events(self, match_id: str) -> list[Event]:
        if match_id != self._match.id:
            raise DataNotFoundError(f"Unknown fixture match: {match_id}")
        return [self._event.model_copy(deep=True)]
