import { useEffect, useMemo, useState } from "react";
import { CategoryDistribution } from "./components/CategoryDistribution";
import { DailyUptimeChart } from "./components/DailyUptimeChart";
import { Header } from "./components/Header";
import { IncidentsTable } from "./components/IncidentsTable";
import { LatencyChart } from "./components/LatencyChart";
import { MonitorCard } from "./components/MonitorCard";
import { MonitorFilters } from "./components/MonitorFilters";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "./components/StatusStates";
import { SECTOR_META } from "./components/categoryMeta";
import {
  buildCategoryDistribution,
  buildDailyUptimeSeries,
  buildLatencySeriesByMonitor,
  buildMonitorCards,
  filterMonitorCards,
  getOverallStatus,
  listIncidents,
} from "./lib/history";
import {
  ALL_MONITOR_SECTORS,
  type HistoryReport,
  type SectorFilter,
  type StatusFilter,
  type TimeWindow,
} from "./types";

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
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [sectorFilter, setSectorFilter] = useState<SectorFilter>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [groupedBySector, setGroupedBySector] = useState<boolean>(true);

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
    () =>
      report ? getOverallStatus(report) : { allOk: true, failingCount: 0 },
    [report],
  );

  const monitorCards = useMemo(
    () => (report ? buildMonitorCards(report, windowRange) : []),
    [report, windowRange],
  );

  const filteredMonitorCards = useMemo(
    () =>
      filterMonitorCards(monitorCards, {
        query: searchQuery,
        sector: sectorFilter,
        status: statusFilter,
      }),
    [monitorCards, searchQuery, sectorFilter, statusFilter],
  );

  const visibleMonitorNames = useMemo(
    () => new Set(filteredMonitorCards.map((c) => c.name)),
    [filteredMonitorCards],
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

  const incidents = useMemo(() => {
    if (!report) {
      return [];
    }
    const allIncidents = listIncidents(report, windowRange);
    const hasFilter =
      searchQuery.trim().length > 0 ||
      sectorFilter !== "all" ||
      statusFilter !== "all";
    if (!hasFilter) {
      return allIncidents;
    }
    return allIncidents.filter((inc) => visibleMonitorNames.has(inc.name));
  }, [
    report,
    windowRange,
    searchQuery,
    sectorFilter,
    statusFilter,
    visibleMonitorNames,
  ]);

  const handleResetFilters = () => {
    setSearchQuery("");
    setSectorFilter("all");
    setStatusFilter("all");
  };

  if (loading) {
    return <LoadingState />;
  }

  if (error) {
    return <ErrorState message={error} />;
  }

  if (!report || report.runs.length === 0) {
    return <EmptyState />;
  }

  return (
    <div className="min-h-screen pb-14 overflow-x-hidden">
      <Header
        generatedAt={report.generated_at}
        runsCount={report.runs.length}
        allOk={overallStatus.allOk}
        failingCount={overallStatus.failingCount}
        windowRange={windowRange}
        onWindowChange={setWindowRange}
      />

      <main className="mx-auto max-w-7xl px-4 pt-6 sm:px-6 lg:px-8 space-y-8">
        <section aria-labelledby="monitors-heading" className="min-w-0">
          <div className="mb-3 flex items-center justify-between">
            <h2
              id="monitors-heading"
              className="text-base sm:text-lg font-semibold text-[var(--text-primary)]"
            >
              Estado por Monitor ({windowRange})
            </h2>
          </div>

          <MonitorFilters
            cards={monitorCards}
            filteredCount={filteredMonitorCards.length}
            query={searchQuery}
            sectorFilter={sectorFilter}
            statusFilter={statusFilter}
            groupedBySector={groupedBySector}
            onQueryChange={setSearchQuery}
            onSectorChange={setSectorFilter}
            onStatusChange={setStatusFilter}
            onGroupedChange={setGroupedBySector}
            onReset={handleResetFilters}
          />

          {filteredMonitorCards.length === 0 ? (
            <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-secondary)] p-8 text-center">
              <p className="text-sm font-medium text-[var(--text-secondary)]">
                No se encontraron monitores que coincidan con los filtros
                seleccionados.
              </p>
              <button
                type="button"
                onClick={handleResetFilters}
                className="mt-3 rounded-lg border border-sky-500/40 bg-sky-500/10 px-4 py-2 text-xs font-semibold text-sky-400 hover:bg-sky-500/20 cursor-pointer"
              >
                Restablecer filtros
              </button>
            </div>
          ) : groupedBySector ? (
            <div className="space-y-6">
              {ALL_MONITOR_SECTORS.map((sectorKey) => {
                const groupCards = filteredMonitorCards.filter(
                  (c) => c.sector === sectorKey,
                );
                if (groupCards.length === 0) {
                  return null;
                }
                const sectorMeta = SECTOR_META[sectorKey];
                const okCount = groupCards.filter(
                  (c) => c.lastStatusCategory === "ok",
                ).length;

                return (
                  <div
                    key={sectorKey}
                    data-testid={`sector-group-${sectorKey}`}
                    className="space-y-3"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-subtle)] pb-2">
                      <div>
                        <h3 className="text-sm sm:text-base font-semibold text-[var(--text-primary)]">
                          {sectorMeta.label}
                        </h3>
                        <p className="text-xs text-[var(--text-muted)]">
                          {sectorMeta.description}
                        </p>
                      </div>
                      <span
                        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${
                          okCount === groupCards.length
                            ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
                            : "border-amber-500/30 bg-amber-500/10 text-amber-400"
                        }`}
                      >
                        {okCount}/{groupCards.length} OK
                      </span>
                    </div>

                    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                      {groupCards.map((card) => (
                        <MonitorCard
                          key={card.name}
                          card={card}
                          windowRange={windowRange}
                        />
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {filteredMonitorCards.map((card) => (
                <MonitorCard
                  key={card.name}
                  card={card}
                  windowRange={windowRange}
                />
              ))}
            </div>
          )}
        </section>

        {filteredMonitorCards.length > 0 && (
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
              {filteredMonitorCards.map((card) => (
                <LatencyChart
                  key={card.name}
                  monitorName={card.name}
                  maxLatencyMs={card.maxLatencyMs}
                  series={latencySeriesByMonitor[card.name] ?? []}
                />
              ))}
            </div>
          </section>
        )}

        <section className="grid grid-cols-1 gap-6 lg:grid-cols-3 min-w-0">
          <DailyUptimeChart
            dailyUptime={dailyUptime}
            windowRange={windowRange}
          />
          <CategoryDistribution
            items={categoryDistribution}
            windowRange={windowRange}
          />
        </section>

        <IncidentsTable incidents={incidents} windowRange={windowRange} />
      </main>
    </div>
  );
}

export default App;
