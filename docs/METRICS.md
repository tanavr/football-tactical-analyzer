# Team-season raw metrics

`TeamSeasonMetrics.calculate(team_id, season, matches, events_by_match)` produces a
Pydantic `TeamSeasonProfile`. This is a statistical summary, not a tactical score,
classification, strength rating, or prediction. Calculations perform no network or
filesystem access. Source adapters populate event semantics before analytics runs.
The separate scoring layer is documented in [TACTICAL_MODEL.md](TACTICAL_MODEL.md).

## Inputs and coverage

Pass a `Season`, match records from that competition-season, and a mapping from
match ID to `MatchEvents`. The engine selects the requested team's home and away
matches. Matches from another competition-season, duplicate records, wrong-match
events, unknown teams/possession owners, and mixed providers or real/sample records
raise `MetricsInputError`. An empty match list returns zero observed matches and
unavailable derived metrics. A team absent from a nonempty match list is an error.

`MatchEvents.complete` defaults to false. Set it true only after establishing that
you have the full match event feed, not filtered team events, selected highlights,
or a partial download. Both teams' actions are required for conceded metrics and
pass share. The engine cannot prove completeness from an event list alone. Empty,
missing, or unconfirmed feeds are excluded from event metrics, never treated as
zero-action games. A full feed with no shots genuinely contributes zero shots/xG.

Every metric returns its numerator, denominator, eligible match IDs, excluded match
IDs with reasons, unit, value, and status (`available`, `partial`, `unavailable`).
Each formula uses only matches eligible for that metric. Missing required fields
exclude the entire match for that metric, not merely the missing observations.
Consequently different metrics can have different coverage: do not combine them
into a score without aligning coverage first. Eligibility with a zero denominator
is retained, but the final ratio is null if the aggregate denominator is zero.
No eligible observations also produces null, not zero.

`matches_played` is the number of supplied match records containing the team. It is
not a verified count of the team's entire season. Supply completed match records;
score fields must be final goals excluding shootout tallies. Match catalog presence
does not establish full-season coverage. The engine does not infer total season
length, missing fixtures, or extrapolate totals.

All event metrics include periods 1–4 (including extra time) and exclude period 5
(penalty shootouts). Penalty shots during play remain included. Final match scores
are used for goals, preserving own goals rather than reconstructing scores from
shots. Match rates are **per match, not per 90 minutes**: extra-time games can have
larger values. Unknown team attribution on an on-ball/defensive action excludes the
feed from event metrics because for/against counts cannot be safely separated.

## Formulas

For each row below, let `E` be its eligible matches and `M = |E|`. Sum counts across
`E` before dividing. Percentages and averages are weighted by their observation
counts, never calculated as an unweighted mean of match percentages. Numerators
for percentage metrics already include the factor of 100.

| Output | Formula | Football interpretation and required data |
| --- | --- | --- |
| `matches_played` | Number of supplied team match records | Size of the observed match sample, home and away |
| `goals_for_per_match` | Sum of team final goals / M | Scoring output; requires both final scores for each eligible match |
| `goals_against_per_match` | Sum of opponent final goals / M | Goals conceded; same score eligibility as goals for |
| `shots_per_match` | Team Shot events / M | Shooting volume, including blocked shots and in-game penalties |
| `shots_conceded_per_match` | Opponent Shot events / M | Opponents' shooting volume |
| `xg_per_match` | Sum of team shot xG / M | Source model's estimated scoring chances; every team shot must have finite xG in [0,1] |
| `xg_conceded_per_match` | Sum of opponent shot xG / M | Quality and quantity of chances allowed; every opponent shot must have xG |
| `passes_attempted_per_match` | Team Pass events / M | Passing volume; includes restarts, crosses and unsuccessful passes |
| `pass_completion_pct` | 100 × completed team passes / team pass attempts | Passing success, influenced by difficulty and risk; every pass needs known completion |
| `possession_pass_share_pct` | 100 × team pass attempts / both teams' pass attempts | A **passing-share possession proxy**, not measured time on the ball |
| `passes_per_possession` | Team passes in team-owned possessions / team-owned possessions | Passing sequence length; includes possessions without passes in the denominator |
| `average_pass_length` | Sum sqrt((end_x − start_x)² + (end_y − start_y)²) / team passes | Average straight-line distance from start to recorded endpoint for all attempted passes |
| `net_forward_progression_per_pass` | Sum (end_x − start_x) / team passes | Signed forward displacement: backwards passes subtract, lateral passes contribute zero |
| `defensive_actions_per_match` | (Tackle duels + Interceptions + Blocks + Clearances) / M | Defensive action volume; includes unsuccessful attempts, not a success or pressing measure |
| `advanced_defensive_actions_per_match` | Those defensive actions starting at x ≥ 80 / M | Defensive activity in the attacking third, under the same action definition |
| `attacking_third_activity_per_match` | Team Pass + Carry + Shot + Dribble events starting at x ≥ 80 / M | On-ball activity starting in the attacking third; not touches, entries, or distinct attacks |
| `counterattack_possession_share_pct` | 100 × explicitly counter-tagged team possessions / team possessions | Share of source-tagged counterattacking possessions, not an inferred transition probability |

