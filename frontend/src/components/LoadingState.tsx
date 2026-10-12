interface Props {
  label: string;
}

export function LoadingState({ label }: Props) {
  return (
    <div role="status" aria-live="polite" className="space-y-3">
      <div className="flex items-center gap-3 rounded-lg border border-line bg-surface p-4">
        <span
          aria-hidden="true"
          className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-accent"
        />
        <div>
          <p className="text-sm font-medium text-ink">{label}</p>
          <p className="text-xs text-ink-3">
            The first analysis of a location downloads about 30 years of daily data and can take up to
            a minute. Repeat requests are served from the database.
          </p>
        </div>
      </div>
      <div aria-hidden="true" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[0, 1, 2, 3].map((index) => (
          <div key={index} className="h-24 animate-pulse rounded-lg border border-line bg-surface" />
        ))}
      </div>
      <div aria-hidden="true" className="h-72 animate-pulse rounded-lg border border-line bg-surface" />
    </div>
  );
}
