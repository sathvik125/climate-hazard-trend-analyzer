import type { AnalysisParams, Hazard, LocationsResponse } from "../api/types";

export interface FormState {
  mode: "preset" | "custom";
  presetId: string;
  latitude: string;
  longitude: string;
  startYear: number;
  endYear: number;
  hazard: Hazard;
}

export type FormErrors = Partial<Record<"latitude" | "longitude" | "years" | "location", string>>;

function parseCoordinate(text: string, limit: number): number | null {
  if (text.trim() === "") return null;
  const value = Number(text);
  return Number.isFinite(value) && Math.abs(value) <= limit ? value : null;
}

/** Mirrors the backend rules so most mistakes are caught before a request is sent. */
export function validateForm(
  form: FormState,
  config: LocationsResponse,
): { errors: FormErrors; params: AnalysisParams | null } {
  const errors: FormErrors = {};
  let latitude: number | null = null;
  let longitude: number | null = null;

  if (form.mode === "preset") {
    const preset = config.locations.find((location) => location.id === form.presetId);
    if (preset) {
      latitude = preset.latitude;
      longitude = preset.longitude;
    } else {
      errors.location = "Choose a location.";
    }
  } else {
    latitude = parseCoordinate(form.latitude, 90);
    longitude = parseCoordinate(form.longitude, 180);
    if (latitude === null) errors.latitude = "Enter a latitude between −90 and 90.";
    if (longitude === null) errors.longitude = "Enter a longitude between −180 and 180.";
  }

  const span = form.endYear - form.startYear + 1;
  if (form.startYear < config.min_year || form.endYear > config.max_year) {
    errors.years = `Years must be between ${config.min_year} and ${config.max_year}.`;
  } else if (form.startYear > form.endYear) {
    errors.years = "The start year must not be after the end year.";
  } else if (span > config.max_year_range) {
    errors.years = `Choose a range of at most ${config.max_year_range} years.`;
  }

  if (Object.keys(errors).length > 0 || latitude === null || longitude === null) {
    return { errors, params: null };
  }
  return {
    errors,
    params: {
      latitude,
      longitude,
      start_year: form.startYear,
      end_year: form.endYear,
      hazard: form.hazard,
    },
  };
}
