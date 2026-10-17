"""Ejecución de checks HTTP, manejo de reintentos y generación de reportes."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import httpx

from monitor.models import CheckResult, MonitorConfig, RunReport, RunSummary


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def execute_check(
    monitor: MonitorConfig,
    client: httpx.Client | None = None,
) -> CheckResult:
    """Ejecuta el check de un monitor con soporte de reintentos ante red/timeout y 5xx."""
    max_attempts = monitor.retries + 1
    attempts = 0
    last_status: int | None = None
    last_latency_ms = 0.0
    last_error: str | None = None

    owns_client = client is None
    http_client = client if client is not None else httpx.Client()

    try:
        while attempts < max_attempts:
            attempts += 1
            start = perf_counter()
            try:
                response = http_client.request(
                    method=monitor.method,
                    url=monitor.url,
                    timeout=monitor.timeout_s,
                )
                elapsed_ms = round((perf_counter() - start) * 1000, 2)
                last_status = response.status_code
                last_latency_ms = elapsed_ms
                last_error = None
            except httpx.HTTPError as exc:
                elapsed_ms = round((perf_counter() - start) * 1000, 2)
                last_status = None
                last_latency_ms = elapsed_ms
                last_error = f"{type(exc).__name__}: {exc}"
                if attempts < max_attempts:
                    continue
                break

            # Si es 5xx y no es el status esperado, reintentamos si quedan intentos
            if (
                500 <= response.status_code < 600
                and response.status_code != monitor.expected_status
            ):
                last_error = (
                    f"Status inesperado: se esperaba {monitor.expected_status}, "
                    f"se recibió {response.status_code}"
                )
                if attempts < max_attempts:
                    continue
                break

            # Para 2xx, 3xx, 4xx (o 5xx esperado), no se reintenta
            break
    finally:
        if owns_client:
            http_client.close()

    if last_status is None:
        return CheckResult(
            name=monitor.name,
            url=monitor.url,
            timestamp=_utc_now_iso(),
            status_code=None,
            latency_ms=last_latency_ms,
            ok=False,
            error=last_error or "Error de red desconocido",
            attempts=attempts,
        )

    errors: list[str] = []
    if last_status != monitor.expected_status:
        errors.append(
            f"Status inesperado: se esperaba {monitor.expected_status}, se recibió {last_status}"
        )
    if last_latency_ms > monitor.max_latency_ms:
        errors.append(
            f"Latencia excedida: {last_latency_ms:.2f}ms > máximo {monitor.max_latency_ms:.2f}ms"
        )

    ok = len(errors) == 0
    return CheckResult(
        name=monitor.name,
        url=monitor.url,
        timestamp=_utc_now_iso(),
        status_code=last_status,
        latency_ms=last_latency_ms,
        ok=ok,
        error="; ".join(errors) if errors else None,
        attempts=attempts,
    )


def run_monitors(monitors: list[MonitorConfig]) -> RunReport:
    """Ejecuta todos los monitores configurados y devuelve el reporte consolidado."""
    results: list[CheckResult] = []
    with httpx.Client() as client:
        for monitor in monitors:
            results.append(execute_check(monitor, client=client))

    total = len(results)
    ok_count = sum(1 for item in results if item.ok)
    failed_count = total - ok_count

    return RunReport(
        summary=RunSummary(total=total, ok=ok_count, failed=failed_count),
        results=results,
    )


def save_report(report: RunReport, output_path: str | Path = Path("results/run.json")) -> Path:
    """Guarda el reporte en formato JSON creando el directorio de destino si no existe."""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report.model_dump(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target
