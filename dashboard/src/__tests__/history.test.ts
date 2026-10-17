import { describe, expect, it } from "vitest";
import sampleHistoryRaw from "../../sample-history.json";
import {
  buildCategoryDistribution,
  buildDailyUptimeSeries,
  buildLatencySeriesByMonitor,
  buildMonitorCards,
  computeWindowStats,
  filterChecksByWindow,
  filterRunsByWindow,
  getOverallStatus,
  listIncidents,
} from "../lib/history";
import type { HistoryReport } from "../types";

const sampleHistory = sampleHistoryRaw as HistoryReport;

describe("history pure functions", () => {
  it("filtra corridas y checks según la ventana seleccionada (24h, 7d, 30d)", () => {
    const runs24h = filterRunsByWindow(
      sampleHistory.runs,
      "24h",
      sampleHistory.generated_at,
    );
    const runs7d = filterRunsByWindow(
      sampleHistory.runs,
      "7d",
      sampleHistory.generated_at,
    );
    const runs30d = filterRunsByWindow(
      sampleHistory.runs,
      "30d",
      sampleHistory.generated_at,
    );

    expect(runs24h).toHaveLength(4);
    expect(runs7d).toHaveLength(9);
    expect(runs30d).toHaveLength(10);

    const checks24h = filterChecksByWindow(sampleHistory, "24h");
    const checks7d = filterChecksByWindow(sampleHistory, "7d");
    const checks30d = filterChecksByWindow(sampleHistory, "30d");

    expect(checks24h).toHaveLength(8);
    expect(checks7d).toHaveLength(18);
    expect(checks30d).toHaveLength(20);
  });

  it("arma la serie de latencia por monitor y asigna null cuando no hubo respuesta HTTP", () => {
    const series7d = buildLatencySeriesByMonitor(sampleHistory, "7d");

    expect(Object.keys(series7d)).toEqual([
      "DolarApi - Dolar Oficial",
      "Open-Meteo - Clima CABA",
    ]);

    const dolarSeries = series7d["DolarApi - Dolar Oficial"];
    const meteoSeries = series7d["Open-Meteo - Clima CABA"];

    expect(dolarSeries).toHaveLength(9);
    expect(meteoSeries).toHaveLength(9);

    // El 2026-10-13 Open-Meteo tuvo network_error con status_code: null
    const networkFailurePoint = meteoSeries.find(
      (p) => p.statusCategory === "network_error",
    );
    expect(networkFailurePoint).toBeDefined();
    expect(networkFailurePoint?.latencyMs).toBeNull();

    // El último punto tiene latencia numérica
    expect(meteoSeries.at(-1)?.latencyMs).toBe(598.6);
  });

  it("agrupa el uptime diario por fecha UTC en orden cronológico", () => {
    const daily7d = buildDailyUptimeSeries(sampleHistory, "7d");

    // Del 11/10 al 17/10 son 7 días distintos
    expect(daily7d).toHaveLength(7);
    expect(daily7d[0].date).toBe("2026-10-11");
    expect(daily7d[0].uptimePct).toBe(100);

    // El 2026-10-12 hubo 1 OK y 1 server_error -> 50%
    const oct12 = daily7d.find((d) => d.date === "2026-10-12");
    expect(oct12?.uptimePct).toBe(50);
    expect(oct12?.totalChecks).toBe(2);
    expect(oct12?.okChecks).toBe(1);

    // El 2026-10-17 hubo 3 corridas (6 checks), todos OK -> 100%
    const oct17 = daily7d.find((d) => d.date === "2026-10-17");
    expect(oct17?.uptimePct).toBe(100);
    expect(oct17?.totalChecks).toBe(6);
  });

  it("lista los incidentes (status_category != ok) ordenados del más reciente al más antiguo", () => {
    const incidents30d = listIncidents(sampleHistory, "30d");

    // Incidentes en 30d:
    // 2026-10-16T18:00:01Z (degraded)
    // 2026-10-14T12:00:00Z (contract_error)
    // 2026-10-13T12:00:01Z (network_error)
    // 2026-10-12T12:00:00Z (server_error)
    // 2026-10-05T12:00:01Z (client_error)
    expect(incidents30d).toHaveLength(5);
    expect(incidents30d.map((i) => i.statusCategory)).toEqual([
      "degraded",
      "contract_error",
      "network_error",
      "server_error",
      "client_error",
    ]);

    // En 24h solo está el incidente degraded del 16/10 18:00:01Z
    const incidents24h = listIncidents(sampleHistory, "24h");
    expect(incidents24h).toHaveLength(1);
    expect(incidents24h[0].statusCategory).toBe("degraded");
  });

  it("calcula tarjetas de monitores y distribución de categorías para la ventana seleccionada", () => {
    const cards24h = buildMonitorCards(sampleHistory, "24h");
    expect(cards24h).toHaveLength(2);

    const dolarCard = cards24h.find(
      (c) => c.name === "DolarApi - Dolar Oficial",
    );
    expect(dolarCard?.maxLatencyMs).toBe(2500);
    expect(dolarCard?.windowStats.uptime_pct).toBe(100);

    const dist30d = buildCategoryDistribution(sampleHistory, "30d");
    const okItem = dist30d.find((d) => d.category === "ok");
    expect(okItem?.count).toBe(15);
    expect(okItem?.percentage).toBe(75);
  });

  it("maneja correctamente un historial vacío sin arrojar errores", () => {
    const emptyReport: HistoryReport = {
      generated_at: "2026-10-17T18:00:00Z",
      runs: [],
      stats: {},
    };

    expect(filterRunsByWindow(emptyReport.runs, "24h")).toEqual([]);
    expect(filterChecksByWindow(emptyReport, "7d")).toEqual([]);
    expect(buildMonitorCards(emptyReport, "30d")).toEqual([]);
    expect(buildLatencySeriesByMonitor(emptyReport, "24h")).toEqual({});
    expect(buildDailyUptimeSeries(emptyReport, "7d")).toEqual([]);
    expect(listIncidents(emptyReport, "30d")).toEqual([]);
    expect(getOverallStatus(emptyReport)).toEqual({
      allOk: true,
      failingCount: 0,
    });

    const emptyWindowStats = computeWindowStats([]);
    expect(emptyWindowStats.total_checks).toBe(0);
    expect(emptyWindowStats.uptime_pct).toBeNull();
    expect(emptyWindowStats.latency_p50_ms).toBeNull();
    expect(emptyWindowStats.latency_p95_ms).toBeNull();
  });
});
