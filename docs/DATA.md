# Football data layer

## Providers and boundaries

`backend/app/data/provider.py` defines the `FootballDataProvider` abstract base class.
Providers implement `get_competitions()`, `get_seasons(competition)`,
`get_matches(competition, season)`, and `get_match_events(match_id)`. Shared methods
derive `get_teams(competition, season)` and `get_team_matches(team, season)` from
available matches, including both home and away appearances.

Competition and team arguments are namespaced ID strings. Season arguments are
`Season` records carrying both season ID and competition ID: a year label or a
provider season ID alone does not uniquely identify a competition-season. Unknown
IDs and mismatched scopes raise `DataNotFoundError`. A team absent from the available
matches raises that error rather than implying it played zero matches. A valid empty
match/event JSON array returns an empty list; a missing resource raises an error.

`StatsBombOpenDataProvider` maps public JSON into Pydantic models in
`backend/app/models/football.py`. `CachedJSONSource` handles HTTP and disk caching
separately from that mapping. Neither layer imports analytics or FastAPI. The
API exposes these providers through a service layer; the frontend is not integrated.
Default HTTP serving is cache-only; use `python -m app.data.prepare` for separate
collection. See [API.md](API.md) for preparation and reviewed coverage requirements.

`FixtureFootballDataProvider` supplies a tiny, invented Sample League, two Sample
teams, one match, and one event. All records carry `data_kind="sample"` and fixture
IDs. These values are for tests only, not representative statistics. The provider
returns independent copies and never performs network access. Tests also exercise
the real adapter using explicitly synthetic upstream-shaped records and mock HTTP.

## Public source

