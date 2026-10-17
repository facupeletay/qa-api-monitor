"""Ejecución de checks HTTP, validación de contratos, clasificación y reportes."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter, sleep

import httpx

from monitor.contracts import validate_contract
from monitor.models import (
    ALL_STATUS_CATEGORIES,
    CheckResult,
    MonitorConfig,
    RunReport,
    RunSummary,
    StatusCategory,
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def execute_check(
    monitor: MonitorConfig,
    client: httpx.Client | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> CheckResult:
    """Ejecuta el check de un monitor con backoff exponencial, contrato y clasificación."""
    max_attempts = monitor.retries + 1
    attempts = 0
    last_response: httpx.Response | None = None
    last_status: int | None = None
    last_latency_ms = 0.0
    last_error: str | None = None

    wait_fn = sleep_fn if sleep_fn is not None else sleep
    owns_client = client is None
    http_client = client if client is not None else httpx.Client()

    check_start = perf_counter()
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
                last_response = response
                last_status = response.status_code
                last_latency_ms = elapsed_ms
                last_error = None
            except httpx.HTTPError as exc:
                elapsed_ms = round((perf_counter() - start) * 1000, 2)
                last_response = None
                last_status = None
                last_latency_ms = elapsed_ms
                last_error = f"{type(exc).__name__}: {exc}"
                if attempts < max_attempts:
                    delay = monitor.backoff_base_s * (2 ** (attempts - 1))
                    wait_fn(delay)
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
                    delay = monitor.backoff_base_s * (2 ** (attempts - 1))
                    wait_fn(delay)
                    continue
                break

            # Para 2xx, 3xx, 4xx (o 5xx esperado), no se reintenta
            break
    finally:
        if owns_client:
            http_client.close()

    raw_total_ms = round((perf_counter() - check_start) * 1000, 2)
    total_duration_ms = max(raw_total_ms, last_latency_ms)

    # Prioridad: network_error > server_error > client_error > contract_error > degraded > ok
    if last_status is None or last_response is None:
        return CheckResult(
            name=monitor.name,
            url=monitor.url,
            timestamp=_utc_now_iso(),
            status_code=None,
            latency_ms=last_latency_ms,
            total_duration_ms=total_duration_ms,
            status_category="network_error",
            error=last_error or "Error de red desconocido",
            attempts=attempts,
        )

    if last_status != monitor.expected_status:
        category: StatusCategory = "server_error" if 500 <= last_status < 600 else "client_error"
        return CheckResult(
            name=monitor.name,
            url=monitor.url,
            timestamp=_utc_now_iso(),
            status_code=last_status,
            latency_ms=last_latency_ms,
            total_duration_ms=total_duration_ms,
            status_category=category,
            error=(
                f"Status inesperado: se esperaba {monitor.expected_status}, "
                f"se recibió {last_status}"
            ),
            attempts=attempts,
        )

    # El status coincide con el esperado: validamos contrato si está configurado
    contract_issue: str | None = None
    if monitor.contract is not None:
        try:
            payload = last_response.json()
        except ValueError:
            contract_issue = (
                f"Contrato '{monitor.contract}' inválido: la respuesta no es JSON válido"
            )
        else:
            contract_issue = validate_contract(monitor.contract, payload)

    latency_issue: str | None = None
    if last_latency_ms > monitor.max_latency_ms:
        latency_issue = (
            f"Latencia excedida: {last_latency_ms:.2f}ms > máximo {monitor.max_latency_ms:.2f}ms"
        )

    if contract_issue is not None:
        errors = [contract_issue]
        if latency_issue is not None:
            errors.append(latency_issue)
        return CheckResult(
            name=monitor.name,
            url=monitor.url,
            timestamp=_utc_now_iso(),
            status_code=last_status,
            latency_ms=last_latency_ms,
            total_duration_ms=total_duration_ms,
            status_category="contract_error",
            error="; ".join(errors),
            attempts=attempts,
        )

    if latency_issue is not None:
        return CheckResult(
            name=monitor.name,
            url=monitor.url,
            timestamp=_utc_now_iso(),
            status_code=last_status,
            latency_ms=last_latency_ms,
            total_duration_ms=total_duration_ms,
            status_category="degraded",
            error=latency_issue,
            attempts=attempts,
        )

    return CheckResult(
        name=monitor.name,
        url=monitor.url,
        timestamp=_utc_now_iso(),
        status_code=last_status,
        latency_ms=last_latency_ms,
        total_duration_ms=total_duration_ms,
        status_category="ok",
        error=None,
        attempts=attempts,
    )


def run_monitors(monitors: list[MonitorConfig]) -> RunReport:
    """Ejecuta todos los monitores configurados y devuelve el reporte consolidado."""
    results: list[CheckResult] = []
    with httpx.Client() as client:
        for monitor in monitors:
            results.append(execute_check(monitor, client=client))

    total = len(results)
    by_category: dict[StatusCategory, int] = {cat: 0 for cat in ALL_STATUS_CATEGORIES}
    for item in results:
        by_category[item.status_category] += 1

    ok_count = by_category["ok"]
    failed_count = total - ok_count

    return RunReport(
        summary=RunSummary(
            total=total,
            ok=ok_count,
            failed=failed_count,
            by_category=by_category,
        ),
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
