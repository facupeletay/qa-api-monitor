import { cardHasIssues, cardIsDegraded } from "../lib/history";
import {
  ALL_MONITOR_SECTORS,
  type MonitorCardView,
  type SectorFilter,
  type StatusFilter,
} from "../types";
import { SECTOR_META } from "./categoryMeta";

export interface MonitorFiltersProps {
  cards: readonly MonitorCardView[];
  filteredCount: number;
  query: string;
  sectorFilter: SectorFilter;
  statusFilter: StatusFilter;
  groupedBySector: boolean;
  onQueryChange: (value: string) => void;
  onSectorChange: (sector: SectorFilter) => void;
  onStatusChange: (status: StatusFilter) => void;
  onGroupedChange: (grouped: boolean) => void;
  onReset: () => void;
}

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "Todos" },
  { value: "ok", label: "OK" },
  { value: "issues", label: "Con incidentes" },
  { value: "degraded", label: "Degradado (SLA)" },
];

export function MonitorFilters({
  cards,
  filteredCount,
  query,
  sectorFilter,
  statusFilter,
  groupedBySector,
  onQueryChange,
  onSectorChange,
  onStatusChange,
  onGroupedChange,
  onReset,
}: MonitorFiltersProps) {
  const hasActiveFilters =
    query.trim().length > 0 || sectorFilter !== "all" || statusFilter !== "all";

  const sectorCounts: Record<SectorFilter, number> = {
    all: cards.length,
    finanzas: cards.filter((c) => c.sector === "finanzas").length,
    sgr_pyme: cards.filter((c) => c.sector === "sgr_pyme").length,
    datos_publicos: cards.filter((c) => c.sector === "datos_publicos").length,
    infra_cripto: cards.filter((c) => c.sector === "infra_cripto").length,
  };

  const statusCounts: Record<StatusFilter, number> = {
    all: cards.length,
    ok: cards.filter((c) => c.lastStatusCategory === "ok").length,
    issues: cards.filter((c) => cardHasIssues(c)).length,
    degraded: cards.filter((c) => cardIsDegraded(c)).length,
  };

  const sectorOptions: { value: SectorFilter; label: string }[] = [
    { value: "all", label: "Todos los rubros" },
    ...ALL_MONITOR_SECTORS.map((sec) => ({
      value: sec as SectorFilter,
      label: SECTOR_META[sec].shortLabel,
    })),
  ];

  return (
    <form
      role="search"
      action="#monitors-heading"
      method="GET"
      onSubmit={(e) => e.preventDefault()}
      aria-label="Filtros y búsqueda de monitores"
      className="mb-5 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-secondary)] p-4 shadow-sm space-y-4"
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="flex-1 min-w-0">
          <label
            htmlFor="monitor-search-input"
            className="block mb-1.5 text-xs font-semibold text-[var(--text-secondary)]"
          >
            Buscar por servicio o endpoint URL
          </label>
          <input
            id="monitor-search-input"
            name="q"
            type="search"
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder="Ej. BCRA, SGR, MAV, dolarapi.com..."
            autoCorrect="off"
            autoCapitalize="off"
            spellCheck={false}
            enterKeyHint="search"
            className="w-full rounded-lg border border-[var(--border-strong)] bg-[var(--surface-primary)] px-3.5 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-500"
          />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <label className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-strong)] bg-[var(--surface-primary)] px-3 py-2 text-xs font-medium text-[var(--text-secondary)] cursor-pointer select-none">
            <input
              type="checkbox"
              name="grouped_by_sector"
              checked={groupedBySector}
              onChange={(e) => onGroupedChange(e.target.checked)}
              className="h-4 w-4 rounded accent-sky-500"
            />
            Agrupar por rubro
          </label>

          {hasActiveFilters && (
            <button
              type="button"
              onClick={onReset}
              className="rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-2 text-xs font-semibold text-sky-400 hover:bg-sky-500/20 cursor-pointer"
            >
              Limpiar filtros
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2 pt-2 border-t border-[var(--border-subtle)]">
        <fieldset className="min-w-0 border-0 p-0 m-0">
          <legend className="mb-1.5 text-xs font-semibold text-[var(--text-secondary)]">
            Filtrar por rubro
          </legend>
          <div className="flex flex-wrap gap-1.5">
            {sectorOptions.map((opt) => {
              const active = sectorFilter === opt.value;
              const count = sectorCounts[opt.value];
              return (
                <label
                  key={opt.value}
                  className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors cursor-pointer select-none ${
                    active
                      ? "border-sky-500 bg-sky-500/15 text-sky-400"
                      : "border-[var(--border-strong)] bg-[var(--surface-primary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                  }`}
                >
                  <input
                    type="radio"
                    name="sector_filter"
                    value={opt.value}
                    checked={active}
                    onChange={() => onSectorChange(opt.value)}
                    className="sr-only"
                  />
                  <span>{opt.label}</span>
                  <span
                    className={`rounded-full px-1.5 py-0.2 text-[11px] font-semibold ${
                      active
                        ? "bg-sky-500/25 text-sky-300"
                        : "bg-[var(--surface-elevated)] text-[var(--text-muted)]"
                    }`}
                  >
                    {count}
                  </span>
                </label>
              );
            })}
          </div>
        </fieldset>

        <fieldset className="min-w-0 border-0 p-0 m-0">
          <legend className="mb-1.5 text-xs font-semibold text-[var(--text-secondary)]">
            Filtrar por estado
          </legend>
          <div className="flex flex-wrap gap-1.5">
            {STATUS_OPTIONS.map((opt) => {
              const active = statusFilter === opt.value;
              const count = statusCounts[opt.value];
              return (
                <label
                  key={opt.value}
                  className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors cursor-pointer select-none ${
                    active
                      ? "border-sky-500 bg-sky-500/15 text-sky-400"
                      : "border-[var(--border-strong)] bg-[var(--surface-primary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                  }`}
                >
                  <input
                    type="radio"
                    name="status_filter"
                    value={opt.value}
                    checked={active}
                    onChange={() => onStatusChange(opt.value)}
                    className="sr-only"
                  />
                  <span>{opt.label}</span>
                  <span
                    className={`rounded-full px-1.5 py-0.2 text-[11px] font-semibold ${
                      active
                        ? "bg-sky-500/25 text-sky-300"
                        : "bg-[var(--surface-elevated)] text-[var(--text-muted)]"
                    }`}
                  >
                    {count}
                  </span>
                </label>
              );
            })}
          </div>
        </fieldset>
      </div>

      <div
        aria-live="polite"
        className="flex items-center justify-between text-xs text-[var(--text-muted)]"
      >
        <span>
          Mostrando{" "}
          <strong className="font-semibold text-[var(--text-primary)]">
            {filteredCount}
          </strong>{" "}
          de{" "}
          <strong className="font-semibold text-[var(--text-primary)]">
            {cards.length}
          </strong>{" "}
          monitores
        </span>
      </div>
    </form>
  );
}
