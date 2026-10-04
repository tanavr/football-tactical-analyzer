"""Provider contract and common discovery operations; no analytics or HTTP routes."""

from abc import ABC, abstractmethod

from app.models.football import Competition, Event, Match, Season, Team


class DataProviderError(Exception):
    """Base error for callers of the data layer."""


class DataNotFoundError(DataProviderError):
    """The requested identifier or public resource is unavailable."""


class DataNetworkError(DataProviderError):
    """The source could not be reached or returned a server error."""


class DataFormatError(DataProviderError):
    """The source or cache contains invalid data."""


class DataCacheError(DataProviderError):
    """Local cache access failed."""


class DataNotPreparedError(DataProviderError):
    """A required resource has not been downloaded for offline serving."""


class FootballDataProvider(ABC):
    @abstractmethod
    def get_competitions(self) -> list[Competition]:
        """Return available competitions, once per ID."""

    @abstractmethod
    def get_seasons(self, competition: str) -> list[Season]:
        """Return seasons within a competition ID."""

    @abstractmethod
    def get_matches(self, competition: str, season: Season) -> list[Match]:
        """Return available matches, not necessarily a full schedule."""

    @abstractmethod
    def get_match_events(self, match_id: str) -> list[Event]:
        """Return events in source order; unavailable data raises an error."""

    def get_teams(self, competition: str, season: Season) -> list[Team]:
        teams = {team.id: team for match in self.get_matches(competition, season)
                 for team in (match.home_team, match.away_team)}
        return sorted(teams.values(), key=lambda team: (team.name, team.id))

    def get_team_matches(self, team: str, season: Season) -> list[Match]:
        matches = self.get_matches(season.competition_id, season)
        selected = [match for match in matches
                    if team in (match.home_team.id, match.away_team.id)]
        if not selected:
            raise DataNotFoundError(f"Team {team!r} is not present in this season's available matches")
        return selected

    def validate_season(self, competition: str, season: Season) -> None:
        if season.competition_id != competition:
            raise DataNotFoundError("Season belongs to a different competition")
        if season.id not in {item.id for item in self.get_seasons(competition)}:
            raise DataNotFoundError(f"Unknown season: {season.id}")
