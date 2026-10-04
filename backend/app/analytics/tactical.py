"""Competition-season percentile scores; no fitting, downloads, or LLM calls."""

from math import ceil, fsum, isclose, isfinite
from typing import Mapping, Optional, Sequence

from app.analytics.team_season import UNITS
from app.models.metrics import TeamSeasonProfile
from app.models.tactical import TacticalConfig, TacticalProfile, TacticalScore

# Equal weights give each named aspect one vote; no missing-component reweighting.
DIMENSIONS = {
    "possession": ("possession_pass_share_pct",),
    "pressing": ("advanced_defensive_share",),
    "directness": ("average_pass_length", "net_forward_progression_per_pass"),
    "attacking_intensity": ("shots_per_match", "attacking_third_activity_per_match"),
    "defensive_intensity": ("defensive_actions_per_match",),
    "counterattacking_tendency": ("counterattack_possession_share_pct",),
    "passing_control": ("pass_completion_pct", "passes_per_possession"),
}
INTERPRETATIONS = {
    "possession": "Relative passing share; proxy for possession, not possession time",
    "pressing": "Relative share of defensive actions in the attacking third; pressing proxy only",
    "directness": "Relative pass distance and signed forward displacement",
    "attacking_intensity": "Relative shot volume and attacking-third on-ball activity",
    "defensive_intensity": "Relative defensive action volume, not defensive quality or effort",
    "counterattacking_tendency": "Relative source-tagged counterattack possession share",
    "passing_control": "Relative pass completion and passing sequence length",
}
TRAITS = {
    "possession": "Possession-oriented (pass-share proxy)",
    "pressing": "Advanced defensive activity (pressing proxy)",
    "directness": "Direct passing",
    "attacking_intensity": "High attacking activity",
    "defensive_intensity": "High defensive activity",
    "counterattacking_tendency": "Counterattacking",
    "passing_control": "Passing control",
}


class TacticalInputError(ValueError):
    """Cohort scope or profile structure is inconsistent."""


class IneligibleMetric(ValueError):
    """A team lacks enough compatible observations for a dimension."""


def percentile(value: float, values: Sequence[float]) -> float:
    """Average-rank percentile for a member of a finite reference sample."""
    if len(values) < 2 or not all(isfinite(x) for x in values) or not isfinite(value):
        raise ValueError("Percentiles require at least two finite values")
    equal = sum(x == value for x in values)
    if not equal:
        raise ValueError("The ranked value must belong to the cohort")
    rank = sum(x < value for x in values) + (equal + 1) / 2
    return 100 * (rank - 1) / (len(values) - 1)


def _components(profile: TeamSeasonProfile, names: tuple[str, ...], expected: int,
                config: TacticalConfig) -> tuple[dict[str, float], list[str]]:
    required = set(names)
    if "advanced_defensive_share" in required:
        required.remove("advanced_defensive_share")
        required.update({"advanced_defensive_actions_per_match", "defensive_actions_per_match"})
    values = {}
    common = None
    for name in sorted(required):
        metric = profile.metrics.get(name)
        if metric is None or metric.status == "unavailable" or metric.value is None:
            raise IneligibleMetric(f"{name}: unavailable")
        if metric.unit != UNITS[name]:
            raise IneligibleMetric(f"{name}: incompatible unit")
        if (not all(isfinite(x) for x in (metric.value, metric.numerator, metric.denominator))
                or metric.denominator <= 0
                or not isclose(metric.value, metric.numerator / metric.denominator, rel_tol=1e-9, abs_tol=1e-9)):
            raise IneligibleMetric(f"{name}: invalid value or denominator")
        if name != "net_forward_progression_per_pass" and metric.value < 0:
            raise IneligibleMetric(f"{name}: negative value")
        if name.endswith("_pct") and metric.value > 100:
            raise IneligibleMetric(f"{name}: percentage above 100")
        ids = set(metric.eligible_match_ids)
        if (len(ids) != len(metric.eligible_match_ids) or not ids <= set(profile.match_ids)
                or ids & set(metric.excluded_matches)):
            raise IneligibleMetric(f"{name}: invalid coverage identifiers")
        if name.endswith("_per_match") and metric.denominator != len(ids):
            raise IneligibleMetric(f"{name}: rate denominator does not match eligible matches")
        if len(ids) < config.min_matches or len(ids) / expected < config.min_match_coverage:
            raise IneligibleMetric(f"{name}: insufficient matches or coverage")
        if common is not None and ids != common:
            raise IneligibleMetric("Component metrics use different match sets; recompute on a common set")
        common = ids
        values[name] = metric.value
    if "advanced_defensive_share" in names:
        advanced = values["advanced_defensive_actions_per_match"]
        total = values["defensive_actions_per_match"]
        if total <= 0 or advanced > total:
            raise IneligibleMetric("Advanced defensive share needs positive total and a valid subset")
        values["advanced_defensive_share"] = advanced / total
    return {name: values[name] for name in names}, sorted(common or [])


