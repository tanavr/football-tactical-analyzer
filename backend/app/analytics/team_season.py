"""Pure season aggregation. Definitions and assumptions are in docs/METRICS.md."""

from collections import defaultdict
from math import fsum, hypot, isfinite
from typing import Mapping, Optional, Sequence

from app.models.football import Event, Match, Season
from app.models.metrics import MatchEvents, Metric, TeamSeasonProfile


class MetricsInputError(ValueError):
    """Records cannot safely be combined into a team-season profile."""


class MissingMetricData(ValueError):
    """A match lacks the observations required for a particular metric."""


UNITS = {
    "goals_for_per_match": "goals/match", "goals_against_per_match": "goals/match",
    "shots_per_match": "shots/match", "shots_conceded_per_match": "shots/match",
    "xg_per_match": "expected goals/match", "xg_conceded_per_match": "expected goals/match",
    "possession_pass_share_pct": "% of both teams' pass attempts (proxy)",
    "passes_attempted_per_match": "passes/match", "pass_completion_pct": "%",
    "passes_per_possession": "passes/possession",
    "average_pass_length": "120x80 pitch units/pass",
    "net_forward_progression_per_pass": "120x80 x-units/pass",
    "defensive_actions_per_match": "actions/match",
    "advanced_defensive_actions_per_match": "actions/match",
    "attacking_third_activity_per_match": "actions/match",
    "counterattack_possession_share_pct": "%",
}


def _point(point: Optional[tuple[float, float]]) -> tuple[float, float]:
    if point is None or not all(isfinite(v) for v in point):
        raise MissingMetricData("Missing or non-finite coordinates")
    if not (0 <= point[0] <= 120 and 0 <= point[1] <= 80):
        raise MissingMetricData("Coordinates outside the 120x80 pitch")
    return point


def _start(event: Event) -> tuple[float, float]:
    if event.coordinate_system != "attacking_120x80":
        raise MissingMetricData("Attacking-direction 120x80 coordinates not supplied")
    return _point(event.location)


def _defensive(events: list[Event]) -> list[Event]:
    if any(e.type == "Duel" and e.is_tackle is None for e in events):
        raise MissingMetricData("Duel subtype is missing")
    return [e for e in events if e.type in {"Interception", "Block", "Clearance"}
            or (e.type == "Duel" and e.is_tackle is True)]


def _possessions(events: list[Event], team_id: str) -> dict[tuple[int, str], list[Event]]:
    groups = defaultdict(list)
    # All on-ball action records must identify their possession; no event count/time guess.
    actions = [e for e in events if e.type in {"Pass", "Carry", "Shot", "Dribble"}]
    if not actions:
        raise MissingMetricData("No on-ball actions to establish possession coverage")
    for event in actions:
        if event.possession_id is None or event.possession_team_id is None:
            raise MissingMetricData("Missing possession identity or owner")
    owners = {}
    for event in events:
        if event.possession_id is not None and event.possession_team_id is not None:
            key = (event.period, event.possession_id)
            if key in owners and owners[key] != event.possession_team_id:
                raise MissingMetricData("Conflicting possession owners")
            owners[key] = event.possession_team_id
            if event.possession_team_id == team_id:
                groups[key].append(event)
    return dict(groups)


def _event_ratio(name: str, events: list[Event], team_id: str) -> tuple[float, float]:
    ours = [e for e in events if e.team_id == team_id]
    passes = [e for e in ours if e.type == "Pass"]
    shots = [e for e in ours if e.type == "Shot"]
    against = [e for e in events if e.type == "Shot" and e.team_id != team_id]
    if name == "shots_per_match":
        return len(shots), 1
    if name == "shots_conceded_per_match":
        return len(against), 1
    if name in {"xg_per_match", "xg_conceded_per_match"}:
        selected = shots if name == "xg_per_match" else against
        if any(e.shot_xg is None for e in selected):
            raise MissingMetricData("At least one shot has no xG")
        return fsum(e.shot_xg for e in selected), 1
    if name == "passes_attempted_per_match":
        return len(passes), 1
    if name == "possession_pass_share_pct":
        return 100 * len(passes), sum(e.type == "Pass" for e in events)
    if name == "pass_completion_pct":
        if any(e.pass_completed is None for e in passes):
            raise MissingMetricData("At least one pass has unknown completion")
        return 100 * sum(e.pass_completed for e in passes), len(passes)
    if name in {"average_pass_length", "net_forward_progression_per_pass"}:
        starts = [_start(e) for e in passes]
        ends = [_point(e.pass_end_location) for e in passes]
        distances = [hypot(b[0] - a[0], b[1] - a[1]) if name == "average_pass_length"
                     else b[0] - a[0] for a, b in zip(starts, ends)]
        return fsum(distances), len(passes)
    if name in {"defensive_actions_per_match", "advanced_defensive_actions_per_match"}:
        actions = _defensive(ours)
        if name == "advanced_defensive_actions_per_match":
            return sum(_start(e)[0] >= 80 for e in actions), 1
        return len(actions), 1
    if name == "attacking_third_activity_per_match":
        actions = [e for e in ours if e.type in {"Pass", "Carry", "Shot", "Dribble"}]
        return sum(_start(e)[0] >= 80 for e in actions), 1
    possessions = _possessions(events, team_id)
    if name == "passes_per_possession":
        return sum(e.type == "Pass" and e.team_id == team_id
                   for group in possessions.values() for e in group), len(possessions)
    if name == "counterattack_possession_share_pct":
        counter_count = 0
        for group in possessions.values():
            flags = {e.from_counterattack for e in group}
            if None in flags or len(flags) != 1:
                raise MissingMetricData("Missing or conflicting counterattack tags within a possession")
            counter_count += True in flags
        return 100 * counter_count, len(possessions)
    raise ValueError(f"Unknown metric: {name}")


