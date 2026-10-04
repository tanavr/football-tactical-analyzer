"""Synthetic style contrasts and reference-cohort safeguards."""

from datetime import datetime, timezone
from math import nan

import pytest

from app.analytics.tactical import TacticalInputError, TacticalStyleModel, percentile
from app.analytics.team_season import UNITS
from app.models.football import Provenance
from app.models.metrics import Metric, TeamSeasonProfile


def synthetic_cohort() -> list[TeamSeasonProfile]:
    """Eleven invented teams spanning direct transitions to passing control."""
    provenance = Provenance(source="fixture", data_kind="sample", url="fixture://tactics",
                            retrieved_at=datetime(2026, 1, 1, tzinfo=timezone.utc), revision="1",
                            sha256="synthetic")
    profiles = []
    for i in range(11):
        values = {
            "possession_pass_share_pct": 30 + 4 * i,
            "average_pass_length": 35 - 2 * i,
            "net_forward_progression_per_pass": 14 - i,
            "shots_per_match": 6 + i,
            "attacking_third_activity_per_match": 30 + 10 * i,
            "defensive_actions_per_match": 20 + i,
            "advanced_defensive_actions_per_match": (20 + i) * (.05 + .025 * i),
            "counterattack_possession_share_pct": 35 - 3 * i,
            "pass_completion_pct": 60 + 3 * i,
            "passes_per_possession": 2 + .4 * i,
        }
        ids = [f"team-{i}-match-{j}" for j in range(20)]
        metrics = {}
        for key, value in values.items():
            denominator = 20 if key.endswith("_per_match") else 200
            metrics[key] = Metric(value=value, numerator=value * denominator, denominator=denominator,
                                  unit=UNITS[key], eligible_match_ids=ids, status="available")
        profiles.append(TeamSeasonProfile(team_id=f"team-{i}", competition_id="sample-league",
                                         season_id="sample-season", matches_played=20, match_ids=ids,
                                         metrics=metrics, provenance=[provenance], notes=["Synthetic example"]))
    return profiles


def result(cohort: list[TeamSeasonProfile], target: str = "team-10"):
    return TacticalStyleModel().score(target, cohort, {p.team_id: 20 for p in cohort})


def change(profile: TeamSeasonProfile, metric: str, value: float) -> None:
    old = profile.metrics[metric]
    profile.metrics[metric] = old.model_copy(update={"value": value, "numerator": value * old.denominator})


def test_three_logical_synthetic_identities() -> None:
    cohort = synthetic_cohort()
    possession = result(cohort)
    direct = result(cohort, "team-0")
    balanced = result(cohort, "team-5")
    assert possession.primary_identity == "Possession-Dominant Attacking Team (pass-share proxy)"
    assert direct.primary_identity == "Direct Counterattacking Team"
    assert balanced.primary_identity == "Balanced"
    assert possession.scores["possession"].value == 100
    assert possession.scores["directness"].value == 0
    assert direct.scores["counterattacking_tendency"].value == 100
    assert all(s.value == pytest.approx(50) for s in balanced.scores.values())
    assert "proxy" in possession.explanation
    assert possession.data_kind == "sample"
    assert "High-Pressing" not in possession.primary_identity
    assert "Deep" not in direct.primary_identity


def test_rank_ties_constant_and_outlier() -> None:
    assert percentile(2, [1, 2, 2, 3]) == 50
    assert percentile(7, [7] * 10) == 50
    assert percentile(1e12, list(range(10)) + [1e12]) == 100
    with pytest.raises(ValueError):
        percentile(1, [1])
    with pytest.raises(ValueError):
        percentile(1, [1, nan])


def test_deterministic_order_and_input_preservation() -> None:
    cohort = synthetic_cohort()
    before = [p.model_dump() for p in cohort]
    assert result(cohort) == result(list(reversed(cohort)))
    assert [p.model_dump() for p in cohort] == before


def test_small_cohort_unavailable_not_balanced() -> None:
    scores = result(synthetic_cohort()[:9], "team-5")
    assert scores.primary_identity == "Insufficient Evidence"
    assert all(s.value is None and s.reason for s in scores.scores.values())


def test_full_roster_coverage_not_just_selected_teams() -> None:
    cohort = synthetic_cohort()
    roster = {f"team-{i}": 20 for i in range(20)}
    profile = TacticalStyleModel().score("team-10", cohort, roster)
    assert all(s.value is None for s in profile.scores.values())
    assert "16 eligible teams" in profile.scores["possession"].reason


def test_insufficient_match_count() -> None:
    cohort = synthetic_cohort()
    for name, metric in cohort[-1].metrics.items():
        cohort[-1].metrics[name] = metric.model_copy(update={"eligible_match_ids": cohort[-1].match_ids[:9]})
    assert result(cohort).primary_identity == "Insufficient Evidence"


@pytest.mark.parametrize("count,available", [(15, False), (16, True)])
def test_match_coverage_boundary(count: int, available: bool) -> None:
    cohort = synthetic_cohort()
    for name, metric in cohort[-1].metrics.items():
        cohort[-1].metrics[name] = metric.model_copy(update={"eligible_match_ids": cohort[-1].match_ids[:count]})
    assert (result(cohort).scores["possession"].value is not None) == available


def test_mismatched_component_match_sets_not_reweighted() -> None:
    cohort = synthetic_cohort()
    metric = cohort[-1].metrics["average_pass_length"]
    cohort[-1].metrics["average_pass_length"] = metric.model_copy(update={"eligible_match_ids": cohort[-1].match_ids[:16]})
    score = result(cohort).scores["directness"]
    assert score.value is None
    assert "different match sets" in score.reason


