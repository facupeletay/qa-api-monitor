export function LoadingState() {
  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div
        role="status"
        className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-secondary)] px-8 py-10 text-center shadow-lg max-w-md w-full"
      >
        <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-sky-500 border-t-transparent" />
        <p className="text-base font-medium text-[var(--text-primary)]">
          Cargando historial de monitoreo...
        </p>
        <p className="mt-1 text-sm text-[var(--text-muted)]">
          Consultando métricas recientes de history.json
        </p>
      </div>
    </div>
  );
}

export interface ErrorStateProps {
  message: string;
}

export function ErrorState({ message }: ErrorStateProps) {
  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div
        role="alert"
        className="rounded-xl border border-rose-500/40 bg-[var(--surface-secondary)] px-8 py-10 text-center shadow-lg max-w-lg w-full"
      >
        <div className="mx-auto mb-3 inline-flex h-10 w-10 items-center justify-center rounded-full bg-rose-500/15 text-rose-400 font-bold">
          !
        </div>
        <h1 className="text-lg font-semibold text-[var(--text-primary)]">
          Error al cargar los datos
        </h1>
        <p className="mt-2 text-sm text-rose-400">{message}</p>
      </div>
    </div>
  );
}

export function EmptyState() {
  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-secondary)] px-8 py-10 text-center shadow-lg max-w-lg w-full">
        <h1 className="text-lg font-semibold text-[var(--text-primary)]">
          QA API Monitor
        </h1>
        <p className="mt-2 text-base text-[var(--text-secondary)]">
          Todavía no hay datos disponibles en el historial.
        </p>
        <p className="mt-1 text-sm text-[var(--text-muted)]">
          El dashboard se actualizará automáticamente tras la primera corrida.
        </p>
      </div>
    </div>
  );
}
