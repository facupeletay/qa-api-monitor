import { useEffect, useMemo, useState } from "react";
import { CategoryDistribution } from "./components/CategoryDistribution";
import { DailyUptimeChart } from "./components/DailyUptimeChart";
import { Header } from "./components/Header";
import { IncidentsTable } from "./components/IncidentsTable";
import { LatencyChart } from "./components/LatencyChart";
import { MonitorCard } from "./components/MonitorCard";
import { EmptyState, ErrorState, LoadingState } from "./components/StatusStates";
import {
  buildCategoryDistribution,
  buildDailyUptimeSeries,
  buildLatencySeriesByMonitor,
  buildMonitorCards,
  getOverallStatus,
  listIncidents,
} from "./lib/history";
import type { HistoryReport, TimeWindow } from "./types";

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

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {monitorCards.map((card) => (
              <MonitorCard
                key={card.name}
                card={card}
                windowRange={windowRange}
              />
            ))}
          </div>
        </section>

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
            {monitorCards.map((card) => (
              <LatencyChart
                key={card.name}
                monitorName={card.name}
                maxLatencyMs={card.maxLatencyMs}
                series={latencySeriesByMonitor[card.name] ?? []}
              />
            ))}
          </div>
        </section>

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
