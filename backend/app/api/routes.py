"""HTTP routes. They validate input and delegate; no analysis logic lives here."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from app.config import ALGORITHM_VERSION
from app.errors import AppError
from app.locations import PRESET_LOCATIONS
from app.rate_limit import enforce_rate_limit
from app.schemas import (
    AnalysisQuery,
    AnalysisResponse,
    EventsResponse,
    ExportQuery,
    HealthResponse,
    LocationsResponse,
)
from app.services.analysis_service import AnalysisService
from app.services.export_service import analysis_to_csv

router = APIRouter(prefix="/api")

AnalysisParams = Annotated[AnalysisQuery, Query()]


def get_analysis_service(request: Request) -> AnalysisService:
    return request.app.state.analysis_service


Service = Annotated[AnalysisService, Depends(get_analysis_service)]


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> dict:
    store = request.app.state.mongo_store
    if not store.configured:
        database = "not_configured"
    else:
        try:
            await asyncio.to_thread(store.ping)
            database = "ok"
        except AppError:
            database = "unavailable"
    return {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "source_model": request.app.state.settings.open_meteo_model,
        "algorithm_version": ALGORITHM_VERSION,
    }


@router.get("/locations", response_model=LocationsResponse)
async def locations(request: Request) -> dict:
    settings = request.app.state.settings
    return {
        "locations": PRESET_LOCATIONS,
        "note": "Each location is a single point matched to one reanalysis grid cell, "
        "not an administrative area.",
        "min_year": settings.min_year,
        "max_year": settings.max_year,
        "max_year_range": settings.max_year_range,
        "baseline_start_year": settings.baseline_start_year,
        "baseline_end_year": settings.baseline_end_year,
        "hazards": ["heatwave"],
    }


@router.get(
    "/analysis", response_model=AnalysisResponse, dependencies=[Depends(enforce_rate_limit)]
)
async def analysis(params: AnalysisParams, service: Service) -> dict:
    return await service.analyze(params)


@router.get("/events", response_model=EventsResponse, dependencies=[Depends(enforce_rate_limit)])
async def events(params: AnalysisParams, service: Service) -> dict:
    """Events only. Uses the same cached analysis, so it costs nothing extra after /analysis."""
    result = await service.analyze(params)
    return {
        key: result[key]
        for key in ("location", "selected_period", "threshold_c", "events", "cache_status")
    }


@router.get("/export/csv", dependencies=[Depends(enforce_rate_limit)])
async def export_csv(params: Annotated[ExportQuery, Query()], service: Service) -> Response:
    dataset = params.dataset
    result = await service.analyze(params)
    filename = (
        f"heatwave_{dataset}_{result['location']['latitude']}_{result['location']['longitude']}"
        f"_{params.start_year}-{params.end_year}.csv"
    )
    return Response(
        content=analysis_to_csv(result, dataset),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
