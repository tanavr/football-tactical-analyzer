"""Adapter for the documented StatsBomb open-data JSON structure."""

import re
from typing import Any, Callable, Optional, TypeVar

from app.data.json_source import CachedJSONSource
from app.data.provider import DataFormatError, DataNotFoundError, FootballDataProvider
from app.models.football import Competition, Event, Match, Provenance, Season, Team

T = TypeVar("T")


def source_id(kind: str, value: Any) -> str:
    if type(value) is not int or value <= 0:
        raise ValueError(f"Invalid {kind} ID")
    return f"statsbomb:{kind}:{value}"


def raw_id(kind: str, value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(rf"statsbomb:{kind}:[1-9][0-9]*", value):
        raise DataNotFoundError(f"Invalid StatsBomb {kind} ID: {value!r}")
    return value.rsplit(":", 1)[1]


def normalize_competition(row: dict[str, Any], provenance: Provenance) -> Competition:
    return Competition(id=source_id("competition", row["competition_id"]),
                       name=row["competition_name"], country=row["country_name"],
                       gender=row["competition_gender"], provenance=provenance)


def normalize_season(row: dict[str, Any], provenance: Provenance) -> Season:
    return Season(id=source_id("season", row["season_id"]),
                  competition_id=source_id("competition", row["competition_id"]),
                  name=row["season_name"], provenance=provenance)


def normalize_match(row: dict[str, Any], provenance: Provenance) -> Match:
    def team(side: str) -> Team:
        value = row[f"{side}_team"]
        return Team(id=source_id("team", value[f"{side}_team_id"]),
                    name=value[f"{side}_team_name"], provenance=provenance)

    match = Match(id=source_id("match", row["match_id"]),
                  competition_id=source_id("competition", row["competition"]["competition_id"]),
                  season_id=source_id("season", row["season"]["season_id"]),
                  date=row["match_date"], home_team=team("home"), away_team=team("away"),
                  home_score=row.get("home_score"), away_score=row.get("away_score"),
                  event_status=row.get("match_status"), source_metadata=row.get("metadata", {}),
                  provenance=provenance)
    if match.home_team.id == match.away_team.id:
        raise ValueError("Home and away teams must differ")
    return match


def normalize_event(row: dict[str, Any], provenance: Provenance, match_id: str) -> Event:
    if not isinstance(row["id"], str) or not row["id"]:
        raise ValueError("Event ID must be a nonempty string")
    passing = row.get("pass")
    completed = None
    if isinstance(passing, dict):
        if "outcome" not in passing:
            completed = True  # StatsBomb documents omitted outcome as a completed pass.
        elif isinstance(passing["outcome"], dict):
            outcome = passing["outcome"].get("name")
            if outcome in {"Incomplete", "Out", "Pass Offside", "Injury Clearance"}:
                completed = False
            # Unknown/null outcomes stay unknown; never count them as success.
    pattern = row.get("play_pattern")
    pattern_name = pattern.get("name") if isinstance(pattern, dict) else None
    known_patterns = {"Regular Play", "From Corner", "From Free Kick", "From Throw In",
                      "From Counter", "Other", "From Goal Kick", "From Keeper", "From Kick Off"}
    duel = row.get("duel") or {}
    shot = row.get("shot") or {}
    if not isinstance(duel, dict) or not isinstance(shot, dict):
        raise ValueError("Shot and duel attributes must be objects")
    if duel.get("type") is not None and not isinstance(duel["type"], dict):
        raise ValueError("Duel type must be an object")
    duel_type = (duel.get("type") or {}).get("name")
    return Event(id=f"statsbomb:event:{row['id']}", match_id=match_id, index=row["index"],
                 type=row["type"]["name"], period=row["period"], minute=row["minute"],
                 second=row["second"],
                 team_id=source_id("team", row["team"]["id"]) if row.get("team") else None,
                 player_id=source_id("player", row["player"]["id"]) if row.get("player") else None,
                 location=row.get("location"), source_fields=row, provenance=provenance,
                 coordinate_system="attacking_120x80",
                 pass_end_location=passing.get("end_location") if isinstance(passing, dict) else None,
                 pass_completed=completed,
                 shot_xg=shot.get("statsbomb_xg"),
                 possession_id=str(row["possession"]) if row.get("possession") is not None else None,
                 possession_team_id=source_id("team", row["possession_team"]["id"])
                 if row.get("possession_team") else None,
                 from_counterattack=(pattern_name == "From Counter") if pattern_name in known_patterns else None,
                 is_tackle=(duel_type == "Tackle") if duel_type in {"Tackle", "Aerial Lost"} else None)


class StatsBombOpenDataProvider(FootballDataProvider):
    def __init__(self, source: Optional[CachedJSONSource] = None) -> None:
        self.source = source if source is not None else CachedJSONSource()

    def _load(self, path: str, normalize: Callable[[dict[str, Any], Provenance], T]) -> list[T]:
        rows, provenance = self.source.read(path)
        try:
            return [normalize(row, provenance) for row in rows]
        except (KeyError, TypeError, ValueError) as exc:
            raise DataFormatError(f"Invalid StatsBomb record in {path}: {exc}") from exc

    def get_competitions(self) -> list[Competition]:
        rows = self._load("competitions.json", normalize_competition)
        return list({row.id: row for row in rows}.values())

    def get_seasons(self, competition: str) -> list[Season]:
        raw_id("competition", competition)
        rows = self._load("competitions.json", normalize_season)
        selected = [row for row in rows if row.competition_id == competition]
        if not selected:
            raise DataNotFoundError(f"Unknown competition: {competition}")
        self._unique(selected)
        return selected

    def get_matches(self, competition: str, season: Season) -> list[Match]:
        self.validate_season(competition, season)
        path = f"matches/{raw_id('competition', competition)}/{raw_id('season', season.id)}.json"
        matches = self._load(path, normalize_match)
        self._unique(matches)
        if any(m.competition_id != competition or m.season_id != season.id for m in matches):
            raise DataFormatError("Match does not belong to the requested competition-season")
        return sorted(matches, key=lambda match: (match.date, match.id))

    def get_match_events(self, match_id: str) -> list[Event]:
        path = f"events/{raw_id('match', match_id)}.json"
        events = self._load(path, lambda row, provenance: normalize_event(row, provenance, match_id))
        self._unique(events)
        if len({event.index for event in events}) != len(events):
            raise DataFormatError("Duplicate event indices")
        return sorted(events, key=lambda event: event.index)

    @staticmethod
    def _unique(records: list[Any]) -> None:
        if len({record.id for record in records}) != len(records):
            raise DataFormatError("Duplicate record IDs")
