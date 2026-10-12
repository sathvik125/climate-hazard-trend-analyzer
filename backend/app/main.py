"""FastAPI application factory.

Run locally with:  uvicorn app.main:app --reload --port 8000   (from backend/)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.clients.open_meteo import OpenMeteoClient
from app.config import Settings, get_settings
from app.db.mongo import MongoStore
from app.db.repositories import AnalysisCacheRepository, WeatherRepository
from app.errors import register_error_handlers
from app.rate_limit import RateLimiter
from app.services.analysis_service import AnalysisService
from app.services.weather_service import WeatherService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(
    settings: Settings | None = None,
    mongo_client: Any | None = None,
    http_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    """Build the app. ``mongo_client`` and ``http_transport`` exist so tests can inject fakes."""
    settings = settings or get_settings()
    store = (
        MongoStore(mongo_client, settings.mongodb_db)
        if mongo_client is not None
        else MongoStore.from_settings(settings)
    )
    open_meteo = OpenMeteoClient(settings, transport=http_transport)
    weather = WeatherService(settings, open_meteo, WeatherRepository(store))
    analysis = AnalysisService(settings, weather, AnalysisCacheRepository(store))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await open_meteo.aclose()
        store.close()

    production = settings.app_env == "production"
    app = FastAPI(
        title="Climate Hazard Trend Analyzer API",
        version="1.0.0",
        description="Heatwave frequency, duration and intensity trends from ERA5 reanalysis.",
        lifespan=lifespan,
        docs_url=None if production else "/docs",
        redoc_url=None,
        openapi_url=None if production else "/openapi.json",
    )
    app.state.settings = settings
    app.state.mongo_store = store
    app.state.open_meteo = open_meteo
    app.state.analysis_service = analysis
    app.state.rate_limiter = RateLimiter(settings.rate_limit_per_minute, settings.trust_proxy_headers)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET"],
        allow_headers=["Accept", "Content-Type"],
        expose_headers=["Content-Disposition", "Retry-After"],
    )
    register_error_handlers(app)
    app.include_router(router)
    return app


app = create_app()