def classify(scores: Mapping[str, TacticalScore]) -> tuple[str, list[str], str]:
    """Ordered threshold rules with evidence-qualified wording."""
    def high(name: str) -> bool:
        return scores[name].value is not None and scores[name].value >= 75

    rules = [
        (high("directness") and high("counterattacking_tendency"), "Direct Counterattacking Team"),
        (high("possession") and high("attacking_intensity"), "Possession-Dominant Attacking Team (pass-share proxy)"),
        (high("possession") and high("passing_control"), "Possession and Passing-Control Team (pass-share proxy)"),
        (high("defensive_intensity") and high("counterattacking_tendency"), "Defensively Active / Transition Team"),
    ]
    identity = next((label for applies, label in rules if applies), None)
    traits = [TRAITS[name] for name in DIMENSIONS if high(name)]
    available = [s for s in scores.values() if s.value is not None]
    if identity is None:
        if traits:
            identity = traits[0] + " Team"
        elif len(available) < len(DIMENSIONS):
            identity = "Insufficient Evidence"
        elif all(len(s.constant_components) == len(s.components) for s in available):
            identity = "No Distinct Relative Style"
        elif all(25 <= s.value < 75 for s in available):
            identity = "Balanced"
        else:
            identity = "Mixed Relative Style"
    priority = []
    if identity.startswith("Direct Counterattacking"):
        priority = ["directness", "counterattacking_tendency"]
    elif identity.startswith("Possession-Dominant"):
        priority = ["possession", "attacking_intensity"]
    elif identity.startswith("Possession and"):
        priority = ["possession", "passing_control"]
    elif identity.startswith("Defensively Active"):
        priority = ["defensive_intensity", "counterattacking_tendency"]
    evidence = []
    for name in priority + [name for name in DIMENSIONS if name not in priority]:
        score = scores[name]
        if score.value is not None and (score.value >= 75 or score.value < 25):
            evidence.append(f"{name.replace('_', ' ')} scores {score.value:.1f}/100 "
                            f"among {len(score.cohort_team_ids)} eligible teams")
            if len(evidence) == 3:
                break
    explanation = ("; ".join(evidence) + ".") if evidence else "No supported dimension is in an extreme quartile."
    if len(available) < len(DIMENSIONS):
        explanation += " Some dimensions are unavailable; the identity uses only supported evidence."
    if any(s.proxy and s.value is not None for s in scores.values()):
        explanation += " Possession uses a passing-share proxy; pressing uses advanced defensive activity, not measured pressing intensity."
    return identity, traits, explanation


