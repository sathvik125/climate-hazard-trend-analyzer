"""Shared test fixtures.

All temperatures here are synthetic TEST FIXTURES served by a mocked HTTP
transport. No test contacts the real Open-Meteo API or a real MongoDB server.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Callable

import httpx
import mongomock
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

NORMAL_TEMP = 30.0
HOT_TEMP = 40.0


def date_range(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


# Hot spells in the fixture series. Everything else is NORMAL_TEMP, so the
# 1991-2020 95th percentile threshold is exactly NORMAL_TEMP.
HOT_DAYS = set(
    date_range(date(2000, 5, 10), date(2000, 5, 12))  # exactly 3 days -> one event
    + date_range(date(2001, 12, 30), date(2002, 1, 2))  # 4 days across a year boundary
    + date_range(date(2003, 6, 1), date(2003, 6, 2))  # only 2 days -> no event
    + date_range(date(2008, 4, 20), date(2008, 4, 26))  # 7 days
)


def make_payload(start: date, end: date, temperature_for: Callable[[date], float | None]) -> dict:
    days = date_range(start, end)
    return {
        "latitude": 17.4,
        "longitude": 78.5,
        "elevation": 515.0,
        "timezone": "Asia/Kolkata",
        "utc_offset_seconds": 19800,
        "daily_units": {"time": "iso8601", "temperature_2m_max": "°C"},
        "daily": {
            "time": [d.isoformat() for d in days],
            "temperature_2m_max": [temperature_for(d) for d in days],
        },
    }


def fixture_temperature(day: date) -> float:
    return HOT_TEMP if day in HOT_DAYS else NORMAL_TEMP


class FakeProvider:
    """Stands in for Open-Meteo and records every request it receives."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.temperature_for: Callable[[date], float | None] = fixture_temperature

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        start = date.fromisoformat(request.url.params["start_date"])
        end = date.fromisoformat(request.url.params["end_date"])
        return httpx.Response(200, json=make_payload(start, end, self.temperature_for))


def make_settings(**overrides) -> Settings:
    values = dict(
        app_env="test",
        mongodb_uri=None,
        open_meteo_backoff_seconds=0.0,
        open_meteo_max_backoff_seconds=0.0,
        open_meteo_max_retries=2,
        rate_limit_per_minute=1000,
    )
    values.update(overrides)
    return Settings(_env_file=None, **values)


INDEX_CALLS: list[tuple[str, object, dict]] = []


@pytest.fixture(autouse=True)
def fast_mongomock_indexes(monkeypatch):
    """Record index definitions, but do not let mongomock enforce the weather_daily one.

    mongomock checks a unique index by scanning the whole collection on every
    insert, which makes inserting 30 years of days take minutes. The definition
    is asserted in test_api.py; real MongoDB enforces it in production.
    """
    INDEX_CALLS.clear()
    original = mongomock.collection.Collection.create_index

    def create_index(self, keys, **kwargs):
        INDEX_CALLS.append((self.name, keys, dict(kwargs)))
        if self.name == "weather_daily":
            kwargs.pop("unique", None)
        return original(self, keys, **kwargs)

    monkeypatch.setattr(mongomock.collection.Collection, "create_index", create_index)


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def mongo() -> mongomock.MongoClient:
    return mongomock.MongoClient(tz_aware=True)


@pytest.fixture
def client(provider: FakeProvider, mongo: mongomock.MongoClient):
    app = create_app(
        make_settings(), mongo_client=mongo, http_transport=httpx.MockTransport(provider)
    )
    with TestClient(app) as test_client:
        yield test_client


HYDERABAD = {"latitude": 17.385, "longitude": 78.4867}
