"""All upstream-shaped records below are synthetic. No test uses the internet."""

import json
from pathlib import Path
from typing import Optional

import httpx
import pytest

from app.data.fixture import FixtureFootballDataProvider
from app.data.json_source import CachedJSONSource
from app.data.provider import (
    DataCacheError, DataFormatError, DataNetworkError, DataNotFoundError, FootballDataProvider,
)
from app.data.statsbomb import StatsBombOpenDataProvider


@pytest.fixture
def payloads() -> dict:
    competition = {"competition_id": 1, "season_id": 2, "competition_name": "Synthetic League",
                   "country_name": "Sample", "competition_gender": "male", "season_name": "Demo"}
    match = {"match_id": 3, "match_date": "2020-01-02", "competition": {"competition_id": 1},
             "season": {"season_id": 2}, "home_team": {"home_team_id": 4, "home_team_name": "North"},
             "away_team": {"away_team_id": 5, "away_team_name": "South"}, "home_score": 0,
             "match_status": "available", "metadata": {"data_version": "test"}}
    event = {"id": "synthetic-event", "index": 1, "type": {"name": "Pass"}, "period": 1,
             "minute": 0, "second": 2, "team": {"id": 4}, "location": [10, 20],
             "pass": {"length": 12.5}}
    return {"competitions.json": [competition], "matches/1/2.json": [match], "events/3.json": [event]}


def make_provider(payloads: dict, cache_dir: Optional[Path] = None,
                  calls: Optional[list] = None) -> StatsBombOpenDataProvider:
    def respond(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(str(request.url))
        path = request.url.path.split("/data/", 1)[1]
        return httpx.Response(200, json=payloads[path]) if path in payloads else httpx.Response(404)
    return StatsBombOpenDataProvider(CachedJSONSource(cache_dir, transport=httpx.MockTransport(respond)))


def test_base_requires_implementation() -> None:
    with pytest.raises(TypeError):
        FootballDataProvider()


@pytest.mark.parametrize("kind", ["fixture", "statsbomb"])
def test_provider_contract(kind: str, payloads: dict) -> None:
    provider = FixtureFootballDataProvider() if kind == "fixture" else make_provider(payloads)
    assert isinstance(provider, FootballDataProvider)
    competition = provider.get_competitions()[0]
    season = provider.get_seasons(competition.id)[0]
    teams = provider.get_teams(competition.id, season)
    matches = provider.get_matches(competition.id, season)
    assert len(teams) == 2
    for team in teams:
        assert [m.id for m in provider.get_team_matches(team.id, season)] == [m.id for m in matches]
    assert provider.get_match_events(matches[0].id)[0].match_id == matches[0].id
    with pytest.raises(DataNotFoundError):
        provider.get_team_matches("unknown", season)
    with pytest.raises(DataNotFoundError):
        provider.get_seasons("unknown")
    with pytest.raises(DataNotFoundError):
        provider.get_matches(competition.id, season.model_copy(update={"competition_id": "other"}))
    with pytest.raises(DataNotFoundError):
        provider.get_matches(competition.id, season.model_copy(update={"id": "unknown"}))
    with pytest.raises(DataNotFoundError):
        provider.get_match_events("unknown")


def test_fixture_is_sample_and_isolated() -> None:
    provider = FixtureFootballDataProvider()
    competition = provider.get_competitions()[0]
    season = provider.get_seasons(competition.id)[0]
    match = provider.get_matches(competition.id, season)[0]
    event = provider.get_match_events(match.id)[0]
    for record in [competition, season, match, match.home_team, event]:
        assert record.provenance.data_kind == "sample"
    event.source_fields["changed"] = True
    assert provider.get_match_events(match.id)[0].source_fields == {}


def test_normalization(payloads: dict) -> None:
    provider = make_provider(payloads)
    season = provider.get_seasons("statsbomb:competition:1")[0]
    match = provider.get_matches(season.competition_id, season)[0]
    assert match.home_score == 0
    assert match.away_score is None  # Missing is not zero.
    assert match.date.isoformat() == "2020-01-02"
    assert match.source_metadata == {"data_version": "test"}
    event = provider.get_match_events(match.id)[0]
    assert event.location == (10, 20)
    assert event.player_id is None
    assert event.source_fields["pass"]["length"] == 12.5
    assert event.team_id == match.home_team.id
    assert event.provenance.source == "statsbomb"


def test_discovery_deduplicates_competitions(payloads: dict) -> None:
    payloads["competitions.json"].append({**payloads["competitions.json"][0], "season_id": 8})
    provider = make_provider(payloads)
    assert len(provider.get_competitions()) == 1
    assert len(provider.get_seasons("statsbomb:competition:1")) == 2


@pytest.mark.parametrize("mutation", ["missing", "negative", "wrong_season", "duplicate"])
def test_invalid_matches_raise_format_error(payloads: dict, mutation: str) -> None:
    match = payloads["matches/1/2.json"][0]
    if mutation == "missing":
        del match["home_team"]
    elif mutation == "negative":
        match["home_score"] = -1
    elif mutation == "wrong_season":
        match["season"]["season_id"] = 88
    else:
        payloads["matches/1/2.json"].append(match.copy())
    provider = make_provider(payloads)
    season = provider.get_seasons("statsbomb:competition:1")[0]
    with pytest.raises(DataFormatError):
        provider.get_matches(season.competition_id, season)


def test_event_order_and_duplicates(payloads: dict) -> None:
    event = payloads["events/3.json"][0]
    payloads["events/3.json"] = [{**event, "id": "second", "index": 2}, event]
    provider = make_provider(payloads)
    assert [e.index for e in provider.get_match_events("statsbomb:match:3")] == [1, 2]
    payloads["events/3.json"].append(event)
    with pytest.raises(DataFormatError):
        provider.get_match_events("statsbomb:match:3")


@pytest.mark.parametrize("status,error", [(404, DataNotFoundError), (429, DataNetworkError), (500, DataNetworkError)])
def test_http_errors(status: int, error: type) -> None:
    source = CachedJSONSource(None, transport=httpx.MockTransport(lambda request: httpx.Response(status)))
    with pytest.raises(error):
        source.read("competitions.json")


def test_timeout() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("test timeout", request=request)
    with pytest.raises(DataNetworkError):
        CachedJSONSource(None, transport=httpx.MockTransport(timeout)).read("competitions.json")


@pytest.mark.parametrize("body", ["not json", '{}', '[1]', '[null]'])
def test_invalid_json(body: str, tmp_path: Path) -> None:
    source = CachedJSONSource(tmp_path, transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body)))
    with pytest.raises(DataFormatError):
        source.read("competitions.json")
    assert not list(tmp_path.iterdir())


