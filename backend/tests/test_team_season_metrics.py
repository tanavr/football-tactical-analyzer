"""Small synthetic matches with hand-calculated expectations; no network."""

from datetime import datetime, timezone
from math import nan

import pytest
from pydantic import ValidationError

from app.analytics.team_season import MetricsInputError, TeamSeasonMetrics
from app.data.statsbomb import normalize_event
from app.models.football import Event, Match, Provenance, Season, Team
from app.models.metrics import MatchEvents


@pytest.fixture
def sample():
    p = Provenance(source="fixture", data_kind="sample", url="fixture://metrics", revision="1",
                   retrieved_at=datetime(2026, 1, 1, tzinfo=timezone.utc), sha256="synthetic")
    a, b = [Team(id=id, name=id, provenance=p) for id in ("a", "b")]
    season = Season(id="s", competition_id="c", name="Test", provenance=p)
    matches = [Match(id="m1", competition_id="c", season_id="s", date="2026-01-01",
                     home_team=a, away_team=b, home_score=2, away_score=1, provenance=p),
               Match(id="m2", competition_id="c", season_id="s", date="2026-01-02",
                     home_team=b, away_team=a, home_score=0, away_score=1, provenance=p)]

    def event(match, index, kind, team="a", **kwargs):
        defaults = dict(location=(80, 40), coordinate_system="attacking_120x80",
                        possession_id="1" if team == "a" else "2",
                        possession_team_id=team, from_counterattack=False)
        defaults.update(kwargs)
        return Event(id=f"{match}:{index}", match_id=match, index=index, type=kind, period=1,
                     minute=0, second=index, team_id=team, provenance=p, **defaults)

    first = [event("m1", 1, "Pass", location=(70, 40), pass_end_location=(80, 40), pass_completed=True),
             event("m1", 2, "Pass", pass_end_location=(74, 48), pass_completed=False),
             event("m1", 3, "Shot", shot_xg=.3),
             event("m1", 4, "Shot", "b", shot_xg=.2),
             event("m1", 5, "Pass", "b", pass_end_location=(90, 40), pass_completed=True),
             event("m1", 6, "Duel", is_tackle=True),
             event("m1", 7, "Interception", location=(79.9, 40))]
    # 1 pass (length 20), 2 shots, 1 counter possession for A in match 2.
    second = [event("m2", 1, "Pass", location=(60, 40), pass_end_location=(80, 40),
                    pass_completed=True, from_counterattack=True),
              event("m2", 2, "Shot", shot_xg=.4, from_counterattack=True),
              event("m2", 3, "Shot", shot_xg=.1, from_counterattack=True),
              event("m2", 4, "Pass", "b", pass_end_location=(90, 40), pass_completed=True),
              event("m2", 5, "Pass", "b", pass_end_location=(90, 40), pass_completed=True),
              event("m2", 6, "Pass", "b", pass_end_location=(90, 40), pass_completed=True)]
    feeds = {"m1": MatchEvents(events=first, complete=True), "m2": MatchEvents(events=second, complete=True)}
    return season, matches, feeds


def calculate(sample):
    return TeamSeasonMetrics.calculate("a", *sample)


def replace_event(sample, match, position, **changes):
    batch = sample[2][match]
    events = list(batch.events)
    # Revalidate rather than bypassing Pydantic field constraints.
    events[position] = Event.model_validate({**events[position].model_dump(), **changes})
    sample[2][match] = MatchEvents(events=events, complete=batch.complete)


def test_known_profile(sample):
    result = calculate(sample)
    assert result.matches_played == 2
    expected = {
        "goals_for_per_match": 1.5, "goals_against_per_match": .5,
        "shots_per_match": 1.5, "shots_conceded_per_match": .5,
        "xg_per_match": .4, "xg_conceded_per_match": .1,
        "passes_attempted_per_match": 1.5, "pass_completion_pct": 200 / 3,
        "possession_pass_share_pct": 300 / 7, "passes_per_possession": 1.5,
        "average_pass_length": 40 / 3, "net_forward_progression_per_pass": 8,
        "defensive_actions_per_match": 1, "advanced_defensive_actions_per_match": .5,
        "attacking_third_activity_per_match": 2,
        "counterattack_possession_share_pct": 50,
    }
    for name, value in expected.items():
        assert result.metrics[name].value == pytest.approx(value), name
        assert result.metrics[name].status == "available"
    assert result.metrics["high_turnovers_per_match"].value is None
    assert result.metrics["high_turnovers_per_match"].reason
    assert result.metrics["pass_completion_pct"].denominator == 3
    assert result.provenance[0].data_kind == "sample"