def test_missing_component_does_not_zero_or_reweight() -> None:
    cohort = synthetic_cohort()
    del cohort[-1].metrics["pass_completion_pct"]
    scores = result(cohort).scores
    assert scores["passing_control"].value is None
    assert scores["possession"].value == 100


@pytest.mark.parametrize("case", ["nan", "negative", "percentage", "unit", "denominator", "coverage"])
def test_invalid_raw_metric_excluded(case: str) -> None:
    cohort = synthetic_cohort()
    key = "possession_pass_share_pct"
    metric = cohort[-1].metrics[key]
    updates = {
        "nan": {"value": nan}, "negative": {"value": -1, "numerator": -200},
        "percentage": {"value": 101, "numerator": 20200}, "unit": {"unit": "seconds"},
        "denominator": {"denominator": 0}, "coverage": {"eligible_match_ids": ["foreign"] * 20},
    }
    cohort[-1].metrics[key] = metric.model_copy(update=updates[case])
    assert result(cohort).scores["possession"].value is None


@pytest.mark.parametrize("case", ["season", "competition", "version", "source", "kind", "duplicate", "counts"])
def test_incompatible_cohorts_rejected(case: str) -> None:
    cohort = synthetic_cohort()
    if case in {"season", "competition", "version"}:
        field = {"season": "season_id", "competition": "competition_id", "version": "metrics_version"}[case]
        cohort[0] = cohort[0].model_copy(update={field: "other"})
    elif case in {"source", "kind"}:
        p = cohort[0].provenance[0].model_copy(update={"source": "other"} if case == "source" else {"data_kind": "real"})
        cohort[0] = cohort[0].model_copy(update={"provenance": [p]})
    elif case == "counts":
        cohort[0] = cohort[0].model_copy(update={"matches_played": 99})
    else:
        cohort.append(cohort[0])
    with pytest.raises(TacticalInputError):
        result(cohort)


def test_constant_cohort_is_not_evidence_of_balanced_tactics() -> None:
    cohort = synthetic_cohort()
    for profile in cohort:
        for key, metric in cohort[5].metrics.items():
            change(profile, key, metric.value)
    scored = result(cohort)
    assert all(s.value == 50 for s in scored.scores.values())
    assert scored.primary_identity == "No Distinct Relative Style"


def test_pressing_uses_location_share_not_defensive_volume() -> None:
    cohort = synthetic_cohort()
    # Most defensive actions, but all deep: cannot claim strong pressing.
    change(cohort[-1], "defensive_actions_per_match", 100)
    change(cohort[-1], "advanced_defensive_actions_per_match", 0)
    scores = result(cohort).scores
    assert scores["defensive_intensity"].value == 100
    assert scores["pressing"].value == 0
    assert scores["pressing"].proxy


def test_invalid_defensive_subset() -> None:
    cohort = synthetic_cohort()
    change(cohort[-1], "advanced_defensive_actions_per_match", 100)
    assert result(cohort).scores["pressing"].value is None


def test_threshold_75_is_inclusive_and_balanced_excludes_missing() -> None:
    from app.analytics.tactical import classify
    scores = result(synthetic_cohort(), "team-5").scores
    scores["directness"] = scores["directness"].model_copy(update={"value": 75})
    scores["counterattacking_tendency"] = scores["counterattacking_tendency"].model_copy(update={"value": 75})
    assert classify(scores)[0] == "Direct Counterattacking Team"
    scores["directness"] = scores["directness"].model_copy(update={"value": 74.999})
    assert classify(scores)[0] != "Direct Counterattacking Team"
    scores = result(synthetic_cohort(), "team-5").scores
    scores["pressing"] = scores["pressing"].model_copy(update={"value": None})
    assert classify(scores)[0] == "Insufficient Evidence"


def test_composite_is_mean_of_ranks_not_raw_units() -> None:
    cohort = synthetic_cohort()
    # Longest passes but least forward: ranks 100 and 0, not an automatic direct label.
    change(cohort[-1], "average_pass_length", 100)
    score = result(cohort).scores["directness"]
    assert score.components == {"average_pass_length": 100, "net_forward_progression_per_pass": 0}
    assert score.value == 50


def test_eligible_peers_and_cohort_size_are_explicit() -> None:
    cohort = synthetic_cohort()
    del cohort[0].metrics["possession_pass_share_pct"]
    scored = result(cohort).scores["possession"]
    assert scored.value == 100
    assert len(scored.cohort_team_ids) == 10
    assert "team-0" in scored.excluded_teams
    del cohort[1].metrics["possession_pass_share_pct"]
    assert result(cohort).scores["possession"].value is None


def test_low_level_of_counters_is_not_called_absent() -> None:
    cohort = synthetic_cohort()
    scored = result(cohort)
    assert cohort[-1].metrics["counterattack_possession_share_pct"].value == 5
    assert scored.scores["counterattacking_tendency"].value == 0
    assert "never" not in scored.explanation


def test_no_roster_and_no_provenance_rejected() -> None:
    cohort = synthetic_cohort()
    with pytest.raises(TacticalInputError):
        TacticalStyleModel().score("team-10", cohort, {})
    cohort[0] = cohort[0].model_copy(update={"provenance": []})
    with pytest.raises(TacticalInputError):
        result(cohort)
