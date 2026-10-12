import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { AnnualPoint } from "../api/types";
import {
  AXIS_TICK,
  CHART_COLORS,
  CHART_MARGIN,
  ChartCard,
  INCOMPLETE_OPACITY,
  YearTooltip,
  yearFromChartClick,
} from "./ChartCard";

interface Props {
  data: AnnualPoint[];
  selectedYear: number | null;
  onSelectYear: (year: number) => void;
}

export function FrequencyChart({ data, selectedYear, onSelectYear }: Props) {
  const total = data.reduce((sum, point) => sum + point.event_count, 0);
  const hasIncomplete = data.some((point) => !point.is_complete);

  return (
    <ChartCard
      title="Annual heatwave frequency"
      subtitle="Number of heatwave events per year, counted in the year each event starts"
      description={`Bar chart of heatwave events per year from ${data[0]?.year} to ${data[data.length - 1]?.year}, ${total} events in total. The annual data table below lists every value.`}
      footnote={hasIncomplete ? "Faded bars mark years with less than 95% valid daily data." : undefined}
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
            allowDecimals={false}
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={false}
            width={44}
            label={{ value: "Events per year", angle: -90, position: "insideLeft", offset: 14, style: { ...AXIS_TICK, textAnchor: "middle" } }}
          />
          <Tooltip
            cursor={{ fill: "#10191d", fillOpacity: 0.05 }}
            content={
              <YearTooltip
                rows={(point) => [
                  { label: "Events", value: String(point.event_count), color: CHART_COLORS.heat },
                  { label: "Longest event", value: point.longest_event_days ? `${point.longest_event_days} days` : "–" },
                ]}
              />
            }
          />
          <Bar dataKey="event_count" name="Events" maxBarSize={24} radius={[4, 4, 0, 0]} isAnimationActive={false}>
            {data.map((point) => (
              <Cell
                key={point.year}
                fill={point.year === selectedYear ? CHART_COLORS.heatSelected : CHART_COLORS.heat}
                fillOpacity={point.is_complete ? 1 : INCOMPLETE_OPACITY}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
