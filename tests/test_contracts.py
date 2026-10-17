"""Tests para validación de contratos JSON y registro de contratos."""

from __future__ import annotations

import httpx
import pytest
import respx

from monitor.contracts import CONTRACTS, get_contract, validate_contract
from monitor.models import MonitorConfig
from monitor.runner import execute_check


def _make_monitor(**overrides: object) -> MonitorConfig:
    defaults: dict[str, object] = {
        "name": "DolarApi Test",
        "url": "https://dolarapi.com/v1/dolares/oficial",
        "method": "GET",
        "expected_status": 200,
        "max_latency_ms": 500.0,
        "timeout_s": 2.0,
        "retries": 0,
        "backoff_base_s": 0.5,
        "contract": "dolar_api",
    }
    defaults.update(overrides)
    return MonitorConfig.model_validate(defaults)


def test_contracts_registry_contains_dolar_api_and_open_meteo() -> None:
    """Verifica que el registro exponga los contratos esperados."""
    assert "dolar_api" in CONTRACTS
    assert "open_meteo" in CONTRACTS
    assert get_contract("dolar_api") is CONTRACTS["dolar_api"]
    assert get_contract("open_meteo") is CONTRACTS["open_meteo"]
    assert get_contract("inexistente") is None


@respx.mock
def test_contract_missing_field_returns_contract_error_mentioning_field() -> None:
    """Contrato con un campo faltante -> contract_error, y el error menciona el campo."""
    monitor = _make_monitor(contract="dolar_api")
    # Falta el campo 'venta'
    respx.get(monitor.url).mock(
        return_value=httpx.Response(
            200,
            json={
                "moneda": "USD",
                "casa": "oficial",
                "nombre": "Oficial",
                "compra": 1485,
                "fechaActualizacion": "2026-10-16T18:55:00.000Z",
            },
        )
    )

    result = execute_check(monitor)

    assert result.status_category == "contract_error"
    assert result.ok is False
    assert result.error is not None
    assert "venta" in result.error


@respx.mock
def test_contract_wrong_type_returns_contract_error() -> None:
    """Contrato con un tipo incorrecto -> contract_error."""
    monitor = _make_monitor(
        name="Open-Meteo Test",
        url="https://api.open-meteo.com/v1/forecast",
        contract="open_meteo",
    )
    # temperature_2m debería ser numérico, enviamos un string
    respx.get(monitor.url).mock(
        return_value=httpx.Response(
            200,
            json={
                "latitude": -34.62,
                "longitude": -58.40,
                "current": {
                    "time": "2026-10-17T18:45",
                    "temperature_2m": "trece punto uno",
                },
            },
        )
    )

    result = execute_check(monitor)

    assert result.status_category == "contract_error"
    assert result.ok is False
    assert result.error is not None
    assert "current.temperature_2m" in result.error


@respx.mock
def test_contract_extra_fields_are_ignored_and_result_is_ok() -> None:
    """Campo extra en la respuesta -> sigue siendo ok."""
    monitor = _make_monitor(contract="dolar_api")
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
                "campoNuevoExtra": {"version": 2, "activo": True},
            },
        )
    )

    result = execute_check(monitor)

    assert result.status_category == "ok"
    assert result.ok is True
    assert result.error is None


@respx.mock
def test_non_json_200_response_returns_contract_error() -> None:
    """Respuesta 200 que no es JSON -> contract_error."""
    monitor = _make_monitor(contract="dolar_api")
    respx.get(monitor.url).mock(
        return_value=httpx.Response(
            200,
            text="<html><body>Maintenance</body></html>",
            headers={"content-type": "text/html"},
        )
    )

    result = execute_check(monitor)

    assert result.status_category == "contract_error"
    assert result.ok is False
    assert result.error is not None
    assert "json" in result.error.lower()


@respx.mock
def test_monitor_without_contract_only_validates_status_and_latency() -> None:
    """Monitor sin contract -> se valida solo status y latencia, como antes."""
    monitor = _make_monitor(contract=None)
    # Incluso devolviendo texto plano sin JSON, al no tener contrato es ok
    respx.get(monitor.url).mock(return_value=httpx.Response(200, text="PONG"))

    result = execute_check(monitor)

    assert result.status_category == "ok"
    assert result.ok is True
    assert result.error is None


@respx.mock
def test_slow_response_with_broken_contract_prioritizes_contract_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prioridad: respuesta lenta Y con contrato roto -> contract_error."""
    monitor = _make_monitor(contract="dolar_api", max_latency_ms=100.0)
    respx.get(monitor.url).mock(
        return_value=httpx.Response(200, json={"moneda": "USD"})  # Faltan campos obligatorios
    )

    # Simulamos 300ms de latencia (> 100ms de max_latency_ms)
    ticks = iter([10.0, 10.0, 10.30, 10.30])
    monkeypatch.setattr("monitor.runner.perf_counter", lambda: next(ticks))

    result = execute_check(monitor)

    assert result.latency_ms == pytest.approx(300.0)
    assert result.status_category == "contract_error"
    assert result.ok is False
    assert result.error is not None
    assert "compra" in result.error


def test_validate_contract_unknown_name_raises_value_error() -> None:
    """Si se invoca validate_contract con un contrato inexistente, lanza ValueError."""
    with pytest.raises(ValueError, match="no registrado"):
        validate_contract("inexistente", {})
