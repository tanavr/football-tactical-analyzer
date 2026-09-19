# Football Tactical Analyzer architecture

## Scope and status

The project is in the planning stage. This document describes the proposed design;
application code and a data provider have not been added yet.

The application will let a user select a club and season, inspect seven tactical
traits and their explanations, compare two club-seasons, and simulate a hypothetical
match with win/draw/loss probabilities. Clubs and seasons will come from the dataset,
so historical comparisons use the same logic as current-season comparisons.

## Planned layout

```text
frontend/                 React + Vite + JavaScript; lightweight Recharts visuals
backend/
  app/
    api/                  FastAPI routes and request orchestration
    analytics/            Pure rate, normalization, scoring, and simulation functions
    data/                 Source interface, provider adapters, collection commands
    models/               Pydantic canonical records and API schemas
  tests/                  pytest analytics, adapter, and API tests
data/                     Local datasets; small labeled fixtures when added
docs/                     Architecture, metric definitions, and source documentation
```

Directories will be added as their modules are implemented. The analytics layer will
use pandas/numpy for tabular analysis and scipy for statistical distributions.
There is no planned machine-learning dependency for the initial model.

## Data flow and contracts

Collection commands download or import licensed data separately from serving HTTP
requests. Provider adapters map that data into validated canonical records. Analytics
consume those records, and routes serialize their results to the frontend. The
frontend displays calculations and explanations; it does not reimplement scoring.

A planned Python `DataSource` protocol exposes competition/season and club discovery,
team-season records, match records, and supported metric capabilities. Implementations
may read fixtures or a real provider's local data. Provider-specific names, units,
identifiers, and collection details stay inside adapters. Inject the source into the
API rather than selecting providers inside analytics.

Canonical records carry source and stable club/competition/season IDs, date boundaries,
minutes and matches covered, metric values and units, and metric availability. Retain
source name/version, retrieval date, definitions, licensing notes, and an explicit
`real` or `sample` data designation. Club names are display fields, not join keys.
Season labels must not assume every competition spans two calendar years.

Missing metrics remain null with a reason. Check nonnegative counts, valid minutes,
bounded proportions, duplicate records, and denominator coverage at ingestion.
Store totals and denominators so rates use weighted aggregation rather than averages
of match percentages. Never combine mismatched match coverage. Metric definitions
must be compatible before pooling providers; otherwise report incompatibility.

## Proposed tactical metrics

The following metrics are provisional until a data source is selected. Missing inputs
leave the corresponding trait unavailable. The metric reference will record source
fields, formulas, units, coverage, cohort rules, and limitations for each version.

For an event count `x`, `per90(x) = 90 * x / minutes`. Undefined or nonpositive
denominators produce an unavailable value. Percentages below are proportions in
`[0, 1]` until formatted for display. Define `P(x)` as the cohort percentile score
below; each trait lies on a 0–100 relative scale.

| Trait | Proposed raw measure | Score and interpretation |
| --- | --- | --- |
| Possession | Possession time / measured in-play time, or a documented source possession measure | `P(possession)`; higher means more ball control |
| Pressing intensity | PPDA: opponent passes in the defined pressing zone / team defensive actions in that same zone | `100 - P(PPDA)`; higher means fewer passes allowed per action |
| Attacking intensity | Shots per 90 | `P(shots_per90)`; attacking volume, not shot quality |
| Directness | Long-pass attempts / all pass attempts | `P(long_pass_share)`; a long-ball proxy, not attack speed |
| Defensive activity | Tackles plus interceptions per 30 out-of-possession minutes: `30 * actions / oop_minutes` | `P(defensive_action_rate)`; activity, not defensive quality |
| Counterattacking tendency | Source-tagged counterattack possessions / all team possessions | `P(counter_share)`; requires documented, consistent event tags |
| Passing style | Short-pass attempts / all pass attempts | `P(short_pass_share)`; higher means a shorter passing preference |

PPDA zone boundaries and eligible actions, pass-length thresholds, and counterattack
definitions must be recorded per provider and reconciled before comparisons. Do not
infer counters from low possession or substitute tackles alone for pressing. Defensive
activity requires measured out-of-possession time; it is unavailable without it.
Directness and passing style overlap and are not independent dimensions.

## Normalization and tactical descriptions

Build reference cohorts from all eligible teams in the same competition-season,
using consistent metric definitions and match coverage. Initially require coverage
of at least 80% of a team's completed league matches and at least 10 eligible teams
per metric. These starting thresholds are configurable and need validation.
An insufficient cohort produces an unavailable score and explanation.

For `n` eligible teams and ascending average rank `r` (ties use average ranks), define
`P(x) = 100 * (r - 1) / (n - 1)`. A constant cohort yields 50 for every team. Reverse
direction only for metrics such as PPDA where a smaller value implies greater
intensity. Missing records are excluded per metric, with cohort size and coverage
returned in results. Do not impute values or silently renormalize a composite score.

