import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { DailyUptimePoint, TimeWindow } from "../types";

export interface DailyUptimeChartProps {
  dailyUptime: DailyUptimePoint[];
  windowRange: TimeWindow;
}

export function DailyUptimeChart({
  dailyUptime,
  windowRange,
}: DailyUptimeChartProps) {
  return (
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
  );
}
