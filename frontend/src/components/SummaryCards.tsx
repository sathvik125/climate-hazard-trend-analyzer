import type { AnalysisResponse } from "../api/types";
import { formatDate, formatNumber, formatSigned, pluralize } from "../lib/format";

interface Props {
  analysis: AnalysisResponse;
}

export function SummaryCards({ analysis }: Props) {
  const { overall_summary: summary, selected_period: period } = analysis;
  const span = `${period.start_year}–${period.end_year}`;

  return (
    <section aria-label="Summary metrics" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Card
        label="Total heatwave events"
        value={formatNumber(summary.total_events)}
        detail={`${summary.years_with_events} of ${summary.years_analyzed} years had an event (${span})`}
      />
      <Card
        label="Total heatwave days"
        value={formatNumber(summary.total_heatwave_days)}
        detail={
          summary.years_analyzed > 0
            ? `${formatNumber(summary.total_heatwave_days / summary.years_analyzed, 1)} days per year on average`
            : ""
        }
      />
      <Card
        label="Longest heatwave"
        value={summary.longest_event_days > 0 ? formatNumber(summary.longest_event_days) : "–"}
        unit={summary.longest_event_days > 0 ? pluralize(summary.longest_event_days, "day") : undefined}
        detail={
          summary.longest_event_start
            ? `${formatDate(summary.longest_event_start)} to ${formatDate(summary.longest_event_end)}`
            : "No events detected"
        }
      />
      <Card
        label="Average intensity"
        value={formatSigned(summary.average_intensity_c, 2)}
        unit={summary.average_intensity_c === null ? undefined : "°C"}
        detail={
          summary.average_intensity_c === null
            ? "No events detected"
            : `Mean exceedance above the ${formatNumber(analysis.threshold_c, 1)} °C threshold`
        }
      />
    </section>
  );
}

interface CardProps {
  label: string;
  value: string;
  unit?: string;
  detail: string;
}

function Card({ label, value, unit, detail }: CardProps) {
  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <p className="text-xs font-medium text-ink-2">{label}</p>
      <p className="mt-1.5 text-3xl font-semibold leading-none text-ink">
        {value}
        {unit && <span className="text-base font-medium text-ink-2"> {unit}</span>}
      </p>
      <p className="mt-2 text-xs leading-snug text-ink-3">{detail}</p>
    </div>
  );
}
