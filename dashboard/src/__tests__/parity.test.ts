import { describe, expect, it } from "vitest";
import expectedMetricsRaw from "../../../tests/fixtures/parity_expected_metrics.json";
import parityInputRaw from "../../../tests/fixtures/parity_history_input.json";
import { buildMonitorCards } from "../lib/history";
import type { HistoryReport } from "../types";

interface ExpectedWindow {
  total_checks: number;
  uptime_pct: number;
  latency_p50_ms: number;
  latency_p95_ms: number;
}

const parityInput = parityInputRaw as HistoryReport;
const expectedMetrics = expectedMetricsRaw as Record<
  string,
  { window_24h: ExpectedWindow; window_7d: ExpectedWindow }
>;

describe("Python / TypeScript metrics parity", () => {
  it("calcula exactamente los mismos valores de uptime, p50 y p95 en 24h y 7d que monitor/history.py", () => {
    const cards24h = buildMonitorCards(parityInput, "24h");
    const cards7d = buildMonitorCards(parityInput, "7d");

    for (const [monitorName, expected] of Object.entries(expectedMetrics)) {
      const card24 = cards24h.find((c) => c.name === monitorName);
      expect(card24).toBeDefined();
      expect(card24?.windowStats.total_checks).toBe(
        expected.window_24h.total_checks,
      );
      expect(card24?.windowStats.uptime_pct).toBe(
        expected.window_24h.uptime_pct,
      );
      expect(card24?.windowStats.latency_p50_ms).toBe(
        expected.window_24h.latency_p50_ms,
      );
      expect(card24?.windowStats.latency_p95_ms).toBe(
        expected.window_24h.latency_p95_ms,
      );

      const card7 = cards7d.find((c) => c.name === monitorName);
      expect(card7).toBeDefined();
      expect(card7?.windowStats.total_checks).toBe(
        expected.window_7d.total_checks,
      );
      expect(card7?.windowStats.uptime_pct).toBe(
        expected.window_7d.uptime_pct,
      );
      expect(card7?.windowStats.latency_p50_ms).toBe(
        expected.window_7d.latency_p50_ms,
      );
      expect(card7?.windowStats.latency_p95_ms).toBe(
        expected.window_7d.latency_p95_ms,
      );
    }
  });
});