def test_home_away_and_opponent_symmetry(sample):
    ours = calculate(sample)
    theirs = TeamSeasonMetrics.calculate("b", *sample)
    assert theirs.metrics["goals_for_per_match"].value == ours.metrics["goals_against_per_match"].value
    assert theirs.metrics["shots_per_match"].value == ours.metrics["shots_conceded_per_match"].value
    assert theirs.metrics["xg_per_match"].value == ours.metrics["xg_conceded_per_match"].value


def test_order_independence_and_no_mutation(sample):
    original = calculate(sample)
    before = {k: v.model_dump() for k, v in sample[2].items()}
    shuffled = {k: MatchEvents(events=list(reversed(v.events)), complete=True)
                for k, v in reversed(list(sample[2].items()))}
    assert TeamSeasonMetrics.calculate("a", sample[0], list(reversed(sample[1])), shuffled) == original
    assert {k: v.model_dump() for k, v in sample[2].items()} == before


@pytest.mark.parametrize("mode", ["missing", "incomplete", "empty"])
def test_event_coverage_does_not_dilute_rates(sample, mode):
    if mode == "missing":
        del sample[2]["m2"]
    else:
        sample[2]["m2"] = MatchEvents(events=[] if mode == "empty" else sample[2]["m2"].events,
                                     complete=mode == "empty")
    result = calculate(sample)
    assert result.metrics["shots_per_match"].value == 1
    assert result.metrics["shots_per_match"].denominator == 1
    assert result.metrics["shots_per_match"].status == "partial"
    assert "m2" in result.metrics["shots_per_match"].excluded_matches
    assert result.metrics["goals_for_per_match"].value == 1.5


@pytest.mark.parametrize("field,index,metric", [
    ("shot_xg", 2, "xg_per_match"),
    ("pass_completed", 0, "pass_completion_pct"),
    ("pass_end_location", 0, "average_pass_length"),
    ("coordinate_system", 0, "net_forward_progression_per_pass"),
    ("is_tackle", 5, "defensive_actions_per_match"),
    ("location", 5, "advanced_defensive_actions_per_match"),
    ("location", 2, "attacking_third_activity_per_match"),
    ("possession_id", 0, "passes_per_possession"),
    ("from_counterattack", 0, "counterattack_possession_share_pct"),
])
def test_missing_field_excludes_whole_match_for_affected_metric(sample, field, index, metric):
    replace_event(sample, "m1", index, **{field: None})
    result = calculate(sample)
    assert result.metrics[metric].status == "partial"
    assert result.metrics[metric].eligible_match_ids == ["m2"]
    assert result.metrics["shots_per_match"].value == 1.5


def test_missing_score(sample):
    sample[1][0] = sample[1][0].model_copy(update={"home_score": None})
    result = calculate(sample)
    assert result.metrics["goals_for_per_match"].value == 1
    assert result.metrics["goals_against_per_match"].value == 0
    assert result.metrics["goals_for_per_match"].status == "partial"


def test_no_matches_or_observations(sample):
    result = TeamSeasonMetrics.calculate("a", sample[0], [], {})
    assert result.matches_played == 0
    assert all(m.value is None for m in result.metrics.values())
    assert all(m.reason for m in result.metrics.values())


def test_zero_shots_vs_undefined_pass_ratios(sample):
    events = [e for e in sample[2]["m1"].events if e.type == "Interception"]
    sample[2]["m1"] = MatchEvents(events=events, complete=True)
    result = TeamSeasonMetrics.calculate("a", sample[0], sample[1][:1], {"m1": sample[2]["m1"]})
    assert result.metrics["shots_per_match"].value == 0
    assert result.metrics["xg_per_match"].value == 0
    assert result.metrics["pass_completion_pct"].value is None
    assert result.metrics["possession_pass_share_pct"].value is None


def test_extra_time_included_shootout_excluded(sample):
    event = sample[2]["m1"].events[2]
    batch = sample[2]["m1"]
    batch.events.extend([event.model_copy(update={"id": "extra", "index": 8, "period": 3}),
                         event.model_copy(update={"id": "shootout", "index": 9, "period": 5})])
    assert calculate(sample).metrics["shots_per_match"].value == 2


@pytest.mark.parametrize("value", [nan, -0.1, 1.1])
def test_invalid_xg_rejected(sample, value):
    with pytest.raises(ValidationError):
        replace_event(sample, "m1", 2, shot_xg=value)


