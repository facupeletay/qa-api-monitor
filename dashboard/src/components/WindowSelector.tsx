import type { TimeWindow } from "../types";

const WINDOW_OPTIONS: { value: TimeWindow; label: string }[] = [
  { value: "24h", label: "24 h" },
  { value: "7d", label: "7 días" },
  { value: "30d", label: "30 días" },
];

export interface WindowSelectorProps {
  value: TimeWindow;
  onChange: (window: TimeWindow) => void;
}

export function WindowSelector({ value, onChange }: WindowSelectorProps) {
  return (
    <div
      role="group"
      aria-label="Selector de ventana temporal"
      className="inline-flex self-start sm:self-auto rounded-lg border border-[var(--border-strong)] bg-[var(--surface-primary)] p-1"
    >
      {WINDOW_OPTIONS.map((opt) => {
        const active = value === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            aria-pressed={active}
            className={`rounded-md px-3.5 py-1.5 text-xs sm:text-sm font-medium transition-colors whitespace-nowrap cursor-pointer ${
              active
                ? "bg-sky-500 text-white shadow-sm"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
