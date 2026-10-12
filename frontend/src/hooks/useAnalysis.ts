import { useQuery } from "@tanstack/react-query";
import { fetchAnalysis, fetchLocations } from "../api/client";
import type { AnalysisParams } from "../api/types";

/** Preset locations and the year bounds the backend accepts. */
export function useLocations() {
  return useQuery({
    queryKey: ["locations"],
    queryFn: ({ signal }) => fetchLocations(signal),
    staleTime: Infinity,
    // A sleeping free-tier server can drop or refuse the first request while it
    // starts, so keep trying for about a minute before showing an error.
    retry: 6,
    retryDelay: 10_000,
  });
}

/** Runs only once the user has submitted parameters with the Analyze button. */
export function useAnalysis(params: AnalysisParams | null) {
  return useQuery({
    queryKey: ["analysis", params],
    queryFn: ({ signal }) => fetchAnalysis(params as AnalysisParams, signal),
    enabled: params !== null,
    staleTime: 5 * 60 * 1000,
    // The backend already retries the weather provider; retrying here would
    // only multiply the wait and the rate-limit cost.
    retry: false,
    refetchOnWindowFocus: false,
  });
}
