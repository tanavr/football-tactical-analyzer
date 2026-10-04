# Football API

Start from `backend/` with the virtual environment active:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Interactive Swagger docs: <http://127.0.0.1:8000/docs>. OpenAPI schema:
<http://127.0.0.1:8000/openapi.json>. ReDoc: <http://127.0.0.1:8000/redoc>.
All routes below are GET requests and return JSON with Pydantic response models.
No authentication is required for this local-development API. Bind to localhost;
production deployment, access control, and request limits are separate work.

## Routes

Let `B = /competitions/{competition_id}/seasons/{season_id}`.

| Path | Response model | Purpose |
| --- | --- | --- |
| `/health` | `HealthResponse` | Process liveness; does not download or check football data |
| `/competitions` | `CompetitionList` | Source competition catalog |
| `/competitions/{competition_id}/seasons` | `SeasonList` | Seasons within a competition |
| `B/teams` | `TeamList` | Teams appearing in available matches |
| `B/teams/{team_id}/metrics` | `TeamSeasonProfile` | Raw metrics, denominators, coverage, and provenance |
| `B/teams/{team_id}/tactical-profile` | `TacticalProfile` | Cohort-relative scores, rule-based identity, and explanation |

Competition scope is included in the path because season IDs alone are ambiguous
across competitions. Use IDs returned by discovery endpoints, not display names or
year labels. IDs may contain letters, digits, colons, underscores and hyphens, must
start with a letter/digit, and have at most 128 characters. Unknown valid IDs return
404; malformed IDs return 422. There are no unscoped `/teams` aliases yet.

## Prepare real data separately

The default app serves **local cached StatsBomb data only**. It never initiates
upstream HTTP requests. Preparation uses the same provider abstraction, in a separate
process, so requests do not silently launch large season downloads.

```bash
# Catalog only: prints competition and season IDs.
python -m app.data.prepare

# Example public competition-season; download its match records.
python -m app.data.prepare --competition statsbomb:competition:43 --season statsbomb:season:106

# Explicitly opt into all available event files for that season.
python -m app.data.prepare --competition statsbomb:competition:43 --season statsbomb:season:106 --events
```

Preparation requires internet access, no commercial credentials. `--refresh` forces
redownloads. If preparation fails, it exits nonzero and retains successfully cached
files; retrying without refresh reuses those files. It does not certify event or
season completeness. See [DATA.md](DATA.md) for cache format and source limitations.

An uncached required resource returns 503 `data_not_prepared`, not 404 or an empty
season. Corrupt data fails explicitly rather than falling back to a network fetch.
Discovery and score-based goals metrics can work once catalog/matches are cached.
Detailed event metrics require reviewed event-completeness evidence as described below.

## Coverage configuration

The API must not invent the completeness/roster inputs required by the existing
analytics engines. Server-owned `SeasonCoverage` entries record reviewed evidence:

```json
[
  {
    "competition_id": "fixture:competition:1",
    "season_id": "fixture:season:1",
    "source": "fixture",
    "data_kind": "sample",
    "match_data_sha256": "not-applicable-synthetic",
    "complete_event_sha256": {"fixture:match:1": "not-applicable-synthetic"},
    "expected_matches": {"fixture:team:1": 1, "fixture:team:2": 1},
    "evidence": "Known synthetic test schedule and event list; not real football"
  }
]
```

This is a **synthetic schema example**, not a real StatsBomb manifest. For real data,
use the actual competition/season, real-data designation, source name, and SHA-256
hashes printed by preparation and stored in cache provenance. Only list event files
whose full-match coverage has been reviewed. `expected_matches` must include the
full independently verified roster and completed-match counts at a common cutoff;
do not infer them from selected open-data matches. `evidence` records that review's
source/cutoff. Hashes bind the review to the specific prepared data, not to a moving
upstream branch. The software checks consistency but cannot perform the review.

Store real configuration in repository-root `data/coverage.json` (gitignored), or
set `FOOTBALL_COVERAGE_PATH` to another local JSON file before starting the server.
The optional file is loaded at app creation; restart after changing it. Explicitly
configured missing files, malformed manifests, and duplicate scopes fail startup.
Never put credentials in this file. Request parameters cannot override coverage or
lower the scorer's thresholds.

- Without a coverage entry, metrics return 200 with match-count/known-score metrics;
  event metrics remain null with exclusion reasons. No event downloads are attempted.
