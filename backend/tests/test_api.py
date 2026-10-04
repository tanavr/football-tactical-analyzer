from collections import Counter
from pathlib import Path
from typing import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from app.data.fixture import FixtureFootballDataProvider
from app.data.json_source import CachedJSONSource
from app.data.provider import DataCacheError, DataFormatError, DataNetworkError, DataNotFoundError
from app.data.statsbomb import StatsBombOpenDataProvider
from app.main import create_app
from app.models.api import SeasonCoverage
from app.models.football import Competition, Event, Match, Season, Team

BASE = "/competitions/fixture:competition:1/seasons/fixture:season:1"
TEAM = BASE + "/teams/fixture:team:1"


def coverage() -> SeasonCoverage:
    return SeasonCoverage(competition_id="fixture:competition:1", season_id="fixture:season:1",
                          source="fixture", data_kind="sample", match_data_sha256="not-applicable-synthetic",
                          complete_event_sha256={"fixture:match:1": "not-applicable-synthetic"},
                          expected_matches={"fixture:team:1": 1, "fixture:team:2": 1},
                          evidence="Known synthetic test schedule and event list; not real football")


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(FixtureFootballDataProvider(), [coverage()])) as c:
        yield c


def test_catalog_and_scoped_teams(client: TestClient) -> None:
    competitions = client.get("/competitions")
    assert competitions.status_code == 200
    assert competitions.json()["competitions"][0]["provenance"]["data_kind"] == "sample"
    seasons = client.get("/competitions/fixture:competition:1/seasons")
    assert seasons.status_code == 200
    assert seasons.json()["seasons"][0]["id"] == "fixture:season:1"
    teams = client.get(BASE + "/teams")
    assert teams.status_code == 200
    assert len(teams.json()["teams"]) == 2


def test_metrics_uses_real_engine_with_fixture_data(client: TestClient) -> None:
    response = client.get(TEAM + "/metrics")
    assert response.status_code == 200
    body = response.json()
    assert body["matches_played"] == 1
    assert body["metrics"]["goals_for_per_match"]["value"] == 1
    assert body["metrics"]["passes_attempted_per_match"]["value"] == 1
    assert body["metrics"]["pass_completion_pct"]["value"] is None
    assert all(p["data_kind"] == "sample" for p in body["provenance"])
    away = client.get(BASE + "/teams/fixture:team:2/metrics").json()
    assert away["metrics"]["goals_against_per_match"]["value"] == 1


def test_tactical_returns_honest_insufficient_evidence(client: TestClient) -> None:
    response = client.get(TEAM + "/tactical-profile")
    assert response.status_code == 200
    body = response.json()
    assert body["primary_identity"] == "Insufficient Evidence"
    assert len(body["scores"]) == 7
    assert all(s["value"] is None and s["reason"] for s in body["scores"].values())
    assert body["data_kind"] == "sample"


def test_no_coverage_does_not_invent_complete_feeds_or_roster() -> None:
    with TestClient(create_app(FixtureFootballDataProvider())) as client:
        metrics = client.get(TEAM + "/metrics")
        assert metrics.status_code == 200
        assert metrics.json()["metrics"]["shots_per_match"]["value"] is None
        tactical = client.get(TEAM + "/tactical-profile")
        assert tactical.status_code == 409
        assert tactical.json()["error"]["code"] == "coverage_not_verified"


