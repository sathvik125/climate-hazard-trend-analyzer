import { useEffect, useMemo, useState } from "react";
import type { HeatwaveEvent } from "../api/types";
import { formatDate, formatNumber, pluralize } from "../lib/format";

type SortKey = "start_date" | "duration_days" | "peak_temperature_c" | "mean_exceedance_c";

const COLUMNS: { key: SortKey | null; label: string; numeric: boolean }[] = [
  { key: "start_date", label: "Start date", numeric: false },
  { key: null, label: "End date", numeric: false },
  { key: "duration_days", label: "Duration (days)", numeric: true },
  { key: "peak_temperature_c", label: "Peak temperature (°C)", numeric: true },
  { key: "mean_exceedance_c", label: "Exceedance intensity (°C)", numeric: true },
];

const PAGE_SIZE = 10;

interface Props {
  events: HeatwaveEvent[];
  thresholdC: number;
  selectedYear: number | null;
  onClearYear: () => void;
  exportLinks?: { events: string; annual: string };
}

export function EventHistoryTable({ events, thresholdC, selectedYear, onClearYear, exportLinks }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("start_date");
  const [descending, setDescending] = useState(false);
  const [page, setPage] = useState(0);

  const rows = useMemo(() => {
    // An event belongs to a year if any of its days fall in it, so an event that
    // crosses 31 December is listed under both years.
    const filtered =
      selectedYear === null
        ? events
        : events.filter(
            (event) =>
              Number(event.start_date.slice(0, 4)) <= selectedYear &&
              Number(event.end_date.slice(0, 4)) >= selectedYear,
          );
    const sorted = [...filtered].sort((a, b) => {
      const left = a[sortKey];
      const right = b[sortKey];
      return left < right ? -1 : left > right ? 1 : a.start_date.localeCompare(b.start_date);
    });
    return descending ? sorted.reverse() : sorted;
  }, [events, selectedYear, sortKey, descending]);

  useEffect(() => setPage(0), [selectedYear, sortKey, descending, events]);

  const pageCount = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const visible = rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setDescending((current) => !current);
    } else {
      setSortKey(key);
      setDescending(key !== "start_date"); // numeric columns start with the largest first
    }
  }

  return (
    <section className="rounded-lg border border-line bg-surface" aria-labelledby="events-title">
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 pt-4">
        <div>
          <h3 id="events-title" className="text-sm font-semibold text-ink">
            Event history
          </h3>
          <p className="mt-0.5 text-xs text-ink-3">
            {rows.length} {pluralize(rows.length, "event")}
            {selectedYear !== null ? ` with days in ${selectedYear}` : " in the selected period"}.
            Exceedance intensity is the mean °C above the {formatNumber(thresholdC, 1)} °C threshold.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {selectedYear !== null && (
            <button
              type="button"
              onClick={onClearYear}
              className="h-8 rounded-md border border-line px-3 text-xs text-ink-2 hover:bg-page"
            >
              Show all years
            </button>
          )}
          {exportLinks && (
            <>
              <ExportLink href={exportLinks.events} label="Events CSV" />
              <ExportLink href={exportLinks.annual} label="Annual CSV" />
            </>
          )}
        </div>
      </div>

      {rows.length === 0 ? (
        <p className="px-4 py-8 text-center text-sm text-ink-2">
          {selectedYear !== null
            ? `No heatwave events have days in ${selectedYear}.`
            : "No heatwave events were detected in the selected period."}
        </p>
      ) : (
        <>
          <div className="mt-3 overflow-x-auto">
            <table className="tabular w-full min-w-[40rem] text-left text-sm">
              <thead className="border-y border-line bg-page text-xs text-ink-2">
                <tr>
                  {COLUMNS.map((column) => (
                    <th
                      key={column.label}
                      scope="col"
                      className={"px-4 py-2 font-medium " + (column.numeric ? "text-right" : "")}
                      aria-sort={
                        column.key === sortKey ? (descending ? "descending" : "ascending") : undefined
                      }
                    >
                      {column.key ? (
                        <button
                          type="button"
                          onClick={() => toggleSort(column.key as SortKey)}
                          className="inline-flex items-center gap-1 rounded hover:text-ink"
                        >
                          {column.label}
                          <span aria-hidden="true" className="w-2 text-ink-3">
                            {column.key === sortKey ? (descending ? "↓" : "↑") : ""}
                          </span>
                        </button>
                      ) : (
                        column.label
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visible.map((event) => (
                  <tr key={event.id} className="border-b border-line-soft last:border-b-0">
                    <td className="px-4 py-2 text-ink">{formatDate(event.start_date)}</td>
                    <td className="px-4 py-2 text-ink">
                      {formatDate(event.end_date)}
                      {event.touches_period_boundary && (
                        <span
                          className="ml-2 rounded border border-warn-line bg-warn-bg px-1.5 py-0.5 text-[11px] text-warn-ink"
                          title="This event touches the first or last day of the selected period and may continue outside it."
                        >
                          period edge
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-right text-ink">{event.duration_days}</td>
                    <td className="px-4 py-2 text-right text-ink">
                      {formatNumber(event.peak_temperature_c, 1)}
                    </td>
                    <td className="px-4 py-2 text-right text-ink">
                      +{formatNumber(event.mean_exceedance_c, 2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {pageCount > 1 && (
            <div className="flex items-center justify-between border-t border-line px-4 py-2 text-xs text-ink-2">
              <span>
                Page {page + 1} of {pageCount}
              </span>
              <div className="flex gap-2">
                <PageButton label="Previous" disabled={page === 0} onClick={() => setPage(page - 1)} />
                <PageButton
                  label="Next"
                  disabled={page >= pageCount - 1}
                  onClick={() => setPage(page + 1)}
                />
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}

function ExportLink({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      download
      className="inline-flex h-8 items-center rounded-md border border-line px-3 text-xs font-medium text-accent hover:bg-accent-soft"
    >
      {label}
    </a>
  );
}

function PageButton({ label, disabled, onClick }: { label: string; disabled: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="h-8 rounded-md border border-line px-3 text-ink-2 hover:bg-page disabled:cursor-not-allowed disabled:opacity-40"
    >
      {label}
    </button>
  );
}
