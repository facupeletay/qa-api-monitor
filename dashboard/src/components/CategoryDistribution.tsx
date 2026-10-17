import type { CategoryDistributionItem, TimeWindow } from "../types";
import { CATEGORY_META } from "./categoryMeta";

export interface CategoryDistributionProps {
  items: CategoryDistributionItem[];
  windowRange: TimeWindow;
}

export function CategoryDistribution({
  items,
  windowRange,
}: CategoryDistributionProps) {
  return (
    <div className="min-w-0 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-secondary)] p-5 shadow-sm">
      <div className="mb-4">
        <h2 className="text-base font-semibold text-[var(--text-primary)]">
          Distribución de Categorías ({windowRange})
        </h2>
        <p className="text-xs text-[var(--text-muted)]">
          Proporción de resultados por clasificación
        </p>
      </div>

      <div className="space-y-3">
        {items.map((item) => {
          const meta = CATEGORY_META[item.category];
          return (
            <div key={item.category} className="space-y-1">
              <div className="flex items-center justify-between text-xs sm:text-sm">
                <span className="inline-flex items-center gap-2 font-medium text-[var(--text-secondary)]">
                  <span
                    className="h-2.5 w-2.5 rounded-full shrink-0"
                    style={{ backgroundColor: meta.dotColor }}
                  />
                  {meta.label}
                </span>
                <span className="font-semibold text-[var(--text-primary)] whitespace-nowrap">
                  {item.count} ({item.percentage.toFixed(1)} %)
                </span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-[var(--surface-elevated)]">
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${Math.min(100, item.percentage)}%`,
                    backgroundColor: meta.barColor,
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
