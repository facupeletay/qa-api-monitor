import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  buildCategoryDistribution,
  buildDailyUptimeSeries,
  buildLatencySeriesByMonitor,
  buildMonitorCards,
  formatShortTimestamp,
  getOverallStatus,
  listIncidents,
} from "./lib/history";
import type { HistoryReport, StatusCategory, TimeWindow } from "./types";

const WINDOW_OPTIONS: { value: TimeWindow; label: string }[] = [
  { value: "24h", label: "24 h" },
  { value: "7d", label: "7 días" },
  { value: "30d", label: "30 días" },
];

const CATEGORY_META: Record<
  StatusCategory,
  {
    label: string;
    badgeClass: string;
    dotColor: string;
    barColor: string;
  }
> = {
  ok: {
    label: "OK",
    badgeClass:
      "bg-emerald-500/15 text-emerald-400 border-emerald-500/30 light:text-emerald-700",
    dotColor: "#10b981",
    barColor: "#10b981",
  },
  degraded: {
    label: "Degraded (SLA)",
    badgeClass:
      "bg-amber-500/15 text-amber-400 border-amber-500/30 light:text-amber-700",
    dotColor: "#f59e0b",
    barColor: "#f59e0b",
  },
  contract_error: {
    label: "Contract Error",
    badgeClass:
      "bg-purple-500/15 text-purple-400 border-purple-500/30 light:text-purple-700",
    dotColor: "#a855f7",
    barColor: "#a855f7",
  },
  client_error: {
    label: "Client Error (4xx)",
    badgeClass:
      "bg-orange-500/15 text-orange-400 border-orange-500/30 light:text-orange-700",
    dotColor: "#f97316",
    barColor: "#f97316",
  },
  server_error: {
    label: "Server Error (5xx)",
    badgeClass:
      "bg-rose-500/15 text-rose-400 border-rose-500/30 light:text-rose-700",
    dotColor: "#f43f5e",
    barColor: "#f43f5e",
  },
  network_error: {
    label: "Network / Timeout",
    badgeClass:
      "bg-red-500/15 text-red-400 border-red-500/30 light:text-red-700",
    dotColor: "#ef4444",
    barColor: "#ef4444",
  },
};

function formatNumber(val: number | null, suffix = ""): string {
  if (val === null || Number.isNaN(val)) {
    return "—";
  }
  return `${val.toFixed(1)}${suffix}`;
}

export interface AppProps {
  historyUrl?: string;
}

