// Mirrors backend/app/schemas.py. Keep the two in sync.

export type Hazard = "heatwave";

export interface AnalysisParams {
  latitude: number;
  longitude: number;
  start_year: number;
  end_year: number;
  hazard: Hazard;
}

export interface LocationInfo {
  kind: "point";
  name: string | null;
  latitude: number;
  longitude: number;
  grid_latitude: number | null;
  grid_longitude: number | null;
  elevation_m: number | null;
  timezone: string | null;
}

export interface Period {
  start_year: number;
  end_year: number;
  start_date: string;
  end_date: string;
}

export interface AnnualPoint {
  year: number;
  event_count: number;
  heatwave_days: number;
  longest_event_days: number;
  mean_event_intensity_c: number | null;
  max_event_intensity_c: number | null;
  peak_temperature_c: number | null;
  heatwave_days_rolling_avg_5y: number | null;
  valid_days: number;
  expected_days: number;
  completeness: number;
  is_complete: boolean;
}

export interface HeatwaveEvent {
  id: string;
  start_date: string;
  end_date: string;
  start_year: number;
  duration_days: number;
  peak_temperature_c: number;
  peak_date: string;
  mean_temperature_c: number;
  mean_exceedance_c: number;
  max_exceedance_c: number;
  touches_period_boundary: boolean;
}

export interface OverallSummary {
  total_events: number;
  total_heatwave_days: number;
  longest_event_days: number;
  longest_event_start: string | null;
  longest_event_end: string | null;
  average_intensity_c: number | null;
  highest_peak_temperature_c: number | null;
  highest_peak_date: string | null;
  years_analyzed: number;
  years_with_events: number;
}

export interface Trend {
  status: "ok" | "insufficient_data";
  unit: string;
  n_years: number;
  slope_per_decade: number | null;
  slope_ci95_low_per_decade: number | null;
  slope_ci95_high_per_decade: number | null;
  r_squared: number | null;
  p_value: number | null;
  first_year: number | null;
  last_year: number | null;
}

export interface MannKendall {
  status: "ok" | "insufficient_data";
  unit: string;
  n_years: number;
  s_statistic: number | null;
  kendall_tau: number | null;
  z_score: number | null;
  p_value: number | null;
  direction: "increasing" | "decreasing" | "none" | null;
  sen_slope_per_decade: number | null;
  sen_slope_ci95_low_per_decade: number | null;
  sen_slope_ci95_high_per_decade: number | null;
}

export interface PeriodComparison {
  status: "ok" | "zero_baseline" | "insufficient_data";
  metric: string;
  period_years: number;
  early_start: number | null;
  early_end: number | null;
  late_start: number | null;
  late_end: number | null;
  early_mean: number | null;
  late_mean: number | null;
  absolute_change: number | null;
  percent_change: number | null;
}

export interface TrendSection {
  method: string;
  min_years_required: number;
  years_used: number;
  years_excluded: number[];
  events_per_decade: Trend;
  heatwave_days_per_decade: Trend;
  events_mann_kendall: MannKendall;
  heatwave_days_mann_kendall: MannKendall;
  period_comparison: PeriodComparison;
}

export interface Insight {
  id: string;
  category: "coverage" | "trend" | "comparison" | "summary" | "caveat";
  severity: "info" | "warning";
  text: string;
}

export interface DataQuality {
  coverage_status: "complete" | "partial";
  min_completeness_required: number;
  overall_completeness: number;
  expected_days: number;
  valid_days: number;
  missing_days: number;
  implausible_days: number;
  incomplete_years: number[];
  baseline_completeness: number;
  baseline_valid_days: number;
  baseline_expected_days: number;
  physical_bounds_c: [number, number];
  excluded_values: { date: string; temperature_max_c: number | null; reason: string }[];
  excluded_values_truncated: boolean;
  warnings: string[];
}

export interface Methodology {
  algorithm_version: string;
  definition: string;
  percentile: number;
  min_duration_days: number;
  threshold_method: string;
  attribution_rules: string[];
  intensity_definition: string;
  trend_method: string;
  missing_data_policy: string;
  limitations: string[];
}

export interface SourceMetadata {
  provider: string;
  api_url: string;
  model: string;
  model_label: string;
  spatial_resolution: string;
  variable: string;
  unit: string;
  timezone_mode: string;
  attribution: string;
}

export interface CacheStatus {
  status: "hit" | "miss";
  cache_key: string;
  created_at: string;
  expires_at: string;
  daily_records_reused: number;
  daily_records_fetched: number;
  upstream_requests: number;
}

export interface AnalysisResponse {
  location: LocationInfo;
  hazard: Hazard;
  selected_period: Period;
  baseline_period: Period;
  threshold_c: number;
  annual_series: AnnualPoint[];
  events: HeatwaveEvent[];
  overall_summary: OverallSummary;
  trend: TrendSection;
  generated_insights: Insight[];
  data_quality: DataQuality;
  methodology: Methodology;
  source_metadata: SourceMetadata;
  cache_status: CacheStatus;
}

export interface PresetLocation {
  id: string;
  name: string;
  country: string;
  latitude: number;
  longitude: number;
}

export interface LocationsResponse {
  locations: PresetLocation[];
  note: string;
  min_year: number;
  max_year: number;
  max_year_range: number;
  baseline_start_year: number;
  baseline_end_year: number;
  hazards: string[];
}
