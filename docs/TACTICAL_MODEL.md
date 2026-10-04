# Interpretable tactical style model

`TacticalStyleModel.score(team_id, cohort, expected_matches)` consumes the
`TeamSeasonProfile` results returned by `TeamSeasonMetrics.calculate`. It returns
seven named dimensions, a primary identity, supporting secondary traits, and a
deterministic explanation. It does not download data, train a model, call an LLM,
predict results, or change the raw metric profiles.

## Reference cohort and sample safeguards

Supply profiles from one competition-season and one raw metrics version. The target
must appear exactly once. Profiles must share a source and real/sample designation;
missing provenance, duplicated teams, mismatched competitions/seasons/versions, and
inconsistent observed match counts are rejected with `TacticalInputError`.
Model version 1.0.0 supports raw metrics version 1.0.0.

`expected_matches` maps **every team in the actual competition-season roster** to
its independently verified number of completed matches at the analysis cutoff.
Do not derive those counts from an incomplete event dataset or pass just the two
teams being compared. Missing roster teams remain in the coverage denominator.
The model cannot discover the full schedule from the profiles or verify a caller's
roster claims. For historical catalog entries with only selected matches, scoring
will normally remain unavailable until adequate coverage can be established.

Default safeguards, exposed through `TacticalConfig`:

- At least 10 eligible matches for a team's dimension.
- At least 80% of that team's independently expected completed matches covered.
- At least 10 eligible teams for each dimension.
- At least 80% of the full roster eligible for each dimension.

These are conservative operational cutoffs, not confidence intervals or thresholds
learned from results. Config changes are returned with every profile; relaxing them
does not make a sparse dataset statistically representative. Tournaments with fewer
than 10 games per team will not receive scores under the defaults. Separate research
is needed before relaxing that requirement for tournaments or short seasons.

For a composite dimension, **all components must use exactly the same match IDs
within each team**. Matching coverage percentages alone are insufficient. Recompute
raw metrics on a common match set if necessary; this engine has no underlying events
with which to repair mismatched coverage. Different teams naturally have different
match IDs. Each dimension uses one common eligible-team cohort for all its components.
Different dimensions may have different cohorts, which are returned explicitly.

A required null metric, incompatible unit, non-finite value, impossible negative
value, invalid percentage, nonpositive denominator, inconsistent numerator/value,
or invalid eligible match IDs makes that team's dimension ineligible. Missing
components are never zero-filled or silently reweighted. Failed sample/coverage
checks return a null score and reason, not a neutral score of 50.

## Percentile formula

For an eligible cohort of `n` teams, let `L` be the number strictly below the team's
raw value and `T` the number tied with it. Its average rank is

`r = L + (T + 1) / 2`

and its score is

`P(x) = 100 * (r - 1) / (n - 1)`.

This gives 0 to a unique minimum and 100 to a unique maximum. Tied values receive
the same score. A constant cohort receives 50 for that component, explicitly marked
in `constant_components`: it offers no evidence of differences between teams.
Changing input order cannot change a rank. No rounding occurs before classification.

Scores describe **relative position, not metric magnitude**. A 100 does not imply
perfect football, 100% possession, or certainty; 0 does not mean the behavior never
occurs. Composite scores are the arithmetic mean of their component percentile
scores, not the percentile rank of the composite. All components have positive
direction: larger raw values increase the named dimension.

Percentiles are used instead of z-scores because pass distances, count rates, and
counter shares have different scales and potentially skewed distributions. Ranks
avoid a normal-distribution assumption and prevent one enormous outlier from
dominating the scale. They lose information about absolute gaps and can spread tiny
differences across a wide score range. Raw values and component ranks are therefore
returned, and the classifications should not be interpreted as calibrated findings.

## The seven dimensions

Raw definitions remain in [METRICS.md](METRICS.md). No goals or win percentages
influence these scores. No xG model is used to define tactical style.

| Dimension/key | Score | Interpretation |
| --- | --- | --- |
| Possession / `possession` | `P(possession_pass_share_pct)` | Relative passing share, explicitly a possession proxy, not time on the ball |
| Pressing / `pressing` | `P(advanced_defensive_actions_per_match / defensive_actions_per_match)` | Proxy for where defensive actions occur; the ratio controls for total action volume, not out-of-possession exposure |
| Directness / `directness` | `[P(average_pass_length) + P(net_forward_progression_per_pass)] / 2` | Longer passing and greater signed forward displacement; long sideways passes alone are insufficient for the maximum |
| Attacking intensity / `attacking_intensity` | `[P(shots_per_match) + P(attacking_third_activity_per_match)] / 2` | Shot volume and attacking-third activity; an attacking-volume index, not attacking quality |
| Defensive intensity / `defensive_intensity` | `P(defensive_actions_per_match)` | Defensive activity volume, not effort, defensive success, or low-block depth |
| Counterattacking tendency / `counterattacking_tendency` | `P(counterattack_possession_share_pct)` | Relative share of possessions explicitly tagged by the source as counters |
| Passing/control / `passing_control` | `[P(pass_completion_pct) + P(passes_per_possession)] / 2` | Passing success and sustained passing sequences; not a technical-skill rating |