@pytest.mark.parametrize("path", [
    "/competitions/unknown/seasons",
    "/competitions/fixture:competition:1/seasons/unknown/teams",
    BASE + "/teams/unknown/metrics",
    BASE + "/teams/unknown/tactical-profile",
])
def test_unknown_resources(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize("identifier", ["bad%20id", "x" * 129, "bad.id"])
def test_invalid_identifier(client: TestClient, identifier: str) -> None:
    response = client.get(f"/competitions/{identifier}/seasons")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


@pytest.mark.parametrize("error,status", [(DataNetworkError, 503), (DataCacheError, 503),
                                         (DataFormatError, 502), (DataNotFoundError, 404)])
def test_provider_failures_are_sanitized(error: type, status: int) -> None:
    class BrokenProvider(FixtureFootballDataProvider):
        def get_competitions(self) -> list[Competition]:
            raise error("/private/secret-cache-file.json")
    with TestClient(create_app(BrokenProvider())) as client:
        response = client.get("/competitions", headers={"Origin": "http://localhost:5173"})
        assert response.status_code == status
        assert "secret-cache" not in response.text
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


@pytest.mark.parametrize("field", ["match_data_sha256", "complete_event_sha256", "expected_matches"])
def test_stale_coverage_conflict(field: str) -> None:
    updates = {"match_data_sha256": "stale", "complete_event_sha256": {"fixture:match:1": "stale"},
               "expected_matches": {"fixture:team:1": 1}}
    with TestClient(create_app(FixtureFootballDataProvider(), [coverage().model_copy(update={field: updates[field]})])) as client:
        response = client.get(TEAM + "/tactical-profile")
        assert response.status_code == 409


def test_default_source_offline_cache_miss_never_downloads(tmp_path: Path) -> None:
    def forbidden(request: httpx.Request) -> httpx.Response:
        pytest.fail("HTTP request must not initiate downloads")
    provider = StatsBombOpenDataProvider(CachedJSONSource(tmp_path, offline=True, transport=httpx.MockTransport(forbidden)))
    with TestClient(create_app(provider)) as client:
        assert client.get("/health").status_code == 200
        response = client.get("/competitions")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "data_not_prepared"


def test_tactical_fetches_each_match_events_once() -> None:
    calls = Counter()
    class CountingProvider(FixtureFootballDataProvider):
        def get_match_events(self, match_id: str) -> list[Event]:
            calls[match_id] += 1
            return super().get_match_events(match_id)
    with TestClient(create_app(CountingProvider(), [coverage()])) as client:
        assert client.get(TEAM + "/tactical-profile").status_code == 200
    assert calls == {"fixture:match:1": 1}


def test_openapi_models(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    path = "/competitions/{competition_id}/seasons/{season_id}/teams/{team_id}/metrics"
    response = schema["paths"][path]["get"]["responses"]
    assert response["200"]["content"]["application/json"]["schema"]["$ref"].endswith("TeamSeasonProfile")
    assert response["422"]["content"]["application/json"]["schema"]["$ref"].endswith("ErrorResponse")


def test_sufficient_synthetic_cohort_produces_numeric_api_scores() -> None:
    class LeagueFixture(FixtureFootballDataProvider):
        def __init__(self) -> None:
            super().__init__()
            teams = [Team(id=f"fixture:team:{i}", name=f"Sample {i}", provenance=self._match.provenance)
                     for i in range(1, 12)]
            self.matches = [self._match.model_copy(update={"id": f"fixture:match:{i}-{j}",
                                                           "home_team": home, "away_team": away})
                            for i, home in enumerate(teams) for j, away in enumerate(teams) if i < j]

        def get_matches(self, competition: str, season: Season) -> list[Match]:
            self.validate_season(competition, season)
            return self.matches

        def get_match_events(self, match_id: str) -> list[Event]:
            match = next(m for m in self.matches if m.id == match_id)
            events = []
            for i, team in enumerate([match.home_team, match.away_team]):
                for j, kind in enumerate(["Pass", "Duel"]):
                    index = i * 2 + j + 1
                    events.append(self._event.model_copy(update={
                        "id": f"{match_id}:event:{index}", "match_id": match_id, "index": index,
                        "team_id": team.id, "type": kind, "coordinate_system": "attacking_120x80",
                        "location": (80, 40), "pass_end_location": (90, 40), "pass_completed": True,
                        "is_tackle": True, "possession_id": str(i), "possession_team_id": team.id,
                        "from_counterattack": False,
                    }))
            return events

    provider = LeagueFixture()
    manifest = coverage().model_copy(update={
        "complete_event_sha256": {m.id: "not-applicable-synthetic" for m in provider.matches},
        "expected_matches": {f"fixture:team:{i}": 10 for i in range(1, 12)},
    })
    with TestClient(create_app(provider, [manifest])) as client:
        response = client.get(TEAM + "/tactical-profile")
    assert response.status_code == 200
    profile = response.json()
    assert all(score["value"] == 50 for score in profile["scores"].values())
    assert profile["primary_identity"] == "No Distinct Relative Style"
    assert profile["data_kind"] == "sample"


def test_coverage_file_loaded_and_bad_configuration_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "coverage.json"
    path.write_text("[" + coverage().model_dump_json() + "]")
    monkeypatch.setenv("FOOTBALL_COVERAGE_PATH", str(path))
    application = create_app()
    assert ("fixture:competition:1", "fixture:season:1") in application.state.football_service.coverage
    path.write_text("not json")
    with pytest.raises(ValueError):
        create_app()
    monkeypatch.setenv("FOOTBALL_COVERAGE_PATH", str(tmp_path / "missing.json"))
    with pytest.raises(ValueError, match="does not exist"):
        create_app()


def test_offline_cache_hit(tmp_path: Path) -> None:
    source = CachedJSONSource(tmp_path, transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[])))
    original = source.read("competitions.json")
    offline = CachedJSONSource(tmp_path, offline=True)
    assert offline.read("competitions.json") == original
    with pytest.raises(ValueError):
        CachedJSONSource(tmp_path, offline=True, refresh=True)
