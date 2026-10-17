import { formatShortTimestamp } from "../lib/history";
import type { IncidentItem, TimeWindow } from "../types";
import { CATEGORY_META } from "./categoryMeta";

export interface IncidentsTableProps {
  incidents: IncidentItem[];
  windowRange: TimeWindow;
}

export function IncidentsTable({
  incidents,
  windowRange,
}: IncidentsTableProps) {
  return (
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
  );
}
