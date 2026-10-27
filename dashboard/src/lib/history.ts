import {
  ALL_STATUS_CATEGORIES,
  type CategoryDistributionItem,
  type CheckResult,
  type DailyUptimePoint,
  type HistoryReport,
  type HistoryRun,
  type IncidentItem,
  type LatencySeriesPoint,
  type MonitorCardView,
  type MonitorSector,
  type SectorFilter,
  type StatusCategory,
  type StatusFilter,
  type TimeWindow,
  type WindowStats,
} from "../types";

export const WINDOW_HOURS: Record<TimeWindow, number> = {
  "24h": 24,
  "7d": 24 * 7,
  "30d": 24 * 30,
};

export function parseTimestampMs(iso: string): number {
  const ms = Date.parse(iso);
  return Number.isNaN(ms) ? 0 : ms;
}

export function percentile(
  sortedValues: readonly number[],
  q: number,
): number | null {
  if (sortedValues.length === 0) {
    return null;
  }
  if (sortedValues.length === 1) {
    return Math.round(sortedValues[0] * 100) / 100;
  }
  const pos = (sortedValues.length - 1) * q;
  const low = Math.floor(pos);
  const high = Math.ceil(pos);
  if (low === high) {
    return Math.round(sortedValues[low] * 100) / 100;
  }
  const interpolated =
    sortedValues[low] + (sortedValues[high] - sortedValues[low]) * (pos - low);
  return Math.round(interpolated * 100) / 100;
}

export function createEmptyCategoryCounts(): Record<StatusCategory, number> {
  return {
    ok: 0,
    degraded: 0,
    contract_error: 0,
    client_error: 0,
    server_error: 0,
    network_error: 0,
  };
}

export function computeWindowStats(checks: readonly CheckResult[]): WindowStats {
  const by_category = createEmptyCategoryCounts();
  const latencies: number[] = [];

  for (const check of checks) {
    by_category[check.status_category] =
      (by_category[check.status_category] ?? 0) + 1;
    if (check.status_code !== null) {
      latencies.push(check.latency_ms);
    }
  }

  latencies.sort((a, b) => a - b);
  const total_checks = checks.length;
  const uptime_pct =
    total_checks > 0
      ? Math.round((by_category.ok / total_checks) * 10000) / 100
      : null;

  return {
    total_checks,
    uptime_pct,
    latency_p50_ms: percentile(latencies, 0.5),
    latency_p95_ms: percentile(latencies, 0.95),
    by_category,
  };
}

/**
 * Clasifica un monitor dentro de uno de los 4 rubros funcionales del dashboard
 * a partir de su nombre y URL.
 */
export function inferMonitorSector(name: string, url = ""): MonitorSector {
  const haystack = `${name} ${url}`.toLowerCase();

  if (
    haystack.includes("sgr") ||
    haystack.includes("pyme") ||
    haystack.includes("epyme") ||
    haystack.includes("casfog") ||
    haystack.includes("mav") ||
    haystack.includes("garantizar") ||
    haystack.includes("acindar") ||
    haystack.includes("cajadevalores")
  ) {
    return "sgr_pyme";
  }

  if (
    haystack.includes("dolar") ||
    haystack.includes("bcra") ||
    haystack.includes("riesgo") ||
    haystack.includes("argentinadatos") ||
    haystack.includes("finanzas") ||
    haystack.includes("monetaria")
  ) {
    return "finanzas";
  }

  if (
    haystack.includes("meteo") ||
    haystack.includes("clima") ||
    haystack.includes("georef") ||
    haystack.includes("provincia") ||
    haystack.includes("datos.gob.ar")
  ) {
    return "datos_publicos";
  }

  return "infra_cripto";
}

/**
 * Filtra las corridas dentro de la ventana seleccionada tomando como referencia
 * `referenceIso` (por defecto `report.generated_at` o la corrida más reciente).
 */
export function filterRunsByWindow(
  runs: readonly HistoryRun[],
  window: TimeWindow,
  referenceIso?: string,
): HistoryRun[] {
  if (runs.length === 0) {
    return [];
  }

  const refMs = referenceIso
    ? parseTimestampMs(referenceIso)
    : Math.max(...runs.map((r) => parseTimestampMs(r.timestamp)));

  const cutoffMs = refMs - WINDOW_HOURS[window] * 3600 * 1000;

  return [...runs]
    .filter((run) => {
      const ts = parseTimestampMs(run.timestamp);
      return ts >= cutoffMs;
    })
    .sort(
      (a, b) => parseTimestampMs(a.timestamp) - parseTimestampMs(b.timestamp),
    );
}

/**
 * Extrae todos los checks individuales dentro de la ventana seleccionada,
 * ordenados cronológicamente (del más antiguo al más reciente).
 */
