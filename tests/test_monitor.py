"""Suite de pruebas para qa-api-monitor (Fase 1)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from monitor.__main__ import main
from monitor.config import ConfigError, load_config
from monitor.models import MonitorConfig
from monitor.runner import execute_check, run_monitors, save_report


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Evita esperas reales en todos los tests y registra las llamadas a sleep."""
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
    }
    defaults.update(overrides)
    return MonitorConfig.model_validate(defaults)


@respx.mock
def test_fast_200_response_is_ok() -> None:
    """Respuesta 200 rápida -> ok."""
    monitor = _make_monitor()
    respx.get("https://api.example.com/health").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )

    result = execute_check(monitor)

    assert result.ok is True
    assert result.status_code == 200
    assert result.attempts == 1
    assert result.error is None
    assert result.latency_ms <= monitor.max_latency_ms
    assert result.total_duration_ms >= result.latency_ms
    assert result.timestamp.endswith("Z") or "+00:00" in result.timestamp


@respx.mock
def test_unexpected_status_fails() -> None:
    """Status distinto al esperado -> falla."""
    monitor = _make_monitor(expected_status=200, retries=0)
    respx.get("https://api.example.com/health").mock(
        return_value=httpx.Response(201, json={"created": True})
    )

    result = execute_check(monitor)

    assert result.ok is False
    assert result.status_code == 201
    assert result.attempts == 1
    assert result.error is not None
    assert "201" in result.error


@respx.mock
def test_latency_exceeding_max_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """Latencia mayor al máximo -> falla."""
    monitor = _make_monitor(max_latency_ms=100.0, retries=2)
    respx.get("https://api.example.com/health").mock(
        return_value=httpx.Response(200, json={"status": "slow"})
    )

    # check_start=10.0, attempt1_start=10.0, attempt1_end=10.25, check_end=10.25
    ticks = iter([10.0, 10.0, 10.25, 10.25])
    monkeypatch.setattr("monitor.runner.perf_counter", lambda: next(ticks))

    result = execute_check(monitor)

    assert result.ok is False
    assert result.status_code == 200
    assert result.latency_ms == pytest.approx(250.0)
    assert result.total_duration_ms == pytest.approx(250.0)
    assert result.attempts == 1
    assert result.error is not None
    assert "latencia" in result.error.lower() or "latency" in result.error.lower()


@respx.mock
def test_timeout_in_all_attempts_fails_gracefully() -> None:
    """Timeout en todos los intentos -> attempts = retries + 1, ok=false, error registrado."""
    monitor = _make_monitor(retries=2, backoff_base_s=0.5)
    sleep_calls: list[float] = []
    route = respx.get("https://api.example.com/health").mock(
        side_effect=httpx.ReadTimeout("Read timed out")
    )

    result = execute_check(monitor, sleep_fn=sleep_calls.append)

    assert result.ok is False
    assert result.status_code is None
    assert result.attempts == monitor.retries + 1 == 3
    assert route.call_count == 3
    assert sleep_calls == [0.5, 1.0]
    assert result.error is not None
    assert "timeout" in result.error.lower() or "timed out" in result.error.lower()


@respx.mock
def test_5xx_recovers_on_retry() -> None:
    """5xx que se recupera en el reintento -> ok con attempts=2."""
    monitor = _make_monitor(retries=2)
    route = respx.get("https://api.example.com/health").mock(
        side_effect=[
            httpx.Response(503, text="Service Unavailable"),
            httpx.Response(200, json={"status": "recovered"}),
        ]
    )

    result = execute_check(monitor)

    assert result.ok is True
    assert result.status_code == 200
    assert result.attempts == 2
    assert route.call_count == 2
    assert result.error is None


@respx.mock
def test_5xx_5xx_200_exponential_backoff_calls_sleep() -> None:
    """5xx -> 5xx -> 200: attempts=3, se llamó a sleep con 0.5 y 1.0."""
    monitor = _make_monitor(retries=3, backoff_base_s=0.5)
    sleep_calls: list[float] = []
    route = respx.get("https://api.example.com/health").mock(
        side_effect=[
            httpx.Response(502, text="Bad Gateway"),
            httpx.Response(503, text="Service Unavailable"),
            httpx.Response(200, json={"status": "ok"}),
        ]
    )

    result = execute_check(monitor, sleep_fn=sleep_calls.append)

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
    respx.get("https://api.example.com/health").mock(
        side_effect=[
            httpx.Response(503, text="Slow fail 1"),
            httpx.Response(200, json={"status": "fast success"}),
        ]
    )

    # Simulamos tiempos en segundos:
    # check_start = 0.000
    # intento 1: start=0.000, end=0.400 (400ms) -> 503
    # sleep(0.5) simulado -> reloj avanza a 0.900
    # intento 2: start=0.900, end=0.950 (50ms)  -> 200
    # check_end = 0.950 (total_duration_ms = 950ms)
    ticks = iter([0.000, 0.000, 0.400, 0.900, 0.950, 0.950])
    monkeypatch.setattr("monitor.runner.perf_counter", lambda: next(ticks))

    result = execute_check(monitor)

    assert result.attempts == 2
    assert result.latency_ms == pytest.approx(50.0)
    assert result.total_duration_ms == pytest.approx(950.0)
    assert result.total_duration_ms >= result.latency_ms
    # Como latency_ms del último intento (50ms) <= max_latency_ms (100ms), ok es True
    # aunque el primer intento haya tardado 400ms y el total sea 950ms
    assert result.ok is True


