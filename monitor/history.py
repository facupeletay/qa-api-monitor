"""Gestión del historial de corridas (30 días) y cálculo de estadísticas 24h / 7d."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from pydantic import BaseModel, ValidationError

from monitor.models import (
    ALL_STATUS_CATEGORIES,
    CheckResult,
    RunReport,
    StatusCategory,
)

RETENTION_DAYS = 30


class HistoryError(RuntimeError):
    """Error al obtener, validar o procesar el historial de corridas."""


class HistoryRun(BaseModel):
    """Una corrida almacenada dentro del historial."""

    timestamp: str
    results: list[CheckResult]


class WindowStats(BaseModel):
    """Métricas agregadas de un monitor para una ventana temporal (24h o 7d)."""

    total_checks: int
    uptime_pct: float | None
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    by_category: dict[StatusCategory, int]


class MonitorStats(BaseModel):
    """Estadísticas consolidadas de un monitor en history.json."""

    last_status_category: StatusCategory
    last_timestamp: str
    window_24h: WindowStats
    window_7d: WindowStats


class HistoryReport(BaseModel):
    """Estructura raíz de history.json."""

    generated_at: str
    runs: list[HistoryRun]
    stats: dict[str, MonitorStats]


def _parse_iso_utc(ts: str) -> datetime:
    normalized = ts.replace("Z", "+00:00") if ts.endswith("Z") else ts
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _format_iso_utc(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _percentile(sorted_values: list[float], q: float) -> float | None:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return round(sorted_values[0], 2)
    pos = (len(sorted_values) - 1) * q
    low = math.floor(pos)
    high = math.ceil(pos)
    if low == high:
        return round(sorted_values[low], 2)
    interpolated = sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (pos - low)
    return round(interpolated, 2)


def _compute_window_stats(checks: list[CheckResult]) -> WindowStats:
    by_category: dict[StatusCategory, int] = {cat: 0 for cat in ALL_STATUS_CATEGORIES}
    latencies: list[float] = []

    for check in checks:
        by_category[check.status_category] += 1
        if check.status_code is not None:
            latencies.append(check.latency_ms)

    latencies.sort()
    total = len(checks)
    uptime_pct = round((by_category["ok"] / total) * 100.0, 2) if total > 0 else None

    return WindowStats(
        total_checks=total,
        uptime_pct=uptime_pct,
        latency_p50_ms=_percentile(latencies, 0.50),
        latency_p95_ms=_percentile(latencies, 0.95),
        by_category=by_category,
    )


def merge_history(
    previous: HistoryReport | None,
    new_run: RunReport,
    now: datetime | None = None,
) -> HistoryReport:
    """Agrega `new_run` al historial previo, descarta corridas > 30 días y recalcula stats."""
    ref_now = now.astimezone(UTC) if now is not None else datetime.now(UTC)
    generated_at = _format_iso_utc(ref_now)

    run_ts = new_run.results[0].timestamp if new_run.results else generated_at
    existing_runs = list(previous.runs) if previous is not None else []
    existing_runs.append(HistoryRun(timestamp=run_ts, results=new_run.results))

    cutoff_30d = ref_now - timedelta(days=RETENTION_DAYS)
    kept_runs = [run for run in existing_runs if _parse_iso_utc(run.timestamp) >= cutoff_30d]
    kept_runs.sort(key=lambda r: _parse_iso_utc(r.timestamp))

    # Agrupamos todos los checks por monitor ordenados cronológicamente
    checks_by_monitor: dict[str, list[CheckResult]] = {}
    for run in kept_runs:
        for res in run.results:
            checks_by_monitor.setdefault(res.name, []).append(res)

    cutoff_24h = ref_now - timedelta(hours=24)
    cutoff_7d = ref_now - timedelta(days=7)

    stats: dict[str, MonitorStats] = {}
    for monitor_name, checks in checks_by_monitor.items():
        checks.sort(key=lambda c: _parse_iso_utc(c.timestamp))
        last_check = checks[-1]
        checks_24h = [c for c in checks if _parse_iso_utc(c.timestamp) >= cutoff_24h]
        checks_7d = [c for c in checks if _parse_iso_utc(c.timestamp) >= cutoff_7d]

        stats[monitor_name] = MonitorStats(
            last_status_category=last_check.status_category,
            last_timestamp=last_check.timestamp,
            window_24h=_compute_window_stats(checks_24h),
            window_7d=_compute_window_stats(checks_7d),
        )

    return HistoryReport(
        generated_at=generated_at,
        runs=kept_runs,
        stats=stats,
    )


def load_previous_history(source: str | None) -> HistoryReport | None:
    """Obtiene el historial anterior desde una URL HTTP/HTTPS o un archivo local.

    - Si `source` es una URL y devuelve 404: retorna None (primera corrida).
    - Si `source` falla por timeout, error de red, 5xx o JSON corrupto/inválido:
      lanza HistoryError para evitar pisar el historial con uno vacío.
    """
    if not source:
        return None

    trimmed = source.strip()
    if trimmed.startswith(("http://", "https://")):
        try:
            response = httpx.get(
                trimmed,
                headers={"Cache-Control": "no-cache"},
                timeout=10.0,
                follow_redirects=True,
            )
        except httpx.HTTPError as exc:
            raise HistoryError(
                f"No se pudo descargar el historial anterior desde {trimmed} "
                f"({type(exc).__name__}: {exc})"
            ) from exc

        if response.status_code == 404:
            return None

        if response.status_code != 200:
            raise HistoryError(
                f"Respuesta inesperada al descargar historial desde {trimmed}: "
                f"HTTP {response.status_code}"
            )

        raw_text = response.text
    else:
        path = Path(trimmed)
        if not path.is_file():
            raise HistoryError(f"No se encontró el archivo de historial previo: {path}")
        raw_text = path.read_text(encoding="utf-8")

    try:
        data = json.loads(raw_text)
    except ValueError as exc:
        raise HistoryError(
            f"El historial anterior en '{trimmed}' no contiene JSON válido: {exc}"
        ) from exc

    try:
        return HistoryReport.model_validate(data)
    except ValidationError as exc:
        raise HistoryError(
            f"El historial anterior en '{trimmed}' tiene un formato inválido:\n{exc}"
        ) from exc


def load_run_report(path: str | Path) -> RunReport:
    """Carga y valida el archivo run.json de la corrida actual."""
    run_path = Path(path)
    if not run_path.is_file():
        raise HistoryError(f"No se encontró el archivo de corrida actual: {run_path}")
    try:
        data = json.loads(run_path.read_text(encoding="utf-8"))
        return RunReport.model_validate(data)
    except (ValueError, ValidationError) as exc:
        raise HistoryError(f"Archivo de corrida inválido ({run_path}): {exc}") from exc


def save_history(report: HistoryReport, output_path: str | Path) -> Path:
    """Guarda history.json creando el directorio destino si no existe."""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report.model_dump(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="monitor.history",
        description="Combina el historial previo con la última corrida y genera history.json.",
    )
    parser.add_argument(
        "--previous",
        default=None,
        help="Ruta local o URL del history.json anterior (ej. GitHub Pages).",
    )
    parser.add_argument(
        "--run",
        default="results/run.json",
        help="Ruta al archivo run.json de la corrida actual (default: results/run.json).",
    )
    parser.add_argument(
        "--output",
        default="site/history.json",
        help="Ruta de salida para history.json (default: site/history.json).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        previous = load_previous_history(args.previous)
        current_run = load_run_report(args.run)
        merged = merge_history(previous, current_run)
        saved = save_history(merged, args.output)
    except HistoryError as exc:
        print(f"Error de historial: {exc}", file=sys.stderr)
        return 1

    print(f"Historial actualizado en {saved} (corridas almacenadas: {len(merged.runs)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
