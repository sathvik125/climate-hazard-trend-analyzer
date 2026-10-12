"""Orchestrates one analysis: cache lookup, data retrieval, computation, storage."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Sequence

from app.analysis import insights as insight_text
from app.analysis.heatwave import (
    DEFAULT_MIN_COMPLETENESS,
    DEFAULT_MIN_DURATION_DAYS,
    DEFAULT_MIN_TREND_YEARS,
    DEFAULT_PERCENTILE,
    DEFAULT_ROLLING_WINDOW,
    HeatwaveEvent,
    MannKendallResult,
    PeriodComparison,
    TrendResult,
    aggregate_annual_metrics,
    calculate_threshold,
    calculate_trend,
    compare_matched_periods,
    days_in_year,
    detect_heatwaves,
    mann_kendall_test,
    rolling_average,
)
from app.analysis.quality import (
    PHYSICAL_MAX_C,
    PHYSICAL_MIN_C,
    QUALITY_IMPLAUSIBLE,
    QUALITY_MISSING,
    QUALITY_VALID,
    DailyRecord,
)
from app.clients.open_meteo import GridMetadata
from app.config import ALGORITHM_VERSION, OPEN_METEO_ARCHIVE_URL, SOURCE_MODELS, Settings
from app.db.repositories import AnalysisCacheRepository
from app.errors import InsufficientDataError, UpstreamTimeoutError
from app.locations import find_preset
from app.schemas import AnalysisQuery
from app.services.weather_service import WeatherService

MAX_EXCLUDED_VALUES_LISTED = 50


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


def build_cache_key(
    settings: Settings, latitude: float, longitude: float, query: AnalysisQuery
) -> str:
    """Deterministic key covering everything that can change the result."""
    parts = {
        "algorithm_version": ALGORITHM_VERSION,
        "model": settings.open_meteo_model,
        "latitude": latitude,
        "longitude": longitude,
        "hazard": query.hazard,
        "start_year": query.start_year,
        "end_year": query.end_year,
        "baseline_start": settings.baseline_start_year,
        "baseline_end": settings.baseline_end_year,
        "percentile": DEFAULT_PERCENTILE,
        "min_duration_days": DEFAULT_MIN_DURATION_DAYS,
    }
    digest = hashlib.sha256(json.dumps(parts, sort_keys=True).encode("utf-8")).hexdigest()
    return f"{query.hazard}:{digest[:40]}"


class AnalysisService:
    def __init__(
        self, settings: Settings, weather: WeatherService, cache: AnalysisCacheRepository
    ) -> None:
        self._settings = settings
        self._weather = weather
        self._cache = cache
        # One lock per cache key so identical concurrent requests share one computation.
        self._locks: dict[str, asyncio.Lock] = {}

    async def analyze(self, query: AnalysisQuery) -> dict[str, Any]:
        settings = self._settings
        latitude = round(query.latitude, settings.coordinate_precision)
        longitude = round(query.longitude, settings.coordinate_precision)
        cache_key = build_cache_key(settings, latitude, longitude, query)

        lock = self._locks.setdefault(cache_key, asyncio.Lock())
        try:
            async with lock:
                return await self._analyze_locked(query, latitude, longitude, cache_key)
        finally:
            if not lock.locked():
                self._locks.pop(cache_key, None)

    async def _analyze_locked(
        self, query: AnalysisQuery, latitude: float, longitude: float, cache_key: str
    ) -> dict[str, Any]:
        settings = self._settings
        now = datetime.now(timezone.utc)

        cached = await asyncio.to_thread(self._cache.get, cache_key, now)
        if cached is not None:
            result = cached["result"]
            # Served entirely from MongoDB: no provider call, no recomputation.
            result["cache_status"] = {
                **result["cache_status"],
                "status": "hit",
                "daily_records_reused": 0,
                "daily_records_fetched": 0,
                "upstream_requests": 0,
            }
            return result

        analysis_range = (date(query.start_year, 1, 1), date(query.end_year, 12, 31))
        baseline_range = (
            date(settings.baseline_start_year, 1, 1),
            date(settings.baseline_end_year, 12, 31),
        )
        try:
            async with asyncio.timeout(settings.max_request_seconds):
                series = await self._weather.get_series(
                    latitude, longitude, [analysis_range, baseline_range]
                )
        except TimeoutError as exc:
            raise UpstreamTimeoutError(
                "Retrieving weather data took longer than the allowed request time."
            ) from exc

        expires_at = now + timedelta(days=settings.analysis_cache_ttl_days)
        result = build_analysis(settings, query, latitude, longitude, series.records, series.metadata)
        result["cache_status"] = {
            "status": "miss",
            "cache_key": cache_key,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "daily_records_reused": series.records_reused,
            "daily_records_fetched": series.records_fetched,
            "upstream_requests": series.upstream_requests,
        }

        await asyncio.to_thread(
            self._cache.put,
            {
                "cache_key": cache_key,
                "algorithm_version": ALGORITHM_VERSION,
                "source_model": settings.open_meteo_model,
                "latitude": latitude,
                "longitude": longitude,
                "hazard": query.hazard,
                "start_year": query.start_year,
                "end_year": query.end_year,
                "baseline_start": settings.baseline_start_year,
                "baseline_end": settings.baseline_end_year,
                "result": result,
                "created_at": now,
                "expires_at": expires_at,
            },
        )
        return result


def build_analysis(
    settings: Settings,
    query: AnalysisQuery,
    latitude: float,
    longitude: float,
    records: Sequence[DailyRecord],
    metadata: GridMetadata,
) -> dict[str, Any]:
    """Compute the full analysis document from validated daily records (no I/O)."""
    start_year, end_year = query.start_year, query.end_year
    base_start, base_end = settings.baseline_start_year, settings.baseline_end_year
    min_completeness = DEFAULT_MIN_COMPLETENESS

    # --- Baseline threshold: always from the fixed baseline, whatever range was selected.
    baseline = [r for r in records if base_start <= r.date.year <= base_end]
    baseline_valid = [r.temperature_max_c for r in baseline if r.quality_status == QUALITY_VALID]
    baseline_expected = sum(days_in_year(y) for y in range(base_start, base_end + 1))
    baseline_completeness = len(baseline_valid) / baseline_expected
    if baseline_completeness < settings.min_baseline_completeness:
        raise InsufficientDataError(
            f"Only {baseline_completeness:.1%} of the {base_start}-{base_end} baseline has valid "
            "data at this location, which is too little to compute a reliable threshold.",
        )
    threshold = calculate_threshold(baseline_valid, DEFAULT_PERCENTILE)

    # --- Detection on the selected period only.
    selected = [r for r in records if start_year <= r.date.year <= end_year]
    observations = [r.to_observation() for r in selected]
    valid_days = sum(1 for r in selected if r.quality_status == QUALITY_VALID)
    if valid_days == 0:
        raise InsufficientDataError(
            "The weather provider has no valid daily temperatures for the selected period."
        )
    events = detect_heatwaves(observations, threshold, DEFAULT_MIN_DURATION_DAYS)
    annual = aggregate_annual_metrics(observations, events, start_year, end_year, min_completeness)

    # --- Trend and comparison use complete years only.
    complete = [a for a in annual if a.is_complete]
    incomplete_years = [a.year for a in annual if not a.is_complete]
    complete_years = [a.year for a in complete]
    events_trend = calculate_trend(complete_years, [a.event_count for a in complete])
    days_trend = calculate_trend(complete_years, [a.heatwave_days for a in complete])
    events_mk = mann_kendall_test(complete_years, [a.event_count for a in complete])
    days_mk = mann_kendall_test(complete_years, [a.heatwave_days for a in complete])
    comparison = compare_matched_periods(
        [a.year for a in annual],
        [a.heatwave_days for a in annual],
        [a.is_complete for a in annual],
    )
    rolling = rolling_average(
        [a.heatwave_days if a.is_complete else None for a in annual], DEFAULT_ROLLING_WINDOW
    )

    # --- Summary.
    period_start, period_end = date(start_year, 1, 1), date(end_year, 12, 31)
    longest = max(events, key=lambda e: e.duration_days, default=None)
    hottest = max(events, key=lambda e: e.peak_temperature_c, default=None)
    total_days = sum(e.duration_days for e in events)
    years_with_events = sum(1 for a in annual if a.event_count > 0)
    boundary_events = [e for e in events if e.start_date == period_start or e.end_date == period_end]

    # --- Data quality.
    expected_days = sum(a.expected_days for a in annual)
    implausible = [r for r in selected if r.quality_status == QUALITY_IMPLAUSIBLE]
    overall_completeness = valid_days / expected_days
    warnings: list[str] = []
    if incomplete_years:
        warnings.append(
            f"{len(incomplete_years)} year(s) have less than {min_completeness:.0%} valid daily "
            "data and are excluded from trend and comparison calculations."
        )
    if implausible:
        warnings.append(
            f"{len(implausible)} value(s) outside the physical bounds "
            f"({PHYSICAL_MIN_C:.0f} to {PHYSICAL_MAX_C:.0f} °C) were excluded."
        )
    if baseline_completeness < min_completeness:
        warnings.append(
            f"The baseline period is only {baseline_completeness:.1%} complete; the threshold is "
            "less certain than usual."
        )

    model_info = SOURCE_MODELS[settings.open_meteo_model]
    preset = find_preset(latitude, longitude, settings.coordinate_precision)
    baseline_label = f"{base_start}-{base_end}"
    overlaps_baseline = start_year <= base_end and end_year >= base_start

    generated_insights = [
        insight_text.coverage_insight(
            len(annual), incomplete_years, overall_completeness, min_completeness
        ),
        insight_text.summary_insight(len(events), total_days, len(annual), years_with_events),
        insight_text.trend_insight(
            days_trend, "heatwave_days", "annual heatwave days", "days", DEFAULT_MIN_TREND_YEARS
        ),
        insight_text.trend_insight(
            events_trend, "events", "annual heatwave events", "events", DEFAULT_MIN_TREND_YEARS
        ),
        insight_text.mann_kendall_insight(
            days_mk, "annual heatwave days", "days", DEFAULT_MIN_TREND_YEARS
        ),
        insight_text.comparison_insight(comparison),
        *insight_text.caveat_insights(
            overlaps_baseline, baseline_label, len(boundary_events), DEFAULT_PERCENTILE
        ),
    ]

    return {
        "location": {
            "kind": "point",
            "name": preset["name"] if preset else None,
            "latitude": latitude,
            "longitude": longitude,
            "grid_latitude": metadata.grid_latitude,
            "grid_longitude": metadata.grid_longitude,
            "elevation_m": metadata.elevation_m,
            "timezone": metadata.timezone,
        },
        "hazard": query.hazard,
        "selected_period": _period(start_year, end_year),
        "baseline_period": _period(base_start, base_end),
        "threshold_c": round(threshold, 2),
        "annual_series": [
            {
                "year": a.year,
                "event_count": a.event_count,
                "heatwave_days": a.heatwave_days,
                "longest_event_days": a.longest_event_days,
                "mean_event_intensity_c": _round(a.mean_event_intensity_c),
                "max_event_intensity_c": _round(a.max_event_intensity_c),
                "peak_temperature_c": _round(a.peak_temperature_c, 1),
                "heatwave_days_rolling_avg_5y": _round(rolling[i]),
                "valid_days": a.valid_days,
                "expected_days": a.expected_days,
                "completeness": round(a.completeness, 4),
                "is_complete": a.is_complete,
            }
            for i, a in enumerate(annual)
        ],
        "events": [_event_out(e, i, e in boundary_events) for i, e in enumerate(events, start=1)],
        "overall_summary": {
            "total_events": len(events),
            "total_heatwave_days": total_days,
            "longest_event_days": longest.duration_days if longest else 0,
            "longest_event_start": longest.start_date.isoformat() if longest else None,
            "longest_event_end": longest.end_date.isoformat() if longest else None,
            "average_intensity_c": _round(
                sum(e.mean_exceedance_c for e in events) / len(events) if events else None
            ),
            "highest_peak_temperature_c": _round(hottest.peak_temperature_c, 1) if hottest else None,
            "highest_peak_date": hottest.peak_date.isoformat() if hottest else None,
            "years_analyzed": len(annual),
            "years_with_events": years_with_events,
        },
        "trend": {
            "method": "Ordinary least squares regression of the annual value on the year",
            "min_years_required": DEFAULT_MIN_TREND_YEARS,
            "years_used": len(complete),
            "years_excluded": incomplete_years,
            "events_per_decade": _trend_out(events_trend, "events per decade"),
            "heatwave_days_per_decade": _trend_out(days_trend, "days per decade"),
            "events_mann_kendall": _mann_kendall_out(events_mk, "events per decade"),
            "heatwave_days_mann_kendall": _mann_kendall_out(days_mk, "days per decade"),
            "period_comparison": _comparison_out(comparison),
        },
        "generated_insights": generated_insights,
        "data_quality": {
            "coverage_status": "partial" if incomplete_years else "complete",
            "min_completeness_required": min_completeness,
            "overall_completeness": round(overall_completeness, 4),
            "expected_days": expected_days,
            "valid_days": valid_days,
            "missing_days": expected_days - valid_days - len(implausible),
            "implausible_days": len(implausible),
            "incomplete_years": incomplete_years,
            "baseline_completeness": round(baseline_completeness, 4),
            "baseline_valid_days": len(baseline_valid),
            "baseline_expected_days": baseline_expected,
            "physical_bounds_c": [PHYSICAL_MIN_C, PHYSICAL_MAX_C],
            "excluded_values": [
                {
                    "date": r.date.isoformat(),
                    "temperature_max_c": r.temperature_max_c,
                    "reason": "outside physical sanity bounds",
                }
                for r in implausible[:MAX_EXCLUDED_VALUES_LISTED]
            ],
            "excluded_values_truncated": len(implausible) > MAX_EXCLUDED_VALUES_LISTED,
            "warnings": warnings,
        },
        "methodology": _methodology(baseline_label, model_info["label"]),
        "source_metadata": {
            "provider": "Open-Meteo Historical Weather API",
            "api_url": OPEN_METEO_ARCHIVE_URL,
            "model": settings.open_meteo_model,
            "model_label": model_info["label"],
            "spatial_resolution": model_info["resolution"],
            "variable": "temperature_2m_max (daily maximum air temperature at 2 m)",
            "unit": "°C",
            "timezone_mode": "auto (days are local calendar days at the location)",
            "attribution": "Weather data by Open-Meteo.com (CC BY 4.0); reanalysis by ECMWF/Copernicus.",
        },
    }


def _period(start_year: int, end_year: int) -> dict[str, Any]:
    return {
        "start_year": start_year,
        "end_year": end_year,
        "start_date": date(start_year, 1, 1).isoformat(),
        "end_date": date(end_year, 12, 31).isoformat(),
    }


def _event_out(event: HeatwaveEvent, index: int, touches_boundary: bool) -> dict[str, Any]:
    return {
        "id": f"hw-{index:04d}",
        "start_date": event.start_date.isoformat(),
        "end_date": event.end_date.isoformat(),
        "start_year": event.start_date.year,
        "duration_days": event.duration_days,
        "peak_temperature_c": round(event.peak_temperature_c, 1),
        "peak_date": event.peak_date.isoformat(),
        "mean_temperature_c": round(event.mean_temperature_c, 2),
        "mean_exceedance_c": round(event.mean_exceedance_c, 2),
        "max_exceedance_c": round(event.max_exceedance_c, 2),
        "touches_period_boundary": touches_boundary,
    }


def _trend_out(trend: TrendResult, unit: str) -> dict[str, Any]:
    return {
        "status": trend.status,
        "unit": unit,
        "n_years": trend.n_years,
        "slope_per_decade": _round(trend.slope_per_decade, 3),
        "slope_ci95_low_per_decade": _round(trend.slope_ci95_low_per_decade, 3),
        "slope_ci95_high_per_decade": _round(trend.slope_ci95_high_per_decade, 3),
        "r_squared": _round(trend.r_squared, 3),
        "p_value": _round(trend.p_value, 4),
        "first_year": trend.first_year,
        "last_year": trend.last_year,
    }


def _mann_kendall_out(result: MannKendallResult, unit: str) -> dict[str, Any]:
    return {
        "status": result.status,
        "unit": unit,
        "n_years": result.n_years,
        "s_statistic": result.s_statistic,
        "kendall_tau": _round(result.kendall_tau, 3),
        "z_score": _round(result.z_score, 3),
        "p_value": _round(result.p_value, 4),
        "direction": result.direction,
        "sen_slope_per_decade": _round(result.sen_slope_per_decade, 3),
        "sen_slope_ci95_low_per_decade": _round(result.sen_slope_ci95_low_per_decade, 3),
        "sen_slope_ci95_high_per_decade": _round(result.sen_slope_ci95_high_per_decade, 3),
    }


def _comparison_out(comparison: PeriodComparison) -> dict[str, Any]:
    return {
        "status": comparison.status,
        "metric": "mean heatwave days per year",
        "period_years": comparison.period_years,
        "early_start": comparison.early_start,
        "early_end": comparison.early_end,
        "late_start": comparison.late_start,
        "late_end": comparison.late_end,
        "early_mean": _round(comparison.early_mean),
        "late_mean": _round(comparison.late_mean),
        "absolute_change": _round(comparison.absolute_change),
        "percent_change": _round(comparison.percent_change, 1),
    }


def _methodology(baseline_label: str, model_label: str) -> dict[str, Any]:
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "definition": (
            f"A heatwave is at least {DEFAULT_MIN_DURATION_DAYS} consecutive calendar days with "
            "daily maximum 2 m air temperature strictly greater than the threshold. A day exactly "
            "at the threshold does not count."
        ),
        "percentile": DEFAULT_PERCENTILE,
        "min_duration_days": DEFAULT_MIN_DURATION_DAYS,
        "threshold_method": (
            f"{DEFAULT_PERCENTILE:.0f}th percentile (linear interpolation) of all valid daily "
            f"maximum temperatures in the fixed {baseline_label} baseline at this grid cell. One "
            "year-round threshold is used for every year, regardless of the period selected."
        ),
        "attribution_rules": [
            "An event is counted once, in the calendar year in which it starts.",
            "Each heatwave day is counted in the calendar year it falls in, so an event crossing "
            "31 December contributes days to both years.",
            "Longest duration and intensity for a year describe the events that start in that year.",
        ],
        "intensity_definition": (
            "Event intensity is the mean number of degrees Celsius by which the daily maximum "
            "exceeds the threshold across the event's days."
        ),
        "trend_method": (
            f"Ordinary least squares slope per decade over years with at least "
            f"{DEFAULT_MIN_COMPLETENESS:.0%} valid days; reported only with "
            f"{DEFAULT_MIN_TREND_YEARS} or more such years. A Mann-Kendall test (rank based, "
            "corrected for ties, two-sided) with the Theil-Sen median slope is reported alongside "
            "it as a check that does not assume normally distributed values. The early versus late "
            "comparison uses two equal, non-overlapping periods of 5 to 10 years."
        ),
        "missing_data_policy": (
            "Missing values are never interpolated. A missing value or missing calendar date ends "
            "any heatwave run, so gaps can only reduce, never create, events."
        ),
        "limitations": [
            "This is a simplified operational definition. It is not the WMO definition nor that of "
            "any national meteorological service.",
            "A single year-round threshold means events cluster in the hottest season; unusually "
            "warm spells in cooler months are not detected.",
            f"The data are {model_label} reanalysis values for one grid cell, not station "
            "measurements. Grid-cell averages smooth local extremes and urban heat island effects, "
            "and coastal cells can blend land and sea.",
            "Results describe a point location, not a city boundary, state or region.",
            "Regression statistics assume independent residuals; annual counts are discrete and can "
            "be autocorrelated, so intervals are indicative only. The Mann-Kendall test is likewise "
            "not corrected for autocorrelation.",
            "No causal attribution is made.",
            "Events touching the first or last day of the selected period may be truncated.",
        ],
    }
