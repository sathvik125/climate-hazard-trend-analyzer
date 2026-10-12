"""Unit tests for provider payload validation."""

from __future__ import annotations

from datetime import date

import pytest

from app.analysis.quality import (
    QUALITY_IMPLAUSIBLE,
    QUALITY_MISSING,
    QUALITY_VALID,
    PayloadError,
    parse_daily_payload,
)

START, END = date(2020, 1, 1), date(2020, 1, 4)


def payload(times: list, temps: list, unit: str = "°C") -> dict:
    return {
        "daily_units": {"time": "iso8601", "temperature_2m_max": unit},
        "daily": {"time": times, "temperature_2m_max": temps},
    }


DATES = ["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-04"]


def test_valid_payload_yields_one_record_per_day():
    records, report = parse_daily_payload(payload(DATES, [30.1, 31, 29.5, 28]), START, END)
    assert [r.date.isoformat() for r in records] == DATES
    assert all(r.quality_status == QUALITY_VALID for r in records)
    assert report.null_values == report.absent_dates == report.duplicate_dates_removed == 0


def test_null_measurement_is_recorded_as_missing_not_filled():
    records, report = parse_daily_payload(payload(DATES, [30, None, 30, 30]), START, END)
    assert records[1].quality_status == QUALITY_MISSING
    assert records[1].to_observation().temperature_max_c is None
    assert report.null_values == 1


def test_absent_date_is_recorded_as_missing():
    times = ["2020-01-01", "2020-01-02", "2020-01-04"]
    records, report = parse_daily_payload(payload(times, [30, 30, 30]), START, END)
    assert len(records) == 4
    assert records[2].quality_status == QUALITY_MISSING
    assert report.absent_dates == 1


def test_implausible_value_is_kept_for_audit_but_excluded_from_analysis():
    records, report = parse_daily_payload(payload(DATES, [30, 75.0, 30, -120.0]), START, END)
    assert records[1].quality_status == QUALITY_IMPLAUSIBLE
    assert records[1].temperature_max_c == 75.0
    assert records[1].to_observation().temperature_max_c is None
    assert report.implausible_values == 2


def test_identical_duplicate_dates_are_collapsed():
    times = DATES + ["2020-01-04"]
    records, report = parse_daily_payload(payload(times, [30, 30, 30, 28, 28]), START, END)
    assert len(records) == 4
    assert report.duplicate_dates_removed == 1


def test_conflicting_duplicate_dates_fail_clearly():
    times = DATES + ["2020-01-04"]
    with pytest.raises(PayloadError, match="conflicting duplicate"):
        parse_daily_payload(payload(times, [30, 30, 30, 28, 33]), START, END)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), "31.2", True])
def test_non_finite_or_non_numeric_values_are_rejected(bad):
    with pytest.raises(PayloadError):
        parse_daily_payload(payload(DATES, [30, bad, 30, 30]), START, END)


def test_wrong_unit_is_rejected():
    with pytest.raises(PayloadError, match="unit"):
        parse_daily_payload(payload(DATES, [86, 87, 88, 89], unit="°F"), START, END)


def test_array_length_mismatch_is_rejected():
    with pytest.raises(PayloadError, match="length mismatch"):
        parse_daily_payload(payload(DATES, [30, 30]), START, END)


def test_empty_arrays_are_rejected():
    with pytest.raises(PayloadError, match="no daily records"):
        parse_daily_payload(payload([], []), START, END)


def test_date_outside_requested_range_is_rejected():
    with pytest.raises(PayloadError, match="outside the requested range"):
        parse_daily_payload(payload(["2019-12-31"], [30]), START, END)


def test_provider_error_body_is_rejected():
    with pytest.raises(PayloadError, match="provider reported an error"):
        parse_daily_payload({"error": True, "reason": "bad things"}, START, END)
