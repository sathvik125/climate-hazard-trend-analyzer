"""API tests: real routes and services, mongomock storage, mocked provider."""

from __future__ import annotations

from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.weather_service import merge_ranges, missing_ranges
from tests.conftest import HYDERABAD, INDEX_CALLS, NORMAL_TEMP, FakeProvider, make_settings

PARAMS = {**HYDERABAD, "start_year": 1995, "end_year": 2010, "hazard": "heatwave"}


def test_health_reports_database_ok(client):
    body = client.get("/api/health").json()
    assert body == {
        "status": "ok",
        "database": "ok",
        "source_model": "era5",
        "algorithm_version": "heatwave-v2",
    }


def test_locations_lists_the_five_presets(client):
    body = client.get("/api/locations").json()
    assert [loc["name"] for loc in body["locations"]] == [
        "Hyderabad", "Delhi", "Mumbai", "Bengaluru", "Chennai",
    ]
    assert body["min_year"] == 1940
    assert body["max_year"] == date.today().year - 1


def test_analysis_returns_the_full_contract_with_correct_numbers(client):
    response = client.get("/api/analysis", params=PARAMS)
    assert response.status_code == 200
    body = response.json()

    assert set(body) == {
        "location", "hazard", "selected_period", "baseline_period", "threshold_c",
        "annual_series", "events", "overall_summary", "trend", "generated_insights",
        "data_quality", "methodology", "source_metadata", "cache_status",
    }
    assert body["location"]["name"] == "Hyderabad"
    assert body["location"]["kind"] == "point"
    assert body["baseline_period"]["start_year"] == 1991
    assert body["baseline_period"]["end_year"] == 2020
    assert body["threshold_c"] == NORMAL_TEMP

    # Fixture hot spells: 3 days (2000), 4 days across 2001/2002, 2 days (2003, no event), 7 days (2008).
    assert [(e["start_date"], e["end_date"], e["duration_days"]) for e in body["events"]] == [
        ("2000-05-10", "2000-05-12", 3),
        ("2001-12-30", "2002-01-02", 4),
        ("2008-04-20", "2008-04-26", 7),
    ]
    summary = body["overall_summary"]
    assert summary["total_events"] == 3
    assert summary["total_heatwave_days"] == 14
    assert summary["longest_event_days"] == 7
    assert summary["average_intensity_c"] == 10.0

    annual = {a["year"]: a for a in body["annual_series"]}
    assert len(annual) == 16
    assert annual[2001]["event_count"] == 1 and annual[2001]["heatwave_days"] == 2
    assert annual[2002]["event_count"] == 0 and annual[2002]["heatwave_days"] == 2
    assert annual[2003]["heatwave_days"] == 0
    assert annual[2000]["expected_days"] == 366 and annual[2000]["completeness"] == 1.0

    assert body["data_quality"]["coverage_status"] == "complete"
    assert body["trend"]["heatwave_days_per_decade"]["status"] == "ok"
    mann_kendall = body["trend"]["heatwave_days_mann_kendall"]
    assert mann_kendall["status"] == "ok" and mann_kendall["n_years"] == 16
    assert 0 <= mann_kendall["p_value"] <= 1
    assert any(i["id"] == "mann_kendall" for i in body["generated_insights"])
    assert body["source_metadata"]["model"] == "era5"
    assert body["cache_status"]["status"] == "miss"


def test_repeated_request_is_served_from_the_database_cache(client, provider, mongo):
    first = client.get("/api/analysis", params=PARAMS).json()
    upstream_calls = len(provider.requests)
    assert upstream_calls >= 1
    assert first["cache_status"]["status"] == "miss"
    assert first["cache_status"]["daily_records_fetched"] > 0

    second = client.get("/api/analysis", params=PARAMS).json()
    assert second["cache_status"]["status"] == "hit"
    assert len(provider.requests) == upstream_calls  # no further provider calls
    assert second["events"] == first["events"]
    assert second["annual_series"] == first["annual_series"]

    database = mongo["climate_hazards"]
    assert database["analysis_cache"].count_documents({}) == 1
    # 1991-2020 baseline merged with 1995-2010 selection = 30 years, stored once per day.
    assert database["weather_daily"].count_documents({}) == 10958