class TeamSeasonMetrics:
    """Calculate raw metrics from already-retrieved records; performs no I/O."""

    @staticmethod
    def calculate(team_id: str, season: Season, matches: Sequence[Match],
                  events_by_match: Mapping[str, MatchEvents]) -> TeamSeasonProfile:
        ordered = sorted(matches, key=lambda m: (m.date, m.id))
        if len({m.id for m in ordered}) != len(ordered):
            raise MetricsInputError("Duplicate match IDs")
        if set(events_by_match) - {m.id for m in ordered}:
            raise MetricsInputError("Event feeds reference unknown matches")
        provenance = [season.provenance]
        for match in ordered:
            if match.competition_id != season.competition_id or match.season_id != season.id:
                raise MetricsInputError("Matches must belong to the selected competition-season")
            if match.home_team.id == match.away_team.id:
                raise MetricsInputError("A match must contain two different teams")
            provenance.extend([match.provenance, match.home_team.provenance, match.away_team.provenance])
            batch = events_by_match.get(match.id)
            if batch is not None:
                ids, indices = set(), set()
                for event in batch.events:
                    if event.match_id != match.id or event.id in ids or event.index in indices:
                        raise MetricsInputError("Wrong match, duplicate event ID, or duplicate event index")
                    if event.team_id is not None and event.team_id not in {match.home_team.id, match.away_team.id}:
                        raise MetricsInputError("Event belongs to a team outside its match")
                    if event.possession_team_id is not None and event.possession_team_id not in {match.home_team.id, match.away_team.id}:
                        raise MetricsInputError("Possession owner is outside its match")
                    ids.add(event.id)
                    indices.add(event.index)
                    provenance.append(event.provenance)
        if len({(p.source, p.data_kind) for p in provenance}) > 1:
            raise MetricsInputError("Do not mix providers or sample/real records")
        selected = [m for m in ordered if team_id in {m.home_team.id, m.away_team.id}]
        if ordered and not selected:
            raise MetricsInputError("Team is not present in the supplied matches")
        metrics = {}
        for name, unit in UNITS.items():
            numerators, denominators, eligible, excluded = [], [], [], {}
            for match in selected:
                try:
                    if name.startswith("goals_"):
                        if match.home_score is None or match.away_score is None:
                            raise MissingMetricData("Missing final score")
                        home = match.home_team.id == team_id
                        for_us = name == "goals_for_per_match"
                        numerator = match.home_score if home == for_us else match.away_score
                        denominator = 1
                    else:
                        batch = events_by_match.get(match.id)
                        if batch is None or not batch.complete or not batch.events:
                            raise MissingMetricData("No explicitly complete nonempty event feed")
                        events = sorted([e for e in batch.events if e.period <= 4], key=lambda e: e.index)
                        if not events:
                            raise MissingMetricData("No non-shootout events")
                        action_types = {"Pass", "Shot", "Carry", "Dribble", "Duel", "Interception", "Block", "Clearance"}
                        if any(e.team_id is None for e in events if e.type in action_types):
                            raise MissingMetricData("An action has no team attribution")
                        numerator, denominator = _event_ratio(name, events, team_id)
                    numerators.append(numerator)
                    denominators.append(denominator)
                    eligible.append(match.id)
                except MissingMetricData as exc:
                    excluded[match.id] = str(exc)
            numerator, denominator = fsum(numerators), fsum(denominators)
            value = numerator / denominator if denominator > 0 else None
            metrics[name] = Metric(value=value, unit=unit, numerator=numerator, denominator=denominator,
                                   eligible_match_ids=eligible, excluded_matches=excluded,
                                   status="unavailable" if value is None else "partial" if excluded else "available",
                                   reason="No eligible observations or zero denominator" if value is None else None)
        metrics["high_turnovers_per_match"] = Metric(
            unit="turnovers/match", status="unavailable",
            reason="No validated controlled-regain and possession-transition derivation is implemented")
        unique = {p.model_dump_json(): p for p in provenance}
        return TeamSeasonProfile(team_id=team_id, competition_id=season.competition_id,
                                 season_id=season.id, matches_played=len(selected),
                                 match_ids=[m.id for m in selected], metrics=metrics,
                                 provenance=[unique[key] for key in sorted(unique)], notes=[
                                     "Matches played counts supplied team match records, not verified full-season coverage.",
                                     "Periods 1–4 include extra time; period 5 shootout events are excluded.",
                                     "Score inputs must be final scores excluding shootout tallies.",
                                     "Pass share is a possession proxy, not measured possession time.",
                                     "Metrics use their own eligible matches; compare coverage before comparing values.",
                                 ])
