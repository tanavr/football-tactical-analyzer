import os
from pathlib import Path
from typing import Optional, Sequence

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import TypeAdapter

from app.api.errors import register_errors
from app.api.football import router as football_router
from app.api.health import router as health_router
from app.data.json_source import CachedJSONSource
from app.data.provider import FootballDataProvider
from app.data.statsbomb import StatsBombOpenDataProvider
from app.models.api import SeasonCoverage
from app.services.football import FootballService


def create_app(provider: Optional[FootballDataProvider] = None,
               coverage: Optional[Sequence[SeasonCoverage]] = None) -> FastAPI:
    application = FastAPI(title="Football Tactical Analyzer", version="0.2.0",
                          description="Cached football data, raw metrics, and evidence-qualified tactical profiles.")
    if provider is None:
        provider = StatsBombOpenDataProvider(CachedJSONSource(offline=True))
        if coverage is None:
            default = Path(__file__).resolve().parents[2] / "data" / "coverage.json"
            path = Path(os.environ.get("FOOTBALL_COVERAGE_PATH", str(default)))
            if path.exists():
                coverage = TypeAdapter(list[SeasonCoverage]).validate_json(path.read_text())
            elif "FOOTBALL_COVERAGE_PATH" in os.environ:
                raise ValueError("Configured FOOTBALL_COVERAGE_PATH does not exist")
    application.state.football_service = FootballService(provider, coverage or ())
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False, allow_methods=["GET"], allow_headers=["Content-Type"],
    )
    register_errors(application)
    application.include_router(health_router)
    application.include_router(football_router)
    return application


def create_demo_app() -> FastAPI:
    """Offline sample mode; no real data or verified real-season claims."""
    from app.data.fixture import FixtureFootballDataProvider
    return create_app(FixtureFootballDataProvider())


app = create_app()
