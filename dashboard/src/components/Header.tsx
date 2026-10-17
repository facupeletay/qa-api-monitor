import { formatShortTimestamp } from "../lib/history";
import type { TimeWindow } from "../types";
import { WindowSelector } from "./WindowSelector";

export interface HeaderProps {
  generatedAt: string;
  runsCount: number;
  allOk: boolean;
  failingCount: number;
  windowRange: TimeWindow;
  onWindowChange: (window: TimeWindow) => void;
}

export function Header({
  generatedAt,
  runsCount,
  allOk,
  failingCount,
  windowRange,
  onWindowChange,
}: HeaderProps) {
  return (
    <header className="border-b border-[var(--border-subtle)] bg-[var(--surface-secondary)]">
      <div className="mx-auto max-w-7xl px-4 py-5 sm:px-6 lg:px-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-[var(--text-primary)]">
              QA API Monitor
            </h1>
            <span
              className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold whitespace-nowrap ${
                allOk
                  ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                  : "bg-rose-500/15 text-rose-400 border-rose-500/30"
              }`}
            >
              <span
                className="h-2 w-2 rounded-full"
                style={{
                  backgroundColor: allOk ? "#10b981" : "#f43f5e",
                }}
              />
              {allOk ? "Todo OK" : `Hay problemas (${failingCount})`}
            </span>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs sm:text-sm text-[var(--text-muted)]">
            <span>
              Última actualización:{" "}
              <strong className="font-medium text-[var(--text-secondary)] whitespace-nowrap">
                {formatShortTimestamp(generatedAt)} UTC
              </strong>
            </span>
            <span>
              Corridas acumuladas:{" "}
              <strong className="font-medium text-[var(--text-secondary)] whitespace-nowrap">
                {runsCount}
              </strong>
            </span>
          </div>
        </div>

        <WindowSelector value={windowRange} onChange={onWindowChange} />
      </div>
    </header>
  );
}
