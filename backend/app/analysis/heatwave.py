"""Pure heatwave analysis functions.

Nothing in this module touches the network, the database or the clock, so every
function can be unit tested with small hand-written inputs.

Operational definition used throughout:
    A heatwave event is a run of at least ``min_duration_days`` consecutive
    calendar days whose daily maximum 2 m air temperature is *strictly greater*
    than a fixed threshold. A missing value or a missing calendar date ends the run.
"""

from __future__ import annotations

import calendar
import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
from scipy import stats

DEFAULT_PERCENTILE = 95.0
DEFAULT_MIN_DURATION_DAYS = 3
DEFAULT_MIN_COMPLETENESS = 0.95
DEFAULT_MIN_TREND_YEARS = 10
DEFAULT_ROLLING_WINDOW = 5


@dataclass(frozen=True)
class DailyObservation:
    """One calendar day. ``temperature_max_c`` is None when the day is missing or excluded."""

    date: date
    temperature_max_c: float | None


@dataclass(frozen=True)
class HeatwaveEvent:
    start_date: date
    end_date: date
    duration_days: int
    peak_temperature_c: float
    peak_date: date
    mean_temperature_c: float
    mean_exceedance_c: float  # event intensity: mean degrees above the threshold
    max_exceedance_c: float


@dataclass(frozen=True)
class AnnualMetrics:
    year: int
    expected_days: int
    valid_days: int
    completeness: float
    is_complete: bool  # completeness >= the minimum required for comparisons
    event_count: int  # events attributed to the year in which they start
    heatwave_days: int  # event days attributed to the calendar year they fall in
    longest_event_days: int
    mean_event_intensity_c: float | None
    max_event_intensity_c: float | None
    peak_temperature_c: float | None


@dataclass(frozen=True)
class TrendResult:
    status: str  # "ok" or "insufficient_data"
    n_years: int
    slope_per_decade: float | None = None
    slope_ci95_low_per_decade: float | None = None
    slope_ci95_high_per_decade: float | None = None
    intercept: float | None = None
    r_squared: float | None = None
    p_value: float | None = None
    first_year: int | None = None
    last_year: int | None = None


@dataclass(frozen=True)
class MannKendallResult:
    status: str  # "ok" or "insufficient_data"
    n_years: int
    s_statistic: int | None = None  # later-minus-earlier sign count
    kendall_tau: float | None = None  # S scaled to -1..1
    z_score: float | None = None
    p_value: float | None = None  # two-sided
    direction: str | None = None  # sign of S: "increasing", "decreasing" or "none"
    sen_slope_per_decade: float | None = None  # Theil-Sen median slope
    sen_slope_ci95_low_per_decade: float | None = None
    sen_slope_ci95_high_per_decade: float | None = None


@dataclass(frozen=True)
class PeriodComparison:
    status: str  # "ok", "zero_baseline" or "insufficient_data"
    period_years: int = 0
    early_start: int | None = None
    early_end: int | None = None
    late_start: int | None = None
    late_end: int | None = None
    early_mean: float | None = None
    late_mean: float | None = None
    absolute_change: float | None = None
    percent_change: float | None = None  # None whenever the early mean is zero


def _is_valid(value: float | None) -> bool:
    return value is not None and math.isfinite(value)


def days_in_year(year: int) -> int:
    return 366 if calendar.isleap(year) else 365


def calculate_threshold(
    temperatures: Iterable[float | None], percentile: float = DEFAULT_PERCENTILE
) -> float:
    """Return the given percentile of the valid values (linear interpolation).

    Missing and non-finite values are ignored. Raises ValueError when no valid
    value is left, because a threshold computed from nothing would be invented.
    """
    if not 0 < percentile < 100:
        raise ValueError("percentile must be between 0 and 100 (exclusive)")
    valid = [float(t) for t in temperatures if _is_valid(t)]
    if not valid:
        raise ValueError("cannot compute a threshold without valid temperatures")
    return float(np.percentile(valid, percentile))


def detect_heatwaves(
    observations: Sequence[DailyObservation],
    threshold_c: float,
    min_duration_days: int = DEFAULT_MIN_DURATION_DAYS,
) -> list[HeatwaveEvent]:
    """Find every run of consecutive exceedance days of at least ``min_duration_days``.

    A run is broken by: a temperature at or below the threshold, a missing value,
    or a gap in the calendar dates. Runs crossing 31 December continue into
    January as a single event.
    """
    if min_duration_days < 1:
        raise ValueError("min_duration_days must be at least 1")

    ordered = sorted(observations, key=lambda o: o.date)
    events: list[HeatwaveEvent] = []
    run: list[DailyObservation] = []

    def close_run() -> None:
        if len(run) >= min_duration_days:
            events.append(_build_event(run, threshold_c))
        run.clear()

    previous_date: date | None = None
    for obs in ordered:
        if previous_date is not None and obs.date == previous_date:
            raise ValueError(f"duplicate date in observations: {obs.date.isoformat()}")
        if previous_date is not None and obs.date != previous_date + timedelta(days=1):
            close_run()  # a missing calendar date breaks the run
        previous_date = obs.date

        if _is_valid(obs.temperature_max_c) and obs.temperature_max_c > threshold_c:
            run.append(obs)
        else:
            close_run()
    close_run()
    return events


