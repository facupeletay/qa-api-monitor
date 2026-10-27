import type { MonitorSector, StatusCategory } from "../types";

export interface CategoryMeta {
  label: string;
  badgeClass: string;
  dotColor: string;
  barColor: string;
}

export interface SectorMeta {
  label: string;
  shortLabel: string;
  description: string;
  badgeClass: string;
}

export const CATEGORY_META: Record<StatusCategory, CategoryMeta> = {
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

export const SECTOR_META: Record<MonitorSector, SectorMeta> = {
  finanzas: {
    label: "Finanzas & BCRA",
    shortLabel: "Finanzas & BCRA",
    description: "Cotizaciones cambiarias, Riesgo País y variables monetarias",
    badgeClass:
      "bg-sky-500/10 text-sky-400 border-sky-500/25 light:text-sky-700",
  },
  sgr_pyme: {
    label: "Ecosistema SGR / PyME / MAV",
    shortLabel: "SGR / PyME / MAV",
    description:
      "Garantías recíprocas, ePyme Caja de Valores, CASFOG y Mercado Argentino de Valores",
    badgeClass:
      "bg-indigo-500/10 text-indigo-400 border-indigo-500/25 light:text-indigo-700",
  },
  datos_publicos: {
    label: "Datos Públicos & Clima",
    shortLabel: "Datos & Clima",
    description: "APIs geográficas nacionales y pronóstico meteorológico",
    badgeClass:
      "bg-teal-500/10 text-teal-400 border-teal-500/25 light:text-teal-700",
  },
  infra_cripto: {
    label: "Infraestructura & Cripto",
    shortLabel: "Infra & Cripto",
    description: "Estado de plataformas globales y cotizaciones cripto",
    badgeClass:
      "bg-fuchsia-500/10 text-fuchsia-400 border-fuchsia-500/25 light:text-fuchsia-700",
  },
};

export function formatNumber(val: number | null, suffix = ""): string {
  if (val === null || Number.isNaN(val)) {
    return "—";
  }
  return `${val.toFixed(1)}${suffix}`;
}
