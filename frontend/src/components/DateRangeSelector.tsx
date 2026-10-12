import { FieldError } from "./LocationSelector";
import { fieldClass, labelClass } from "./formStyles";

interface Props {
  startYear: number;
  endYear: number;
  minYear: number;
  maxYear: number;
  error?: string;
  onChange: (patch: { startYear?: number; endYear?: number }) => void;
}

/** Full calendar years only, so no partial boundary year can be compared. */
export function DateRangeSelector({ startYear, endYear, minYear, maxYear, error, onChange }: Props) {
  const years = Array.from({ length: maxYear - minYear + 1 }, (_, index) => minYear + index);
  const describedBy = error ? "years-error" : undefined;

  return (
    <div>
      <div className="flex gap-3">
        <div className="w-28">
          <label htmlFor="start-year" className={labelClass}>
            Start year
          </label>
          <select
            id="start-year"
            className={fieldClass}
            value={startYear}
            aria-invalid={error ? true : undefined}
            aria-describedby={describedBy}
            onChange={(event) => onChange({ startYear: Number(event.target.value) })}
          >
            {years.map((year) => (
              <option key={year} value={year}>
                {year}
              </option>
            ))}
          </select>
        </div>
        <div className="w-28">
          <label htmlFor="end-year" className={labelClass}>
            End year
          </label>
          <select
            id="end-year"
            className={fieldClass}
            value={endYear}
            aria-invalid={error ? true : undefined}
            aria-describedby={describedBy}
            onChange={(event) => onChange({ endYear: Number(event.target.value) })}
          >
            {years.map((year) => (
              <option key={year} value={year}>
                {year}
              </option>
            ))}
          </select>
        </div>
      </div>
      {error && <FieldError id="years-error" text={error} />}
    </div>
  );
}