Comparing seasons displays raw metrics alongside their own league-season percentile
scores, cohort metadata, and data limitations. These percentiles compare relative
style within each environment; they do not establish absolute cross-league strength.
Do not normalize only the two selected teams or treat percentile differences as
calibrated probability differences. Use historical data available at the evaluation
cutoff when backtesting to prevent future-data leakage.

Initial tactical labels use configurable thresholds: possession,
pressing, counterattacking, or directness scores of at least 75 trigger
“possession-oriented,” “high pressing,” “counterattacking,” or “direct,” respectively.
Labels may coexist. Use “balanced” only if all seven traits are available and each is
between 25 and 75, excluding 75; otherwise return a mixed or incomplete profile.
Missing evidence must not be described as balanced.

Do not infer “defensive / low block” from high defensive activity or low possession.
That label is deferred until spatial evidence such as defensive line height or action
locations supports a separately documented rule. Return reasons for every assigned
label and expose score/rule versions so descriptions remain reproducible.

## Hypothetical match model

Start with an independent Poisson goals baseline and a neutral venue by default.
For each team's competition-season, let `g` be total league goals / total team-match
appearances. With goals for `GF`, goals against `GA`, and matches `M`, estimate
`attack = (GF / M) / g` and `defense = (GA / M) / g`; a larger defense ratio means
more goals conceded. Reject zero matches, unavailable baselines, or `g <= 0`.

For teams A and B, use `g_ref = (g_A + g_B) / 2`,
`lambda_A = g_ref * attack_A * defense_B`, and
`lambda_B = g_ref * attack_B * defense_A`. This symmetric baseline is a transparent
scenario assumption, not a validated conversion between league or era strengths.
Display that limitation prominently for cross-competition and historical matchups.
Do not use tactical percentiles as arbitrary probability multipliers.

Use the outer product of Poisson goal probabilities to sum A wins, draws, and B wins.
Choose each goal cutoff so its omitted tail is at most `5e-9`; the joint omitted mass
is then at most `1e-8`. Report that mass and normalize the retained outcome totals.
Handle zero expected goals explicitly. The analytical calculation is deterministic;
any later Monte Carlo simulation must expose its random seed and sample size.

Return expected goals, all three probabilities, venue assumptions, data provenance,
model version, and limitations. Home advantage requires an explicitly estimated,
documented parameter before offering a home/away option. Small samples, independent
goals, absent player availability, and uncalibrated league strength limit the model.
Do not claim calibrated accuracy or invent confidence intervals. Evaluate on held-out,
chronologically later matches using log loss, Brier score, and calibration summaries
against simple baselines before making predictive claims.

## Planned API and user experience

- `GET /api/catalog`: available competitions, clubs, seasons, and source capabilities.
- `GET /api/profiles`: one club-season selected by stable identifiers.
- `GET /api/comparisons`: two explicitly identified club-seasons and their profiles.
- `POST /api/simulations`: two club-season identifiers and supported venue settings.

Use Pydantic request/response schemas and explicit errors for unknown records,
incompatible definitions, or insufficient data. Return partial profiles with reasons
for unavailable traits; reject simulations lacking required inputs. Routes orchestrate
source reads and analytics calls without implementing formulas or downloading data.

The frontend will offer source-driven selectors, profile cards, a trait chart, raw
metric comparisons, explanation text, and a probability display. Show sample-data
badges, missing-data states, cohort context, and model limitations where relevant.
Use accessible labels and text/table equivalents for charts; do not encode meaning
only in color. Include loading, error, and empty states.

## Implementation order and tests

1. Select a permitted source; document coverage, definitions, and licensing. Add the
   canonical models, source protocol, and a small explicitly labeled fixture adapter.
2. Implement and test rates, percentile normalization, trait scores, and label rules.
3. Add thin profile/comparison endpoints and frontend views.
4. Add the Poisson model, evaluation documentation, simulation endpoint, and UI.

Use focused Git commits after stable milestones. pytest coverage should include unit
conversion, weighted rates, invalid denominators, ties, constant/small cohorts,
missing metrics, threshold boundaries, source compatibility, and sample/real data
separation. Simulation tests should cover nonnegative probabilities summing to one,
neutral-venue swap symmetry, zero-goal cases, and truncation tolerance. Adapter tests
verify canonical contracts; API tests verify validation and serialized metadata.
Add frontend build/lint checks when frontend configuration exists.

Never commit secrets, `.env` files, dependencies, virtual environments, or large raw
datasets. Keep collection output ignored and review fixture size and rights before
tracking it. Until application code is added, checks cover document consistency,
ignore rules, and whitespace.