- With reviewed event hashes, only those feeds contribute to event metrics. Other
  matches stay visible as excluded coverage; missing data is never treated as zero.
- A changed match/event hash or incompatible source/sample designation returns 409.
- Without reviewed roster counts, tactical scoring returns 409 `coverage_not_verified`.
- With valid review but a cohort too small for the scorer, tactical scoring returns
  200 with null scores and `Insufficient Evidence`, rather than fabricated scores.
- A feed listed as reviewed but missing from the cache fails the request with 503;
  malformed data fails with 502. Operational failures are not silently hidden as
  partial football evidence.

No real coverage manifest is supplied by this stage. A complete tournament may also
have fewer than the default 10 matches per team, so verified availability alone does
not ensure tactical scores. See [TACTICAL_MODEL.md](TACTICAL_MODEL.md).

## Offline demonstration and response shapes

For a quick demonstration with clearly labeled sample data, stop the normal server
and run:

```bash
python -m uvicorn app.main:create_demo_app --factory --host 127.0.0.1 --port 8000
```

Then request:

```bash
curl http://127.0.0.1:8000/competitions
curl http://127.0.0.1:8000/competitions/fixture:competition:1/seasons
curl http://127.0.0.1:8000/competitions/fixture:competition:1/seasons/fixture:season:1/teams
curl http://127.0.0.1:8000/competitions/fixture:competition:1/seasons/fixture:season:1/teams/fixture:team:1/metrics
```

Abbreviated response shapes (additional fields omitted here; inspect `/docs` for full schemas):

```text
competitions: {"competitions": [{"id": "fixture:competition:1", "name": "Sample League", "provenance": {...}}]}
seasons: {"competition_id": "fixture:competition:1", "seasons": [{"id": "fixture:season:1", ...}]}
teams: {"competition_id": "fixture:competition:1", "season_id": "fixture:season:1", "teams": [{"id": "fixture:team:1", ...}]}
metrics: {"team_id": "fixture:team:1", "matches_played": 1, "metrics": {"goals_for_per_match": {"value": 1.0, "unit": "goals/match", ...}}, "provenance": [...]}
tactical-profile: {"team_id": "...", "scores": {"possession": {"value": null, "reason": "...", ...}, ...}, "primary_identity": "Insufficient Evidence", "secondary_traits": [], "explanation": "...", ...}
```

Demo mode deliberately supplies no coverage review, so its tactical endpoint returns
409. Endpoint tests also run with explicit synthetic coverage and verify both the
small-fixture insufficient-evidence result and numeric scores for an 11-team synthetic
league. Sample designation is retained in every response's record provenance or
top-level tactical `data_kind`; nothing is presented as real football.

## Errors and layering

Handled errors use `{"error": {"code": "...", "message": "..."}}`:

| HTTP | Code | Meaning |
| --- | --- | --- |
| 404 | `not_found` | Unknown competition/season/team or unavailable requested provider resource |
| 409 | `coverage_not_verified` | Missing, stale, or incompatible review metadata |
| 422 | `invalid_request` | Invalid route parameter format; message identifies the field |
| 502 | `invalid_source_data` | Malformed provider/cache records or incompatible analytics inputs |
| 503 | `data_not_prepared` | Required resource is not in the offline cache |
| 503 | `data_unavailable` | Provider transport or local-cache access failure |

These messages do not expose local paths or upstream response bodies. Unknown paths
and unsupported HTTP methods retain FastAPI's standard 404/405 `detail` responses.
Unexpected programming errors remain server errors rather than being mislabeled as
bad user input. CORS remains limited to the two local port-5173 frontend origins.

`api/football.py` validates path parameters and calls `services/football.py`.
`FootballService` resolves identifiers, retrieves records through `FootballDataProvider`,
checks review metadata, and calls the existing pure analytics modules. Tactical requests
load each reviewed match's events once, then build team profiles for the available
cohort. Calculations and provider I/O are synchronous route dependencies/handlers
and run in FastAPI's thread pool. There is no persistent derived-profile cache yet;
large prepared seasons can still take time and memory to calculate.

Tests inject `FixtureFootballDataProvider` through `create_app(provider, coverage)`.
`get_service` can also be overridden using FastAPI dependencies. No mutable global
test provider is shared with the default app. Run `python -m pytest` from `backend/`;
all tests block external HTTP.
