"""CSV export of an analysis result."""

from __future__ import annotations

from typing import Any

import pandas as pd

EVENT_COLUMNS = [
    "id",
    "start_date",
    "end_date",
    "duration_days",
    "peak_temperature_c",
    "peak_date",
    "mean_temperature_c",
    "mean_exceedance_c",
    "max_exceedance_c",
    "touches_period_boundary",
]
ANNUAL_COLUMNS = [
    "year",
    "event_count",
    "heatwave_days",
    "longest_event_days",
    "mean_event_intensity_c",
    "max_event_intensity_c",
    "peak_temperature_c",
    "heatwave_days_rolling_avg_5y",
    "valid_days",
    "expected_days",
    "completeness",
    "is_complete",
]


def analysis_to_csv(result: dict[str, Any], dataset: str) -> str:
    """Render the events or annual table as CSV, preceded by provenance comment lines."""
    location = result["location"]
    period, baseline = result["selected_period"], result["baseline_period"]
    source = result["source_metadata"]
    header = [
        f"# Climate Hazard Trend Analyzer - {dataset} export",
        f"# point location: latitude {location['latitude']}, longitude {location['longitude']}",
        f"# selected period: {period['start_year']}-{period['end_year']}",
        f"# threshold_c: {result['threshold_c']} (95th percentile, baseline "
        f"{baseline['start_year']}-{baseline['end_year']})",
        f"# source: {source['provider']}, model {source['model']} ({source['spatial_resolution']})",
        f"# algorithm: {result['methodology']['algorithm_version']}",
    ]
    rows, columns = (
        (result["events"], EVENT_COLUMNS) if dataset == "events" else (result["annual_series"], ANNUAL_COLUMNS)
    )
    table = pd.DataFrame(rows, columns=columns).to_csv(index=False, lineterminator="\n")
    return "\n".join(header) + "\n" + table
