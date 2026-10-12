import type { ReactNode } from "react";
import type { AnnualPoint } from "../api/types";
import { formatPercent } from "../lib/format";

// Chart colours. Orange and red carry heat data; blue is the smoothed trend line.
export const CHART_COLORS = {
  heat: "#eb6834",
  heatSelected: "#b8431a",
  heatRed: "#e34948",
  heatRedSelected: "#a82a29",
  trend: "#2a78d6",
  grid: "#e6e8e6",
  axis: "#c3c8c5",
  tick: "#6b767d",
};

export const AXIS_TICK = { fill: CHART_COLORS.tick, fontSize: 11 };
export const CHART_MARGIN = { top: 8, right: 12, bottom: 4, left: 0 };
/** Bars for years below the completeness requirement are drawn faded. */
export const INCOMPLETE_OPACITY = 0.4;

interface ChartCardProps {
  title: string;
  subtitle: string;
  /** Text alternative read by screen readers in place of the SVG. */
  description: string;
  controls?: ReactNode;
  footnote?: ReactNode;
  children: ReactNode;
}

export function ChartCard({ title, subtitle, description, controls, footnote, children }: ChartCardProps) {
  return (
    <section className="rounded-lg border border-line bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div>
          <h3 className="text-sm font-semibold text-ink">{title}</h3>
          <p className="mt-0.5 text-xs text-ink-3">{subtitle}</p>
        </div>
        {controls}
      </div>
      <div role="img" aria-label={description} className="mt-3 h-60 w-full cursor-pointer">
        {children}
      </div>
      {footnote && <p className="mt-2 text-xs text-ink-3">{footnote}</p>}
    </section>
  );
}

interface TooltipRow {
  label: string;
  value: string;
  color?: string;
}

interface YearTooltipProps {
  active?: boolean;
  payload?: { payload: AnnualPoint }[];
  rows: (point: AnnualPoint) => TooltipRow[];
}

/** Shared tooltip: the year, the chart's values, and a completeness note when relevant. */
export function YearTooltip({ active, payload, rows }: YearTooltipProps) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return (
    <div className="rounded-md border border-line bg-surface px-3 py-2 text-xs shadow-md">
      <p className="font-semibold text-ink">{point.year}</p>
      <ul className="mt-1 space-y-0.5">
        {rows(point).map((row) => (
          <li key={row.label} className="flex items-center gap-2 text-ink-2">
            {row.color && (
              <span
                aria-hidden="true"
                className="inline-block h-2 w-2 rounded-full"
                style={{ background: row.color }}
              />
            )}
            <span>{row.label}</span>
            <span className="tabular ml-auto pl-3 font-medium text-ink">{row.value}</span>
          </li>
        ))}
      </ul>
      {!point.is_complete && (
        <p className="mt-1.5 max-w-52 text-warn-ink">
          Only {formatPercent(point.completeness)} of days are valid; counts are lower bounds.
        </p>
      )}
      <p className="mt-1.5 text-ink-3">Click to inspect this year</p>
    </div>
  );
}

/** Recharts passes the hovered category label to chart-level click handlers. */
export function yearFromChartClick(state: { activeLabel?: string | number } | null): number | null {
  const year = Number(state?.activeLabel);
  return Number.isInteger(year) && year > 0 ? year : null;
}

interface SegmentedProps<T extends string> {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}

export function Segmented<T extends string>({ label, value, options, onChange }: SegmentedProps<T>) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-md border border-line p-0.5">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={option.value === value}
          onClick={() => onChange(option.value)}
          className={
            "rounded px-2.5 py-1 text-xs font-medium " +
            (option.value === value ? "bg-accent text-white" : "text-ink-2 hover:bg-page")
          }
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
