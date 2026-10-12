"""Open-Meteo client behaviour against a mocked HTTP transport."""

from __future__ import annotations

import asyncio
from datetime import date

import httpx
import pytest

from app.clients.open_meteo import OpenMeteoClient, split_range_by_years
from app.config import OPEN_METEO_ARCHIVE_URL
from app.errors import (
    UpstreamInvalidDataError,
    UpstreamRateLimitedError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)
from tests.conftest import make_payload, make_settings

START, END = date(2020, 1, 1), date(2020, 1, 10)


def run_fetch(handler, **settings_overrides):
    """Run one fetch and return (result or exception, client, recorded sleep delays)."""
    delays: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)

    async def scenario():
        client = OpenMeteoClient(
            make_settings(**settings_overrides),
            transport=httpx.MockTransport(handler),
            sleep=fake_sleep,
        )
        try:
            return await client.fetch_daily_max(17.39, 78.49, START, END), client
        except Exception as exc:  # returned so each test can assert on it
            return exc, client
        finally:
            await client.aclose()

    outcome, client = asyncio.run(scenario())
    return outcome, client, delays


def ok_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=make_payload(START, END, lambda d: 30.0))


def test_request_uses_the_fixed_url_and_expected_parameters():
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return ok_response(request)

    result, _, _ = run_fetch(handler)
    assert len(result.records) == 10
    assert result.metadata.timezone == "Asia/Kolkata"
    url = seen[0].url
    assert str(url).startswith(OPEN_METEO_ARCHIVE_URL)
    assert url.params["daily"] == "temperature_2m_max"
    assert url.params["timezone"] == "auto"
    assert url.params["temperature_unit"] == "celsius"
    assert url.params["models"] == "era5"
    assert (url.params["start_date"], url.params["end_date"]) == ("2020-01-01", "2020-01-10")


def test_timeout_is_retried_then_reported():
    def handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    outcome, client, delays = run_fetch(handler, open_meteo_max_retries=2)
    assert isinstance(outcome, UpstreamTimeoutError)
    assert client.request_count == 3  # first attempt + 2 bounded retries
    assert len(delays) == 2


def test_backoff_grows_exponentially_and_is_capped():
    def handler(request):
        return httpx.Response(503)

    outcome, _, delays = run_fetch(
        handler,
        open_meteo_max_retries=4,
        open_meteo_backoff_seconds=0.5,
        open_meteo_max_backoff_seconds=3.0,
    )
    assert isinstance(outcome, UpstreamUnavailableError)
    assert delays == [0.5, 1.0, 2.0, 3.0]


def test_http_429_is_retried_and_then_reported_as_rate_limited():
    def handler(request):
        return httpx.Response(429, headers={"Retry-After": "2"}, json={"error": True})

    outcome, client, delays = run_fetch(
        handler, open_meteo_max_retries=2, open_meteo_max_backoff_seconds=5.0
    )
    assert isinstance(outcome, UpstreamRateLimitedError)
    assert client.request_count == 3
    assert delays == [2.0, 2.0]  # honours Retry-After


def test_recovers_when_a_retry_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(429) if calls["n"] == 1 else ok_response(request)

    result, client, _ = run_fetch(handler)
    assert len(result.records) == 10
    assert client.request_count == 2


def test_http_400_is_not_retried():
    def handler(request):
        return httpx.Response(400, json={"error": True, "reason": "Invalid date"})

    outcome, client, _ = run_fetch(handler)
    assert isinstance(outcome, UpstreamInvalidDataError)
    assert "Invalid date" in outcome.message
    assert client.request_count == 1


def test_empty_provider_response_is_an_error_not_an_empty_result():
    def handler(request):
        body = make_payload(START, END, lambda d: 30.0)
        body["daily"] = {"time": [], "temperature_2m_max": []}
        return httpx.Response(200, json=body)

    outcome, _, _ = run_fetch(handler)
    assert isinstance(outcome, UpstreamInvalidDataError)
    assert "no daily records" in outcome.message


def test_non_json_body_is_an_error():
    outcome, _, _ = run_fetch(lambda request: httpx.Response(200, text="<html>oops</html>"))
    assert isinstance(outcome, UpstreamInvalidDataError)


def test_split_range_by_years():
    chunks = split_range_by_years(date(1990, 1, 1), date(2020, 12, 31), 15)
    assert chunks == [
        (date(1990, 1, 1), date(2004, 12, 31)),
        (date(2005, 1, 1), date(2019, 12, 31)),
        (date(2020, 1, 1), date(2020, 12, 31)),
    ]


@pytest.mark.parametrize("chunk_years", [1, 30])
def test_split_range_covers_every_day_once(chunk_years):
    chunks = split_range_by_years(date(2019, 3, 5), date(2021, 2, 1), chunk_years)
    assert chunks[0][0] == date(2019, 3, 5) and chunks[-1][1] == date(2021, 2, 1)
    for (_, prev_end), (next_start, _) in zip(chunks, chunks[1:]):
        assert (next_start - prev_end).days == 1
