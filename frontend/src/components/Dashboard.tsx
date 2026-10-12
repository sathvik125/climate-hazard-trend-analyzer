import { type FormEvent, useEffect, useState } from "react";
import { csvExportUrl } from "../api/client";
import type { AnalysisParams, AnalysisResponse, LocationsResponse } from "../api/types";
import { useAnalysis, useLocations } from "../hooks/useAnalysis";
import { formatCoordinate, formatDate, formatNumber } from "../lib/format";
import { type FormState, validateForm } from "../lib/validation";
import { DateRangeSelector } from "./DateRangeSelector";
import { DurationChart } from "./DurationChart";
import { ErrorState } from "./ErrorState";
import { EventHistoryTable } from "./EventHistoryTable";
import { FrequencyChart } from "./FrequencyChart";
import { HazardSelector } from "./HazardSelector";
import { InsightsPanel } from "./InsightsPanel";
import { IntensityChart } from "./IntensityChart";
import { LoadingState } from "./LoadingState";
import { LocationSelector } from "./LocationSelector";
import { type MapPoint, MapPicker } from "./MapPicker";
import { MethodologyPanel } from "./MethodologyPanel";
import { SummaryCards } from "./SummaryCards";
import { YearInspector } from "./YearInspector";

const DEFAULT_START_YEAR = 1990;
const DEFAULT_END_YEAR = 2020;

function initialForm(config: LocationsResponse): FormState {
  return {
    mode: "preset",
    presetId: config.locations[0]?.id ?? "",
    latitude: "",
    longitude: "",
    startYear: Math.max(DEFAULT_START_YEAR, config.min_year),
    endYear: Math.min(DEFAULT_END_YEAR, config.max_year),
    hazard: "heatwave",
  };
}

/** The point the form currently describes, or null while custom coordinates are invalid. */
function selectedPoint(form: FormState, config: LocationsResponse): MapPoint | null {
  if (form.mode === "preset") {
    const preset = config.locations.find((location) => location.id === form.presetId);
    return preset ? { latitude: preset.latitude, longitude: preset.longitude } : null;
  }
  const latitude = Number(form.latitude);
  const longitude = Number(form.longitude);
  const valid =
    form.latitude.trim() !== "" &&
    form.longitude.trim() !== "" &&
    Number.isFinite(latitude) &&
    Number.isFinite(longitude) &&
    Math.abs(latitude) <= 90 &&
    Math.abs(longitude) <= 180;
  return valid ? { latitude, longitude } : null;
}

export function Dashboard() {
  const locations = useLocations();

  return (
    <div className="min-h-screen">
      <Header />
      <main className="mx-auto max-w-7xl space-y-4 px-4 py-5 sm:px-6">
        {locations.isPending && <LoadingState label="Connecting to the analysis service…" />}
        {locations.isError && (
          <ErrorState error={locations.error} onRetry={() => void locations.refetch()} />
        )}
        {locations.data && <Workspace config={locations.data} />}
      </main>
      <footer className="mx-auto max-w-7xl px-4 pb-8 pt-2 text-xs text-ink-3 sm:px-6">
        Weather data by Open-Meteo.com (CC BY 4.0), derived from ECMWF reanalysis. Point location
        analysis; not an official heat warning product.
      </footer>
    </div>
  );
}

function Header() {
  return (
    <header className="border-b border-line bg-surface">
      <div className="mx-auto flex max-w-7xl flex-wrap items-end justify-between gap-x-6 gap-y-2 px-4 py-4 sm:px-6">
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-ink">
            Climate Hazard Trend Analyzer
          </h1>
          <p className="mt-0.5 max-w-2xl text-sm text-ink-2">
            How heatwave frequency, duration and intensity have changed at a point location, from
            historical daily maximum temperature.
          </p>
        </div>
        <p className="text-xs text-ink-3">
          Source: Open-Meteo Historical Weather API · ECMWF reanalysis
        </p>
      </div>
    </header>
  );
}

