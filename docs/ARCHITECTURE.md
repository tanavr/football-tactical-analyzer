# Football Tactical Analyzer architecture

## Scope and status

The project has a React landing page and a FastAPI health endpoint. This document
describes the planned analytical features. The data-provider layer is implemented
(see `DATA.md`), as are raw team-season metrics (see `METRICS.md`) and interpretable
tactical scores/labels (see `TACTICAL_MODEL.md`). The API exposes these layers through
`FootballService` (see `API.md`). Match simulations and frontend integration of
these analytics are not implemented yet.

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
    services/             Provider access, coverage checks, analytics orchestration
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

The Python `FootballDataProvider` abstract base class exposes competition/season and
team discovery, matches, team matches, and match events. The separate
`TeamSeasonMetrics` engine summarizes already-retrieved records without I/O.
Implementations read fixtures or public
StatsBomb JSON through a local cache. Provider-specific names, units,
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

## Tactical metrics, normalization, and descriptions

Raw statistical definitions live in `METRICS.md`; implemented score formulas,
coverage requirements, and ordered classification rules live in `TACTICAL_MODEL.md`.
These replace the preliminary metric proposals based on fields not yet available.

`TacticalStyleModel` consumes `TeamSeasonProfile` records from one competition-season
and an independently verified full roster with expected completed-match counts.
Default eligibility requires 10 covered matches and 80% match coverage per team,
plus 10 eligible teams and 80% roster coverage per dimension. Composite components
must use identical match sets within each team. Missing values are not imputed.

For ascending average rank `r` among `n` eligible teams, `P(x) = 100*(r-1)/(n-1)`.
Ties use average ranks, constant components score 50, and insufficient samples return
null. Two-component dimensions average their percentile scores with equal weights.
The implemented dimensions are possession (passing-share proxy), pressing
(advanced defensive-action share proxy), directness, attacking intensity, defensive
activity, counterattacking tendency, and passing/control.

Explicit top-quartile rules assign identities and supporting traits; deterministic
text templates explain the scores and limitations. Balanced requires all seven
scores in [25,75), with separate handling for a wholly constant reference cohort.
The model does not claim high pressing or deep/low-block defending from the available
activity metrics. PPDA, measured possession time, and block-depth evidence remain
future extensions rather than silently invented fields.

Cross-season comparisons must show raw metrics, coverage, and each team's own
competition-season relative scores. Relative style does not measure absolute
cross-league strength. Do not normalize only the two selected teams or interpret
percentile differences as calibrated probability differences. Backtests must use
only data available at the evaluation cutoff.

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

## API and planned user experience

- `GET /competitions` and `GET /competitions/{competition_id}/seasons`: discovery.
- `GET /competitions/{competition_id}/seasons/{season_id}/teams`: available teams.
- The same scoped path plus `/teams/{team_id}/metrics` or
  `/teams/{team_id}/tactical-profile`: raw metrics or scored profiles.
- Comparison and simulation endpoints remain planned, not implemented.

See `API.md` for response models, errors, offline preparation, and the server-owned
coverage manifest. Default request handling never downloads data. Uncached resources
return 503; tactical requests lacking independently reviewed roster counts return
409. Verified but insufficient cohorts return the model's unavailable scores.

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
tracking it. Current scaffold checks cover the health endpoint, local-development
CORS behavior, and the frontend production build, alongside whitespace checks.