`high_turnovers_per_match` is returned as unavailable with a reason. We have not
implemented a validated derivation of controlled regains after opponent possession.
An advanced interception, tackle attempt, pressure, or recovery alone does not prove
a high turnover. Transition speed, time possession, PPDA, defensive line height,
and low-block labels are not calculated. No score normalizes any metric onto 0–100;
the percentage values above are ordinary ratios, not tactical scores.

## Event semantics and spatial conventions

The StatsBomb adapter populates optional normalized fields on `Event`:
`pass_completed`, `pass_end_location`, `shot_xg`, `possession_id`,
`possession_team_id`, `from_counterattack`, `is_tackle`, and `coordinate_system`.
Other providers must supply equivalent semantics explicitly; analytics never reads
provider-specific `source_fields`. Missing semantic fields stay null. Existing
fixture-provider examples lack many of these fields, so their detailed metrics
will appropriately be unavailable unless a complete, enriched test feed is supplied.

For StatsBomb Pass objects, an omitted `outcome` means complete. Documented failed
outcomes (`Incomplete`, `Out`, `Pass Offside`, `Injury Clearance`) mean false.
`Unknown`, null, or unrecognized outcomes stay null, and a missing Pass object does
not count as a completed pass. See the upstream
[open-data specification](https://github.com/statsbomb/open-data/blob/master/doc/StatsBomb%20Open%20Data%20Specification%20v1.1.pdf)
and [pass-filtering guide](https://support.hudl.com/s/article/filter-event-data-statsbomb?language=en_US).
Source `shot.statsbomb_xg` is preserved, never estimated when absent. Tackle duels
are identified by their subtype; aerial-lost duels are not tackles. A duel lacking
its subtype excludes that match's defensive metrics.

Spatial formulas require `coordinate_system="attacking_120x80"`: x increases toward
the acting team's attacking goal, from 0 to 120; y ranges from 0 to 80. The StatsBomb
adapter identifies this convention. Do not flip opponents' coordinates again.
Any missing, non-finite, out-of-bounds, or unrecognized coordinates on relevant
actions exclude that match from the affected spatial metric. Distances are in this
standardized pitch coordinate system, **not physical meters**. Pass length is derived
from the endpoint rather than trusting a source-specific distance unit. It measures
straight-line displacement, not the ball's flight path. Attempted-pass endpoints
also do not prove completed territorial gain. x=80 is included in the attacking third.

A possession is keyed by **match, period, and possession ID**, so reused IDs across
matches or periods never merge. Ownership must be known for every Pass, Carry,
Shot, and Dribble; contradictory owners within a possession invalidate the metric
for that match. Other events with explicit possession identity and owner also
establish possessions. A team's passes inside an opponent-owned possession do not
count toward its passing sequence numerator. Possessions with no team passes count
as zero-pass possessions. These are source-defined possessions, not a new sequence
segmentation algorithm.

StatsBomb's `play_pattern.name == "From Counter"` maps to a true counterattack tag;
other recognized patterns map to false, and missing/unknown patterns stay null.
All events included in a team-owned possession must agree on the tag for the match
to contribute to counterattack share. This strict rule favors known coverage over
guesses. Counter tags reflect the source's definition, not a universal definition
or a guarantee that every fast transition has been tagged.

## Determinism, provenance, and usage

Matches are sorted by date/ID, events by index; sums use `math.fsum`. Calculations
have no random sampling, current timestamps, rounding, or input mutation. Results
retain sorted unique input provenance and a metrics version. The same inputs yield
the same profile regardless of list order. Callers must keep source definitions,
fidelity versions, and xG model versions compatible; using the same provider alone
does not establish comparability across eras. Input validation prevents mixing
provider names and real/sample designations, but does not calibrate model versions.

```python
from app.analytics.team_season import TeamSeasonMetrics
from app.models.metrics import MatchEvents

# Retrieval happens outside analytics. provider, team_id, and season are selections.
matches = provider.get_team_matches(team_id, season)
feeds = {}
for match in matches:
    events = provider.get_match_events(match.id)
    # Mark complete only after checking source match/event coverage.
    feeds[match.id] = MatchEvents(events=events, complete=True)

profile = TeamSeasonMetrics.calculate(team_id, season, matches, feeds)
print(profile.metrics["shots_per_match"].model_dump())
```

For unavailable downloads, handle the provider error outside the engine and omit
the feed; its match is then explicitly excluded from event metrics. Do not catch
all provider failures and pass an empty list as if it were a complete match.

Run `python -m pytest` from `backend/` in the project virtual environment. Tests use
synthetic feeds with known totals, missing fields, different home/away roles, zero
denominators, extra time/shootouts, duplicate and mismatched inputs, and mixed data
provenance. No internet is required. All statistical formulas use the standard
library; pandas/numpy are unnecessary for these small linear aggregations.

## Interpreting style

Sequence length, pass distance, signed progression, and counter-tagged possession
share describe how a team moves the ball. Pass share adds a limited possession proxy.
Advanced defensive activity suggests where defensive actions occur, but is not
equivalent to pressing intensity. Shots/xG for and against describe attacking and
defensive output more than style, while goals are particularly sensitive to finishing
and small samples. Opponents, score state, red cards, extra time, and selected-match
coverage can change every metric. Compare these raw observations with their coverage
and context before designing tactical scores or assigning labels.
