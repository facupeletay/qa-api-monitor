"""Tests para el runner de checks HTTP, reintentos, backoff y clasificación de fallas."""

from __future__ import annotations

import httpx
import pytest
import respx

from monitor.models import MonitorConfig
from monitor.runner import execute_check


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Evita esperas reales en los tests y registra las llamadas a sleep."""
    calls: list[float] = []
    monkeypatch.setattr("monitor.runner.sleep", lambda seconds: calls.append(seconds))
    return calls


def _make_monitor(**overrides: object) -> MonitorConfig:
    defaults: dict[str, object] = {
        "name": "Test API",
        "url": "https://api.example.com/health",
        "method": "GET",
        "expected_status": 200,
        "max_latency_ms": 500.0,
        "timeout_s": 2.0,
        "retries": 2,
        "backoff_base_s": 0.5,
        "contract": None,
    }
    defaults.update(overrides)
    return MonitorConfig.model_validate(defaults)


@respx.mock
def test_category_ok_fast_response() -> None:
    """Categoría ok: status esperado, contrato válido y latencia dentro del SLA."""
    monitor = _make_monitor(
        url="https://dolarapi.com/v1/dolares/oficial",
        contract="dolar_api",
    )
    respx.get(monitor.url).mock(
        return_value=httpx.Response(
            200,
            json={
                "moneda": "USD",
                "casa": "oficial",
                "nombre": "Oficial",
                "compra": 1485,
                "venta": 1535,
                "fechaActualizacion": "2026-10-16T18:55:00.000Z",
            },
        )
    )

    result = execute_check(monitor)

    assert result.status_category == "ok"
    assert result.ok is True
    assert result.status_code == 200
    assert result.attempts == 1
    assert result.error is None
    assert result.total_duration_ms >= result.latency_ms


@respx.mock
def test_category_degraded_when_latency_exceeds_sla(monkeypatch: pytest.MonkeyPatch) -> None:
    """Categoría degraded: status y contrato bien, pero latencia supera max_latency_ms."""
    monitor = _make_monitor(max_latency_ms=100.0, retries=2)
    respx.get(monitor.url).mock(return_value=httpx.Response(200, json={"status": "slow"}))

    ticks = iter([10.0, 10.0, 10.25, 10.25])
    monkeypatch.setattr("monitor.runner.perf_counter", lambda: next(ticks))

    result = execute_check(monitor)

    assert result.status_category == "degraded"
    assert result.ok is False
    assert result.status_code == 200
    assert result.latency_ms == pytest.approx(250.0)
    assert result.total_duration_ms == pytest.approx(250.0)
    assert result.attempts == 1
    assert result.error is not None
    assert "latencia" in result.error.lower()


@respx.mock
def test_category_contract_error_when_schema_invalid() -> None:
    """Categoría contract_error: status esperado pero JSON no cumple el contrato."""
    monitor = _make_monitor(contract="dolar_api")
    respx.get(monitor.url).mock(return_value=httpx.Response(200, json={"moneda": "USD"}))

    result = execute_check(monitor)

    assert result.status_category == "contract_error"
    assert result.ok is False
    assert result.status_code == 200
    assert result.error is not None


@respx.mock
def test_category_client_error_on_4xx_without_retry() -> None:
    """Categoría client_error: 4xx y no reintenta."""
    monitor = _make_monitor(retries=3)
    sleep_calls: list[float] = []
    route = respx.get(monitor.url).mock(return_value=httpx.Response(404, text="Not Found"))

    result = execute_check(monitor, sleep_fn=sleep_calls.append)

    assert result.status_category == "client_error"
    assert result.ok is False
    assert result.status_code == 404
    assert result.attempts == 1
    assert route.call_count == 1
    assert sleep_calls == []
    assert result.error is not None
    assert "404" in result.error


@respx.mock
def test_category_server_error_after_exhausting_retries() -> None:
    """Categoría server_error: 5xx después de agotar reintentos."""
    monitor = _make_monitor(retries=1)
    route = respx.get(monitor.url).mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )

    result = execute_check(monitor)

    assert result.status_category == "server_error"
    assert result.ok is False
    assert result.status_code == 500
    assert result.attempts == 2
    assert route.call_count == 2
    assert result.error is not None
    assert "500" in result.error


@respx.mock
def test_category_network_error_on_timeout_all_attempts() -> None:
    """Categoría network_error: timeout en todos los intentos (attempts = retries + 1)."""
    monitor = _make_monitor(retries=2, backoff_base_s=0.5)
    sleep_calls: list[float] = []
    route = respx.get(monitor.url).mock(side_effect=httpx.ReadTimeout("Read timed out"))

    result = execute_check(monitor, sleep_fn=sleep_calls.append)

    assert result.status_category == "network_error"
    assert result.ok is False
    assert result.status_code is None
    assert result.attempts == monitor.retries + 1 == 3
    assert route.call_count == 3
    assert sleep_calls == [0.5, 1.0]
    assert result.error is not None
    assert "timeout" in result.error.lower() or "timed out" in result.error.lower()


@respx.mock
def test_5xx_5xx_200_exponential_backoff_calls_sleep() -> None:
    """5xx -> 5xx -> 200: attempts=3, se llamó a sleep con 0.5 y 1.0."""
    monitor = _make_monitor(retries=3, backoff_base_s=0.5)
    sleep_calls: list[float] = []
    route = respx.get(monitor.url).mock(
        side_effect=[
            httpx.Response(502, text="Bad Gateway"),
            httpx.Response(503, text="Service Unavailable"),
            httpx.Response(200, json={"status": "ok"}),
        ]
    )

    result = execute_check(monitor, sleep_fn=sleep_calls.append)

    assert result.status_category == "ok"
    assert result.ok is True
    assert result.status_code == 200
    assert result.attempts == 3
    assert route.call_count == 3
    assert sleep_calls == [0.5, 1.0]
    assert result.error is None


@respx.mock
def test_latency_ms_is_last_attempt_and_total_duration_is_greater_or_equal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """latency_ms corresponde solo al último intento y total_duration_ms es mayor o igual."""
    monitor = _make_monitor(retries=2, max_latency_ms=100.0, backoff_base_s=0.5)
    respx.get(monitor.url).mock(
        side_effect=[
            httpx.Response(503, text="Slow fail 1"),
            httpx.Response(200, json={"status": "fast success"}),
        ]
    )

    ticks = iter([0.000, 0.000, 0.400, 0.900, 0.950, 0.950])
    monkeypatch.setattr("monitor.runner.perf_counter", lambda: next(ticks))

    result = execute_check(monitor)

    assert result.attempts == 2
    assert result.latency_ms == pytest.approx(50.0)
    assert result.total_duration_ms == pytest.approx(950.0)
    assert result.total_duration_ms >= result.latency_ms
    assert result.status_category == "ok"
    assert result.ok is True
