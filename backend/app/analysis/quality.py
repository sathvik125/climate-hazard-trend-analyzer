"""Pure validation of a provider daily payload.

The parser never invents or repairs temperatures. A day is either accepted as
valid, recorded as missing, or recorded as implausible (and excluded from the
analysis while keeping the raw value for audit). Anything structurally wrong
raises PayloadError so the caller can fail the request clearly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.analysis.heatwave import DailyObservation

# Physical sanity bounds for a daily maximum 2 m air temperature. They sit just
# outside the observed world records (-89.2 C at Vostok, 56.7 C at Furnace Creek),
# so a value beyond them is a data fault, not weather. These are not statistical
# clipping limits: real extremes inside the bounds are always kept.
PHYSICAL_MIN_C = -90.0
PHYSICAL_MAX_C = 60.0

EXPECTED_UNIT = "°C"
TEMPERATURE_FIELD = "temperature_2m_max"

QUALITY_VALID = "valid"
QUALITY_MISSING = "missing"
QUALITY_IMPLAUSIBLE = "implausible"


class PayloadError(ValueError):
    """The provider response cannot be trusted or interpreted."""


@dataclass(frozen=True)
class DailyRecord:
    date: date
    temperature_max_c: float | None  # raw provider value; None when missing
    quality_status: str

    def to_observation(self) -> DailyObservation:
        """Only valid records carry a temperature into the analysis."""
        usable = self.temperature_max_c if self.quality_status == QUALITY_VALID else None
        return DailyObservation(self.date, usable)


@dataclass(frozen=True)
class ParseReport:
    duplicate_dates_removed: int = 0
    null_values: int = 0
    absent_dates: int = 0
    implausible_values: int = 0


def classify_temperature(value: float | None) -> str:
    if value is None:
        return QUALITY_MISSING
    if value < PHYSICAL_MIN_C or value > PHYSICAL_MAX_C:
        return QUALITY_IMPLAUSIBLE
    return QUALITY_VALID


def parse_daily_payload(
    payload: Any, start: date, end: date
) -> tuple[list[DailyRecord], ParseReport]:
    """Validate a provider payload and return one record per calendar day in [start, end].

    Deduplication rule: repeated dates with an identical value collapse to one
    record; repeated dates with different values raise PayloadError, because
    there is no defensible way to choose between them.
    """
    if not isinstance(payload, dict):
        raise PayloadError("response body is not a JSON object")
    if payload.get("error"):
        raise PayloadError(f"provider reported an error: {payload.get('reason', 'unknown')}")

    units = payload.get("daily_units")
    if not isinstance(units, dict) or units.get(TEMPERATURE_FIELD) != EXPECTED_UNIT:
        got = units.get(TEMPERATURE_FIELD) if isinstance(units, dict) else None
        raise PayloadError(f"unexpected temperature unit {got!r}; expected {EXPECTED_UNIT!r}")

    daily = payload.get("daily")
    if not isinstance(daily, dict):
        raise PayloadError("response has no 'daily' object")
    times, temps = daily.get("time"), daily.get(TEMPERATURE_FIELD)
    if not isinstance(times, list) or not isinstance(temps, list):
        raise PayloadError("daily.time and daily.temperature_2m_max must both be arrays")
    if len(times) != len(temps):
        raise PayloadError(
            f"array length mismatch: {len(times)} dates but {len(temps)} temperatures"
        )
    if not times:
        raise PayloadError("provider returned no daily records for the requested range")

    by_date: dict[date, float | None] = {}
    duplicates = 0
    for raw_date, raw_temp in zip(times, temps):
        day = _parse_date(raw_date)
        if day < start or day > end:
            raise PayloadError(f"date {day.isoformat()} is outside the requested range")
        value = _parse_temperature(raw_temp, day)
        if day in by_date:
            if by_date[day] != value:
                raise PayloadError(f"conflicting duplicate records for {day.isoformat()}")
            duplicates += 1
            continue
        by_date[day] = value

    records: list[DailyRecord] = []
    absent = nulls = implausible = 0
    day = start
    while day <= end:
        if day not in by_date:
            absent += 1
            records.append(DailyRecord(day, None, QUALITY_MISSING))
        else:
            value = by_date[day]
            status = classify_temperature(value)
            nulls += status == QUALITY_MISSING
            implausible += status == QUALITY_IMPLAUSIBLE
            records.append(DailyRecord(day, value, status))
        day += timedelta(days=1)

    return records, ParseReport(duplicates, nulls, absent, implausible)


def _parse_date(raw: Any) -> date:
    if not isinstance(raw, str):
        raise PayloadError(f"invalid date value {raw!r}")
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise PayloadError(f"invalid date value {raw!r}") from exc


def _parse_temperature(raw: Any, day: date) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise PayloadError(f"non-numeric temperature {raw!r} on {day.isoformat()}")
    value = float(raw)
    if not math.isfinite(value):
        raise PayloadError(f"non-finite temperature on {day.isoformat()}")
    return value