def test_overlapping_analysis_reuses_stored_days_and_fetches_only_the_gap(client, provider):
    client.get("/api/analysis", params=PARAMS)
    provider.requests.clear()

    body = client.get("/api/analysis", params={**PARAMS, "start_year": 1989}).json()
    assert body["cache_status"]["status"] == "miss"
    assert body["cache_status"]["daily_records_reused"] == 10958
    assert body["cache_status"]["daily_records_fetched"] == 730  # 1989 and 1990 only
    assert len(provider.requests) == 1
    assert provider.requests[0].url.params["start_date"] == "1989-01-01"
    assert provider.requests[0].url.params["end_date"] == "1990-12-31"


def test_events_endpoint_reuses_the_cached_analysis(client, provider):
    client.get("/api/analysis", params=PARAMS)
    calls = len(provider.requests)
    body = client.get("/api/events", params=PARAMS).json()
    assert len(body["events"]) == 3
    assert body["cache_status"]["status"] == "hit"
    assert len(provider.requests) == calls


def test_csv_export(client):
    response = client.get("/api/export/csv", params={**PARAMS, "dataset": "events"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    data_lines = [line for line in response.text.splitlines() if not line.startswith("#")]
    assert data_lines[0].startswith("id,start_date,end_date,duration_days")
    assert len(data_lines) == 4  # header + 3 events


@pytest.mark.parametrize(
    "override",
    [
        {"latitude": 90.5},
        {"latitude": -91},
        {"longitude": 181},
        {"longitude": -180.01},
        {"latitude": "abc"},
        {"latitude": "nan"},
        {"start_year": 1900},
        {"end_year": 2999},
        {"start_year": 2011, "end_year": 2010},
        {"hazard": "flood"},
        {"url": "https://example.com"},  # unknown parameters are refused
    ],
)
def test_invalid_parameters_are_rejected_before_any_upstream_call(client, provider, override):
    response = client.get("/api/analysis", params={**PARAMS, **override})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert provider.requests == []


def test_missing_required_parameter_is_rejected(client):
    response = client.get("/api/analysis", params={"latitude": 17.385})
    assert response.status_code == 422


def test_upstream_failure_returns_a_clear_error_and_caches_nothing(mongo):
    def handler(request):
        raise httpx.ConnectTimeout("timed out", request=request)

    app = create_app(make_settings(), mongo_client=mongo, http_transport=httpx.MockTransport(handler))
    with TestClient(app) as test_client:
        response = test_client.get("/api/analysis", params=PARAMS)
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "upstream_timeout"
    assert "Traceback" not in response.text
    assert mongo["climate_hazards"]["analysis_cache"].count_documents({}) == 0
    assert mongo["climate_hazards"]["weather_daily"].count_documents({}) == 0


def test_upstream_429_returns_503(mongo):
    app = create_app(
        make_settings(),
        mongo_client=mongo,
        http_transport=httpx.MockTransport(lambda request: httpx.Response(429)),
    )
    with TestClient(app) as test_client:
        response = test_client.get("/api/analysis", params=PARAMS)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "upstream_rate_limited"


def test_database_failure_is_reported_not_hidden(provider):
    # A real driver pointed at a closed port: connection is refused quickly.
    settings = make_settings(mongodb_uri="mongodb://127.0.0.1:9/", mongodb_timeout_ms=300)
    app = create_app(settings, http_transport=httpx.MockTransport(provider))
    with TestClient(app) as test_client:
        response = test_client.get("/api/analysis", params=PARAMS)
        health = test_client.get("/api/health").json()
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "database_unavailable"
    assert "127.0.0.1" not in error["message"]  # no connection details leak
    assert health["status"] == "degraded" and health["database"] == "unavailable"
    assert provider.requests == []


def test_invalid_connection_string_does_not_crash_startup(provider):
    # An unescaped "@" in the password makes the driver reject the URI.
    settings = make_settings(mongodb_uri="mongodb://user:p@ss:word@127.0.0.1:9/")
    app = create_app(settings, http_transport=httpx.MockTransport(provider))
    with TestClient(app) as test_client:
        health = test_client.get("/api/health").json()
        response = test_client.get("/api/analysis", params=PARAMS)
    assert health["database"] == "unavailable"
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "database_unavailable"
    assert "p@ss" not in response.text


def test_unconfigured_database_is_reported(provider):
    app = create_app(make_settings(), http_transport=httpx.MockTransport(provider))
    with TestClient(app) as test_client:
        assert test_client.get("/api/health").json()["database"] == "not_configured"
        response = test_client.get("/api/analysis", params=PARAMS)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"


def test_missing_source_data_produces_partial_coverage_warning(mongo):
    provider = FakeProvider()
    # The provider has no values for June-August 1996: that year drops below 95%.
    provider.temperature_for = lambda d: (
        None if d.year == 1996 and d.month in (6, 7, 8) else NORMAL_TEMP
    )
    app = create_app(make_settings(), mongo_client=mongo, http_transport=httpx.MockTransport(provider))
    with TestClient(app) as test_client:
        body = test_client.get("/api/analysis", params=PARAMS).json()

    quality = body["data_quality"]
    assert quality["coverage_status"] == "partial"
    assert quality["incomplete_years"] == [1996]
    assert quality["missing_days"] == 92
    assert body["trend"]["years_excluded"] == [1996]
    assert body["trend"]["years_used"] == 15
    coverage = next(i for i in body["generated_insights"] if i["id"] == "coverage")
    assert coverage["severity"] == "warning"
    # No events and an all-zero early period: a percentage must not be invented.
    assert body["trend"]["period_comparison"]["percent_change"] is None


def test_no_percentage_in_insights_when_early_period_has_no_heatwave_days(client):
    # 1991-2008 splits into 1991-1999 (no fixture heatwave days) and 2000-2008.
    body = client.get("/api/analysis", params={**PARAMS, "start_year": 1991, "end_year": 2008}).json()
    comparison = body["trend"]["period_comparison"]
    assert (comparison["early_start"], comparison["early_end"]) == (1991, 1999)
    assert comparison["status"] == "zero_baseline"
    assert comparison["percent_change"] is None
    text = next(i["text"] for i in body["generated_insights"] if i["id"] == "period_comparison")
    assert "%" not in text.replace("A percentage change is not given", "")


def test_short_range_does_not_report_a_trend(client):
    body = client.get("/api/analysis", params={**PARAMS, "start_year": 2005, "end_year": 2009}).json()
    assert body["trend"]["heatwave_days_per_decade"]["status"] == "insufficient_data"
    assert body["trend"]["heatwave_days_per_decade"]["slope_per_decade"] is None
    assert body["trend"]["heatwave_days_mann_kendall"]["status"] == "insufficient_data"
    assert all(a["heatwave_days_rolling_avg_5y"] is None for a in body["annual_series"][:4])


def test_rate_limit_applies_to_analysis(provider, mongo):
    app = create_app(
        make_settings(rate_limit_per_minute=2),
        mongo_client=mongo,
        http_transport=httpx.MockTransport(provider),
    )
    with TestClient(app) as test_client:
        codes = [test_client.get("/api/analysis", params=PARAMS).status_code for _ in range(3)]
        limited = test_client.get("/api/analysis", params=PARAMS)
    assert codes == [200, 200, 429]
    assert limited.json()["error"]["code"] == "rate_limited"
    assert "Retry-After" in limited.headers


def test_cors_allows_only_configured_origins(client):
    allowed = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    denied = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in denied.headers


def test_required_indexes_are_requested(client):
    client.get("/api/health")
    client.get("/api/analysis", params=PARAMS)
    by_name = {kwargs["name"]: (collection, keys, kwargs) for collection, keys, kwargs in INDEX_CALLS}

    collection, keys, kwargs = by_name["uniq_model_location_date"]
    assert collection == "weather_daily" and kwargs["unique"] is True
    assert [field for field, _ in keys] == ["source_model", "latitude", "longitude", "date"]

    assert by_name["uniq_cache_key"][0] == "analysis_cache"
    assert by_name["uniq_cache_key"][2]["unique"] is True
    assert by_name["ttl_expires_at"][2]["expireAfterSeconds"] == 0


def test_merge_and_missing_range_helpers():
    merged = merge_ranges(
        [(date(1995, 1, 1), date(2010, 12, 31)), (date(1991, 1, 1), date(2020, 12, 31))]
    )
    assert merged == [(date(1991, 1, 1), date(2020, 12, 31))]

    stored = {date(2020, 1, 2), date(2020, 1, 3)}
    gaps = missing_ranges([(date(2020, 1, 1), date(2020, 1, 5))], stored)
    assert gaps == [(date(2020, 1, 1), date(2020, 1, 1)), (date(2020, 1, 4), date(2020, 1, 5))]