def _build_event(run: Sequence[DailyObservation], threshold_c: float) -> HeatwaveEvent:
    temps = [float(o.temperature_max_c) for o in run]  # type: ignore[arg-type]
    peak = max(run, key=lambda o: o.temperature_max_c)  # first hottest day
    exceedances = [t - threshold_c for t in temps]
    return HeatwaveEvent(
        start_date=run[0].date,
        end_date=run[-1].date,
        duration_days=len(run),
        peak_temperature_c=float(peak.temperature_max_c),  # type: ignore[arg-type]
        peak_date=peak.date,
        mean_temperature_c=sum(temps) / len(temps),
        mean_exceedance_c=sum(exceedances) / len(exceedances),
        max_exceedance_c=max(exceedances),
    )


def aggregate_annual_metrics(
    observations: Sequence[DailyObservation],
    events: Sequence[HeatwaveEvent],
    start_year: int,
    end_year: int,
    min_completeness: float = DEFAULT_MIN_COMPLETENESS,
) -> list[AnnualMetrics]:
    """Summarise observations and events for every year in [start_year, end_year].

    Attribution rules:
      * an event counts once, in the year it starts (frequency, longest, intensity);
      * each heatwave day counts in the calendar year it actually falls in.
    Completeness is valid days divided by expected calendar days (366 in leap years).
    """
    years = range(start_year, end_year + 1)
    valid_days = {y: 0 for y in years}
    for obs in observations:
        if obs.date.year in valid_days and _is_valid(obs.temperature_max_c):
            valid_days[obs.date.year] += 1

    heatwave_days = {y: 0 for y in years}
    events_by_start_year: dict[int, list[HeatwaveEvent]] = {y: [] for y in years}
    for event in events:
        if event.start_date.year in events_by_start_year:
            events_by_start_year[event.start_date.year].append(event)
        day = event.start_date
        while day <= event.end_date:
            if day.year in heatwave_days:
                heatwave_days[day.year] += 1
            day += timedelta(days=1)

    result: list[AnnualMetrics] = []
    for year in years:
        expected = days_in_year(year)
        completeness = valid_days[year] / expected
        started = events_by_start_year[year]
        result.append(
            AnnualMetrics(
                year=year,
                expected_days=expected,
                valid_days=valid_days[year],
                completeness=completeness,
                is_complete=completeness >= min_completeness,
                event_count=len(started),
                heatwave_days=heatwave_days[year],
                longest_event_days=max((e.duration_days for e in started), default=0),
                mean_event_intensity_c=(
                    sum(e.mean_exceedance_c for e in started) / len(started) if started else None
                ),
                max_event_intensity_c=max((e.max_exceedance_c for e in started), default=None),
                peak_temperature_c=max((e.peak_temperature_c for e in started), default=None),
            )
        )
    return result


def calculate_trend(
    years: Sequence[int],
    values: Sequence[float],
    min_years: int = DEFAULT_MIN_TREND_YEARS,
) -> TrendResult:
    """Ordinary least squares slope of an annual series, reported per decade.

    Returns ``insufficient_data`` rather than a slope when fewer than ``min_years``
    annual values are supplied. The p-value and confidence interval are those of a
    plain OLS fit; they assume independent, roughly normal residuals, which annual
    count data only approximately satisfy. Callers must present them with that caveat.
    """
    if len(years) != len(values):
        raise ValueError("years and values must have the same length")
    n = len(years)
    if n < max(min_years, 3) or len(set(years)) < 3:
        return TrendResult(status="insufficient_data", n_years=n)

    fit = stats.linregress(np.asarray(years, dtype=float), np.asarray(values, dtype=float))
    if not math.isfinite(fit.slope):
        return TrendResult(status="insufficient_data", n_years=n)

    # A perfectly constant series (for example no heatwaves at all) has zero
    # residual variance: scipy reports NaN for the error terms, which here means 0.
    stderr = float(fit.stderr) if math.isfinite(fit.stderr) else 0.0
    r_squared = float(fit.rvalue) ** 2 if math.isfinite(fit.rvalue) else None
    t_critical = float(stats.t.ppf(0.975, n - 2))
    margin = t_critical * stderr
    return TrendResult(
        status="ok",
        n_years=n,
        slope_per_decade=float(fit.slope) * 10,
        slope_ci95_low_per_decade=(float(fit.slope) - margin) * 10,
        slope_ci95_high_per_decade=(float(fit.slope) + margin) * 10,
        intercept=float(fit.intercept),
        r_squared=r_squared,
        p_value=float(fit.pvalue) if math.isfinite(fit.pvalue) else None,
        first_year=int(min(years)),
        last_year=int(max(years)),
    )


