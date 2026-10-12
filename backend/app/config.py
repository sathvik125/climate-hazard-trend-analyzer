"""Runtime configuration, read from environment variables (or backend/.env locally)."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The provider URL is a constant, never built from request input.
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Bump whenever detection, aggregation or the response shape changes, so cached
# analyses produced by older logic are never served.
ALGORITHM_VERSION = "heatwave-v2"  # v2: added the Mann-Kendall test and Theil-Sen slope

# First year each reanalysis is available from the provider, and its grid spacing.
SOURCE_MODELS = {
    "era5": {"first_year": 1940, "label": "ECMWF ERA5", "resolution": "0.25° (~25 km)"},
    "era5_land": {"first_year": 1950, "label": "ECMWF ERA5-Land", "resolution": "0.1° (~11 km)"},
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "production", "test"] = "development"

    # MongoDB. The URI holds credentials and must only ever live in the backend environment.
    mongodb_uri: str | None = None
    mongodb_db: str = "climate_hazards"
    mongodb_timeout_ms: int = 5000

    # Comma separated list of exact origins, e.g. "https://my-app.vercel.app".
    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Open-Meteo. One model is used for baseline and analysis alike; never mixed.
    open_meteo_model: Literal["era5", "era5_land"] = "era5"
    open_meteo_timeout_seconds: float = 30.0
    open_meteo_max_retries: int = 3
    open_meteo_backoff_seconds: float = 0.5
    open_meteo_max_backoff_seconds: float = 8.0
    open_meteo_concurrency: int = 2
    open_meteo_chunk_years: int = 30
    max_request_seconds: float = 90.0  # overall budget for one analysis' upstream work

    # Analysis bounds.
    max_year_range: int = 90
    baseline_start_year: int = 1991
    baseline_end_year: int = 2020
    min_baseline_completeness: float = 0.90
    coordinate_precision: int = 2  # decimals; 0.01° is about 1.1 km, far below the grid spacing

    analysis_cache_ttl_days: int = 30
    rate_limit_per_minute: int = 30
    trust_proxy_headers: bool = False  # set true only behind a proxy that sets X-Forwarded-For

    @model_validator(mode="after")
    def _validate(self) -> "Settings":
        if self.app_env == "production" and "*" in self.cors_origins:
            raise ValueError("CORS_ALLOWED_ORIGINS must list explicit origins in production")
        if self.baseline_start_year > self.baseline_end_year:
            raise ValueError("baseline start year must not be after baseline end year")
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def min_year(self) -> int:
        return SOURCE_MODELS[self.open_meteo_model]["first_year"]

    @property
    def max_year(self) -> int:
        """Last complete calendar year; the current year is always partial."""
        return date.today().year - 1


@lru_cache
def get_settings() -> Settings:
    return Settings()
