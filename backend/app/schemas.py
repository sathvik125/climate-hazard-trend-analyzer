"""Pydantic models for request validation and the analysis response contract."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import get_settings

Hazard = Literal["heatwave"]  # only predefined hazards are accepted


class AnalysisQuery(BaseModel):
    """Query parameters shared by the analysis, events and export endpoints."""

    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False, description="Decimal degrees north")
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False, description="Decimal degrees east")
    start_year: int = Field(description="First full calendar year to analyse")
    end_year: int = Field(description="Last full calendar year to analyse")
    hazard: Hazard = "heatwave"

    @model_validator(mode="after")
    def _check_years(self) -> "AnalysisQuery":
        settings = get_settings()
        low, high = settings.min_year, settings.max_year
        for name, year in (("start_year", self.start_year), ("end_year", self.end_year)):
            if not low <= year <= high:
                raise ValueError(f"{name} must be between {low} and {high}")
        if self.start_year > self.end_year:
            raise ValueError("start_year must not be after end_year")
        span = self.end_year - self.start_year + 1
        if span > settings.max_year_range:
            raise ValueError(f"the year range must not exceed {settings.max_year_range} years")
        return self


class ExportQuery(AnalysisQuery):
    dataset: Literal["events", "annual"] = "events"


class LocationInfo(BaseModel):
    kind: Literal["point"] = "point"
    name: str | None  # None for a custom coordinate
    latitude: float  # normalised request coordinate used for storage and the provider call
    longitude: float
    grid_latitude: float | None  # centre of the grid cell the provider matched
    grid_longitude: float | None
    elevation_m: float | None
    timezone: str | None


class Period(BaseModel):
    start_year: int
    end_year: int
    start_date: str
    end_date: str


class AnnualPoint(BaseModel):
    year: int
    event_count: int
    heatwave_days: int
    longest_event_days: int
    mean_event_intensity_c: float | None
    max_event_intensity_c: float | None
    peak_temperature_c: float | None
    heatwave_days_rolling_avg_5y: float | None
    valid_days: int
    expected_days: int
    completeness: float
    is_complete: bool


class EventOut(BaseModel):
    id: str
    start_date: str
    end_date: str
    start_year: int
    duration_days: int
    peak_temperature_c: float
    peak_date: str
    mean_temperature_c: float
    mean_exceedance_c: float
    max_exceedance_c: float
    touches_period_boundary: bool  # may continue outside the selected period


class OverallSummary(BaseModel):
    total_events: int
    total_heatwave_days: int
    longest_event_days: int
    longest_event_start: str | None
    longest_event_end: str | None
    average_intensity_c: float | None  # mean of event mean exceedances
    highest_peak_temperature_c: float | None
    highest_peak_date: str | None
    years_analyzed: int
    years_with_events: int


class TrendOut(BaseModel):
    status: Literal["ok", "insufficient_data"]
    unit: str
    n_years: int
    slope_per_decade: float | None
    slope_ci95_low_per_decade: float | None
    slope_ci95_high_per_decade: float | None
    r_squared: float | None
    p_value: float | None
    first_year: int | None
    last_year: int | None


class MannKendallOut(BaseModel):
    status: Literal["ok", "insufficient_data"]
    unit: str
    n_years: int
    s_statistic: int | None
    kendall_tau: float | None
    z_score: float | None
    p_value: float | None
    direction: Literal["increasing", "decreasing", "none"] | None
    sen_slope_per_decade: float | None
    sen_slope_ci95_low_per_decade: float | None
    sen_slope_ci95_high_per_decade: float | None


class PeriodComparisonOut(BaseModel):
    status: Literal["ok", "zero_baseline", "insufficient_data"]
    metric: str
    period_years: int
    early_start: int | None
    early_end: int | None
    late_start: int | None
    late_end: int | None
    early_mean: float | None
    late_mean: float | None
    absolute_change: float | None
    percent_change: float | None


class TrendSection(BaseModel):
    method: str
    min_years_required: int
    years_used: int
    years_excluded: list[int]
    events_per_decade: TrendOut
    heatwave_days_per_decade: TrendOut
    events_mann_kendall: MannKendallOut
    heatwave_days_mann_kendall: MannKendallOut
    period_comparison: PeriodComparisonOut


class Insight(BaseModel):
    id: str
    category: Literal["coverage", "trend", "comparison", "summary", "caveat"]
    severity: Literal["info", "warning"]
    text: str


class ExcludedValue(BaseModel):
    date: str
    temperature_max_c: float | None
    reason: str


class DataQuality(BaseModel):
    coverage_status: Literal["complete", "partial"]
    min_completeness_required: float
    overall_completeness: float
    expected_days: int
    valid_days: int
    missing_days: int
    implausible_days: int
    incomplete_years: list[int]
    baseline_completeness: float
    baseline_valid_days: int
    baseline_expected_days: int
    physical_bounds_c: tuple[float, float]
    excluded_values: list[ExcludedValue]
    excluded_values_truncated: bool
    warnings: list[str]


class Methodology(BaseModel):
    algorithm_version: str
    definition: str
    percentile: float
    min_duration_days: int
    threshold_method: str
    attribution_rules: list[str]
    intensity_definition: str
    trend_method: str
    missing_data_policy: str
    limitations: list[str]


class SourceMetadata(BaseModel):
    provider: str
    api_url: str
    model: str
    model_label: str
    spatial_resolution: str
    variable: str
    unit: str
    timezone_mode: str
    attribution: str


class CacheStatus(BaseModel):
    status: Literal["hit", "miss"]
    cache_key: str
    created_at: str
    expires_at: str
    daily_records_reused: int
    daily_records_fetched: int
    upstream_requests: int


class AnalysisResponse(BaseModel):
    location: LocationInfo
    hazard: Hazard
    selected_period: Period
    baseline_period: Period
    threshold_c: float
    annual_series: list[AnnualPoint]
    events: list[EventOut]
    overall_summary: OverallSummary
    trend: TrendSection
    generated_insights: list[Insight]
    data_quality: DataQuality
    methodology: Methodology
    source_metadata: SourceMetadata
    cache_status: CacheStatus


class EventsResponse(BaseModel):
    location: LocationInfo
    selected_period: Period
    threshold_c: float
    events: list[EventOut]
    cache_status: CacheStatus


class PresetLocation(BaseModel):
    id: str
    name: str
    country: str
    latitude: float
    longitude: float


class LocationsResponse(BaseModel):
    locations: list[PresetLocation]
    note: str
    min_year: int
    max_year: int
    max_year_range: int
    baseline_start_year: int
    baseline_end_year: int
    hazards: list[str]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable", "not_configured"]
    source_model: str
    algorithm_version: str
