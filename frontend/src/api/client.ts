import type { AnalysisParams, AnalysisResponse, LocationsResponse } from "./types";

// Empty in development (Vite proxies /api). In production set VITE_API_BASE_URL
// to the backend origin, for example https://your-api.onrender.com
const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export interface ApiErrorDetail {
  field?: string;
  message?: string;
}

export class ApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status: number | null = null,
    public readonly details: ApiErrorDetail[] = [],
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function toQuery(params: object): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) search.set(key, String(value));
  return search.toString();
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, { signal, headers: { Accept: "application/json" } });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError(
      "network_error",
      "The API server could not be reached. Check that the backend is running and try again.",
    );
  }

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // handled below: a non-JSON body is only acceptable if we never read it
  }

  if (!response.ok) {
    const error = (body as { error?: { code?: string; message?: string; details?: unknown } } | null)
      ?.error;
    throw new ApiError(
      error?.code ?? "http_error",
      error?.message ?? `The server responded with HTTP ${response.status}.`,
      response.status,
      Array.isArray(error?.details) ? (error.details as ApiErrorDetail[]) : [],
    );
  }
  if (body === null) {
    throw new ApiError("invalid_response", "The server returned a response that is not valid JSON.");
  }
  return body as T;
}

export function fetchLocations(signal?: AbortSignal): Promise<LocationsResponse> {
  return getJson<LocationsResponse>("/api/locations", signal);
}

export function fetchAnalysis(
  params: AnalysisParams,
  signal?: AbortSignal,
): Promise<AnalysisResponse> {
  return getJson<AnalysisResponse>(`/api/analysis?${toQuery(params)}`, signal);
}

export function csvExportUrl(params: AnalysisParams, dataset: "events" | "annual"): string {
  return `${BASE_URL}/api/export/csv?${toQuery({ ...params, dataset })}`;
}
