"""Repositories: the only place MongoDB query shapes are written.

Every filter is built here from typed Python values (floats, strings, dates),
never from a request body, so a caller cannot inject query operators.
Dates are stored as ISO "YYYY-MM-DD" strings: they are local calendar days at
the location (timezone=auto), not instants, and ISO strings sort correctly.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Sequence

from pymongo import ASCENDING
from pymongo.errors import BulkWriteError

from app.analysis.quality import DailyRecord
from app.clients.open_meteo import GridMetadata
from app.db.mongo import ANALYSIS_CACHE, LOCATION_METADATA, WEATHER_DAILY, MongoStore, storage_errors

BULK_BATCH_SIZE = 5000
DUPLICATE_KEY_CODE = 11000


class WeatherRepository:
    def __init__(self, store: MongoStore) -> None:
        self._store = store

    @storage_errors
    def find_days(
        self, source_model: str, latitude: float, longitude: float, start: date, end: date
    ) -> list[DailyRecord]:
        cursor = (
            self._store.collection(WEATHER_DAILY)
            .find(
                {
                    "source_model": source_model,
                    "latitude": latitude,
                    "longitude": longitude,
                    "date": {"$gte": start.isoformat(), "$lte": end.isoformat()},
                },
                {"_id": 0, "date": 1, "temperature_max_c": 1, "quality_status": 1},
            )
            .sort("date", ASCENDING)
        )
        return [
            DailyRecord(
                date=date.fromisoformat(doc["date"]),
                temperature_max_c=doc["temperature_max_c"],
                quality_status=doc["quality_status"],
            )
            for doc in cursor
        ]

    @storage_errors
    def insert_days(
        self,
        source_model: str,
        latitude: float,
        longitude: float,
        records: Sequence[DailyRecord],
        fetched_at: datetime,
    ) -> None:
        """Store newly fetched days.

        Only days with no stored record are ever fetched, so this is a plain
        insert. If two requests fetch the same days at once, the unique index
        rejects the second copy; that duplicate-key error is expected and
        ignored (first writer wins, both hold identical provider data).
        """
        collection = self._store.collection(WEATHER_DAILY)
        for offset in range(0, len(records), BULK_BATCH_SIZE):
            documents = [
                {
                    "source_model": source_model,
                    "latitude": latitude,
                    "longitude": longitude,
                    "date": record.date.isoformat(),
                    "temperature_max_c": record.temperature_max_c,
                    "quality_status": record.quality_status,
                    "fetched_at": fetched_at,
                }
                for record in records[offset : offset + BULK_BATCH_SIZE]
            ]
            try:
                collection.insert_many(documents, ordered=False)
            except BulkWriteError as exc:
                errors = exc.details.get("writeErrors", [])
                if any(error.get("code") != DUPLICATE_KEY_CODE for error in errors):
                    raise

    @storage_errors
    def get_grid_metadata(
        self, source_model: str, latitude: float, longitude: float
    ) -> GridMetadata | None:
        doc = self._store.collection(LOCATION_METADATA).find_one(
            {"source_model": source_model, "latitude": latitude, "longitude": longitude},
            {"_id": 0},
        )
        if doc is None:
            return None
        return GridMetadata(
            grid_latitude=doc.get("grid_latitude"),
            grid_longitude=doc.get("grid_longitude"),
            elevation_m=doc.get("elevation_m"),
            timezone=doc.get("timezone"),
        )

    @storage_errors
    def save_grid_metadata(
        self, source_model: str, latitude: float, longitude: float, metadata: GridMetadata
    ) -> None:
        self._store.collection(LOCATION_METADATA).update_one(
            {"source_model": source_model, "latitude": latitude, "longitude": longitude},
            {
                "$set": {
                    "grid_latitude": metadata.grid_latitude,
                    "grid_longitude": metadata.grid_longitude,
                    "elevation_m": metadata.elevation_m,
                    "timezone": metadata.timezone,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )


class AnalysisCacheRepository:
    def __init__(self, store: MongoStore) -> None:
        self._store = store

    @storage_errors
    def get(self, cache_key: str, now: datetime) -> dict[str, Any] | None:
        """Return the cached document, or None when absent or already expired.

        The explicit expiry check matters because MongoDB's TTL monitor only
        runs about once a minute.
        """
        doc = self._store.collection(ANALYSIS_CACHE).find_one({"cache_key": cache_key}, {"_id": 0})
        if doc is None:
            return None
        expires_at = doc["expires_at"]
        if expires_at.tzinfo is None:  # drivers return naive UTC unless tz_aware is set
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return doc if expires_at > now else None

    @storage_errors
    def put(self, document: dict[str, Any]) -> None:
        self._store.collection(ANALYSIS_CACHE).replace_one(
            {"cache_key": document["cache_key"]}, document, upsert=True
        )
