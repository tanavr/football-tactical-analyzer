"""Stable API errors without exposing local paths or upstream response bodies."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.analytics.tactical import TacticalInputError
from app.analytics.team_season import MetricsInputError
from app.data.provider import DataFormatError, DataNotFoundError, DataNotPreparedError, DataProviderError
from app.models.api import ErrorInfo, ErrorResponse
from app.services.football import CoverageConflictError


def register_errors(app: FastAPI) -> None:
    async def provider_error(request: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, DataNotFoundError):
            status, code, message = 404, "not_found", "Requested competition, season, team, or event resource is unavailable."
        elif isinstance(exc, CoverageConflictError):
            status, code, message = 409, "coverage_not_verified", str(exc)
        elif isinstance(exc, (DataFormatError, MetricsInputError, TacticalInputError)):
            status, code, message = 502, "invalid_source_data", "Source records are invalid or incompatible; review the prepared dataset."
        elif isinstance(exc, DataNotPreparedError):
            status, code, message = 503, "data_not_prepared", "Required data is not cached. Run the data preparation command before requesting it."
        else:
            status, code, message = 503, "data_unavailable", "Data source or local cache is unavailable. Try again after restoring access."
        body = ErrorResponse(error=ErrorInfo(code=code, message=message))
        return JSONResponse(status_code=status, content=body.model_dump())

    for error in (DataProviderError, CoverageConflictError, MetricsInputError, TacticalInputError):
        app.add_exception_handler(error, provider_error)

    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = sorted({".".join(str(part) for part in error["loc"]) for error in exc.errors()})
        body = ErrorResponse(error=ErrorInfo(code="invalid_request", message="Invalid request fields: " + ", ".join(fields)))
        return JSONResponse(status_code=422, content=body.model_dump())
    app.add_exception_handler(RequestValidationError, validation_error)