@pytest.mark.parametrize("location", [(121, 40), (80, -1), (nan, 1)])
def test_invalid_coordinates_make_spatial_metric_partial(sample, location):
    replace_event(sample, "m1", 0, location=location)
    assert calculate(sample).metrics["average_pass_length"].status == "partial"


@pytest.mark.parametrize("case", ["duplicate_match", "duplicate_event", "duplicate_index", "wrong_match",
                                 "wrong_season", "wrong_team", "mixed_kind", "mixed_source", "extra_feed"])
def test_invalid_inputs(sample, case):
    if case == "duplicate_match":
        sample[1].append(sample[1][0])
    elif case == "duplicate_event":
        sample[2]["m1"].events.append(sample[2]["m1"].events[0])
    elif case == "duplicate_index":
        replace_event(sample, "m1", 1, index=1)
    elif case == "wrong_match":
        replace_event(sample, "m1", 0, match_id="m2")
    elif case == "wrong_season":
        sample[1][0] = sample[1][0].model_copy(update={"season_id": "other"})
    elif case == "wrong_team":
        replace_event(sample, "m1", 0, team_id="outsider")
    elif case in {"mixed_kind", "mixed_source"}:
        p = sample[2]["m1"].events[0].provenance
        replace_event(sample, "m1", 0, provenance=p.model_copy(update=
                      {"data_kind": "real"} if case == "mixed_kind" else {"source": "other"}))
    else:
        sample[2]["unknown"] = sample[2]["m1"]
    with pytest.raises(MetricsInputError):
        calculate(sample)


def test_unknown_team_rejected(sample):
    with pytest.raises(MetricsInputError):
        TeamSeasonMetrics.calculate("unknown", *sample)


def test_unattributed_action_not_counted_as_opponent(sample):
    replace_event(sample, "m1", 3, team_id=None)
    assert calculate(sample).metrics["shots_conceded_per_match"].status == "partial"


def test_possession_ids_do_not_merge_across_periods(sample):
    replace_event(sample, "m1", 1, period=2)
    assert calculate(sample).metrics["passes_per_possession"].value == 1


@pytest.mark.parametrize("outcome,expected", [("absent", True), ("Incomplete", False),
                                              ("Out", False), ("Unknown", None), (None, None)])
def test_statsbomb_completion_semantics(sample, outcome, expected):
    passing = {"end_location": [90, 40]}
    if outcome != "absent":
        passing["outcome"] = {"name": outcome} if outcome is not None else None
    row = dict(id="e", index=1, type={"name": "Pass"}, period=1, minute=0, second=0,
               team={"id": 4}, possession=1, possession_team={"id": 4},
               play_pattern={"name": "From Counter"}, location=[80, 40], **{"pass": passing})
    event = normalize_event(row, sample[0].provenance, "m1")
    assert event.pass_completed is expected
    assert event.from_counterattack is True
    assert event.possession_team_id == "statsbomb:team:4"
    assert event.pass_end_location == (90, 40)


def test_default_feed_is_not_assumed_complete(sample):
    sample[2]["m1"] = MatchEvents(events=sample[2]["m1"].events)
    assert calculate(sample).metrics["shots_per_match"].eligible_match_ids == ["m2"]


def test_conflicting_possession_owners_and_tags(sample):
    replace_event(sample, "m1", 1, possession_team_id="b")
    assert calculate(sample).metrics["passes_per_possession"].status == "partial"
    replace_event(sample, "m1", 1, possession_team_id="a", from_counterattack=True)
    assert calculate(sample).metrics["counterattack_possession_share_pct"].status == "partial"


def test_zero_pass_possession_included(sample):
    replace_event(sample, "m2", 2, possession_id="3")
    result = calculate(sample)
    assert result.metrics["passes_per_possession"].value == 1  # 3 passes / 3 possessions
    assert result.metrics["counterattack_possession_share_pct"].value == pytest.approx(200 / 3)


def test_raw_provider_fields_are_not_read(sample):
    before = calculate(sample)
    for batch in sample[2].values():
        for event in batch.events:
            event.source_fields["shot"] = {"statsbomb_xg": 999}
    assert calculate(sample) == before


def test_backwards_progression_can_be_negative(sample):
    replace_event(sample, "m1", 0, location=(90, 40), pass_end_location=(10, 40))
    assert calculate(sample).metrics["net_forward_progression_per_pass"].value < 0
