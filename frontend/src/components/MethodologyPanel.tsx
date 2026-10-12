import type { AnalysisResponse } from "../api/types";
import { formatCoordinate, formatNumber } from "../lib/format";

interface Props {
  analysis: AnalysisResponse;
}

export function MethodologyPanel({ analysis }: Props) {
  const { methodology, source_metadata: source, location, baseline_period: baseline } = analysis;
  const [lower, upper] = analysis.data_quality.physical_bounds_c;

  return (
    <section className="rounded-lg border border-line bg-surface p-4" aria-labelledby="methodology-title">
      <h3 id="methodology-title" className="text-sm font-semibold text-ink">
        Data source and methodology
      </h3>

      <div className="mt-3 grid gap-6 lg:grid-cols-2">
        <div>
          <h4 className="text-xs font-semibold text-ink-2">Source</h4>
          <dl className="mt-2 space-y-1.5 text-xs">
            <Row label="Provider" value={source.provider} />
            <Row label="Model" value={`${source.model_label} (${source.model})`} />
            <Row label="Grid spacing" value={source.spatial_resolution} />
            <Row label="Variable" value={source.variable} />
            <Row label="Unit" value={source.unit} />
            <Row label="Day boundaries" value={source.timezone_mode} />
            <Row
              label="Requested point"
              value={formatCoordinate(location.latitude, location.longitude)}
            />
            <Row
              label="Matched grid cell"
              value={
                location.grid_latitude !== null && location.grid_longitude !== null
                  ? `${formatCoordinate(location.grid_latitude, location.grid_longitude)}${
                      location.elevation_m !== null ? `, ${formatNumber(location.elevation_m)} m elevation` : ""
                    }`
                  : "Not reported"
              }
            />
            <Row label="Timezone" value={location.timezone ?? "Not reported"} />
            <Row label="Algorithm version" value={methodology.algorithm_version} />
          </dl>
          <p className="mt-3 text-xs text-ink-3">{source.attribution}</p>
        </div>

        <div className="space-y-3 text-xs leading-relaxed text-ink-2">
          <Block title="Heatwave definition" text={methodology.definition} />
          <Block
            title={`Threshold: ${formatNumber(analysis.threshold_c, 2)} °C (baseline ${baseline.start_year}–${baseline.end_year})`}
            text={methodology.threshold_method}
          />
          <Block title="Intensity" text={methodology.intensity_definition} />
          <Block title="Trend" text={methodology.trend_method} />
          <Block
            title="Missing and implausible data"
            text={`${methodology.missing_data_policy} Values outside ${lower} to ${upper} °C are treated as data faults, recorded and excluded.`}
          />
          <div>
            <h4 className="font-semibold text-ink-2">Counting rules</h4>
            <ul className="mt-1 list-disc space-y-0.5 pl-5">
              {methodology.attribution_rules.map((rule) => (
                <li key={rule}>{rule}</li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      <h4 className="mt-5 text-xs font-semibold text-ink-2">Limitations</h4>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-xs leading-relaxed text-ink-2">
        {methodology.limitations.map((limitation) => (
          <li key={limitation}>{limitation}</li>
        ))}
      </ul>
    </section>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-3">
      <dt className="w-32 shrink-0 text-ink-3">{label}</dt>
      <dd className="text-ink">{value}</dd>
    </div>
  );
}

function Block({ title, text }: { title: string; text: string }) {
  return (
    <div>
      <h4 className="font-semibold text-ink-2">{title}</h4>
      <p className="mt-0.5">{text}</p>
    </div>
  );
}
