"""Tests para la interfaz de línea de comandos (CLI) y formato del reporte JSON."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from monitor.__main__ import main


@respx.mock
def test_cli_returns_0_when_all_checks_ok_and_includes_category_counts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Código de salida 0 cuando todos son ok; summary incluye conteo por categoría."""
    config_file = tmp_path / "monitors.yaml"
    config_file.write_text(
        "monitors:\n"
        "  - name: Dolar API\n"
        "    url: https://dolarapi.com/v1/dolares/oficial\n"
        "    max_latency_ms: 1000\n"
        "    timeout_s: 2\n"
        "    retries: 0\n"
        "    contract: dolar_api\n",
        encoding="utf-8",
    )
    output_file = tmp_path / "results" / "run.json"

    respx.get("https://dolarapi.com/v1/dolares/oficial").mock(
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

    exit_code = main(["--config", str(config_file), "--output", str(output_file)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "category=ok" in captured.out
    assert "Resumen: Total=1 | OK=1 | Fallidos=0\n" in captured.out
    assert output_file.exists()

    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["summary"]["total"] == 1
    assert payload["summary"]["ok"] == 1
    assert payload["summary"]["failed"] == 0
    assert payload["summary"]["by_category"] == {
        "ok": 1,
        "degraded": 0,
        "contract_error": 0,
        "client_error": 0,
        "server_error": 0,
        "network_error": 0,
    }
    assert payload["results"][0]["status_category"] == "ok"
    assert payload["results"][0]["ok"] is True


@respx.mock
def test_cli_returns_1_on_any_non_ok_category(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Código de salida 1 si algún check queda en estado distinto de ok (ej. contract_error)."""
    config_file = tmp_path / "monitors.yaml"
    config_file.write_text(
        "monitors:\n"
        "  - name: Dolar API Rota\n"
        "    url: https://dolarapi.com/v1/dolares/oficial\n"
        "    max_latency_ms: 1000\n"
        "    timeout_s: 2\n"
        "    retries: 0\n"
        "    contract: dolar_api\n",
        encoding="utf-8",
    )
    output_file = tmp_path / "results" / "run.json"

    respx.get("https://dolarapi.com/v1/dolares/oficial").mock(
        return_value=httpx.Response(200, json={"moneda": "USD"})
    )

    exit_code = main(["--config", str(config_file), "--output", str(output_file)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "category=contract_error" in captured.out
    assert "(contract_error=1)" in captured.out

    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["summary"]["ok"] == 0
    assert payload["summary"]["failed"] == 1
    assert payload["summary"]["by_category"]["contract_error"] == 1


def test_cli_returns_1_when_config_is_invalid(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Código de salida 1 e impresión en stderr cuando falla la carga de configuración."""
    exit_code = main(["--config", str(tmp_path / "missing.yaml")])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Error de configuración" in captured.err
