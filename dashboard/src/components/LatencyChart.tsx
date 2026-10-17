import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { LatencySeriesPoint } from "../types";

export interface LatencyChartProps {
  monitorName: string;
  maxLatencyMs: number | null;
  series: LatencySeriesPoint[];
}

export function LatencyChart({
  monitorName,
  maxLatencyMs,
  series,
}: LatencyChartProps) {
  const maxSeriesVal = series.reduce(
    (acc, pt) =>
      pt.latencyMs !== null && pt.latencyMs > acc ? pt.latencyMs : acc,
    0,
  );
  const yMax = Math.ceil(
    Math.max(maxSeriesVal, maxLatencyMs ?? 0, 100) * 1.15,
  );

  return (
    <div className="min-w-0 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-secondary)] p-5 shadow-sm">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">
            {monitorName}
          </h3>
          <p className="text-xs text-[var(--text-muted)]">
            Latencia por corrida (ms)
          </p>
        </div>
        {maxLatencyMs !== null && (
          <span className="rounded-md bg-amber-500/10 border border-amber-500/30 px-2.5 py-1 text-xs font-medium text-amber-400 whitespace-nowrap">
            SLA: {maxLatencyMs} ms
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
            {maxLatencyMs !== null && (
              <ReferenceLine
                y={maxLatencyMs}
                stroke="#f59e0b"
                strokeDasharray="5 5"
                label={{
                  value: `SLA (${maxLatencyMs} ms)`,
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
}