class TacticalStyleModel:
    def __init__(self, config: Optional[TacticalConfig] = None) -> None:
        self.config = config or TacticalConfig()

    def score(self, team_id: str, cohort: Sequence[TeamSeasonProfile],
              expected_matches: Mapping[str, int]) -> TacticalProfile:
        """expected_matches supplies the full roster and verified completed-match counts."""
        profiles = {p.team_id: p for p in cohort}
        if len(profiles) != len(cohort) or team_id not in profiles:
            raise TacticalInputError("Duplicate team profiles or target absent from cohort")
        if not set(profiles) <= set(expected_matches):
            raise TacticalInputError("Expected-match roster must include every supplied team")
        if any(type(n) is not int or n <= 0 for n in expected_matches.values()):
            raise TacticalInputError("Expected completed-match counts must be positive integers")
        target = profiles[team_id]
        sources = set()
        for profile in cohort:
            if (profile.competition_id, profile.season_id, profile.metrics_version) != (
                    target.competition_id, target.season_id, target.metrics_version):
                raise TacticalInputError("Cohort must share competition, season, and metrics version")
            if profile.metrics_version != "1.0.0":
                raise TacticalInputError("Unsupported metrics version")
            if (len(set(profile.match_ids)) != len(profile.match_ids)
                    or profile.matches_played != len(profile.match_ids)
                    or profile.matches_played > expected_matches[profile.team_id]):
                raise TacticalInputError("Invalid observed or expected match counts")
            if not profile.provenance:
                raise TacticalInputError("Source provenance is required")
            sources.update((p.source, p.data_kind) for p in profile.provenance)
        if len(sources) != 1:
            raise TacticalInputError("Do not mix providers or real/sample profiles")
        scores = {}
        for dimension, names in DIMENSIONS.items():
            eligible, coverage, excluded = {}, {}, {}
            for id in sorted(expected_matches):
                if id not in profiles:
                    excluded[id] = "Team profile not supplied"
                    continue
                try:
                    eligible[id], coverage[id] = _components(profiles[id], names, expected_matches[id], self.config)
                except IneligibleMetric as exc:
                    excluded[id] = str(exc)
            reason = None
            minimum = max(self.config.min_teams, ceil(self.config.min_roster_coverage * len(expected_matches)))
            if team_id not in eligible:
                reason = excluded[team_id]
            elif len(eligible) < minimum:
                reason = f"Need at least {minimum} eligible teams; found {len(eligible)}"
            components, constants = {}, []
            if reason is None:
                for name in names:
                    values = [eligible[id][name] for id in sorted(eligible)]
                    components[name] = percentile(eligible[team_id][name], values)
                    if len(set(values)) == 1:
                        constants.append(name)
            scores[dimension] = TacticalScore(
                value=fsum(components.values()) / len(names) if components else None,
                proxy=dimension in {"possession", "pressing", "defensive_intensity"},
                interpretation=INTERPRETATIONS[dimension], components=components,
                raw_values=eligible.get(team_id, {}), cohort_team_ids=sorted(eligible),
                eligible_match_ids=coverage.get(team_id, []), excluded_teams=excluded,
                constant_components=constants, reason=reason)
        identity, traits, explanation = classify(scores)
        source, kind = next(iter(sources))
        return TacticalProfile(
            team_id=team_id, competition_id=target.competition_id, season_id=target.season_id,
            metrics_version=target.metrics_version, source=source, data_kind=kind,
            scores=scores, primary_identity=identity, secondary_traits=traits, explanation=explanation,
            config=self.config, expected_matches=dict(sorted(expected_matches.items())), limitations=[
                "Relative style within the supplied competition-season, not strength or win probability.",
                "Expected-match counts and the full roster must be independently verified by the caller.",
                "Pressing is an activity-location proxy; no high-pressing or low-block claim is supported.",
                "Per-match activity is not adjusted for possession time, score state, opponents or extra time.",
                "Quartile thresholds and equal weights are transparent design choices, not empirically fitted truths.",
                "Provider fidelity and event definitions must be compatible across the reference cohort.",
            ])
