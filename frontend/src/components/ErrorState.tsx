import { ApiError } from "../api/client";

interface Props {
  error: unknown;
  onRetry?: () => void;
}

const TITLES: Record<string, string> = {
  network_error: "Cannot reach the API server",
  database_unavailable: "The database is unavailable",
  upstream_unavailable: "The weather data provider is unavailable",
  upstream_timeout: "The weather data provider timed out",
  upstream_rate_limited: "The weather data provider is rate limiting requests",
  upstream_invalid_data: "The weather data provider returned unusable data",
  insufficient_data: "Not enough source data for this analysis",
  invalid_request: "The request was not valid",
  rate_limited: "Too many requests",
};

const HINTS: Record<string, string> = {
  database_unavailable:
    "Results are stored in and served from MongoDB, so nothing can be shown until it is reachable again.",
  upstream_rate_limited: "Wait a minute before trying again.",
  rate_limited: "Wait a minute before trying again.",
  insufficient_data: "Try a different location or period.",
};

/** A failed request never falls back to placeholder numbers; it says what failed. */
export function ErrorState({ error, onRetry }: Props) {
  const apiError = error instanceof ApiError ? error : null;
  const code = apiError?.code ?? "unknown";
  const title = TITLES[code] ?? "The analysis could not be completed";
  const message = apiError?.message ?? "An unexpected error occurred in the application.";

  return (
    <div role="alert" className="rounded-lg border border-danger-line bg-danger-bg p-5">
      <h2 className="text-sm font-semibold text-danger-ink">{title}</h2>
      <p className="mt-1 text-sm text-ink">{message}</p>
      {apiError && apiError.details.length > 0 && (
        <ul className="mt-2 list-disc pl-5 text-sm text-ink">
          {apiError.details.map((detail, index) => (
            <li key={index}>
              {detail.field ? `${detail.field}: ` : ""}
              {detail.message}
            </li>
          ))}
        </ul>
      )}
      {HINTS[code] && <p className="mt-2 text-xs text-ink-2">{HINTS[code]}</p>}
      <div className="mt-4 flex items-center gap-3">
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="h-9 rounded-md bg-accent px-4 text-sm font-medium text-white hover:bg-accent-strong"
          >
            Try again
          </button>
        )}
        <span className="text-xs text-ink-3">
          Error code: {code}
          {apiError?.status ? ` (HTTP ${apiError.status})` : ""}
        </span>
      </div>
    </div>
  );
}