The provider reads the documented [StatsBomb Open Data repository](https://github.com/statsbomb/open-data):

- `data/competitions.json`: competition-season catalog.
- `data/matches/{competition_id}/{season_id}.json`: available matches.
- `data/events/{match_id}.json`: match events.

It requires no account, commercial credentials, or statsbombpy dependency. Only the
public files are requested. Lineups and selected-match 360 files exist upstream but
are not ingested yet. See the upstream [format documentation](https://github.com/statsbomb/open-data/tree/master/doc).

Public availability does not mean unrestricted licensing. Review the upstream
[license](https://github.com/statsbomb/open-data/blob/master/LICENSE.pdf) before
redistribution or deployment. Its README requests StatsBomb attribution and logo use
when sharing research, analysis, or insights. No upstream raw files are committed here.

## Normalized records

- IDs are namespaced, for example `statsbomb:team:1`; names are display values.
- Competitions preserve country and gender. Seasons retain source labels without
  inventing start/end dates or assuming a two-year calendar.
- Matches contain a parsed date, both teams, optional scores, source event status,
  and provider metadata (including available fidelity/data versions).
- Events retain source order by index, type, period, minute/second, optional team,
  player, and location. Location remains in StatsBomb coordinates, ordinarily a
  120-by-80 pitch, not meters or a normalized direction across providers. Missing
  locations and players remain null. Event timestamps are not possession durations.
- `source_fields` preserves the original event object, including attributes such as
  pass details or shot xG if actually supplied. These fields are provider-specific,
  not promised universal metrics. No commercial aggregates or tactical scores are
  generated. Unknown extra source fields are retained here for later adapters.
- Provenance includes source, real/sample designation, URL, UTC retrieval time,
  requested branch/commit revision, and SHA-256 of the downloaded text. An injected
  mock transport is a testing mechanism; the StatsBomb adapter always labels its
  records as real. Use the fixture provider when presenting sample data.

Required missing fields, invalid model values, duplicate match/event IDs, duplicate
event indices, or mismatched match scope raise `DataFormatError`. Normalization does
not silently skip malformed records. Optional missing values remain null, not zero.
No coverage percentage or full-season completeness is inferred from catalog presence.

## Cache and errors

The default cache is repository-root `data/cache/statsbomb/`, independent of the
working directory. It is gitignored. Files are keyed by full URL (including revision)
and store the raw JSON text plus provenance. Writes use a temporary file and atomic
replacement. Reads verify the content hash and metadata and validate the JSON shape.
Record validation runs in the adapter on both downloads and cached reads.

Cached files are reused indefinitely by default. This is intentional for local
development, not a freshness guarantee. Pass `refresh=True` to redownload, or
`cache_dir=None` to disable disk caching. A refresh failure raises an error, without
silently returning stale data. Corrupt files fail explicitly; refresh them to recover.
Schema-invalid raw JSON can be cached and will continue failing until refreshed.

The default revision is `master`, which changes upstream. Pin a repository commit
hash via `revision=...` for reproducible comparisons; a branch name and retrieval
timestamp alone are not an immutable source version. There is no background sync,
automatic retry, bulk season download, or cache eviction yet. Requests time out after
30 seconds. Errors are subclasses of `DataProviderError`:

| Error | Meaning |
| --- | --- |
| `DataNotFoundError` | Unknown identifier, invalid scope, or HTTP 404 |
| `DataNetworkError` | Timeout, connection failure, or other unsuccessful HTTP status |
| `DataFormatError` | Invalid JSON, cache integrity failure, or invalid normalized records |
| `DataCacheError` | Cache read/write failure |

## Usage

From `backend/`, with the virtual environment activated and dependencies installed:

```python
from app.data.json_source import CachedJSONSource
from app.data.statsbomb import StatsBombOpenDataProvider

provider = StatsBombOpenDataProvider(CachedJSONSource())
competitions = provider.get_competitions()
competition = competitions[0]  # In a UI, use the user's selection.
seasons = provider.get_seasons(competition.id)
season = seasons[0]
teams = provider.get_teams(competition.id, season)
matches = provider.get_matches(competition.id, season)
if teams:
    team_matches = provider.get_team_matches(teams[0].id, season)
if matches:
    events = provider.get_match_events(matches[0].id)
```

All catalog choices come from data, not hardcoded teams or seasons. Swap in
`FixtureFootballDataProvider()` for offline development. Install/update dependencies
with `python -m pip install -e '.[dev]'`. Run `python -m pytest` for the entire backend
suite; tests block real HTTP and require no downloads or cached data.

## Availability and comparison limitations

The catalog snapshot below was retrieved on 2026-10-01. It describes available
competition-season entries, **not verified complete schedules**. There are 24
competitions and 80 competition-season pairs. Refresh the provider to discover
subsequent additions. A complete inventory follows.

| Competition (source ID) | Seasons in catalog |
| --- | --- |
| 1. Bundesliga (9) | 2023/2024, 2015/2016 |
| African Cup of Nations (1267) | 2023 |
| Champions League (16) | 2018/2019, 2017/2018, 2016/2017, 2015/2016, 2014/2015, 2013/2014, 2012/2013, 2011/2012, 2010/2011, 2009/2010, 2008/2009, 2006/2007, 2004/2005, 2003/2004, 1999/2000, 1972/1973, 1971/1972, 1970/1971 |
| Copa America (223) | 2024 |
| Copa del Rey (87) | 1983/1984, 1982/1983, 1977/1978 |
| FA Women's Super League (37) | 2023/2024, 2020/2021, 2019/2020, 2018/2019 |
| FIFA U20 World Cup (1470) | 1979 |
| FIFA World Cup (43) | 2022, 2018, 1990, 1986, 1974, 1970, 1962, 1958 |
| Frauen Bundesliga (135) | 2023/2024 |
| Indian Super league (1238) | 2021/2022 |
| La Liga (11) | 2020/2021, 2019/2020, 2018/2019, 2017/2018, 2016/2017, 2015/2016, 2014/2015, 2013/2014, 2012/2013, 2011/2012, 2010/2011, 2009/2010, 2008/2009, 2007/2008, 2006/2007, 2005/2006, 2004/2005, 1973/1974 |
| Liga F (182) | 2023/2024 |
| Liga Profesional (81) | 1997/1998, 1981 |
| Ligue 1 (7) | 2022/2023, 2021/2022, 2015/2016 |
| Major League Soccer (44) | 2023 |
| North American League (116) | 1977 |
| NWSL (49) | 2023, 2018 |
| Premier League (2) | 2015/2016, 2003/2004 |
| Serie A (12) | 2015/2016, 1986/1987 |
| Serie A Women (131) | 2023/2024 |
| UEFA Euro (55) | 2024, 2020 |
| UEFA Europa League (35) | 1988/1989 |
| UEFA Women's Euro (53) | 2025, 2022 |
| Women's World Cup (72) | 2023, 2019 |

Cross-season work must first audit match counts per team, opponent coverage, event
availability, and source/fidelity versions. Historical entries can contain only
selected matches; a catalog season is not proof of representative league-wide data.
Different genders, youth/senior competitions, national teams, club competitions, and
knockout formats must not automatically share normalization cohorts. Extra time and
shootouts need explicit treatment before rates or goal models are calculated.

Liverpool's Premier League 2019/20 season is absent from this catalog. The provider
cannot currently support that example as a full league-season profile. Arsenal
comparisons must likewise check actual match coverage rather than assuming every
listed Premier League season contains every team's entire campaign.

Possession percentage, PPDA, counterattack rates, and other tactical aggregates are
not supplied as ready-to-use fields by this layer. Some can potentially be derived
from events only after definitions, coverage, and denominators are established.
Continuous tracking and defensive-line height are not available through these
methods; 360 snapshots are a separate, selectively available source. Raw rates are
now calculated by the separate engine documented in [METRICS.md](METRICS.md).
No cross-league strength adjustment, tactical normalization score, or prediction is built.

The event adapter now also exposes optional normalized pass completion/endpoints,
shot xG, possession identity/owner, counter tags, tackle classification, and an
explicit coordinate convention. These semantic fields allow analytics to avoid
reading provider-specific `source_fields`. Their missing-data rules are in METRICS.md.