def mann_kendall_test(
    years: Sequence[int],
    values: Sequence[float],
    min_years: int = DEFAULT_MIN_TREND_YEARS,
) -> MannKendallResult:
    """Mann-Kendall test for a monotonic trend, with the Theil-Sen slope.

    The test compares every year with every later year and counts +1 when the
    later value is higher and -1 when it is lower; the total is S. It uses only
    the order of the values, so it suits lumpy annual counts better than a
    straight-line fit, and one extreme year cannot dominate it.

    The variance of S is corrected for tied values (many years share the same
    count). The test still assumes the years are independent: it is NOT
    corrected for autocorrelation, so the p-value can be too small when hot
    years cluster. The p-value is two-sided.
    """
    if len(years) != len(values):
        raise ValueError("years and values must have the same length")
    n = len(years)
    if n < max(min_years, 4):
        return MannKendallResult(status="insufficient_data", n_years=n)

    order = np.argsort(years)
    x = np.asarray(years, dtype=float)[order]
    y = np.asarray(values, dtype=float)[order]

    s = 0
    for i in range(n - 1):
        s += int(np.sign(y[i + 1 :] - y[i]).sum())

    # Variance of S under "no trend", reduced for each group of tied values.
    _, tie_counts = np.unique(y, return_counts=True)
    tie_term = sum(int(t) * (int(t) - 1) * (2 * int(t) + 5) for t in tie_counts)
    variance = (n * (n - 1) * (2 * n + 5) - tie_term) / 18

    if variance <= 0:  # every value identical: no evidence of any trend
        z = 0.0
    elif s > 0:
        z = (s - 1) / math.sqrt(variance)  # -1 / +1 is the continuity correction
    elif s < 0:
        z = (s + 1) / math.sqrt(variance)
    else:
        z = 0.0
    p_value = float(2 * stats.norm.sf(abs(z)))

    # Theil-Sen: the median of the slopes between every pair of years.
    sen_slope, _, sen_low, sen_high = stats.theilslopes(y, x, alpha=0.95)
    return MannKendallResult(
        status="ok",
        n_years=n,
        s_statistic=s,
        kendall_tau=s / (n * (n - 1) / 2),
        z_score=z,
        p_value=p_value,
        direction="increasing" if s > 0 else "decreasing" if s < 0 else "none",
        sen_slope_per_decade=float(sen_slope) * 10,
        sen_slope_ci95_low_per_decade=float(sen_low) * 10,
        sen_slope_ci95_high_per_decade=float(sen_high) * 10,
    )


def rolling_average(
    values: Sequence[float | None], window: int = DEFAULT_ROLLING_WINDOW
) -> list[float | None]:
    """Trailing mean over ``window`` consecutive entries.

    An entry is None until ``window`` values exist, and whenever any value inside
    its window is None (for example a year excluded for low completeness).
    """
    if window < 1:
        raise ValueError("window must be at least 1")
    series = pd.Series([np.nan if v is None else float(v) for v in values], dtype="float64")
    rolled = series.rolling(window=window, min_periods=window).mean()
    return [None if pd.isna(v) else float(v) for v in rolled]


def compare_matched_periods(
    years: Sequence[int],
    values: Sequence[float],
    complete: Sequence[bool],
    max_period_years: int = 10,
    min_period_years: int = 5,
) -> PeriodComparison:
    """Compare the mean of the first N years with the mean of the last N years.

    Both periods have the same length and never overlap. The comparison is refused
    when the range is too short or either period contains an incomplete year. A
    percentage is only produced when the early mean is greater than zero.
    """
    n = len(years)
    period = min(max_period_years, n // 2)
    if period < min_period_years:
        return PeriodComparison(status="insufficient_data")
    if not all(complete[:period]) or not all(complete[-period:]):
        return PeriodComparison(status="insufficient_data", period_years=period)

    early_mean = float(np.mean(values[:period]))
    late_mean = float(np.mean(values[-period:]))
    common = dict(
        period_years=period,
        early_start=years[0],
        early_end=years[period - 1],
        late_start=years[-period],
        late_end=years[-1],
        early_mean=early_mean,
        late_mean=late_mean,
        absolute_change=late_mean - early_mean,
    )
    if early_mean == 0:
        return PeriodComparison(status="zero_baseline", percent_change=None, **common)
    return PeriodComparison(
        status="ok", percent_change=(late_mean - early_mean) / early_mean * 100, **common
    )