Each two-component composite gives equal weight to two named aspects. Equal weights
are explicit, reviewable design choices rather than fitted importance estimates.
No raw metric is multiplied by an arbitrary constant to manufacture a score. A
constant component retains its neutral 50 contribution rather than being dropped.
Correlation between components means scores are not independent; averaging opposing
extremes can also hide distinct tendencies, so inspect component scores.

The pressing ratio requires positive total defensive activity and an advanced count
no greater than the total, with matching coverage. The advanced share is the ratio
of the two per-match rates because their match denominators are identical. A team
with many clearances near its own goal can have high defensive activity and low
advanced share; it must not be described as high pressing on that evidence.

True pressing intensity (e.g., a properly defined PPDA or pressure rate), measured
possession, and defensive-line/low-block depth are not available in the current raw
profiles. Consequently `pressing` is flagged as a proxy and explanations state that
limit. This version does **not** emit “High-Pressing Possession Team” or “Deep
Defensive / Transition Team.” Advanced activity and defensive volume cannot prove
those claims. PPDA and spatial block-depth support remain future model extensions.

## Identity rules

“High” means an available score **at least 75**. A single-component score then lies
in the top relative quartile under the rank convention; a composite means its
average component percentile is at least 75. This is a descriptive threshold, not
an empirically validated boundary between tactical systems.

Apply the first matching rule in this explicit order:

1. High directness AND counterattacking → **Direct Counterattacking Team**.
2. High possession AND attacking intensity → **Possession-Dominant Attacking Team
   (pass-share proxy)**.
3. High possession AND passing/control → **Possession and Passing-Control Team
   (pass-share proxy)**.
4. High defensive intensity AND counterattacking → **Defensively Active /
   Transition Team** (no claim about defensive depth).
5. Otherwise, use the first high dimension's trait plus “Team,” ordered possession,
   pressing, directness, attacking intensity, defensive intensity, counterattacking,
   passing/control. Proxy qualifications remain in the trait text.
6. If no high trait and any dimension is unavailable → **Insufficient Evidence**.
7. If all components in every dimension are constant → **No Distinct Relative Style**.
8. If all seven scores are in `[25, 75)` → **Balanced**.
9. Otherwise → **Mixed Relative Style**.

Priority determines which of several valid descriptions becomes primary; it is not
a ranking of football quality. A supported high trait can yield a provisional
identity even with other dimensions unavailable. The explanation then explicitly
states incomplete evidence. Balanced requires all seven dimensions: missing data
can never silently become “Balanced.” Balanced refers to these relative summary
scores, not a claim that a team uses every tactic equally.

Secondary traits list every high dimension in the same stable order, including
traits supporting the primary identity. Explanations use fixed text templates with
up to three extreme scores (high ≥75 or low <25), prioritizing the primary identity's
dimensions, and eligible cohort sizes. They contain no
invented coach intent, match outcomes, causation, or unobserved tactical facts.

## API and reproducibility

```python
from app.analytics.tactical import TacticalStyleModel

# profiles: TeamSeasonProfile results for the competition-season.
# roster_counts: independently verified team ID -> completed match count.
style = TacticalStyleModel().score(selected_team_id, profiles, roster_counts)
print(style.primary_identity)
print(style.scores["directness"].model_dump())
print(style.explanation)
```

Return models are in `backend/app/models/tactical.py`. Each score includes its raw
component values, component percentiles, eligible team IDs, target match IDs,
excluded teams/reasons, constant components, and an interpretation/proxy flag.
The profile carries competition-season, source and real/sample status, raw/model
versions, configuration, and expected match counts. Input profiles are not modified.
The full raw profiles must be retained by the caller for source hashes/provenance.
No frontend or API endpoint is added in this stage.

Cross-season comparisons must rank each team against its own competition-season,
using the same model/configuration and compatible source definitions. A 90 in one
league is not evidence of greater absolute strength than an 80 in another. Partial
match selection, opponent strength, game state, dismissals, extra time, and differing
event fidelity remain confounders. These scores do not calibrate any of them.

## Synthetic examples and checks

`backend/tests/test_tactical.py::synthetic_cohort` creates 11 **invented** team
profiles, each with 20 observed/expected matches. It is a test construction, not a
dataset of real teams. Its high-control end has 70% passing share, 16 shots/match,
15-unit average passes, 90% completion, and 6 passes/possession. The direct end has
30% passing share, 35-unit average passes, 14 units of forward displacement per pass,
and 35% counter-tagged possessions. The midpoint is intermediate in every component.

| Synthetic team | Possession | Directness | Attack | Counter | Control | Identity |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Control end (`team-10`) | 100 | 0 | 100 | 0 | 100 | Possession-Dominant Attacking Team (pass-share proxy) |
| Direct end (`team-0`) | 0 | 100 | 0 | 100 | 0 | Direct Counterattacking Team |
| Midpoint (`team-5`) | 50 | 50 | 50 | 50 | 50 | Balanced |

Run `python -m pytest` from `backend/`. Tests cover these contrasts, ties, constant
cohorts, outliers, ordering, exact thresholds, missing components, mismatched match
sets, insufficient matches/roster size, bad units/values, and incompatible sources
or seasons. These tests demonstrate rule behavior, not predictive or tactical-label
validation against expert-annotated real teams.
