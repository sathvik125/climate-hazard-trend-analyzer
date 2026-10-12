import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { analysisFixture, locationsFixture } from "./fixtures";

// Leaflet needs real layout and tile loading, which jsdom does not provide.
// The map is replaced by two buttons that fire the same callbacks a click would.
vi.mock("../components/MapPicker", () => ({
  MapPicker: (props: {
    onPickPoint: (point: { latitude: number; longitude: number }) => void;
    onPickPreset: (presetId: string) => void;
  }) => (
    <div>
      <button type="button" onClick={() => props.onPickPoint({ latitude: 26.9124, longitude: 75.7873 })}>
        map: click custom point
      </button>
      <button type="button" onClick={() => props.onPickPreset("delhi")}>
        map: click Delhi marker
      </button>
    </div>
  ),
}));

type Handler = (url: URL) => Response;

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Replaces fetch with a router over the two endpoints the dashboard calls. */
function mockApi(analysis: Handler) {
  const calls: URL[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://localhost");
      calls.push(url);
      if (url.pathname === "/api/locations") return jsonResponse(locationsFixture);
      if (url.pathname === "/api/analysis") return analysis(url);
      return jsonResponse({ error: { code: "not_found", message: "not found" } }, 404);
    }),
  );
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

describe("Dashboard", () => {
  it("shows no numbers until the user runs an analysis", async () => {
    mockApi(() => jsonResponse(analysisFixture));
    render(<App />);

    expect(await screen.findByText("No analysis yet")).toBeInTheDocument();
    expect(screen.queryByLabelText("Summary metrics")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Location")).toHaveValue("hyderabad");
    expect(screen.getByLabelText("Hazard")).toHaveValue("heatwave");
    expect(screen.getByLabelText("Start year")).toHaveValue("1990");
    expect(screen.getByLabelText("End year")).toHaveValue("2020");
  });

  it("requests the selected analysis and renders the returned metrics and events", async () => {
    const calls = mockApi(() => jsonResponse(analysisFixture));
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: "Analyze" }));

    const summary = await screen.findByLabelText("Summary metrics");
    expect(within(summary).getByText("Total heatwave events").nextSibling).toHaveTextContent("2");
    expect(within(summary).getByText("Total heatwave days").nextSibling).toHaveTextContent("11");
    expect(within(summary).getByText("Longest heatwave").nextSibling).toHaveTextContent("7 days");
    expect(within(summary).getByText("Average intensity").nextSibling).toHaveTextContent("+1.25 °C");

    const request = calls.find((url) => url.pathname === "/api/analysis");
    expect(request?.searchParams.get("latitude")).toBe("17.385");
    expect(request?.searchParams.get("longitude")).toBe("78.4867");
    expect(request?.searchParams.get("start_year")).toBe("1990");
    expect(request?.searchParams.get("end_year")).toBe("2020");
    expect(request?.searchParams.get("hazard")).toBe("heatwave");

    expect(screen.getByText("20 May 2003")).toBeInTheDocument();
    expect(screen.getByText(/Freshly computed/)).toBeInTheDocument();
    expect(screen.getByText("Data source and methodology")).toBeInTheDocument();
  });

  it("filters the event table when a year is inspected", async () => {
    mockApi(() => jsonResponse(analysisFixture));
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Analyze" }));
    await screen.findByLabelText("Summary metrics");

    await user.selectOptions(screen.getByLabelText("Year to inspect"), "2001");
    expect(screen.getByText("10 May 2001")).toBeInTheDocument();
    expect(screen.queryByText("20 May 2003")).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Year to inspect"), "2002");
    expect(screen.getByText("No heatwave events have days in 2002.")).toBeInTheDocument();
  });

  it("shows a clear error, and no metrics, when the database is unavailable", async () => {
    mockApi(() =>
      jsonResponse(
        { error: { code: "database_unavailable", message: "The database is unavailable." } },
        503,
      ),
    );
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Analyze" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The database is unavailable");
    expect(alert).toHaveTextContent("database_unavailable (HTTP 503)");
    expect(screen.queryByLabelText("Summary metrics")).not.toBeInTheDocument();
  });

  it("shows a data quality banner for partial data", async () => {
    const partial = structuredClone(analysisFixture);
    partial.data_quality.coverage_status = "partial";
    partial.data_quality.warnings = ["1 year(s) have less than 95% valid daily data."];
    mockApi(() => jsonResponse(partial));
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Analyze" }));

    expect(await screen.findByText(/results are based on partial data/)).toBeInTheDocument();
    expect(screen.getByText("1 year(s) have less than 95% valid daily data.")).toBeInTheDocument();
  });

  it("uses a point picked on the map as custom coordinates for the analysis", async () => {
    const calls = mockApi(() => jsonResponse(analysisFixture));
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: "map: click custom point" }));
    expect(screen.getByLabelText("Latitude (°N)")).toHaveValue("26.9124");
    expect(screen.getByLabelText("Longitude (°E)")).toHaveValue("75.7873");

    await user.click(screen.getByRole("button", { name: "Analyze" }));
    await screen.findByLabelText("Summary metrics");
    const request = calls.find((url) => url.pathname === "/api/analysis");
    expect(request?.searchParams.get("latitude")).toBe("26.9124");
    expect(request?.searchParams.get("longitude")).toBe("75.7873");
  });

  it("selects a preset when its map marker is clicked", async () => {
    mockApi(() => jsonResponse(analysisFixture));
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: "map: click Delhi marker" }));
    expect(screen.getByLabelText("Location")).toHaveValue("delhi");
    expect(screen.queryByLabelText("Latitude (°N)")).not.toBeInTheDocument();
  });

  it("blocks invalid custom coordinates before calling the API", async () => {
    const calls = mockApi(() => jsonResponse(analysisFixture));
    const user = userEvent.setup();
    render(<App />);

    await user.selectOptions(await screen.findByLabelText("Location"), "Custom coordinates…");
    await user.type(screen.getByLabelText("Latitude (°N)"), "123");
    await user.type(screen.getByLabelText("Longitude (°E)"), "78.5");
    await user.click(screen.getByRole("button", { name: "Analyze" }));

    expect(screen.getByText("Enter a latitude between −90 and 90.")).toBeInTheDocument();
    expect(calls.some((url) => url.pathname === "/api/analysis")).toBe(false);
  });
});
