"""Punto de entrada CLI para ejecutar `python -m monitor`."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from monitor.config import ConfigError, load_config
from monitor.models import RunReport
from monitor.runner import run_monitors, save_report


def print_console_summary(report: RunReport, output_path: Path) -> None:
    """Imprime un resumen legible de la corrida por consola."""
    print("=" * 68)
    print("QA API MONITOR - RESULTADOS DE LA CORRIDA")
    print("=" * 68)
    for res in report.results:
        state = "OK  " if res.ok else "FAIL"
        status_display = str(res.status_code) if res.status_code is not None else "ERR"
        line = (
            f"[{state}] {res.name} | status={status_display} "
            f"| latency={res.latency_ms:.2f}ms | attempts={res.attempts}"
        )
        print(line)
        if res.error:
            print(f"       -> {res.error}")
    print("-" * 68)
    print(
        f"Resumen: Total={report.summary.total} | "
        f"OK={report.summary.ok} | Fallidos={report.summary.failed}"
    )
    print(f"Reporte guardado en: {output_path}")
    print("=" * 68)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="monitor",
        description="Ejecuta checks de disponibilidad y latencia sobre APIs configuradas en YAML.",
    )
    parser.add_argument(
        "--config",
        default="config/monitors.yaml",
        help="Ruta al archivo YAML de configuración (default: config/monitors.yaml)",
    )
    parser.add_argument(
        "--output",
        default="results/run.json",
        help="Ruta al archivo JSON de salida (default: results/run.json)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        monitors = load_config(args.config)
    except ConfigError as exc:
        print(f"Error de configuración: {exc}", file=sys.stderr)
        return 1

    report = run_monitors(monitors)
    saved_path = save_report(report, args.output)
    print_console_summary(report, saved_path)

    return 0 if report.summary.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
