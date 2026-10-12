"""Turn computed statistics into plain-language insights.

Pure functions: every sentence is assembled from numbers already computed
elsewhere. Wording rules:
  * no claim of statistical significance and no causal attribution;
  * no percentage when the comparison baseline is zero;
  * no trend statement when there are too few complete years.
"""

from __future__ import annotations

from typing import Sequence

from app.analysis.heatwave import MannKendallResult, PeriodComparison, TrendResult


def _signed(value: float, digits: int = 1) -> str:
    return f"{value:+.{digits}f}"


def _years_text(years: Sequence[int], limit: int = 8) -> str:
    shown = ", ".join(str(y) for y in years[:limit])
    return shown + (f" and {len(years) - limit} more" if len(years) > limit else "")


def coverage_insight(
    n_years: int, incomplete_years: Sequence[int], overall_completeness: float, min_completeness: float
) -> dict:
    percent = f"{min_completeness:.0%}"
    if not incomplete_years:
        return {
            "id": "coverage",
            "category": "coverage",
            "severity": "info",
            "text": (
                f"Data coverage is complete: all {n_years} selected years have at least {percent} "
                f"valid daily values ({overall_completeness:.1%} overall)."
            ),
        }
    return {
        "id": "coverage",
        "category": "coverage",
        "severity": "warning",
        "text": (
            f"Data coverage is partial: {len(incomplete_years)} of {n_years} years fall below "
            f"{percent} valid daily values ({_years_text(incomplete_years)}). Those years are shown "
            "but excluded from the trend and period comparison, and their counts are lower bounds."
        ),
    }


def trend_insight(trend: TrendResult, metric_id: str, label: str, unit: str, min_years: int) -> dict:
    if trend.status != "ok":
        return {
            "id": f"trend_{metric_id}",
            "category": "trend",
            "severity": "info",
            "text": (
                f"No trend is reported for {label}: only {trend.n_years} complete year(s) are "
                f"available and at least {min_years} are required to fit a slope."
            ),
        }
    low, high = trend.slope_ci95_low_per_decade, trend.slope_ci95_high_per_decade
    if low <= 0 <= high:
        reading = (
            "The interval includes zero, so this fit does not distinguish the change from no trend."
        )
    else:
        reading = (
            "The interval excludes zero under ordinary least squares assumptions, which annual "
            "counts only approximately meet; treat it as descriptive, not as a formal significance test."
        )
    return {
        "id": f"trend_{metric_id}",
        "category": "trend",
        "severity": "info",
        "text": (
            f"{label.capitalize()} changed by {_signed(trend.slope_per_decade, 2)} {unit} per decade "
            f"over {trend.first_year}-{trend.last_year} (linear fit, 95% interval "
            f"{_signed(low, 2)} to {_signed(high, 2)}, {trend.n_years} years). {reading}"
        ),
    }


def mann_kendall_insight(result: MannKendallResult, label: str, unit: str, min_years: int) -> dict:
    base = {"id": "mann_kendall", "category": "trend", "severity": "info"}
    if result.status != "ok":
        return {
            **base,
            "text": (
                f"No Mann-Kendall test is reported for {label}: only {result.n_years} complete "
                f"year(s) are available and at least {min_years} are required."
            ),
        }
    if result.p_value < 0.05:
        reading = (
            f"The p-value is below 0.05, which is consistent with a monotonic {result.direction} "
            "trend. The test assumes independent years and is not corrected for autocorrelation, "
            "and it says nothing about cause."
        )
    else:
        reading = (
            "The p-value is above 0.05, so this test does not establish a monotonic trend in "
            "either direction."
        )
    return {
        **base,
        "text": (
            f"Mann-Kendall test on {label}: Kendall's tau {_signed(result.kendall_tau, 2)}, "
            f"two-sided p = {result.p_value:.3f} ({result.n_years} years); Theil-Sen slope "
            f"{_signed(result.sen_slope_per_decade, 2)} {unit} per decade. {reading}"
        ),
    }


def comparison_insight(comparison: PeriodComparison) -> dict:
    base = {"id": "period_comparison", "category": "comparison", "severity": "info"}
    if comparison.status == "insufficient_data":
        return {
            **base,
            "text": (
                "No early versus late period comparison is shown: it needs two non-overlapping "
                "periods of at least 5 complete years each."
            ),
        }
    early = f"{comparison.early_start}-{comparison.early_end}"
    late = f"{comparison.late_start}-{comparison.late_end}"
    lead = (
        f"Mean heatwave days per year were {comparison.early_mean:.1f} in {early} and "
        f"{comparison.late_mean:.1f} in {late}, a change of "
        f"{_signed(comparison.absolute_change)} days per year"
    )
    if comparison.status == "zero_baseline":
        return {
            **base,
            "text": (
                f"{lead}. A percentage change is not given because the earlier period had no "
                "heatwave days, which makes a percentage undefined."
            ),
        }
    return {**base, "text": f"{lead} ({_signed(comparison.percent_change, 0)}%)."}


def summary_insight(total_events: int, total_days: int, n_years: int, years_with_events: int) -> dict:
    if total_events == 0:
        text = (
            "No heatwave events were detected in the selected period under this definition. "
            "This does not mean no hot days occurred, only that no run of 3 or more consecutive "
            "days exceeded the threshold."
        )
    else:
        text = (
            f"{total_events} heatwave event(s) covering {total_days} day(s) were detected; "
            f"{years_with_events} of {n_years} years had at least one event."
        )
    return {"id": "summary", "category": "summary", "severity": "info", "text": text}


def caveat_insights(
    overlaps_baseline: bool, baseline_label: str, boundary_events: int, percentile: float
) -> list[dict]:
    caveats = [
        {
            "id": "caveat_attribution",
            "category": "caveat",
            "severity": "info",
            "text": (
                "These results describe one reanalysis grid cell. They do not establish a cause "
                "for any change and should not be read as a city-wide or regional average."
            ),
        }
    ]
    if overlaps_baseline:
        caveats.append(
            {
                "id": "caveat_baseline_overlap",
                "category": "caveat",
                "severity": "info",
                "text": (
                    f"The selected period overlaps the {baseline_label} baseline. By construction "
                    f"about {100 - percentile:.0f}% of baseline days exceed the threshold, so counts "
                    "inside the baseline years are partly fixed by the definition itself."
                ),
            }
        )
    if boundary_events:
        caveats.append(
            {
                "id": "caveat_boundary",
                "category": "caveat",
                "severity": "warning",
                "text": (
                    f"{boundary_events} event(s) touch the first or last day of the selected period "
                    "and may continue outside it; their duration is a lower bound."
                ),
            }
        )
    return caveats
