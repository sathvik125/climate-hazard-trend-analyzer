"""Daily temperature retrieval: reuse stored days, fetch only what is missing."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Sequence

from app.analysis.quality import DailyRecord
from app.clients.open_meteo import GridMetadata, OpenMeteoClient, split_range_by_years
from app.config import Settings
from app.db.repositories import WeatherRepository

DateRange = tuple[date, date]


@dataclass(frozen=True)
class WeatherSeries:
    records: list[DailyRecord]  # sorted by date, one per requested calendar day
    metadata: GridMetadata
    records_reused: int
    records_fetched: int
    upstream_requests: int


def merge_ranges(ranges: Iterable[DateRange]) -> list[DateRange]:
    """Merge overlapping or adjacent date ranges so no day is requested twice."""
    merged: list[DateRange] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1] + timedelta(days=1):
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def missing_ranges(wanted: Sequence[DateRange], stored_dates: set[date]) -> list[DateRange]:
    """Return the contiguous sub-ranges of ``wanted`` that have no stored record."""
    gaps: list[DateRange] = []
    for start, end in wanted:
        gap_start: date | None = None
        day = start
        while day <= end:
            if day not in stored_dates:
                gap_start = gap_start or day
            elif gap_start is not None:
                gaps.append((gap_start, day - timedelta(days=1)))
                gap_start = None
            day += timedelta(days=1)
        if gap_start is not None:
            gaps.append((gap_start, end))
    return gaps


class WeatherService:
    def __init__(
        self, settings: Settings, client: OpenMeteoClient, repository: WeatherRepository
    ) -> None:
        self._settings = settings
        self._client = client
        self._repository = repository

    async def get_series(
        self, latitude: float, longitude: float, ranges: Sequence[DateRange]
    ) -> WeatherSeries:
        """Return one record per day across ``ranges`` for a normalised location."""
        model = self._settings.open_meteo_model
        wanted = merge_ranges(ranges)

        stored: list[DailyRecord] = []
        for start, end in wanted:
            stored += await asyncio.to_thread(
                self._repository.find_days, model, latitude, longitude, start, end
            )
        metadata = await asyncio.to_thread(
            self._repository.get_grid_metadata, model, latitude, longitude
        )

        gaps = missing_ranges(wanted, {r.date for r in stored})
        chunks = [
            chunk
            for gap_start, gap_end in gaps
            for chunk in split_range_by_years(gap_start, gap_end, self._settings.open_meteo_chunk_years)
        ]

        fetched: list[DailyRecord] = []
        if chunks:
            # The client's semaphore bounds how many of these run at once.
            results = await asyncio.gather(
                *(self._client.fetch_daily_max(latitude, longitude, s, e) for s, e in chunks)
            )
            for result in results:
                fetched += result.records
            metadata = results[0].metadata
            now = datetime.now(timezone.utc)
            await asyncio.to_thread(
                self._repository.insert_days, model, latitude, longitude, fetched, now
            )
            await asyncio.to_thread(
                self._repository.save_grid_metadata, model, latitude, longitude, metadata
            )

        records = sorted(stored + fetched, key=lambda r: r.date)
        return WeatherSeries(
            records=records,
            metadata=metadata or GridMetadata(None, None, None, None),
            records_reused=len(stored),
            records_fetched=len(fetched),
            upstream_requests=len(chunks),
        )
