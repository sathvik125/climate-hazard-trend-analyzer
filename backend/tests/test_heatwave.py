"""Unit tests for the pure heatwave functions."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.analysis.heatwave import (
    DailyObservation,
    aggregate_annual_metrics,
    calculate_threshold,
    calculate_trend,
    compare_matched_periods,
    detect_heatwaves,
    mann_kendall_test,
    rolling_average,
)

THRESHOLD = 35.0


def series(start: date, temps: list[float | None]) -> list[DailyObservation]:
    return [DailyObservation(start + timedelta(days=i), t) for i, t in enumerate(temps)]


# --- calculate_threshold ---------------------------------------------------------


def test_threshold_is_the_95th_percentile_with_linear_interpolation():
    assert calculate_threshold(range(1, 101)) == pytest.approx(95.05)


def test_threshold_ignores_missing_and_non_finite_values():
    assert calculate_threshold([10.0, None, float("nan"), 20.0], percentile=50) == pytest.approx(15.0)


def test_threshold_without_valid_values_is_an_error():
    with pytest.raises(ValueError):
        calculate_threshold([None, None])


# --- detect_heatwaves ------------------------------------------------------------


def test_exactly_three_exceedance_days_create_one_event():
    events = detect_heatwaves(series(date(2020, 5, 1), [30, 36, 37, 38, 30]), THRESHOLD)
    assert len(events) == 1
    event = events[0]
    assert (event.start_date, event.end_date) == (date(2020, 5, 2), date(2020, 5, 4))
    assert event.duration_days == 3
    assert event.peak_temperature_c == 38
    assert event.peak_date == date(2020, 5, 4)
    assert event.mean_exceedance_c == pytest.approx(2.0)  # (1 + 2 + 3) / 3
    assert event.max_exceedance_c == pytest.approx(3.0)


def test_two_exceedance_days_create_no_event():
    assert detect_heatwaves(series(date(2020, 5, 1), [30, 36, 37, 30]), THRESHOLD) == []


def test_temperature_exactly_at_threshold_is_not_an_exceedance():
    # 35.0 is not strictly greater than 35.0, so the run is only 2 days long.
    assert detect_heatwaves(series(date(2020, 5, 1), [36, 35.0, 36, 36]), THRESHOLD) == []


def test_null_temperature_breaks_an_event():
    temps = [36, 36, None, 36, 36]
    assert detect_heatwaves(series(date(2020, 5, 1), temps), THRESHOLD) == []


def test_missing_calendar_date_breaks_an_event():
    observations = [
        DailyObservation(date(2020, 5, 1), 36),
        DailyObservation(date(2020, 5, 2), 36),
        # 3 May is absent from the series entirely
        DailyObservation(date(2020, 5, 4), 36),
        DailyObservation(date(2020, 5, 5), 36),
    ]
    assert detect_heatwaves(observations, THRESHOLD) == []


def test_event_spanning_december_and_january_is_one_event():
    events = detect_heatwaves(series(date(2019, 12, 30), [36, 37, 38, 36, 30]), THRESHOLD)
    assert len(events) == 1
    assert (events[0].start_date, events[0].end_date) == (date(2019, 12, 30), date(2020, 1, 2))
    assert events[0].duration_days == 4


def test_event_running_to_the_last_day_is_closed():
    events = detect_heatwaves(series(date(2020, 5, 1), [30, 36, 36, 36]), THRESHOLD)
    assert len(events) == 1 and events[0].end_date == date(2020, 5, 4)


def test_two_separate_events_are_both_found():
    temps = [36, 36, 36, 30, 36, 36, 36, 36]
    events = detect_heatwaves(series(date(2020, 5, 1), temps), THRESHOLD)
    assert [e.duration_days for e in events] == [3, 4]


def test_duplicate_dates_are_rejected():
    day = date(2020, 5, 1)
    with pytest.raises(ValueError):
        detect_heatwaves([DailyObservation(day, 36), DailyObservation(day, 36)], THRESHOLD)


# --- aggregate_annual_metrics ----------------------------------------------------


def full_years(start_year: int, end_year: int, hot: set[date]) -> list[DailyObservation]:
    days = (date(end_year, 12, 31) - date(start_year, 1, 1)).days + 1
    return [
        DailyObservation(d, 40.0 if d in hot else 30.0)
        for d in (date(start_year, 1, 1) + timedelta(days=i) for i in range(days))
    ]


def test_leap_year_completeness_uses_366_days():
    observations = full_years(2020, 2021, set())
    annual = aggregate_annual_metrics(observations, [], 2020, 2021)
    assert (annual[0].expected_days, annual[0].valid_days, annual[0].completeness) == (366, 366, 1.0)
    assert (annual[1].expected_days, annual[1].valid_days) == (365, 365)


def test_leap_year_missing_29_february_is_not_fully_complete():
    observations = [o for o in full_years(2020, 2020, set()) if o.date != date(2020, 2, 29)]
    annual = aggregate_annual_metrics(observations, [], 2020, 2020)
    assert annual[0].valid_days == 365
    assert annual[0].completeness == pytest.approx(365 / 366)
    assert annual[0].is_complete  # still above the 95% requirement


def test_year_below_95_percent_is_flagged_incomplete():
    observations = [o for o in full_years(2021, 2021, set()) if o.date.month != 6]  # 30 days lost
    annual = aggregate_annual_metrics(observations, [], 2021, 2021)
    assert annual[0].completeness == pytest.approx(335 / 365)
    assert not annual[0].is_complete


def test_annual_aggregation_attributes_events_and_days_correctly():
    hot = {
        date(2019, 5, 1), date(2019, 5, 2), date(2019, 5, 3),  # 3-day event in 2019
        date(2019, 12, 30), date(2019, 12, 31), date(2020, 1, 1), date(2020, 1, 2),  # crosses years
        date(2020, 6, 1), date(2020, 6, 2), date(2020, 6, 3), date(2020, 6, 4), date(2020, 6, 5),
    }
    observations = full_years(2019, 2021, hot)
    events = detect_heatwaves(observations, THRESHOLD)
    annual = {a.year: a for a in aggregate_annual_metrics(observations, events, 2019, 2021)}

    # Frequency goes to the start year: the cross-year event belongs to 2019.
    assert [annual[y].event_count for y in (2019, 2020, 2021)] == [2, 1, 0]
    # Days go to the calendar year they fall in: 3 + 2 in 2019, 2 + 5 in 2020.
    assert [annual[y].heatwave_days for y in (2019, 2020, 2021)] == [5, 7, 0]
    assert [annual[y].longest_event_days for y in (2019, 2020, 2021)] == [4, 5, 0]
    assert annual[2019].mean_event_intensity_c == pytest.approx(5.0)
    assert annual[2021].mean_event_intensity_c is None
    assert annual[2021].peak_temperature_c is None


# --- calculate_trend -------------------------------------------------------------


def test_trend_slope_is_reported_per_decade():
    years = list(range(2000, 2020))
    trend = calculate_trend(years, [0.5 * (y - 2000) for y in years])
    assert trend.status == "ok"
    assert trend.slope_per_decade == pytest.approx(5.0)
    assert trend.r_squared == pytest.approx(1.0)
    assert (trend.first_year, trend.last_year, trend.n_years) == (2000, 2019, 20)


def test_trend_is_not_extrapolated_from_too_few_years():
    trend = calculate_trend([2018, 2019, 2020], [1, 2, 3])
    assert trend.status == "insufficient_data"
    assert trend.slope_per_decade is None


def test_trend_of_a_flat_series_is_zero_with_interval_including_zero():
    years = list(range(2000, 2015))
    trend = calculate_trend(years, [0] * len(years))
    assert trend.status == "ok"
    assert trend.slope_per_decade == 0
    assert trend.slope_ci95_low_per_decade <= 0 <= trend.slope_ci95_high_per_decade


# --- mann_kendall_test -----------------------------------------------------------


def test_mann_kendall_hand_worked_example():
    # Pairs of [3, 5, 4, 8]: +1 +1 +1 -1 +1 +1 -> S = 4 of a possible 6.
    result = mann_kendall_test([2001, 2002, 2003, 2004], [3, 5, 4, 8], min_years=4)
    assert result.s_statistic == 4
    assert result.kendall_tau == pytest.approx(4 / 6)
    assert result.direction == "increasing"
    # Var(S) = 4*3*13/18 = 8.667; Z = (4 - 1) / sqrt(8.667) = 1.019
    assert result.z_score == pytest.approx(1.019, abs=0.001)
    assert result.p_value == pytest.approx(0.308, abs=0.001)


def test_mann_kendall_detects_a_strictly_increasing_series():
    years = list(range(2000, 2020))
    result = mann_kendall_test(years, [2 * (y - 2000) for y in years])
    assert result.kendall_tau == pytest.approx(1.0)
    assert result.p_value < 0.001
    assert result.sen_slope_per_decade == pytest.approx(20.0)


def test_mann_kendall_decreasing_series_has_negative_statistics():
    years = list(range(2000, 2015))
    result = mann_kendall_test(years, [30 - y + 2000 for y in years])
    assert result.direction == "decreasing"
    assert result.s_statistic < 0 and result.z_score < 0
    assert result.sen_slope_per_decade == pytest.approx(-10.0)


def test_mann_kendall_constant_series_shows_no_trend():
    years = list(range(2000, 2015))
    result = mann_kendall_test(years, [0] * 15)
    assert (result.s_statistic, result.z_score, result.p_value) == (0, 0.0, 1.0)
    assert result.direction == "none"
    assert result.sen_slope_per_decade == 0


def test_mann_kendall_is_not_dominated_by_one_extreme_year():
    years = list(range(2000, 2012))
    flat = [1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2]
    spiked = flat[:-1] + [500]  # one enormous final year
    assert calculate_trend(years, spiked).slope_per_decade > 100
    result = mann_kendall_test(years, spiked)
    assert result.p_value > 0.05
    assert abs(result.sen_slope_per_decade) < 5


def test_mann_kendall_tie_correction_reduces_the_variance():
    years = list(range(2000, 2010))
    tied = mann_kendall_test(years, [0, 0, 0, 0, 0, 1, 1, 1, 1, 1])
    # S = 25. Without ties Var = 125; two groups of five ties remove 2*5*4*15/18 = 33.33.
    assert tied.s_statistic == 25
    assert tied.z_score == pytest.approx(24 / (125 - 600 / 18) ** 0.5)


def test_mann_kendall_needs_enough_years():
    result = mann_kendall_test([2018, 2019, 2020], [1, 2, 3])
    assert result.status == "insufficient_data"
    assert result.p_value is None and result.sen_slope_per_decade is None


def test_mann_kendall_does_not_depend_on_input_order():
    years = [2003, 2001, 2004, 2002, 2000, 2007, 2005, 2006, 2009, 2008]
    values = [4, 2, 6, 3, 1, 9, 5, 8, 12, 10]
    ordered = sorted(zip(years, values))
    a = mann_kendall_test(years, values)
    b = mann_kendall_test([y for y, _ in ordered], [v for _, v in ordered])
    assert (a.s_statistic, a.p_value) == (b.s_statistic, b.p_value)


# --- rolling_average -------------------------------------------------------------


def test_rolling_average_needs_a_full_window():
    assert rolling_average([1, 2, 3, 4, 5, 6]) == [None, None, None, None, 3.0, 4.0]
    assert rolling_average([1, 2, 3]) == [None, None, None]


def test_rolling_average_is_empty_when_window_contains_an_excluded_year():
    assert rolling_average([1, 2, None, 4, 5, 6, 7, 8]) == [None] * 7 + [6.0]


# --- compare_matched_periods -----------------------------------------------------


def test_no_percentage_when_the_early_period_mean_is_zero():
    years = list(range(2000, 2020))
    values = [0] * 10 + [4] * 10
    comparison = compare_matched_periods(years, values, [True] * 20)
    assert comparison.status == "zero_baseline"
    assert comparison.percent_change is None
    assert comparison.absolute_change == pytest.approx(4.0)


def test_matched_periods_have_equal_length_and_report_percentage():
    years = list(range(1990, 2021))  # 31 years -> two 10-year periods
    values = [2] * 10 + [9] * 11 + [3] * 10
    comparison = compare_matched_periods(years, values, [True] * 31)
    assert comparison.status == "ok"
    assert (comparison.early_start, comparison.early_end) == (1990, 1999)
    assert (comparison.late_start, comparison.late_end) == (2011, 2020)
    assert comparison.percent_change == pytest.approx(50.0)


def test_comparison_refused_for_short_or_incomplete_ranges():
    assert compare_matched_periods([2019, 2020], [1, 2], [True, True]).status == "insufficient_data"
    years = list(range(2000, 2020))
    complete = [True] * 19 + [False]
    assert compare_matched_periods(years, [1] * 20, complete).status == "insufficient_data"