def test_cache_reuse_refresh_and_corruption(payloads: dict, tmp_path: Path) -> None:
    calls = []
    provider = make_provider(payloads, tmp_path, calls)
    first = provider.get_competitions()
    assert provider.get_competitions() == first
    assert len(calls) == 1
    provider.source.refresh = True
    provider.get_competitions()
    assert len(calls) == 2
    provider.source.refresh = False
    cache = next(tmp_path.glob("*.json"))
    envelope = json.loads(cache.read_text())
    envelope["body"] = '[]'
    cache.write_text(json.dumps(envelope))
    with pytest.raises(DataFormatError):
        provider.get_competitions()
    assert len(calls) == 2  # Corruption is explicit, not a silent network fallback.


def test_cache_write_error(payloads: dict, tmp_path: Path) -> None:
    blocked = tmp_path / "file"
    blocked.write_text("not a directory")
    with pytest.raises(DataCacheError):
        make_provider(payloads, blocked).get_competitions()


def test_invalid_id_never_requests_network(payloads: dict) -> None:
    calls = []
    provider = make_provider(payloads, calls=calls)
    with pytest.raises(DataNotFoundError):
        provider.get_match_events("../../etc/passwd")
    assert calls == []


def test_missing_resource_is_not_an_empty_result(payloads: dict) -> None:
    provider = make_provider(payloads)
    with pytest.raises(DataNotFoundError):
        provider.get_match_events("statsbomb:match:999")
    payloads["events/999.json"] = []
    assert provider.get_match_events("statsbomb:match:999") == []


def test_corrupt_cache_body_type(payloads: dict, tmp_path: Path) -> None:
    provider = make_provider(payloads, tmp_path)
    provider.get_competitions()
    cache = next(tmp_path.glob("*.json"))
    envelope = json.loads(cache.read_text())
    envelope["body"] = []
    cache.write_text(json.dumps(envelope))
    with pytest.raises(DataFormatError):
        provider.get_competitions()


def test_refresh_failure_does_not_return_stale_data(payloads: dict, tmp_path: Path) -> None:
    provider = make_provider(payloads, tmp_path)
    provider.get_competitions()
    provider.source.refresh = True
    del payloads["competitions.json"]
    with pytest.raises(DataNotFoundError):
        provider.get_competitions()


def test_missing_optional_event_fields(payloads: dict) -> None:
    event = payloads["events/3.json"][0]
    del event["location"]
    del event["team"]
    normalized = make_provider(payloads).get_match_events("statsbomb:match:3")[0]
    assert normalized.location is None
    assert normalized.team_id is None