@respx.mock
def test_5xx_exhausts_retries_and_fails() -> None:
    """5xx que persiste tras agotar reintentos -> falla con attempts=retries+1."""
    monitor = _make_monitor(retries=1)
    route = respx.get("https://api.example.com/health").mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )

    result = execute_check(monitor)

    assert result.ok is False
    assert result.status_code == 500
    assert result.attempts == 2
    assert route.call_count == 2
    assert result.error is not None
    assert "500" in result.error


@respx.mock
def test_4xx_does_not_retry() -> None:
    """4xx -> no reintenta aunque retries > 0."""
    monitor = _make_monitor(retries=3)
    sleep_calls: list[float] = []
    route = respx.get("https://api.example.com/health").mock(
        return_value=httpx.Response(404, text="Not Found")
    )

    result = execute_check(monitor, sleep_fn=sleep_calls.append)

    assert result.ok is False
    assert result.status_code == 404
    assert result.attempts == 1
    assert route.call_count == 1
    assert sleep_calls == []
    assert result.error is not None
    assert "404" in result.error


def test_invalid_yaml_or_missing_fields_raises_clear_error(tmp_path: Path) -> None:
    """YAML inválido o con campos faltantes -> error de validación claro."""
    # Caso 1: Sintaxis YAML inválida
    broken_yaml = tmp_path / "broken.yaml"
    broken_yaml.write_text("monitors:\n  - name: [unclosed\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="YAML"):
        load_config(broken_yaml)

    # Caso 2: Campos obligatorios faltantes (falta max_latency_ms, timeout_s, retries)
    missing_fields_yaml = tmp_path / "missing.yaml"
    missing_fields_yaml.write_text(
        "monitors:\n  - name: Incompleto\n    url: https://example.com\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="max_latency_ms"):
        load_config(missing_fields_yaml)

    # Caso 3: URL inválida
    bad_url_yaml = tmp_path / "bad_url.yaml"
    bad_url_yaml.write_text(
        "monitors:\n"
        "  - name: Bad URL\n"
        "    url: ftp://invalid-scheme\n"
        "    max_latency_ms: 500\n"
        "    timeout_s: 2\n"
        "    retries: 0\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="url"):
        load_config(bad_url_yaml)

    # Caso 4: Archivo inexistente
    with pytest.raises(ConfigError, match="No se encontró"):
        load_config(tmp_path / "nonexistent.yaml")


@respx.mock
def test_cli_run_and_report_output(tmp_path: Path) -> None:
    """Verifica generación de results/run.json y códigos de salida 0 y 1."""
    config_file = tmp_path / "monitors.yaml"
    config_file.write_text(
        "monitors:\n"
        "  - name: API 1\n"
        "    url: https://api.example.com/one\n"
        "    max_latency_ms: 1000\n"
        "    timeout_s: 2\n"
        "    retries: 0\n",
        encoding="utf-8",
    )
    output_file = tmp_path / "results" / "run.json"

    respx.get("https://api.example.com/one").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    exit_code_ok = main(["--config", str(config_file), "--output", str(output_file)])
    assert exit_code_ok == 0
    assert output_file.exists()

    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["summary"] == {"total": 1, "ok": 1, "failed": 0}
    assert len(payload["results"]) == 1
    assert payload["results"][0]["ok"] is True
    assert "total_duration_ms" in payload["results"][0]
    assert payload["results"][0]["total_duration_ms"] >= payload["results"][0]["latency_ms"]

    # Ahora simulamos fallo (404) y verificamos código de salida 1
    respx.get("https://api.example.com/one").mock(return_value=httpx.Response(404))
    exit_code_fail = main(["--config", str(config_file), "--output", str(output_file)])
    assert exit_code_fail == 1

    report = run_monitors(load_config(config_file))
    save_report(report, output_file)
    assert report.summary.failed == 1
