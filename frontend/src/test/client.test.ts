import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, csvExportUrl, fetchAnalysis } from "../api/client";
import type { AnalysisParams } from "../api/types";

const params: AnalysisParams = {
  latitude: 17.385,
  longitude: 78.4867,
  start_year: 1990,
  end_year: 2020,
  hazard: "heatwave",
};

afterEach(() => vi.unstubAllGlobals());

describe("API client", () => {
  it("turns a backend error body into an ApiError with its code and details", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            error: {
              code: "invalid_request",
              message: "One or more request parameters are invalid.",
              details: [{ field: "latitude", message: "Input should be less than or equal to 90" }],
            },
          }),
          { status: 422 },
        ),
      ),
    );

    const error = await fetchAnalysis(params).catch((caught) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe("invalid_request");
    expect(error.status).toBe(422);
    expect(error.details[0].field).toBe("latitude");
  });

  it("reports an unreachable server as a network error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    const error = await fetchAnalysis(params).catch((caught) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe("network_error");
  });

  it("builds the CSV export URL from the same parameters", () => {
    const url = new URL(csvExportUrl(params, "annual"), "http://localhost");
    expect(url.pathname).toBe("/api/export/csv");
    expect(url.searchParams.get("dataset")).toBe("annual");
    expect(url.searchParams.get("start_year")).toBe("1990");
  });
});
