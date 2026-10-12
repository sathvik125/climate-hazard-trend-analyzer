import { useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { AnnualPoint } from "../api/types";
import { formatNumber } from "../lib/format";
import {
  AXIS_TICK,
  CHART_COLORS,
  CHART_MARGIN,
  ChartCard,
  YearTooltip,
  yearFromChartClick,
} from "./ChartCard";

interface Props {
  data: AnnualPoint[];
  selectedYear: number | null;
  onSelectYear: (year: number) => void;
}

export function DurationChart({ data, selectedYear, onSelectYear }: Props) {
  const [showRolling, setShowRolling] = useState(true);
  // The backend only returns a rolling value once five complete years exist.
  const rollingAvailable = data.some((point) => point.heatwave_days_rolling_avg_5y !== null);
  const rollingVisible = showRolling && rollingAvailable;

  return (
    <ChartCard
      title="Annual heatwave days"
      subtitle="Days inside heatwave events, counted in the calendar year they fall in"
      description={`Line chart of heatwave days per year from ${data[0]?.year} to ${data[data.length - 1]?.year}${rollingVisible ? ", with a five year trailing average" : ""}. The annual data table below lists every value.`}
      controls={
        <label className="flex items-center gap-2 text-xs text-ink-2">
          <input
            type="checkbox"
            className="h-3.5 w-3.5 accent-accent"
            checked={rollingVisible}
            disabled={!rollingAvailable}
            onChange={(event) => setShowRolling(event.target.checked)}
          />
          5-year trailing average
        </label>
      }
      footnote={
        rollingAvailable
          ? undefined
          : "A 5-year trailing average needs at least five consecutive complete years."
      }
    >
      <div className="flex h-full flex-col">
        <ul className="mb-1 flex gap-4 text-xs text-ink-2">
          <LegendItem color={CHART_COLORS.heat} label="Heatwave days" />
          {rollingVisible && <LegendItem color={CHART_COLORS.trend} label="5-year trailing average" />}
        </ul>
        <div className="min-h-0 flex-1">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={data}
              margin={CHART_MARGIN}
              onClick={(state) => {
                const year = yearFromChartClick(state);
                if (year !== null) onSelectYear(year);
              }}
            >
              <CartesianGrid vertical={false} stroke={CHART_COLORS.grid} />
              <XAxis
                dataKey="year"
                tick={AXIS_TICK}
                tickLine={false}
                axisLine={{ stroke: CHART_COLORS.axis }}
                minTickGap={18}
              />
              <YAxis
                allowDecimals={false}
                tick={AXIS_TICK}
                tickLine={false}
                axisLine={false}
                width={44}
                label={{ value: "Days per year", angle: -90, position: "insideLeft", offset: 14, style: { ...AXIS_TICK, textAnchor: "middle" } }}
              />
              <Tooltip
                cursor={{ stroke: CHART_COLORS.axis }}
                content={
                  <YearTooltip
                    rows={(point) => [
                      { label: "Heatwave days", value: String(point.heatwave_days), color: CHART_COLORS.heat },
                      ...(rollingVisible
                        ? [
                            {
                              label: "5-year average",
                              value: formatNumber(point.heatwave_days_rolling_avg_5y, 1),
                              color: CHART_COLORS.trend,
                            },
                          ]
                        : []),
                    ]}
                  />
                }
              />
              {selectedYear !== null && (
                <ReferenceLine x={selectedYear} stroke={CHART_COLORS.tick} strokeWidth={1} />
              )}
              <Line
                dataKey="heatwave_days"
                name="Heatwave days"
                stroke={CHART_COLORS.heat}
                strokeWidth={2}
                dot={{ r: 2.5, fill: CHART_COLORS.heat, strokeWidth: 0 }}
                activeDot={{ r: 5, stroke: "#ffffff", strokeWidth: 2 }}
                isAnimationActive={false}
              />
              {rollingVisible && (
                <Line
                  dataKey="heatwave_days_rolling_avg_5y"
                  name="5-year trailing average"
                  stroke={CHART_COLORS.trend}
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4, stroke: "#ffffff", strokeWidth: 2 }}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              )}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </ChartCard>
  );
}

function LegendItem({ color, label }: { color: string; label: string }) {
  return (
    <li className="flex items-center gap-1.5">
      <span aria-hidden="true" className="inline-block h-0.5 w-4 rounded" style={{ background: color }} />
      {label}
    </li>
  );
}
