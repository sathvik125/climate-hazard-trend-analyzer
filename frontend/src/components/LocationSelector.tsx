import type { PresetLocation } from "../api/types";
import type { FormErrors, FormState } from "../lib/validation";
import { fieldClass, labelClass } from "./formStyles";

interface Props {
  locations: PresetLocation[];
  form: FormState;
  errors: FormErrors;
  onChange: (patch: Partial<FormState>) => void;
}

const CUSTOM = "__custom__";

export function LocationSelector({ locations, form, errors, onChange }: Props) {
  const selectValue = form.mode === "custom" ? CUSTOM : form.presetId;

  return (
    <div className="flex flex-wrap items-start gap-3">
      <div className="min-w-44 flex-1">
        <label htmlFor="location" className={labelClass}>
          Location
        </label>
        <select
          id="location"
          className={fieldClass}
          value={selectValue}
          onChange={(event) =>
            event.target.value === CUSTOM
              ? onChange({ mode: "custom" })
              : onChange({ mode: "preset", presetId: event.target.value })
          }
        >
          {locations.map((location) => (
            <option key={location.id} value={location.id}>
              {location.name}, {location.country}
            </option>
          ))}
          <option value={CUSTOM}>Custom coordinates…</option>
        </select>
        {errors.location && <FieldError id="location-error" text={errors.location} />}
      </div>

      {form.mode === "custom" && (
        <>
          <CoordinateField
            id="latitude"
            label="Latitude (°N)"
            placeholder="17.385"
            value={form.latitude}
            error={errors.latitude}
            onChange={(latitude) => onChange({ latitude })}
          />
          <CoordinateField
            id="longitude"
            label="Longitude (°E)"
            placeholder="78.4867"
            value={form.longitude}
            error={errors.longitude}
            onChange={(longitude) => onChange({ longitude })}
          />
        </>
      )}
    </div>
  );
}

interface CoordinateFieldProps {
  id: string;
  label: string;
  placeholder: string;
  value: string;
  error?: string;
  onChange: (value: string) => void;
}

function CoordinateField({ id, label, placeholder, value, error, onChange }: CoordinateFieldProps) {
  return (
    <div className="w-36">
      <label htmlFor={id} className={labelClass}>
        {label}
      </label>
      <input
        id={id}
        type="text"
        inputMode="decimal"
        autoComplete="off"
        className={fieldClass}
        placeholder={placeholder}
        value={value}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        onChange={(event) => onChange(event.target.value)}
      />
      {error && <FieldError id={`${id}-error`} text={error} />}
    </div>
  );
}

export function FieldError({ id, text }: { id: string; text: string }) {
  return (
    <p id={id} className="mt-1 text-xs text-danger-ink">
      {text}
    </p>
  );
}
