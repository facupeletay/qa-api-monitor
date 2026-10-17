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
    print("=" * 78)
    print("QA API MONITOR - RESULTADOS DE LA CORRIDA")
    print("=" * 78)
    for res in report.results:
        state = "OK  " if res.ok else "FAIL"
        status_display = str(res.status_code) if res.status_code is not None else "ERR"
        line = (
            f"[{state}] {res.name} | category={res.status_category} | status={status_display} "
            f"| latency={res.latency_ms:.2f}ms | total={res.total_duration_ms:.2f}ms "
            f"| attempts={res.attempts}"
        )
        print(line)
        if res.error:
            print(f"       -> {res.error}")
    print("-" * 78)
    non_ok_cats = ", ".join(
        f"{k}={v}" for k, v in report.summary.by_category.items() if k != "ok" and v > 0
    )
    extra = f" ({non_ok_cats})" if non_ok_cats else ""
    print(
        f"Resumen: Total={report.summary.total} | "
        f"OK={report.summary.ok} | Fallidos={report.summary.failed}{extra}"
    )
    print(f"Reporte guardado en: {output_path}")
    print("=" * 78)


def format_markdown_summary(report: RunReport, exit_code: int) -> str:
    """Genera una tabla Markdown de resumen de la corrida y el código de salida."""
    lines = [
        "### Resultados de QA API Monitor",
        "",
        "| Monitor | Categoría | Status | Latencia | Attempts |",
        "| :--- | :---: | :---: | ---: | ---: |",
    ]
    for res in report.results:
        status_str = str(res.status_code) if res.status_code is not None else "ERR"
        lines.append(
            f"| {res.name} | `{res.status_category}` | {status_str} "
            f"| {res.latency_ms:.2f} ms | {res.attempts} |"
        )
    lines.append("")
    lines.append(f"**Código de salida:** `{exit_code}`")
    return "\n".join(lines) + "\n"


def write_markdown_summary(report: RunReport, exit_code: int, summary_path: str | Path) -> Path:
    """Escribe (o agrega) la tabla Markdown en la ruta indicada (ej. $GITHUB_STEP_SUMMARY)."""
    target = Path(summary_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(format_markdown_summary(report, exit_code))
    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="monitor",
        description="Ejecuta checks de disponibilidad, contrato y latencia sobre APIs en YAML.",
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
    parser.add_argument(
        "--summary-md",
        default=None,
        help="Ruta opcional donde escribir un resumen en tabla Markdown (ej. $GITHUB_STEP_SUMMARY)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        monitors = load_config(args.config)
    except ConfigError as exc:
        print(f"Error de configuración: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Error interno al cargar configuración: {exc}", file=sys.stderr)
        return 2

    try:
        report = run_monitors(monitors)
        saved_path = save_report(report, args.output)
        print_console_summary(report, saved_path)
        exit_code = 0 if all(item.status_category == "ok" for item in report.results) else 1
        if args.summary_md:
            write_markdown_summary(report, exit_code, args.summary_md)
        return exit_code
    except Exception as exc:
        print(f"Error interno durante la ejecución del monitor: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
