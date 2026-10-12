import type { ReactNode } from "react";
import type { AnnualPoint } from "../api/types";
import { formatNumber, formatPercent, formatTemp } from "../lib/format";
import { fieldClass } from "./formStyles";

interface Props {
  data: AnnualPoint[];
  selectedYear: number | null;
  onSelectYear: (year: number | null) => void;
}

/** Keyboard-accessible way to inspect one year; charts set the same selection on click. */
export function YearInspector({ data, selectedYear, onSelectYear }: Props) {
  const point = data.find((entry) => entry.year === selectedYear) ?? null;

  return (
    <section className="rounded-lg border border-line bg-surface p-4" aria-labelledby="year-inspector-title">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 id="year-inspector-title" className="text-sm font-semibold text-ink">
            Inspect a year
          </h3>
          <p className="mt-0.5 text-xs text-ink-3">
            Choose a year here or click any chart. The event table filters to match.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label htmlFor="inspect-year" className="sr-only">
            Year to inspect
          </label>
          <select
            id="inspect-year"
            className={`${fieldClass} w-32`}
            value={selectedYear ?? ""}
            onChange={(event) => onSelectYear(event.target.value ? Number(event.target.value) : null)}
          >
            <option value="">All years</option>
            {data.map((entry) => (
              <option key={entry.year} value={entry.year}>
                {entry.year}
              </option>
            ))}
          </select>
          {selectedYear !== null && (
            <button
              type="button"
              className="h-9 rounded-md border border-line px-3 text-sm text-ink-2 hover:bg-page"
              onClick={() => onSelectYear(null)}
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {point && (
        <>
          <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3 lg:grid-cols-6">
            <Stat label="Events" value={formatNumber(point.event_count)} />
            <Stat label="Heatwave days" value={formatNumber(point.heatwave_days)} />
            <Stat
              label="Longest event"
              value={point.longest_event_days ? `${point.longest_event_days} days` : "–"}
            />
            <Stat
              label="Mean intensity"
              value={
                point.mean_event_intensity_c === null
                  ? "–"
                  : `+${formatNumber(point.mean_event_intensity_c, 2)} °C`
              }
            />
            <Stat label="Peak temperature" value={formatTemp(point.peak_temperature_c)} />
            <Stat
              label="Data completeness"
              value={formatPercent(point.completeness)}
              note={`${point.valid_days} of ${point.expected_days} days`}
            />
          </dl>
          {!point.is_complete && (
            <p className="mt-3 rounded-md border border-warn-line bg-warn-bg px-3 py-2 text-xs text-warn-ink">
              {point.year} has less than 95% valid daily data. Its counts are lower bounds and it is
              excluded from the trend and period comparison.
            </p>
          )}
        </>
      )}

      <details className="mt-4">
        <summary className="cursor-pointer text-xs font-medium text-accent">
          Annual data table ({data.length} years)
        </summary>
        <div className="mt-2 max-h-72 overflow-auto rounded-md border border-line-soft">
          <table className="tabular w-full min-w-[36rem] text-left text-xs">
            <thead className="sticky top-0 bg-page text-ink-2">
              <tr>
                <Th>Year</Th>
                <Th right>Events</Th>
                <Th right>Heatwave days</Th>
                <Th right>Longest (days)</Th>
                <Th right>Mean intensity (°C)</Th>
                <Th right>5-yr avg days</Th>
                <Th right>Completeness</Th>
              </tr>
            </thead>
            <tbody>
              {data.map((entry) => (
                <tr
                  key={entry.year}
                  className={
                    "border-t border-line-soft " + (entry.year === selectedYear ? "bg-accent-soft" : "")
                  }
                >
                  <td className="px-3 py-1.5 font-medium text-ink">{entry.year}</td>
                  <Td>{entry.event_count}</Td>
                  <Td>{entry.heatwave_days}</Td>
                  <Td>{entry.longest_event_days || "–"}</Td>
                  <Td>{formatNumber(entry.mean_event_intensity_c, 2)}</Td>
                  <Td>{formatNumber(entry.heatwave_days_rolling_avg_5y, 1)}</Td>
                  <Td>{formatPercent(entry.completeness)}</Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div>
      <dt className="text-xs text-ink-3">{label}</dt>
      <dd className="mt-0.5 text-lg font-semibold text-ink">{value}</dd>
      {note && <dd className="text-xs text-ink-3">{note}</dd>}
    </div>
  );
}

function Th({ children, right }: { children: ReactNode; right?: boolean }) {
  return (
    <th scope="col" className={"px-3 py-2 font-medium " + (right ? "text-right" : "")}>
      {children}
    </th>
  );
}

function Td({ children }: { children: ReactNode }) {
  return <td className="px-3 py-1.5 text-right text-ink-2">{children}</td>;
}