function Workspace({ config }: { config: LocationsResponse }) {
  const [form, setForm] = useState<FormState>(() => initialForm(config));
  const [submitted, setSubmitted] = useState<AnalysisParams | null>(null);
  const [showErrors, setShowErrors] = useState(false);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);

  const { errors, params } = validateForm(form, config);
  const analysis = useAnalysis(submitted);

  // A year picked for one analysis may not exist in the next one.
  useEffect(() => setSelectedYear(null), [submitted]);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setShowErrors(true);
    if (!params) return;
    const unchanged = JSON.stringify(params) === JSON.stringify(submitted);
    setSubmitted(params);
    // Pressing Analyze again after a failure should retry the same request.
    if (unchanged && analysis.isError) void analysis.refetch();
  }

  const visibleErrors = showErrors ? errors : {};
  const matched = analysis.data?.location;
  const gridCell =
    matched && matched.grid_latitude !== null && matched.grid_longitude !== null
      ? { latitude: matched.grid_latitude, longitude: matched.grid_longitude }
      : null;

  return (
    <>
      <form
        onSubmit={handleSubmit}
        noValidate
        aria-label="Analysis filters"
        className="rounded-lg border border-line bg-surface p-4"
      >
        <div className="flex flex-wrap items-start gap-x-4 gap-y-3">
          <div className="min-w-56 flex-1">
            <LocationSelector
              locations={config.locations}
              form={form}
              errors={visibleErrors}
              onChange={(patch) => setForm((current) => ({ ...current, ...patch }))}
            />
          </div>
          <HazardSelector
            hazards={config.hazards}
            value={form.hazard}
            onChange={(hazard) => setForm((current) => ({ ...current, hazard }))}
          />
          <DateRangeSelector
            startYear={form.startYear}
            endYear={form.endYear}
            minYear={config.min_year}
            maxYear={config.max_year}
            error={visibleErrors.years}
            onChange={(patch) => setForm((current) => ({ ...current, ...patch }))}
          />
          <div>
            <span className="mb-1 block text-xs">&nbsp;</span>
            <button
              type="submit"
              disabled={analysis.isFetching}
              className="h-9 rounded-md bg-accent px-5 text-sm font-semibold text-white hover:bg-accent-strong disabled:cursor-wait disabled:opacity-60"
            >
              {analysis.isFetching ? "Analyzing…" : "Analyze"}
            </button>
          </div>
        </div>
        <div className="mt-4">
          <MapPicker
            locations={config.locations}
            selected={selectedPoint(form, config)}
            selectedPresetId={form.mode === "preset" ? form.presetId : null}
            gridCell={gridCell}
            onPickPreset={(presetId) =>
              setForm((current) => ({ ...current, mode: "preset", presetId }))
            }
            onPickPoint={(point) =>
              setForm((current) => ({
                ...current,
                mode: "custom",
                latitude: String(point.latitude),
                longitude: String(point.longitude),
              }))
            }
          />
        </div>
        <p className="mt-3 text-xs text-ink-3">
          {config.note} Threshold baseline is fixed at {config.baseline_start_year}–
          {config.baseline_end_year}. Full calendar years {config.min_year}–{config.max_year} are
          available.
        </p>
      </form>

      {submitted === null && <EmptyState />}
      {submitted !== null && analysis.isPending && (
        <LoadingState label="Retrieving daily temperatures and detecting heatwaves…" />
      )}
      {submitted !== null && analysis.isError && (
        <ErrorState error={analysis.error} onRetry={() => void analysis.refetch()} />
      )}
      {submitted !== null && analysis.data && (
        <Results
          analysis={analysis.data}
          params={submitted}
          selectedYear={selectedYear}
          onSelectYear={setSelectedYear}
        />
      )}
    </>
  );
}

function EmptyState() {
  return (
    <div className="rounded-lg border border-dashed border-line bg-surface px-6 py-12 text-center">
      <h2 className="text-sm font-semibold text-ink">No analysis yet</h2>
      <p className="mx-auto mt-1 max-w-md text-sm text-ink-2">
        Choose a location and a range of years, then select Analyze. Charts and metrics appear here
        once real data has been retrieved; nothing is shown before that.
      </p>
    </div>
  );
}

interface ResultsProps {
  analysis: AnalysisResponse;
  params: AnalysisParams;
  selectedYear: number | null;
  onSelectYear: (year: number | null) => void;
}

function Results({ analysis, params, selectedYear, onSelectYear }: ResultsProps) {
  const { location, selected_period: period, baseline_period: baseline, cache_status: cache } = analysis;
  const quality = analysis.data_quality;
  const title = location.name ?? `Custom point ${formatCoordinate(location.latitude, location.longitude)}`;

  return (
    <div className="space-y-4">
      <section aria-label="Analysis context" className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
        <div>
          <h2 className="text-base font-semibold text-ink">
            {title} · heatwaves {period.start_year}–{period.end_year}
          </h2>
          <p className="mt-0.5 text-xs text-ink-2">
            Point {formatCoordinate(location.latitude, location.longitude)} · {analysis.source_metadata.model_label}{" "}
            ({analysis.source_metadata.spatial_resolution}) · threshold{" "}
            <strong className="font-semibold text-ink">{formatNumber(analysis.threshold_c, 1)} °C</strong>{" "}
            (95th percentile, baseline {baseline.start_year}–{baseline.end_year})
          </p>
        </div>
        <p className="text-xs text-ink-3">
          {cache.status === "hit"
            ? `Served from database cache · computed ${formatDate(cache.created_at.slice(0, 10))}`
            : `Freshly computed · ${formatNumber(cache.daily_records_fetched)} days fetched, ${formatNumber(cache.daily_records_reused)} reused from database`}
        </p>
      </section>

      {quality.warnings.length > 0 && (
        <div role="status" className="rounded-lg border border-warn-line bg-warn-bg px-4 py-3">
          <h3 className="text-sm font-semibold text-warn-ink">
            Data quality warning: results are based on partial data
          </h3>
          <ul className="mt-1 list-disc pl-5 text-sm text-warn-ink">
            {quality.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}

      <SummaryCards analysis={analysis} />

      <div className="grid gap-4 lg:grid-cols-2">
        <FrequencyChart
          data={analysis.annual_series}
          selectedYear={selectedYear}
          onSelectYear={onSelectYear}
        />
        <DurationChart
          data={analysis.annual_series}
          selectedYear={selectedYear}
          onSelectYear={onSelectYear}
        />
      </div>
      <IntensityChart
        data={analysis.annual_series}
        thresholdC={analysis.threshold_c}
        selectedYear={selectedYear}
        onSelectYear={onSelectYear}
      />

      <YearInspector
        data={analysis.annual_series}
        selectedYear={selectedYear}
        onSelectYear={onSelectYear}
      />
      <EventHistoryTable
        events={analysis.events}
        thresholdC={analysis.threshold_c}
        selectedYear={selectedYear}
        onClearYear={() => onSelectYear(null)}
        exportLinks={{
          events: csvExportUrl(params, "events"),
          annual: csvExportUrl(params, "annual"),
        }}
      />
      <InsightsPanel analysis={analysis} />
      <MethodologyPanel analysis={analysis} />
    </div>
  );
}
