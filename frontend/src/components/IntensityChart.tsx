import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { AnnualPoint } from "../api/types";
import { formatNumber, formatTemp } from "../lib/format";
import {
  AXIS_TICK,
  CHART_COLORS,
  CHART_MARGIN,
  ChartCard,
  INCOMPLETE_OPACITY,
  Segmented,
  YearTooltip,
  yearFromChartClick,
} from "./ChartCard";

type Measure = "mean" | "max";

const MEASURES = {
  mean: {
    key: "mean_event_intensity_c",
    label: "Mean intensity",
    subtitle: "Mean exceedance above the threshold, averaged over events starting in each year",
  },
  max: {
    key: "max_event_intensity_c",
    label: "Maximum intensity",
    subtitle: "Largest single-day exceedance above the threshold in events starting in each year",
  },
} as const;

interface Props {
  data: AnnualPoint[];
  thresholdC: number;
  selectedYear: number | null;
  onSelectYear: (year: number) => void;
}

export function IntensityChart({ data, thresholdC, selectedYear, onSelectYear }: Props) {
  const [measure, setMeasure] = useState<Measure>("mean");
  const config = MEASURES[measure];
  const yearsWithEvents = data.filter((point) => point.event_count > 0).length;

  return (
    <ChartCard
      title="Annual event intensity"
      subtitle={config.subtitle}
      description={`Bar chart of ${config.label.toLowerCase()} in degrees Celsius above the ${thresholdC} degree threshold, for the ${yearsWithEvents} years with at least one event. The annual data table below lists every value.`}
      controls={
        <Segmented
          label="Intensity measure"
          value={measure}
          onChange={setMeasure}
          options={[
            { value: "mean", label: "Mean" },
            { value: "max", label: "Maximum" },
          ]}
        />
      }
      footnote="Years without a bar had no heatwave event, so no intensity is defined."
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
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
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={false}
            width={44}
            tickFormatter={(value: number) => formatNumber(value, 1)}
            label={{ value: "°C above threshold", angle: -90, position: "insideLeft", offset: 14, style: { ...AXIS_TICK, textAnchor: "middle" } }}
          />
          <Tooltip
            cursor={{ fill: "#10191d", fillOpacity: 0.05 }}
            content={
              <YearTooltip
                rows={(point) => [
                  {
                    label: config.label,
                    value: point[config.key] === null ? "No events" : `+${formatNumber(point[config.key], 2)} °C`,
                    color: CHART_COLORS.heatRed,
                  },
                  { label: "Peak temperature", value: formatTemp(point.peak_temperature_c) },
                ]}
              />
            }
          />
          <Bar dataKey={config.key} name={config.label} maxBarSize={24} radius={[4, 4, 0, 0]} isAnimationActive={false}>
            {data.map((point) => (
              <Cell
                key={point.year}
                fill={point.year === selectedYear ? CHART_COLORS.heatRedSelected : CHART_COLORS.heatRed}
                fillOpacity={point.is_complete ? 1 : INCOMPLETE_OPACITY}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
