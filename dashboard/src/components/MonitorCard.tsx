import { formatShortTimestamp } from "../lib/history";
import type { MonitorCardView, TimeWindow } from "../types";
import { CATEGORY_META, SECTOR_META, formatNumber } from "./categoryMeta";

export interface MonitorCardProps {
  card: MonitorCardView;
  windowRange: TimeWindow;
}

export function MonitorCard({ card, windowRange }: MonitorCardProps) {
  const meta = CATEGORY_META[card.lastStatusCategory];
  const sectorMeta = SECTOR_META[card.sector];

  return (
    <article className="min-w-0 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-secondary)] p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-base font-semibold text-[var(--text-primary)]">
              {card.name}
            </h3>
            <span
              className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-medium whitespace-nowrap ${sectorMeta.badgeClass}`}
            >
              {sectorMeta.shortLabel}
            </span>
          </div>
          {card.url && (
            <p
              className="mt-1 truncate font-mono text-xs text-[var(--text-muted)]"
              title={card.url}
            >
              {card.url}
            </p>
          )}
          <p className="mt-1 text-xs text-[var(--text-muted)]">
            Último check:{" "}
            <span className="whitespace-nowrap">
              {formatShortTimestamp(card.lastTimestamp)} UTC
            </span>
          </p>
        </div>
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold whitespace-nowrap shrink-0 ${meta.badgeClass}`}
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
            {formatNumber(card.windowStats.latency_p50_ms, " ms")}
          </span>
        </div>

        <div>
          <span className="block text-xs text-[var(--text-muted)]">
            Latencia p95
          </span>
          <span className="mt-1 block text-lg font-bold text-[var(--text-primary)] whitespace-nowrap">
            {formatNumber(card.windowStats.latency_p95_ms, " ms")}
          </span>
        </div>

        <div>
          <span className="block text-xs text-[var(--text-muted)]">
            SLA Máximo
          </span>
          <span className="mt-1 block text-lg font-semibold text-sky-400 whitespace-nowrap">
            {card.maxLatencyMs !== null ? `${card.maxLatencyMs} ms` : "—"}
          </span>
        </div>
      </div>
    </article>
  );
}
