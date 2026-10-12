"""MongoDB connection, collection names and index definitions."""

from __future__ import annotations

import functools
import logging
import threading
from typing import Any, Callable, TypeVar

from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from app.config import Settings
from app.errors import StorageError

logger = logging.getLogger(__name__)

WEATHER_DAILY = "weather_daily"
ANALYSIS_CACHE = "analysis_cache"
LOCATION_METADATA = "location_metadata"

F = TypeVar("F", bound=Callable[..., Any])


def storage_errors(func: F) -> F:
    """Convert driver errors into StorageError so the API reports a clear 503."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except PyMongoError as exc:
            # The driver message can contain host names; log it, do not return it.
            logger.error("mongodb operation %s failed: %s", func.__name__, exc)
            raise StorageError(
                "The database is unavailable, so the analysis cannot be stored or retrieved."
            ) from exc

    return wrapper  # type: ignore[return-value]


class MongoStore:
    """Thin wrapper that owns the client and creates indexes once, on first use."""

    def __init__(self, client: Any | None, db_name: str) -> None:
        self._client = client
        self._db_name = db_name
        self._indexes_ready = False
        self._lock = threading.Lock()
        self._config_error: str | None = None  # set when MONGODB_URI could not be parsed

    @classmethod
    def from_settings(cls, settings: Settings) -> "MongoStore":
        if not settings.mongodb_uri:
            logger.warning("MONGODB_URI is not set; database-backed endpoints will return 503")
            return cls(None, settings.mongodb_db)
        # MongoClient connects lazily, but it parses the URI (and resolves
        # mongodb+srv DNS records) right away. A bad URI must not stop the API
        # from starting: report it through /api/health and 503 responses instead.
        try:
            client = MongoClient(
                settings.mongodb_uri,
                serverSelectionTimeoutMS=settings.mongodb_timeout_ms,
                connectTimeoutMS=settings.mongodb_timeout_ms,
                tz_aware=True,
                appname="climate-hazard-trend-analyzer",
            )
        except PyMongoError as exc:
            # The exception text never includes the URI, so it is safe to log.
            logger.error(
                "MONGODB_URI is invalid (%s). If the password contains characters such as "
                "@ : / # ? %% they must be percent-encoded (urllib.parse.quote_plus).",
                exc,
            )
            store = cls(None, settings.mongodb_db)
            store._config_error = "The database connection string is invalid."
            return store
        return cls(client, settings.mongodb_db)

    @property
    def configured(self) -> bool:
        return self._client is not None or self._config_error is not None

    def _database(self) -> Any:
        if self._config_error is not None:
            raise StorageError(self._config_error)
        if self._client is None:
            raise StorageError("The database is not configured (MONGODB_URI is missing).")
        return self._client[self._db_name]

    @storage_errors
    def ping(self) -> None:
        self._database().command("ping")

    @storage_errors
    def collection(self, name: str) -> Collection:
        database = self._database()
        with self._lock:
            if not self._indexes_ready:
                self._create_indexes(database)
                self._indexes_ready = True
        return database[name]

    @staticmethod
    def _create_indexes(database: Any) -> None:
        # One record per model, normalised location and calendar date.
        database[WEATHER_DAILY].create_index(
            [
                ("source_model", ASCENDING),
                ("latitude", ASCENDING),
                ("longitude", ASCENDING),
                ("date", ASCENDING),
            ],
            unique=True,
            name="uniq_model_location_date",
        )
        database[ANALYSIS_CACHE].create_index("cache_key", unique=True, name="uniq_cache_key")
        # TTL index: MongoDB deletes each document once its own expires_at has passed.
        database[ANALYSIS_CACHE].create_index(
            "expires_at", expireAfterSeconds=0, name="ttl_expires_at"
        )
        database[LOCATION_METADATA].create_index(
            [("source_model", ASCENDING), ("latitude", ASCENDING), ("longitude", ASCENDING)],
            unique=True,
            name="uniq_model_location",
        )

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
