import type { AnalysisResponse, MannKendall, Trend } from "../api/types";
import { formatNumber, formatPercent, formatSigned } from "../lib/format";

interface Props {
  analysis: AnalysisResponse;
}

/** Shows the backend's insight sentences verbatim, plus the numbers behind them. */
export function InsightsPanel({ analysis }: Props) {
  const { generated_insights: insights, trend, data_quality: quality } = analysis;
  const findings = insights.filter((insight) => insight.category !== "caveat");
  const caveats = insights.filter((insight) => insight.category === "caveat");

  return (
    <section className="rounded-lg border border-line bg-surface p-4" aria-labelledby="insights-title">
      <h3 id="insights-title" className="text-sm font-semibold text-ink">
        Insights
      </h3>
      <p className="mt-0.5 text-xs text-ink-3">
        Descriptive statistics for this grid cell. No statistical significance or cause is claimed.
      </p>

      <ul className="mt-3 space-y-2">
        {findings.map((insight) => (
          <li
            key={insight.id}
            className={
              "rounded-md border px-3 py-2 text-sm leading-relaxed " +
              (insight.severity === "warning"
                ? "border-warn-line bg-warn-bg text-warn-ink"
                : "border-line-soft bg-page text-ink")
            }
          >
            <span className="mr-2 text-[11px] font-semibold uppercase tracking-wide text-ink-3">
              {insight.severity === "warning" ? "Warning · " : ""}
              {insight.category}
            </span>
            {insight.text}
          </li>
        ))}
      </ul>

      <h4 className="mt-5 text-xs font-semibold text-ink-2">Linear trend (per decade)</h4>
      <div className="mt-2 overflow-x-auto">
        <table className="tabular w-full min-w-[30rem] text-left text-xs">
          <thead className="text-ink-3">
            <tr className="border-b border-line">
              <th scope="col" className="py-1.5 pr-3 font-medium">Metric</th>
              <th scope="col" className="px-3 py-1.5 text-right font-medium">Slope</th>
              <th scope="col" className="px-3 py-1.5 text-right font-medium">95% interval</th>
              <th scope="col" className="px-3 py-1.5 text-right font-medium">R²</th>
              <th scope="col" className="px-3 py-1.5 text-right font-medium">p (OLS)</th>
              <th scope="col" className="py-1.5 pl-3 text-right font-medium">Years</th>
            </tr>
          </thead>
          <tbody className="text-ink">
            <TrendRow label="Heatwave days" trend={trend.heatwave_days_per_decade} />
            <TrendRow label="Heatwave events" trend={trend.events_per_decade} />
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs leading-relaxed text-ink-3">
        Ordinary least squares on annual values. The interval and p-value assume independent, roughly
        normal residuals, which yearly counts only approximately meet, so read them as indicative.
        {trend.years_excluded.length > 0 &&
          ` ${trend.years_excluded.length} incomplete year(s) were excluded from the fit.`}
      </p>

      <h4 className="mt-5 text-xs font-semibold text-ink-2">
        Mann-Kendall test with Theil-Sen slope (rank based)
      </h4>
      <div className="mt-2 overflow-x-auto">
        <table className="tabular w-full min-w-[30rem] text-left text-xs">
          <thead className="text-ink-3">
            <tr className="border-b border-line">
              <th scope="col" className="py-1.5 pr-3 font-medium">Metric</th>
              <th scope="col" className="px-3 py-1.5 text-right font-medium">Kendall’s tau</th>
              <th scope="col" className="px-3 py-1.5 text-right font-medium">p (two-sided)</th>
              <th scope="col" className="px-3 py-1.5 text-right font-medium">Sen slope / decade</th>
              <th scope="col" className="px-3 py-1.5 text-right font-medium">95% interval</th>
              <th scope="col" className="py-1.5 pl-3 text-right font-medium">Years</th>
            </tr>
          </thead>
          <tbody className="text-ink">
            <MannKendallRow label="Heatwave days" result={trend.heatwave_days_mann_kendall} />
            <MannKendallRow label="Heatwave events" result={trend.events_mann_kendall} />
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs leading-relaxed text-ink-3">
        Compares every year with every later year using only whether the value rose or fell, so one
        extreme year cannot dominate. Tau runs from −1 (always falling) to +1 (always rising). The
        test is corrected for tied values but not for autocorrelation between years.
      </p>

      <h4 className="mt-5 text-xs font-semibold text-ink-2">Data completeness</h4>
      <dl className="mt-2 grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
        <Fact
          label="Coverage status"
          value={quality.coverage_status === "complete" ? "Complete" : "Partial"}
        />
        <Fact
          label="Valid days"
          value={`${formatNumber(quality.valid_days)} of ${formatNumber(quality.expected_days)}`}
          note={formatPercent(quality.overall_completeness)}
        />
        <Fact
          label="Missing / excluded"
          value={`${formatNumber(quality.missing_days)} / ${formatNumber(quality.implausible_days)}`}
          note="days"
        />
        <Fact label="Baseline completeness" value={formatPercent(quality.baseline_completeness)} />
      </dl>

      {caveats.length > 0 && (
        <>
          <h4 className="mt-5 text-xs font-semibold text-ink-2">Read with these caveats</h4>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-xs leading-relaxed text-ink-2">
            {caveats.map((caveat) => (
              <li key={caveat.id}>{caveat.text}</li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

function TrendRow({ label, trend }: { label: string; trend: Trend }) {
  if (trend.status !== "ok") {
    return (
      <tr className="border-b border-line-soft last:border-b-0">
        <th scope="row" className="py-1.5 pr-3 font-medium">{label}</th>
        <td colSpan={5} className="px-3 py-1.5 text-right text-ink-3">
          Not reported: {trend.n_years} complete year(s), too few to fit a slope
        </td>
      </tr>
    );
  }
  return (
    <tr className="border-b border-line-soft last:border-b-0">
      <th scope="row" className="py-1.5 pr-3 font-medium">{label}</th>
      <td className="px-3 py-1.5 text-right">{formatSigned(trend.slope_per_decade, 2)}</td>
      <td className="px-3 py-1.5 text-right">
        {formatSigned(trend.slope_ci95_low_per_decade, 2)} to{" "}
        {formatSigned(trend.slope_ci95_high_per_decade, 2)}
      </td>
      <td className="px-3 py-1.5 text-right">{formatNumber(trend.r_squared, 2)}</td>
      <td className="px-3 py-1.5 text-right">{formatNumber(trend.p_value, 3)}</td>
      <td className="py-1.5 pl-3 text-right">{trend.n_years}</td>
    </tr>
  );
}

function MannKendallRow({ label, result }: { label: string; result: MannKendall }) {
  if (result.status !== "ok") {
    return (
      <tr className="border-b border-line-soft last:border-b-0">
        <th scope="row" className="py-1.5 pr-3 font-medium">{label}</th>
        <td colSpan={5} className="px-3 py-1.5 text-right text-ink-3">
          Not reported: {result.n_years} complete year(s), too few for the test
        </td>
      </tr>
    );
  }
  return (
    <tr className="border-b border-line-soft last:border-b-0">
      <th scope="row" className="py-1.5 pr-3 font-medium">{label}</th>
      <td className="px-3 py-1.5 text-right">{formatSigned(result.kendall_tau, 2)}</td>
      <td className="px-3 py-1.5 text-right">{formatNumber(result.p_value, 3)}</td>
      <td className="px-3 py-1.5 text-right">{formatSigned(result.sen_slope_per_decade, 2)}</td>
      <td className="px-3 py-1.5 text-right">
        {formatSigned(result.sen_slope_ci95_low_per_decade, 2)} to{" "}
        {formatSigned(result.sen_slope_ci95_high_per_decade, 2)}
      </td>
      <td className="py-1.5 pl-3 text-right">{result.n_years}</td>
    </tr>
  );
}

function Fact({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div>
      <dt className="text-ink-3">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium text-ink">
        {value}
        {note && <span className="ml-1 font-normal text-ink-3">{note}</span>}
      </dd>
    </div>
  );
}
