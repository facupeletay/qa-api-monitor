export type StatusCategory =
  | "ok"
  | "degraded"
  | "contract_error"
  | "client_error"
  | "server_error"
  | "network_error";

export const ALL_STATUS_CATEGORIES: readonly StatusCategory[] = [
  "ok",
  "degraded",
  "contract_error",
  "client_error",
  "server_error",
  "network_error",
] as const;

export interface CheckResult {
  name: string;
  url: string;
  timestamp: string;
  status_code: number | null;
  latency_ms: number;
  total_duration_ms: number;
  status_category: StatusCategory;
  error: string | null;
  attempts: number;
  ok: boolean;
}

export interface HistoryRun {
  timestamp: string;
  results: CheckResult[];
}

export interface WindowStats {
  total_checks: number;
  uptime_pct: number | null;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
  by_category: Record<StatusCategory, number>;
}

export interface MonitorStats {
  last_status_category: StatusCategory;
  last_timestamp: string;
  max_latency_ms: number | null;
  window_24h: WindowStats;
  window_7d: WindowStats;
}

export interface HistoryReport {
  generated_at: string;
  runs: HistoryRun[];
  stats: Record<string, MonitorStats>;
}

export type TimeWindow = "24h" | "7d" | "30d";

export interface MonitorCardView {
  name: string;
  lastStatusCategory: StatusCategory;
  lastTimestamp: string;
  maxLatencyMs: number | null;
  windowStats: WindowStats;
}

export interface LatencySeriesPoint {
  timestamp: string;
  label: string;
  latencyMs: number | null;
  statusCategory: StatusCategory;
  statusCode: number | null;
}

export interface DailyUptimePoint {
  date: string;
  label: string;
  uptimePct: number;
  totalChecks: number;
  okChecks: number;
  byMonitor: Record<string, number | null>;
}

export interface CategoryDistributionItem {
  category: StatusCategory;
  count: number;
  percentage: number;
}

export interface IncidentItem {
  name: string;
  url: string;
  timestamp: string;
  statusCategory: StatusCategory;
  statusCode: number | null;
  latencyMs: number;
  error: string | null;
}