export function filterChecksByWindow(
  report: HistoryReport,
  window: TimeWindow,
): CheckResult[] {
  if (report.runs.length === 0) {
    return [];
  }
  const refMs = parseTimestampMs(report.generated_at);
  const cutoffMs = refMs - WINDOW_HOURS[window] * 3600 * 1000;

  const checks: CheckResult[] = [];
  for (const run of report.runs) {
    for (const check of run.results) {
      const checkMs = parseTimestampMs(check.timestamp);
      if (checkMs >= cutoffMs) {
        checks.push(check);
      }
    }
  }

  checks.sort(
    (a, b) => parseTimestampMs(a.timestamp) - parseTimestampMs(b.timestamp),
  );
  return checks;
}

/**
 * Obtiene la lista ordenada de nombres de monitores presentes en el reporte.
 */
export function getMonitorNames(report: HistoryReport): string[] {
  const names = new Set<string>(Object.keys(report.stats));
  for (const run of report.runs) {
    for (const result of run.results) {
      names.add(result.name);
    }
  }
  return Array.from(names).sort((a, b) => a.localeCompare(b));
}

/**
 * Determina si el estado general actual es "todo ok" o si algún monitor presenta fallas.
 */
export function getOverallStatus(report: HistoryReport): {
  allOk: boolean;
  failingCount: number;
} {
  const monitorNames = getMonitorNames(report);
  if (monitorNames.length === 0) {
    return { allOk: true, failingCount: 0 };
  }

  let failingCount = 0;
  for (const name of monitorNames) {
    const stat = report.stats[name];
    if (stat && stat.last_status_category !== "ok") {
      failingCount += 1;
    }
  }

  return {
    allOk: failingCount === 0,
    failingCount,
  };
}

/**
 * Construye la vista de tarjeta para cada monitor en la ventana seleccionada.
 */
export function buildMonitorCards(
  report: HistoryReport,
  window: TimeWindow,
): MonitorCardView[] {
  const monitorNames = getMonitorNames(report);
  const filteredChecks = filterChecksByWindow(report, window);

  const latestUrlByMonitor = new Map<string, string>();
  for (const run of report.runs) {
    for (const check of run.results) {
      if (check.url) {
        latestUrlByMonitor.set(check.name, check.url);
      }
    }
  }

  return monitorNames.map((name) => {
    const monitorChecks = filteredChecks.filter((c) => c.name === name);
    const stat = report.stats[name];
    const computedStats = computeWindowStats(monitorChecks);
    const url =
      monitorChecks.at(-1)?.url ?? latestUrlByMonitor.get(name) ?? "";

    return {
      name,
      url,
      sector: inferMonitorSector(name, url),
      lastStatusCategory:
        stat?.last_status_category ??
        monitorChecks.at(-1)?.status_category ??
        "ok",
      lastTimestamp:
        stat?.last_timestamp ??
        monitorChecks.at(-1)?.timestamp ??
        report.generated_at,
      maxLatencyMs: stat?.max_latency_ms ?? null,
      windowStats: computedStats,
    };
  });
}

export interface MonitorFilterCriteria {
  query?: string;
  sector?: SectorFilter;
  status?: StatusFilter;
}

export function cardHasIssues(card: MonitorCardView): boolean {
  const nonOkInWindow =
    card.windowStats.total_checks - card.windowStats.by_category.ok;
  return card.lastStatusCategory !== "ok" || nonOkInWindow > 0;
}

export function cardIsDegraded(card: MonitorCardView): boolean {
  return (
    card.lastStatusCategory === "degraded" ||
    card.windowStats.by_category.degraded > 0
  );
}

/**
 * Filtra las tarjetas de monitores según texto de búsqueda (nombre o URL),
 * rubro funcional (`sector`) y estado (`status`).
 */
export function filterMonitorCards(
  cards: readonly MonitorCardView[],
  criteria: MonitorFilterCriteria,
): MonitorCardView[] {
  const normalizedQuery = (criteria.query ?? "").trim().toLowerCase();
  const sector = criteria.sector ?? "all";
  const status = criteria.status ?? "all";

  return cards.filter((card) => {
    if (sector !== "all" && card.sector !== sector) {
      return false;
    }

    if (status === "ok" && card.lastStatusCategory !== "ok") {
      return false;
    }
    if (status === "issues" && !cardHasIssues(card)) {
      return false;
    }
    if (status === "degraded" && !cardIsDegraded(card)) {
      return false;
    }

    if (normalizedQuery.length > 0) {
      const matchesName = card.name.toLowerCase().includes(normalizedQuery);
      const matchesUrl = card.url.toLowerCase().includes(normalizedQuery);
      if (!matchesName && !matchesUrl) {
        return false;
      }
    }

    return true;
  });
}

export function formatShortTimestamp(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) {
    return iso;
  }
  const month = String(d.getUTCMonth() + 1).padStart(2, "0");
  const day = String(d.getUTCDate()).padStart(2, "0");
  const hours = String(d.getUTCHours()).padStart(2, "0");
  const minutes = String(d.getUTCMinutes()).padStart(2, "0");
  return `${day}/${month} ${hours}:${minutes}`;
}

