"""Tests para el historial de corridas, cálculo de métricas y descarga remota (Fase 3)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from monitor.history import (
    HistoryError,
    HistoryReport,
    HistoryRun,
    load_previous_history,
    main,
    merge_history,
)
from monitor.models import ALL_STATUS_CATEGORIES, CheckResult, RunReport, RunSummary, StatusCategory


def _make_check(
    *,
    name: str = "DolarApi",
    timestamp: str,
    status_category: StatusCategory = "ok",
    status_code: int | None = 200,
    latency_ms: float = 100.0,
) -> CheckResult:
    return CheckResult(
        name=name,
        url="https://dolarapi.com/v1/dolares/oficial",
        timestamp=timestamp,
        status_code=status_code,
        latency_ms=latency_ms,
        total_duration_ms=latency_ms,
        status_category=status_category,
        error=None if status_category == "ok" else f"Error {status_category}",
        attempts=1,
    )


def _make_run_report(results: list[CheckResult]) -> RunReport:
    by_cat: dict[StatusCategory, int] = {cat: 0 for cat in ALL_STATUS_CATEGORIES}
    for r in results:
        by_cat[r.status_category] += 1
    ok_count = by_cat["ok"]
    return RunReport(
        summary=RunSummary(
            total=len(results),
            ok=ok_count,
            failed=len(results) - ok_count,
            by_category=by_cat,
        ),
        results=results,
    )


def test_merge_with_empty_history_and_subsequent_run_prunes_older_than_30_days() -> None:
    """merge con historial vacío, merge que agrega corrida y descarte de > 30 días."""
    now = datetime(2026, 10, 17, 18, 0, 0, tzinfo=UTC)
    ts_35_days_ago = (now - timedelta(days=35)).isoformat().replace("+00:00", "Z")
    ts_5_days_ago = (now - timedelta(days=5)).isoformat().replace("+00:00", "Z")
    ts_now = now.isoformat().replace("+00:00", "Z")

    # 1) Merge con historial vacío (None)
    first_run = _make_run_report([_make_check(timestamp=ts_5_days_ago, latency_ms=120.0)])
    hist1 = merge_history(None, first_run, now=now)
    assert len(hist1.runs) == 1
    assert hist1.runs[0].timestamp == ts_5_days_ago

    # Inyectamos una corrida vieja (hace 35 días) en el historial previo
    old_run = HistoryRun(
        timestamp=ts_35_days_ago,
        results=[_make_check(timestamp=ts_35_days_ago, latency_ms=999.0)],
    )
    hist_with_old = HistoryReport(
        generated_at=ts_5_days_ago,
        runs=[old_run, hist1.runs[0]],
        stats=hist1.stats,
    )

    # 2) Merge que agrega una nueva corrida y descarta la de hace 35 días (> 30 días)
    second_run = _make_run_report([_make_check(timestamp=ts_now, latency_ms=150.0)])
    hist2 = merge_history(hist_with_old, second_run, now=now)

    assert len(hist2.runs) == 2
    run_timestamps = [r.timestamp for r in hist2.runs]
    assert ts_35_days_ago not in run_timestamps
    assert run_timestamps == [ts_5_days_ago, ts_now]


def test_stats_calculation_with_known_data_and_unanswered_checks_excluded() -> None:
    """stats con datos conocidos: uptime, p50 y p95 a mano; sin respuesta no cuenta en latencia."""
    now = datetime(2026, 10, 17, 18, 0, 0, tzinfo=UTC)

    # Creamos 5 corridas en las últimas 24h y 1 corrida hace 3 días (dentro de 7d pero fuera de 24h)
    # En las últimas 24h:
    # - 5 checks con respuesta (status_code=200):
    #   latencias = [100.0, 200.0, 300.0, 400.0, 500.0] para calcular p50/p95 exactos:
    #   4 'ok' (100, 200, 300, 400 ms) + 1 'degraded' (500 ms, con status_code=200)
    #   + 1 'network_error' (status_code=None, latency_ms=5000.0 -> NO debe contar para latencia)
    # Total checks 24h = 6 -> ok = 4 -> uptime_pct = round(4 / 6 * 100, 2) = 66.67%
    # Latencias con respuesta en 24h (5 valores): [100.0, 200.0, 300.0, 400.0, 500.0]
    #   p50 a mano: índice 2 -> 300.0
    #   p95 a mano: pos = 4 * 0.95 = 3.8 -> 400 + 0.8 * (500 - 400) = 480.0
    runs_data: list[tuple[timedelta, StatusCategory, int | None, float]] = [
        # Hace 3 días (entra en 7d, no en 24h): ok con latencia 50.0ms
        (timedelta(days=3), "ok", 200, 50.0),
        # Últimas 24h:
        (timedelta(hours=10), "ok", 200, 100.0),
        (timedelta(hours=8), "ok", 200, 200.0),
        (timedelta(hours=6), "ok", 200, 300.0),
        (timedelta(hours=4), "ok", 200, 400.0),
        (timedelta(hours=2), "degraded", 200, 500.0),
        (timedelta(hours=1), "network_error", None, 5000.0),
    ]

    history: HistoryReport | None = None
    for delta, category, code, lat in runs_data:
        ts = (now - delta).isoformat().replace("+00:00", "Z")
        run_rep = _make_run_report(
            [
                _make_check(
                    name="DolarApi",
                    timestamp=ts,
                    status_category=category,
                    status_code=code,
                    latency_ms=lat,
                )
            ]
        )
        history = merge_history(history, run_rep, now=now)

    assert history is not None
    monitor_stats = history.stats["DolarApi"]

    # Último estado corresponde al check de hace 1 hora (network_error)
    assert monitor_stats.last_status_category == "network_error"
    assert monitor_stats.last_timestamp == (now - timedelta(hours=1)).isoformat().replace(
        "+00:00", "Z"
    )

    # Ventana 24h
    w24 = monitor_stats.window_24h
    assert w24.total_checks == 6
    assert w24.uptime_pct == pytest.approx(66.67)
    assert w24.latency_p50_ms == pytest.approx(300.0)
    assert w24.latency_p95_ms == pytest.approx(480.0)
    assert w24.by_category["ok"] == 4
    assert w24.by_category["degraded"] == 1
    assert w24.by_category["network_error"] == 1

    # Ventana 7d (suma el check ok de 50ms de hace 3 días: 5 ok de 7 checks = 71.43%)
    # Latencias con respuesta en 7d (6 valores): [50, 100, 200, 300, 400, 500]
    # p50: pos = 5 * 0.5 = 2.5 -> 250.0
    # p95: pos = 5 * 0.95 = 4.75 -> 400 + 0.75 * (500 - 400) = 475.0
    w7d = monitor_stats.window_7d
    assert w7d.total_checks == 7
    assert w7d.uptime_pct == pytest.approx(71.43)
    assert w7d.latency_p50_ms == pytest.approx(250.0)
    assert w7d.latency_p95_ms == pytest.approx(475.0)
    assert w7d.by_category["ok"] == 5


@respx.mock
def test_fetch_previous_history_remote_200_404_5xx_timeout_and_corrupt_json() -> None:
    """Obtener historial: 200 -> se usa; 404 -> vacío; 5xx/timeout/corrupto -> HistoryError."""
    url = "https://facupeletay.github.io/qa-api-monitor/history.json"
    now = datetime(2026, 10, 17, 18, 0, 0, tzinfo=UTC)
    ts = now.isoformat().replace("+00:00", "Z")
    valid_history = merge_history(None, _make_run_report([_make_check(timestamp=ts)]), now=now)

    # 1) 200 OK con JSON válido -> devuelve HistoryReport
    respx.get(url).mock(return_value=httpx.Response(200, json=valid_history.model_dump()))
    loaded = load_previous_history(url)
    assert loaded is not None
    assert len(loaded.runs) == 1

    # 2) 404 Not Found -> primera corrida, devuelve None (historial vacío)
    respx.get(url).mock(return_value=httpx.Response(404, text="Not Found"))
    assert load_previous_history(url) is None

    # 3) 5xx -> lanza HistoryError
    respx.get(url).mock(return_value=httpx.Response(503, text="Service Unavailable"))
    with pytest.raises(HistoryError, match="503"):
        load_previous_history(url)

    # 4) Timeout -> lanza HistoryError
    respx.get(url).mock(side_effect=httpx.ReadTimeout("Timed out"))
    with pytest.raises(HistoryError, match="Timeout"):
        load_previous_history(url)

    # 5) JSON corrupto -> lanza HistoryError
    respx.get(url).mock(return_value=httpx.Response(200, text="{not-valid-json"))
    with pytest.raises(HistoryError, match="JSON"):
        load_previous_history(url)

    # 6) JSON con estructura inválida -> lanza HistoryError
    respx.get(url).mock(return_value=httpx.Response(200, json={"runs": "invalid"}))
    with pytest.raises(HistoryError, match="inválido"):
        load_previous_history(url)


@respx.mock
def test_fetch_previous_history_with_cache_busting_query_and_no_cache_header() -> None:
    """Verifica que una URL con query string (?t=...) se maneje bien y envíe Cache-Control."""
    url_with_query = "https://facupeletay.github.io/qa-api-monitor/history.json?t=987654-1"
    now = datetime(2026, 10, 17, 18, 0, 0, tzinfo=UTC)
    ts = now.isoformat().replace("+00:00", "Z")
    valid_history = merge_history(None, _make_run_report([_make_check(timestamp=ts)]), now=now)

    route = respx.get(url_with_query).mock(
        return_value=httpx.Response(200, json=valid_history.model_dump())
    )

    loaded = load_previous_history(url_with_query)

    assert loaded is not None
    assert len(loaded.runs) == 1
    assert route.call_count == 1
    sent_request = route.calls.last.request
    assert sent_request.headers.get("Cache-Control") == "no-cache"


def test_history_cli_end_to_end_with_temp_files(tmp_path: Path) -> None:
    """CLI de history punta a punta con archivos temporales."""
    now = datetime(2026, 10, 17, 18, 0, 0, tzinfo=UTC)
    ts_prev = (now - timedelta(hours=6)).isoformat().replace("+00:00", "Z")
    ts_curr = now.isoformat().replace("+00:00", "Z")

    prev_run = _make_run_report([_make_check(timestamp=ts_prev, latency_ms=110.0)])
    prev_history = merge_history(None, prev_run, now=now - timedelta(hours=6))

    prev_file = tmp_path / "prev_history.json"
    prev_file.write_text(json.dumps(prev_history.model_dump()), encoding="utf-8")

    curr_run = _make_run_report([_make_check(timestamp=ts_curr, latency_ms=130.0)])
    run_file = tmp_path / "run.json"
    run_file.write_text(json.dumps(curr_run.model_dump()), encoding="utf-8")

    output_file = tmp_path / "site" / "history.json"

    exit_code = main(
        [
            "--previous",
            str(prev_file),
            "--run",
            str(run_file),
            "--output",
            str(output_file),
        ]
    )
    assert exit_code == 0
    assert output_file.exists()

    saved = json.loads(output_file.read_text(encoding="utf-8"))
    assert len(saved["runs"]) == 2
    assert saved["stats"]["DolarApi"]["window_24h"]["total_checks"] == 2
    assert saved["stats"]["DolarApi"]["window_24h"]["latency_p50_ms"] == pytest.approx(120.0)


def test_history_cli_fails_with_exit_code_1_when_previous_is_corrupt(tmp_path: Path) -> None:
    """El CLI devuelve 1 y NO escribe el archivo de salida si falla la lectura de --previous."""
    corrupt_prev = tmp_path / "corrupt.json"
    corrupt_prev.write_text("{corrupt", encoding="utf-8")

    ts = datetime(2026, 10, 17, 18, 0, 0, tzinfo=UTC).isoformat().replace("+00:00", "Z")
    run_file = tmp_path / "run.json"
    run_file.write_text(
        json.dumps(_make_run_report([_make_check(timestamp=ts)]).model_dump()),
        encoding="utf-8",
    )
    output_file = tmp_path / "site" / "history.json"

    exit_code = main(
        [
            "--previous",
            str(corrupt_prev),
            "--run",
            str(run_file),
            "--output",
            str(output_file),
        ]
    )
    assert exit_code == 1
    assert not output_file.exists()