export function App({
  historyUrl = `${import.meta.env.BASE_URL}history.json`,
}: AppProps) {
  const [report, setReport] = useState<HistoryReport | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [windowRange, setWindowRange] = useState<TimeWindow>("7d");

  useEffect(() => {
    let cancelled = false;

    async function fetchHistory() {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(historyUrl, { cache: "no-store" });
        if (res.status === 404) {
          if (!cancelled) {
            setReport({ generated_at: "", runs: [], stats: {} });
            setLoading(false);
          }
          return;
        }
        if (!res.ok) {
          throw new Error(
            `Error HTTP ${res.status} al obtener history.json`,
          );
        }
        const data = (await res.json()) as HistoryReport;
        if (!cancelled) {
          setReport(data);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "No se pudo cargar el historial de monitoreo.",
          );
          setLoading(false);
        }
      }
    }

    void fetchHistory();
    return () => {
      cancelled = true;
    };
  }, [historyUrl]);

  const overallStatus = useMemo(
    () => (report ? getOverallStatus(report) : { allOk: true, failingCount: 0 }),
    [report],
  );

  const monitorCards = useMemo(
    () => (report ? buildMonitorCards(report, windowRange) : []),
    [report, windowRange],
  );

  const latencySeriesByMonitor = useMemo(
    () => (report ? buildLatencySeriesByMonitor(report, windowRange) : {}),
    [report, windowRange],
  );

  const dailyUptime = useMemo(
    () => (report ? buildDailyUptimeSeries(report, windowRange) : []),
    [report, windowRange],
  );

  const categoryDistribution = useMemo(
    () => (report ? buildCategoryDistribution(report, windowRange) : []),
    [report, windowRange],
  );

  const incidents = useMemo(
    () => (report ? listIncidents(report, windowRange) : []),
    [report, windowRange],
  );

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <div
          role="status"
          className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-secondary)] px-8 py-10 text-center shadow-lg max-w-md w-full"
        >
          <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-sky-500 border-t-transparent" />
          <p className="text-base font-medium text-[var(--text-primary)]">
            Cargando historial de monitoreo...
          </p>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            Consultando métricas recientes de history.json
          </p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <div
          role="alert"
          className="rounded-xl border border-rose-500/40 bg-[var(--surface-secondary)] px-8 py-10 text-center shadow-lg max-w-lg w-full"
        >
          <div className="mx-auto mb-3 inline-flex h-10 w-10 items-center justify-center rounded-full bg-rose-500/15 text-rose-400 font-bold">
            !
          </div>
          <h1 className="text-lg font-semibold text-[var(--text-primary)]">
            Error al cargar los datos
          </h1>
          <p className="mt-2 text-sm text-rose-400">{error}</p>
        </div>
      </div>
    );
  }

  if (!report || report.runs.length === 0) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-secondary)] px-8 py-10 text-center shadow-lg max-w-lg w-full">
          <h1 className="text-lg font-semibold text-[var(--text-primary)]">
            QA API Monitor
          </h1>
          <p className="mt-2 text-base text-[var(--text-secondary)]">
            Todavía no hay datos disponibles en el historial.
          </p>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            El dashboard se actualizará automáticamente tras la primera corrida.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen pb-14">
      {/* Header */}
      <header className="border-b border-[var(--border-subtle)] bg-[var(--surface-secondary)]">
        <div className="mx-auto max-w-7xl px-4 py-5 sm:px-6 lg:px-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-[var(--text-primary)]">
                QA API Monitor
              </h1>
              <span
                className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold whitespace-nowrap ${
                  overallStatus.allOk
                    ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                    : "bg-rose-500/15 text-rose-400 border-rose-500/30"
                }`}
              >
                <span
                  className="h-2 w-2 rounded-full"
                  style={{
                    backgroundColor: overallStatus.allOk
                      ? "#10b981"
                      : "#f43f5e",
                  }}
                />
                {overallStatus.allOk
                  ? "Todo OK"
                  : `Hay problemas (${overallStatus.failingCount})`}
              </span>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs sm:text-sm text-[var(--text-muted)]">
              <span>
                Última actualización:{" "}
                <strong className="font-medium text-[var(--text-secondary)] whitespace-nowrap">
                  {formatShortTimestamp(report.generated_at)} UTC
                </strong>
              </span>
              <span>
                Corridas acumuladas:{" "}
                <strong className="font-medium text-[var(--text-secondary)] whitespace-nowrap">
                  {report.runs.length}
                </strong>
              </span>
            </div>
          </div>

          {/* Window Selector */}
          <div
            role="group"
            aria-label="Selector de ventana temporal"
            className="inline-flex self-start sm:self-auto rounded-lg border border-[var(--border-strong)] bg-[var(--surface-primary)] p-1"
          >
            {WINDOW_OPTIONS.map((opt) => {
              const active = windowRange === opt.value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setWindowRange(opt.value)}
                  aria-pressed={active}
                  className={`rounded-md px-3.5 py-1.5 text-xs sm:text-sm font-medium transition-colors whitespace-nowrap cursor-pointer ${
                    active
                      ? "bg-sky-500 text-white shadow-sm"
                      : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                  }`}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 pt-6 sm:px-6 lg:px-8 space-y-8">
        {/* Monitor Cards */}
        <section aria-labelledby="monitors-heading">
          <div className="mb-3 flex items-center justify-between">
            <h2
              id="monitors-heading"
              className="text-base sm:text-lg font-semibold text-[var(--text-primary)]"
            >
              Estado por Monitor ({windowRange})
            </h2>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {monitorCards.map((card) => {
              const meta = CATEGORY_META[card.lastStatusCategory];
              return (
                <article
                  key={card.name}
                  className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-secondary)] p-5 shadow-sm"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h3 className="text-base font-semibold text-[var(--text-primary)]">
                        {card.name}
                      </h3>
                      <p className="mt-0.5 text-xs text-[var(--text-muted)]">
                        Último check:{" "}
                        <span className="whitespace-nowrap">
                          {formatShortTimestamp(card.lastTimestamp)} UTC
                        </span>
                      </p>
                    </div>
                    <span
                      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold whitespace-nowrap ${meta.badgeClass}`}
                    >
                      <span
                        className="h-2 w-2 rounded-full"
                        style={{ backgroundColor: meta.dotColor }}
                      />
                      {meta.label}
                    </span>
                  </div>

                  <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3 pt-4 border-t border-[var(--border-subtle)]">
                    <div>
                      <span className="block text-xs text-[var(--text-muted)]">
                        Uptime ({windowRange})
                      </span>
                      <span className="mt-1 block text-lg font-bold text-[var(--text-primary)] whitespace-nowrap">
                        {card.windowStats.uptime_pct !== null
                          ? `${card.windowStats.uptime_pct.toFixed(2)} %`
                          : "—"}
                      </span>
                    </div>

                    <div>
                      <span className="block text-xs text-[var(--text-muted)]">
                        Latencia p50
                      </span>
                      <span className="mt-1 block text-lg font-bold text-[var(--text-primary)] whitespace-nowrap">
                        {formatNumber(
                          card.windowStats.latency_p50_ms,
                          " ms",
                        )}
                      </span>
                    </div>

                    <div>
                      <span className="block text-xs text-[var(--text-muted)]">
                        Latencia p95
                      </span>
                      <span className="mt-1 block text-lg font-bold text-[var(--text-primary)] whitespace-nowrap">
                        {formatNumber(
                          card.windowStats.latency_p95_ms,
                          " ms",
                        )}
                      </span>
                    </div>

                    <div>
                      <span className="block text-xs text-[var(--text-muted)]">
                        SLA Máximo
                      </span>
                      <span className="mt-1 block text-lg font-semibold text-sky-400 whitespace-nowrap">
                        {card.maxLatencyMs !== null
                          ? `${card.maxLatencyMs} ms`
                          : "—"}
                      </span>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        </section>

        {/* Latency Charts per Monitor */}
        <section
          aria-labelledby="latency-heading"
          className="space-y-4 min-w-0"
        >
          <h2
            id="latency-heading"
            className="text-base sm:text-lg font-semibold text-[var(--text-primary)]"
          >
            Latencia en el Tiempo vs. SLA ({windowRange})
          </h2>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {monitorCards.map((card) => {
              const series = latencySeriesByMonitor[card.name] ?? [];
              const maxSeriesVal = series.reduce(
                (acc, pt) =>
                  pt.latencyMs !== null && pt.latencyMs > acc
                    ? pt.latencyMs
                    : acc,
                0,
              );
              const yMax = Math.ceil(
                Math.max(maxSeriesVal, card.maxLatencyMs ?? 0, 100) * 1.15,
              );
              return (
                <div
                  key={card.name}
                  className="min-w-0 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-secondary)] p-5 shadow-sm"
                >
                  <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <h3 className="text-sm font-semibold text-[var(--text-primary)]">
                        {card.name}
                      </h3>
                      <p className="text-xs text-[var(--text-muted)]">
                        Latencia por corrida (ms)
                      </p>
                    </div>
                    {card.maxLatencyMs !== null && (
                      <span className="rounded-md bg-amber-500/10 border border-amber-500/30 px-2.5 py-1 text-xs font-medium text-amber-400 whitespace-nowrap">
                        SLA: {card.maxLatencyMs} ms
                      </span>
                    )}
                  </div>

                  <div className="h-64 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart
                        data={series}
                        margin={{ top: 10, right: 16, left: 0, bottom: 5 }}
                      >
                        <CartesianGrid
                          strokeDasharray="3 3"
                          stroke="var(--chart-grid)"
                        />
                        <XAxis
                          dataKey="label"
                          stroke="var(--chart-axis)"
                          tick={{ fontSize: 11 }}
                          minTickGap={24}
                        />
                        <YAxis
                          stroke="var(--chart-axis)"
                          tick={{ fontSize: 11 }}
                          domain={[0, yMax]}
                          unit=" ms"
                          width={65}
                        />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: "var(--chart-tooltip-bg)",
                            borderColor: "var(--border-strong)",
                            borderRadius: "0.5rem",
                            fontSize: "12px",
                          }}
                          formatter={(value) => [
                            value !== null && value !== undefined
                              ? `${value} ms`
                              : "Sin respuesta",
                            "Latencia",
                          ]}
                        />
                        <Legend wrapperStyle={{ fontSize: "12px" }} />
                        {card.maxLatencyMs !== null && (
                          <ReferenceLine
                            y={card.maxLatencyMs}
                            stroke="#f59e0b"
                            strokeDasharray="5 5"
                            label={{
                              value: `SLA (${card.maxLatencyMs} ms)`,
                              fill: "#f59e0b",
                              fontSize: 11,
                              position: "insideTopRight",
                            }}
                          />
                        )}
                        <Line
                          type="monotone"
                          dataKey="latencyMs"
                          name="Latencia (ms)"
                          stroke="#38bdf8"
                          strokeWidth={2}
                          dot={{ r: 3 }}
                          activeDot={{ r: 5 }}
                          connectNulls={false}
                          isAnimationActive={false}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* Daily Uptime + Category Distribution */}
        <section className="grid grid-cols-1 gap-6 lg:grid-cols-3 min-w-0">
          {/* Daily Uptime BarChart */}
          <div className="min-w-0 lg:col-span-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-secondary)] p-5 shadow-sm">
            <div className="mb-4">
              <h2 className="text-base font-semibold text-[var(--text-primary)]">
                Uptime Diario ({windowRange})
              </h2>
              <p className="text-xs text-[var(--text-muted)]">
                Porcentaje de checks en estado OK agrupados por fecha (UTC)
              </p>
            </div>

            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={dailyUptime}
                  margin={{ top: 10, right: 16, left: 0, bottom: 5 }}
                >
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="var(--chart-grid)"
                  />
                  <XAxis
                    dataKey="label"
                    stroke="var(--chart-axis)"
                    tick={{ fontSize: 11 }}
                  />
                  <YAxis
                    stroke="var(--chart-axis)"
                    tick={{ fontSize: 11 }}
                    domain={[0, 100]}
                    unit="%"
                    width={52}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "var(--chart-tooltip-bg)",
                      borderColor: "var(--border-strong)",
                      borderRadius: "0.5rem",
                      fontSize: "12px",
                    }}
                    formatter={(value) => [`${value} %`, "Uptime"]}
                  />
                  <Bar
                    dataKey="uptimePct"
                    name="Uptime diario (%)"
                    radius={[4, 4, 0, 0]}
                    isAnimationActive={false}
                  >
                    {dailyUptime.map((entry) => (
                      <Cell
                        key={entry.date}
                        fill={
                          entry.uptimePct >= 98
                            ? "#10b981"
                            : entry.uptimePct >= 90
                              ? "#f59e0b"
                              : "#f43f5e"
                        }
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Category Distribution */}
          <div className="min-w-0 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-secondary)] p-5 shadow-sm">
            <div className="mb-4">
              <h2 className="text-base font-semibold text-[var(--text-primary)]">
                Distribución de Categorías ({windowRange})
              </h2>
              <p className="text-xs text-[var(--text-muted)]">
                Proporción de resultados por clasificación
              </p>
            </div>

            <div className="space-y-3">
              {categoryDistribution.map((item) => {
                const meta = CATEGORY_META[item.category];
                return (
                  <div key={item.category} className="space-y-1">
                    <div className="flex items-center justify-between text-xs sm:text-sm">
                      <span className="inline-flex items-center gap-2 font-medium text-[var(--text-secondary)]">
                        <span
                          className="h-2.5 w-2.5 rounded-full shrink-0"
                          style={{ backgroundColor: meta.dotColor }}
                        />
                        {meta.label}
                      </span>
                      <span className="font-semibold text-[var(--text-primary)] whitespace-nowrap">
                        {item.count} ({item.percentage.toFixed(1)} %)
                      </span>
                    </div>
                    <div className="h-2 w-full overflow-hidden rounded-full bg-[var(--surface-elevated)]">
                      <div
                        className="h-full rounded-full transition-all"
                        style={{
                          width: `${Math.min(100, item.percentage)}%`,
                          backgroundColor: meta.barColor,
                        }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        {/* Incidents Table */}
        <section
          aria-labelledby="incidents-heading"
          className="min-w-0 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-secondary)] p-5 shadow-sm"
        >
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2
                id="incidents-heading"
                className="text-base sm:text-lg font-semibold text-[var(--text-primary)]"
              >
                Registro de Incidentes ({windowRange})
              </h2>
              <p className="text-xs text-[var(--text-muted)]">
                Checks con estado distinto de OK, del más reciente al más antiguo
              </p>
            </div>
            <span className="rounded-full bg-[var(--surface-elevated)] px-3 py-1 text-xs font-semibold text-[var(--text-secondary)] whitespace-nowrap">
              {incidents.length}{" "}
              {incidents.length === 1 ? "incidente" : "incidentes"}
            </span>
          </div>

          {incidents.length === 0 ? (
            <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-primary)] p-6 text-center text-sm text-[var(--text-muted)]">
              Sin incidentes registrados en esta ventana temporal.
            </div>
          ) : (
            <div className="table-responsive">
              <table className="w-full text-left text-xs sm:text-sm border-collapse">
                <thead>
                  <tr className="border-b border-[var(--border-strong)] text-[var(--text-muted)]">
                    <th className="py-2.5 pr-4 font-semibold whitespace-nowrap">
                      Fecha (UTC)
                    </th>
                    <th className="py-2.5 px-4 font-semibold whitespace-nowrap">
                      Monitor
                    </th>
                    <th className="py-2.5 px-4 font-semibold whitespace-nowrap">
                      Categoría
                    </th>
                    <th className="py-2.5 px-4 font-semibold whitespace-nowrap">
                      HTTP Status
                    </th>
                    <th className="py-2.5 px-4 font-semibold whitespace-nowrap">
                      Latencia
                    </th>
                    <th className="py-2.5 pl-4 font-semibold">Detalle Error</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border-subtle)]">
                  {incidents.map((inc, idx) => {
                    const meta = CATEGORY_META[inc.statusCategory];
                    return (
                      <tr
                        key={`${inc.name}-${inc.timestamp}-${idx}`}
                        className="hover:bg-[var(--surface-elevated)]/50"
                      >
                        <td className="py-3 pr-4 font-mono text-xs text-[var(--text-secondary)] whitespace-nowrap">
                          {formatShortTimestamp(inc.timestamp)}
                        </td>
                        <td className="py-3 px-4 font-medium text-[var(--text-primary)] whitespace-nowrap">
                          {inc.name}
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap">
                          <span
                            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap ${meta.badgeClass}`}
                          >
                            <span
                              className="h-1.5 w-1.5 rounded-full"
                              style={{ backgroundColor: meta.dotColor }}
                            />
                            {meta.label}
                          </span>
                        </td>
                        <td className="py-3 px-4 font-mono text-[var(--text-secondary)] whitespace-nowrap">
                          {inc.statusCode !== null ? inc.statusCode : "—"}
                        </td>
                        <td className="py-3 px-4 font-mono text-[var(--text-secondary)] whitespace-nowrap">
                          {inc.latencyMs.toFixed(1)} ms
                        </td>
                        <td className="py-3 pl-4 text-[var(--text-secondary)] min-w-[240px]">
                          {inc.error ?? "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

export default App;
