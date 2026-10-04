from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request

from app.models.api import CompetitionList, ErrorResponse, SeasonList, TeamList
from app.models.metrics import TeamSeasonProfile
from app.models.tactical import TacticalProfile
from app.services.football import FootballService

router = APIRouter(tags=["football"], responses={
    code: {"model": ErrorResponse, "description": description}
    for code, description in {
        404: "Unknown or unavailable resource", 409: "Coverage requires review",
        422: "Invalid request parameters", 502: "Invalid source data", 503: "Data source unavailable",
    }.items()
})
Identifier = Annotated[str, Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9:_-]*$")]


def get_service(request: Request) -> FootballService:
    return request.app.state.football_service


@router.get("/competitions", response_model=CompetitionList)
def competitions(service: FootballService = Depends(get_service)) -> CompetitionList:
    return service.competitions()


@router.get("/competitions/{competition_id}/seasons", response_model=SeasonList)
def seasons(competition_id: Identifier, service: FootballService = Depends(get_service)) -> SeasonList:
    return service.seasons(competition_id)


@router.get("/competitions/{competition_id}/seasons/{season_id}/teams", response_model=TeamList)
def teams(competition_id: Identifier, season_id: Identifier,
          service: FootballService = Depends(get_service)) -> TeamList:
    return service.teams(competition_id, season_id)


@router.get("/competitions/{competition_id}/seasons/{season_id}/teams/{team_id}/metrics",
            response_model=TeamSeasonProfile)
def metrics(competition_id: Identifier, season_id: Identifier, team_id: Identifier,
            service: FootballService = Depends(get_service)) -> TeamSeasonProfile:
    return service.metrics(competition_id, season_id, team_id)


@router.get("/competitions/{competition_id}/seasons/{season_id}/teams/{team_id}/tactical-profile",
            response_model=TacticalProfile)
def tactical_profile(competition_id: Identifier, season_id: Identifier, team_id: Identifier,
                     service: FootballService = Depends(get_service)) -> TacticalProfile:
    return service.tactical_profile(competition_id, season_id, team_id)
