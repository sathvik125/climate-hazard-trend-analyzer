"""Async client for the Open-Meteo Historical Weather (archive) API.

Responsibilities: build the fixed request, retry transient failures with
exponential backoff, honour HTTP 429, cap concurrency, and hand the body to the
pure validator. It never fabricates data when the provider fails.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Awaitable, Callable

import httpx

from app.analysis.quality import (
    TEMPERATURE_FIELD,
    DailyRecord,
    ParseReport,
    PayloadError,
    parse_daily_payload,
)
from app.config import OPEN_METEO_ARCHIVE_URL, Settings
from app.errors import (
    AppError,
    UpstreamInvalidDataError,
    UpstreamRateLimitedError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GridMetadata:
    """What the provider says about the grid cell that answered the request."""

    grid_latitude: float | None
    grid_longitude: float | None
    elevation_m: float | None
    timezone: str | None


@dataclass(frozen=True)
class DailyFetchResult:
    records: list[DailyRecord]
    report: ParseReport
    metadata: GridMetadata


def split_range_by_years(start: date, end: date, chunk_years: int) -> list[tuple[date, date]]:
    """Split [start, end] into consecutive pieces spanning at most ``chunk_years`` calendar years."""
    chunks: list[tuple[date, date]] = []
    chunk_start = start
    while chunk_start <= end:
        chunk_end = min(end, date(chunk_start.year + chunk_years - 1, 12, 31))
        chunks.append((chunk_start, chunk_end))
        chunk_start = date(chunk_end.year + 1, 1, 1)
    return chunks


class OpenMeteoClient:
    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._settings = settings
        self._sleep = sleep
        self._semaphore = asyncio.Semaphore(settings.open_meteo_concurrency)
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.open_meteo_timeout_seconds),
            transport=transport,
            headers={"Accept": "application/json"},
        )
        self.request_count = 0  # successful and failed attempts, for diagnostics and tests

    async def aclose(self) -> None:
        await self._http.aclose()

    async def fetch_daily_max(
        self, latitude: float, longitude: float, start: date, end: date
    ) -> DailyFetchResult:
        """Fetch and validate daily maximum temperature for one contiguous date range."""
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": TEMPERATURE_FIELD,
            "temperature_unit": "celsius",
            "timezone": "auto",
            "models": self._settings.open_meteo_model,
        }
        payload = await self._get_json(params)
        try:
            records, report = parse_daily_payload(payload, start, end)
        except PayloadError as exc:
            raise UpstreamInvalidDataError(
                f"The weather provider returned data that failed validation: {exc}"
            ) from exc
        return DailyFetchResult(records, report, _grid_metadata(payload))

    async def _get_json(self, params: dict[str, Any]) -> Any:
        settings = self._settings
        last_error: AppError = UpstreamUnavailableError("The weather provider is unavailable.")

        for attempt in range(settings.open_meteo_max_retries + 1):
            delay = min(
                settings.open_meteo_backoff_seconds * (2**attempt),
                settings.open_meteo_max_backoff_seconds,
            )
            self.request_count += 1
            try:
                async with self._semaphore:
                    response = await self._http.get(OPEN_METEO_ARCHIVE_URL, params=params)
            except httpx.TimeoutException:
                last_error = UpstreamTimeoutError("The weather provider did not respond in time.")
            except httpx.TransportError:
                last_error = UpstreamUnavailableError("Could not connect to the weather provider.")
            else:
                status = response.status_code
                if status == 200:
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise UpstreamInvalidDataError(
                            "The weather provider returned a response that is not valid JSON."
                        ) from exc
                if status == 429:
                    last_error = UpstreamRateLimitedError(
                        "The weather provider is rate limiting requests. Please try again later."
                    )
                    delay = _retry_after(response, delay, settings.open_meteo_max_backoff_seconds)
                elif status >= 500:
                    last_error = UpstreamUnavailableError(
                        f"The weather provider returned HTTP {status}."
                    )
                else:
                    # Other 4xx responses will not succeed on retry.
                    raise UpstreamInvalidDataError(
                        f"The weather provider rejected the request (HTTP {status}): "
                        f"{_provider_reason(response)}"
                    )

            if attempt < settings.open_meteo_max_retries:
                logger.info("open-meteo attempt %d failed (%s); retrying", attempt + 1, last_error.code)
                await self._sleep(delay)

        raise last_error


def _retry_after(response: httpx.Response, default: float, maximum: float) -> float:
    """Use the provider's Retry-After header when it is a sane number of seconds."""
    try:
        seconds = float(response.headers.get("Retry-After", ""))
    except ValueError:
        return default
    return min(max(seconds, 0.0), maximum)


def _provider_reason(response: httpx.Response) -> str:
    try:
        reason = response.json().get("reason")
    except (ValueError, AttributeError):
        reason = None
    return str(reason)[:200] if reason else "no reason given"


def _grid_metadata(payload: dict[str, Any]) -> GridMetadata:
    def number(key: str) -> float | None:
        value = payload.get(key)
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    timezone = payload.get("timezone")
    return GridMetadata(
        grid_latitude=number("latitude"),
        grid_longitude=number("longitude"),
        elevation_m=number("elevation"),
        timezone=timezone if isinstance(timezone, str) else None,
    )