/**
 * Construye la serie temporal de latencia por monitor dentro de la ventana seleccionada.
 * Si un check no tuvo respuesta HTTP (`status_code === null`), `latencyMs` es `null`.
 */
export function buildLatencySeriesByMonitor(
  report: HistoryReport,
  window: TimeWindow,
): Record<string, LatencySeriesPoint[]> {
  const monitorNames = getMonitorNames(report);
  const filteredChecks = filterChecksByWindow(report, window);
  const seriesByMonitor: Record<string, LatencySeriesPoint[]> = {};

  for (const name of monitorNames) {
    seriesByMonitor[name] = [];
  }

  for (const check of filteredChecks) {
    if (!seriesByMonitor[check.name]) {
      seriesByMonitor[check.name] = [];
    }
    seriesByMonitor[check.name].push({
      timestamp: check.timestamp,
      label: formatShortTimestamp(check.timestamp),
      latencyMs:
        check.status_code !== null
          ? Math.round(check.latency_ms * 100) / 100
          : null,
      statusCategory: check.status_category,
      statusCode: check.status_code,
    });
  }

  return seriesByMonitor;
}

/**
 * Agrupa los checks de la ventana seleccionada por día UTC (YYYY-MM-DD)
 * y calcula el porcentaje de uptime diario general y por monitor.
 */
export function buildDailyUptimeSeries(
  report: HistoryReport,
  window: TimeWindow,
): DailyUptimePoint[] {
  const filteredChecks = filterChecksByWindow(report, window);
  if (filteredChecks.length === 0) {
    return [];
  }

  const monitorNames = getMonitorNames(report);
  const byDate = new Map<
    string,
    {
      total: number;
      ok: number;
      perMonitor: Map<string, { total: number; ok: number }>;
    }
  >();

  for (const check of filteredChecks) {
    const d = new Date(check.timestamp);
    if (Number.isNaN(d.getTime())) {
      continue;
    }
    const dateKey = d.toISOString().slice(0, 10);
    let bucket = byDate.get(dateKey);
    if (!bucket) {
      bucket = { total: 0, ok: 0, perMonitor: new Map() };
      byDate.set(dateKey, bucket);
    }
    bucket.total += 1;
    if (check.status_category === "ok") {
      bucket.ok += 1;
    }

    let monBucket = bucket.perMonitor.get(check.name);
    if (!monBucket) {
      monBucket = { total: 0, ok: 0 };
      bucket.perMonitor.set(check.name, monBucket);
    }
    monBucket.total += 1;
    if (check.status_category === "ok") {
      monBucket.ok += 1;
    }
  }

  return Array.from(byDate.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, bucket]) => {
      const [, month, day] = date.split("-");
      const byMonitor: Record<string, number | null> = {};
      for (const name of monitorNames) {
        const mb = bucket.perMonitor.get(name);
        byMonitor[name] =
          mb && mb.total > 0
            ? Math.round((mb.ok / mb.total) * 10000) / 100
            : null;
      }

      return {
        date,
        label: `${day}/${month}`,
        uptimePct: Math.round((bucket.ok / bucket.total) * 10000) / 100,
        totalChecks: bucket.total,
        okChecks: bucket.ok,
        byMonitor,
      };
    });
}

/**
 * Calcula la distribución de categorías en la ventana seleccionada.
 */
export function buildCategoryDistribution(
  report: HistoryReport,
  window: TimeWindow,
): CategoryDistributionItem[] {
  const filteredChecks = filterChecksByWindow(report, window);
  const counts = createEmptyCategoryCounts();

  for (const check of filteredChecks) {
    counts[check.status_category] = (counts[check.status_category] ?? 0) + 1;
  }

  const total = filteredChecks.length;
  return ALL_STATUS_CATEGORIES.map((category) => {
    const count = counts[category] ?? 0;
    const percentage =
      total > 0 ? Math.round((count / total) * 10000) / 100 : 0;
    return {
      category,
      count,
      percentage,
    };
  });
}

/**
 * Lista todos los incidentes (`status_category !== "ok"`) dentro de la ventana
 * seleccionada, ordenados del más reciente al más antiguo.
 */
export function listIncidents(
  report: HistoryReport,
  window: TimeWindow,
): IncidentItem[] {
  const filteredChecks = filterChecksByWindow(report, window);

  return filteredChecks
    .filter((check) => check.status_category !== "ok")
    .sort(
      (a, b) => parseTimestampMs(b.timestamp) - parseTimestampMs(a.timestamp),
    )
    .map((check) => ({
      name: check.name,
      url: check.url,
      timestamp: check.timestamp,
      statusCategory: check.status_category,
      statusCode: check.status_code,
      latencyMs: Math.round(check.latency_ms * 100) / 100,
      error: check.error,
    }));
}
