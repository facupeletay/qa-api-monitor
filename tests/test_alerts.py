"""Tests para el sistema de alertas vía GitHub Issues por fallas consecutivas (Fase 5)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from monitor.alerts import (
    ALERT_LABEL,
    AlertError,
    issue_title_for_monitor,
    main,
    process_alerts,
)
from monitor.config import load_config
from monitor.history import HistoryReport, HistoryRun, MonitorStats, WindowStats
from monitor.models import ALL_STATUS_CATEGORIES, CheckResult, MonitorConfig, StatusCategory

REPO = "facupeletay/qa-api-monitor"
API_BASE = f"https://api.github.com/repos/{REPO}"
MONITOR_NAME = "DolarApi - Dolar Oficial"


def _make_check(
    *,
    name: str = MONITOR_NAME,
    timestamp: str,
    status_category: StatusCategory = "ok",
    status_code: int | None = 200,
    latency_ms: float = 120.0,
    error: str | None = None,
) -> CheckResult:
    resolved_error = error
    if resolved_error is None and status_category != "ok":
        resolved_error = f"Falla simulada ({status_category})"
    return CheckResult(
        name=name,
        url="https://dolarapi.com/v1/dolares/oficial",
        timestamp=timestamp,
        status_code=status_code,
        latency_ms=latency_ms,
        total_duration_ms=latency_ms,
        status_category=status_category,
        error=resolved_error,
        attempts=1,
    )


def _make_history(checks_per_run: list[list[CheckResult]]) -> HistoryReport:
    base_time = datetime(2026, 10, 17, 18, 0, 0, tzinfo=UTC)
    runs: list[HistoryRun] = []
    for idx, results in enumerate(checks_per_run):
        run_ts = results[0].timestamp if results else (base_time + timedelta(hours=idx)).isoformat()
        runs.append(HistoryRun(timestamp=run_ts, results=results))

    empty_window = WindowStats(
        total_checks=0,
        uptime_pct=None,
        latency_p50_ms=None,
        latency_p95_ms=None,
        by_category={cat: 0 for cat in ALL_STATUS_CATEGORIES},
    )
    stats: dict[str, MonitorStats] = {}
    if runs and runs[-1].results:
        for res in runs[-1].results:
            stats[res.name] = MonitorStats(
                last_status_category=res.status_category,
                last_timestamp=res.timestamp,
                max_latency_ms=2500.0,
                window_24h=empty_window,
                window_7d=empty_window,
            )

    return HistoryReport(
        generated_at="2026-10-17T18:00:00Z",
        runs=runs,
        stats=stats,
    )


def _default_monitor(
    *,
    name: str = MONITOR_NAME,
    alert_after: int = 3,
    alert_on_degraded: bool = False,
) -> MonitorConfig:
    return MonitorConfig(
        name=name,
        url="https://dolarapi.com/v1/dolares/oficial",
        max_latency_ms=2500.0,
        timeout_s=5.0,
        retries=1,
        alert_after=alert_after,
        alert_on_degraded=alert_on_degraded,
    )


@respx.mock
def test_2_consecutive_failures_with_alert_after_3_does_not_open_issue() -> None:
    """2 fallas seguidas con alert_after=3 -> no abre Issue."""
    history = _make_history(
        [
            [_make_check(timestamp="2026-10-17T06:00:00Z", status_category="ok")],
            [
                _make_check(
                    timestamp="2026-10-17T12:00:00Z",
                    status_category="server_error",
                    status_code=503,
                )
            ],
            [
                _make_check(
                    timestamp="2026-10-17T18:00:00Z",
                    status_category="server_error",
                    status_code=503,
                )
            ],
        ]
    )
    list_issues_route = respx.get(f"{API_BASE}/issues").mock(
        return_value=httpx.Response(200, json=[])
    )
    create_issue_route = respx.post(f"{API_BASE}/issues").mock(
        return_value=httpx.Response(201, json={"number": 1})
    )

    actions = process_alerts(
        history=history,
        monitors=[_default_monitor(alert_after=3)],
        repo=REPO,
        token="ghs_test_token",
        dry_run=False,
    )

    assert list_issues_route.called
    assert not create_issue_route.called
    assert len(actions) == 1
    assert actions[0].action == "unchanged"


@respx.mock
def test_3_consecutive_failures_opens_issue_with_label_and_title() -> None:
    """3 fallas seguidas -> abre un Issue con el label y el título correctos."""
    history = _make_history(
        [
            [
                _make_check(
                    timestamp="2026-10-17T06:00:00Z",
                    status_category="server_error",
                    status_code=502,
                    error="HTTP 502 Bad Gateway",
                )
            ],
            [
                _make_check(
                    timestamp="2026-10-17T12:00:00Z",
                    status_category="server_error",
                    status_code=503,
                    error="HTTP 503 Service Unavailable",
                )
            ],
            [
                _make_check(
                    timestamp="2026-10-17T18:00:00Z",
                    status_category="server_error",
                    status_code=503,
                    error="Status HTTP inesperado: recibido 503, esperado 200",
                )
            ],
        ]
    )
    respx.get(f"{API_BASE}/issues").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{API_BASE}/labels/{ALERT_LABEL}").mock(
        return_value=httpx.Response(200, json={"name": ALERT_LABEL})
    )
    create_issue_route = respx.post(f"{API_BASE}/issues").mock(
        return_value=httpx.Response(
            201,
            json={
                "number": 42,
                "html_url": f"https://github.com/{REPO}/issues/42",
            },
        )
    )

    actions = process_alerts(
        history=history,
        monitors=[_default_monitor(alert_after=3)],
        repo=REPO,
        token="ghs_test_token",
        dry_run=False,
        dashboard_url="https://facupeletay.github.io/qa-api-monitor/",
        run_url="https://github.com/facupeletay/qa-api-monitor/actions/runs/999",
    )

    assert create_issue_route.call_count == 1
    payload = json.loads(create_issue_route.calls.last.request.content.decode("utf-8"))
    assert payload["title"] == issue_title_for_monitor(MONITOR_NAME)
    assert payload["labels"] == [ALERT_LABEL]
    assert "server_error" in payload["body"]
    assert "2026-10-17T06:00:00Z" in payload["body"]
    assert "3" in payload["body"]
    assert "503" in payload["body"]
    assert "Status HTTP inesperado: recibido 503, esperado 200" in payload["body"]
    assert "https://facupeletay.github.io/qa-api-monitor/" in payload["body"]
    assert "https://github.com/facupeletay/qa-api-monitor/actions/runs/999" in payload["body"]
    assert actions[0].action == "opened"
    assert actions[0].issue_number == 42


@respx.mock
def test_3_consecutive_failures_with_open_issue_does_not_duplicate() -> None:
    """3 fallas seguidas e Issue abierto -> no duplica ni comenta si la categoría sigue igual."""
    history = _make_history(
        [
            [_make_check(timestamp="2026-10-17T06:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T12:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T18:00:00Z", status_category="server_error")],
        ]
    )
    respx.get(f"{API_BASE}/issues").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "number": 10,
                    "title": issue_title_for_monitor(MONITOR_NAME),
                    "body": (
                        "- **Categoría:** `server_error`\n<!-- monitor-category: server_error -->"
                    ),
                    "created_at": "2026-10-17T12:00:00Z",
                }
            ],
        )
    )
    create_issue_route = respx.post(f"{API_BASE}/issues").mock(
        return_value=httpx.Response(201, json={"number": 11})
    )
    comment_route = respx.post(f"{API_BASE}/issues/10/comments").mock(
        return_value=httpx.Response(201, json={"id": 1})
    )

    actions = process_alerts(
        history=history,
        monitors=[_default_monitor(alert_after=3)],
        repo=REPO,
        token="ghs_test_token",
        dry_run=False,
    )

    assert not create_issue_route.called
    assert not comment_route.called
    assert actions[0].action == "unchanged"


@respx.mock
def test_category_change_with_open_issue_comments_and_same_category_does_not() -> None:
    """Cambio de categoría con Issue abierto -> comenta; misma categoría -> no comenta."""
    history_changed = _make_history(
        [
            [_make_check(timestamp="2026-10-17T00:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T06:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T12:00:00Z", status_category="server_error")],
            [
                _make_check(
                    timestamp="2026-10-17T18:00:00Z",
                    status_category="network_error",
                    status_code=None,
                    error="Timeout tras 3 intentos",
                )
            ],
        ]
    )
    respx.get(f"{API_BASE}/issues").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "number": 15,
                    "title": issue_title_for_monitor(MONITOR_NAME),
                    "body": (
                        "- **Categoría:** `server_error`\n<!-- monitor-category: server_error -->"
                    ),
                    "created_at": "2026-10-17T12:00:00Z",
                }
            ],
        )
    )
    comment_route = respx.post(f"{API_BASE}/issues/15/comments").mock(
        return_value=httpx.Response(201, json={"id": 101})
    )

    actions_changed = process_alerts(
        history=history_changed,
        monitors=[_default_monitor(alert_after=3)],
        repo=REPO,
        token="ghs_test_token",
        dry_run=False,
    )

    assert comment_route.call_count == 1
    comment_payload = json.loads(comment_route.calls.last.request.content.decode("utf-8"))
    assert "server_error" in comment_payload["body"]
    assert "network_error" in comment_payload["body"]
    assert actions_changed[0].action == "commented"

    # Ahora en la siguiente corrida sigue en network_error -> no vuelve a comentar
    history_same = _make_history(
        [
            [_make_check(timestamp="2026-10-17T00:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T06:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T12:00:00Z", status_category="server_error")],
            [
                _make_check(
                    timestamp="2026-10-17T18:00:00Z",
                    status_category="network_error",
                    status_code=None,
                )
            ],
            [
                _make_check(
                    timestamp="2026-10-18T00:00:00Z",
                    status_category="network_error",
                    status_code=None,
                )
            ],
        ]
    )
    comment_route.reset()
    actions_same = process_alerts(
        history=history_same,
        monitors=[_default_monitor(alert_after=3)],
        repo=REPO,
        token="ghs_test_token",
        dry_run=False,
    )
    assert comment_route.call_count == 0
    assert actions_same[0].action == "unchanged"


@respx.mock
def test_recovery_with_open_issue_comments_duration_and_closes() -> None:
    """Recuperación con Issue abierto -> comenta la duración y cierra."""
    history = _make_history(
        [
            [_make_check(timestamp="2026-10-17T00:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T06:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T12:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T18:00:00Z", status_category="ok")],
        ]
    )
    respx.get(f"{API_BASE}/issues").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "number": 21,
                    "title": issue_title_for_monitor(MONITOR_NAME),
                    "body": "Incidente activo",
                    "created_at": "2026-10-17T12:00:00Z",
                }
            ],
        )
    )
    comment_route = respx.post(f"{API_BASE}/issues/21/comments").mock(
        return_value=httpx.Response(201, json={"id": 202})
    )
    close_route = respx.patch(f"{API_BASE}/issues/21").mock(
        return_value=httpx.Response(200, json={"number": 21, "state": "closed"})
    )

    actions = process_alerts(
        history=history,
        monitors=[_default_monitor(alert_after=3)],
        repo=REPO,
        token="ghs_test_token",
        dry_run=False,
    )

    assert comment_route.call_count == 1
    comment_body = json.loads(comment_route.calls.last.request.content.decode("utf-8"))["body"]
    # Desde 2026-10-17T00:00:00Z hasta 2026-10-17T18:00:00Z = 18h 0m
    assert "18h 0m" in comment_body
    assert close_route.call_count == 1
    close_payload = json.loads(close_route.calls.last.request.content.decode("utf-8"))
    assert close_payload == {"state": "closed"}
    assert actions[0].action == "closed"
    assert actions[0].issue_number == 21


@respx.mock
def test_degraded_respects_alert_on_degraded_flag() -> None:
    """degraded con alert_on_degraded=false -> no cuenta; con true -> cuenta y abre Issue."""
    history = _make_history(
        [
            [_make_check(timestamp="2026-10-17T06:00:00Z", status_category="degraded")],
            [_make_check(timestamp="2026-10-17T12:00:00Z", status_category="degraded")],
            [_make_check(timestamp="2026-10-17T18:00:00Z", status_category="degraded")],
        ]
    )
    respx.get(f"{API_BASE}/issues").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{API_BASE}/labels/{ALERT_LABEL}").mock(
        return_value=httpx.Response(200, json={"name": ALERT_LABEL})
    )
    create_issue_route = respx.post(f"{API_BASE}/issues").mock(
        return_value=httpx.Response(201, json={"number": 30})
    )

    actions_false = process_alerts(
        history=history,
        monitors=[_default_monitor(alert_after=3, alert_on_degraded=False)],
        repo=REPO,
        token="ghs_test_token",
        dry_run=False,
    )
    assert not create_issue_route.called
    assert actions_false[0].action == "unchanged"

    actions_true = process_alerts(
        history=history,
        monitors=[_default_monitor(alert_after=3, alert_on_degraded=True)],
        repo=REPO,
        token="ghs_test_token",
        dry_run=False,
    )
    assert create_issue_route.call_count == 1
    assert actions_true[0].action == "opened"


@respx.mock
def test_per_monitor_override_of_alert_after(tmp_path: Path) -> None:
    """Override por monitor de alert_after en monitors.yaml."""
    yaml_file = tmp_path / "monitors.yaml"
    yaml_file.write_text(
        "alert_after: 3\n"
        "alert_on_degraded: false\n"
        "monitors:\n"
        "  - name: Monitor Rapido\n"
        "    url: https://dolarapi.com/v1/dolares/oficial\n"
        "    max_latency_ms: 2000\n"
        "    timeout_s: 5\n"
        "    retries: 1\n"
        "    alert_after: 2\n"
        "  - name: Monitor Default\n"
        "    url: https://api.open-meteo.com/v1/forecast\n"
        "    max_latency_ms: 2000\n"
        "    timeout_s: 5\n"
        "    retries: 1\n",
        encoding="utf-8",
    )
    monitors = load_config(yaml_file)
    assert monitors[0].alert_after == 2
    assert monitors[1].alert_after == 3

    history = _make_history(
        [
            [
                _make_check(
                    name="Monitor Rapido",
                    timestamp="2026-10-17T12:00:00Z",
                    status_category="server_error",
                ),
                _make_check(
                    name="Monitor Default",
                    timestamp="2026-10-17T12:00:00Z",
                    status_category="server_error",
                ),
            ],
            [
                _make_check(
                    name="Monitor Rapido",
                    timestamp="2026-10-17T18:00:00Z",
                    status_category="server_error",
                ),
                _make_check(
                    name="Monitor Default",
                    timestamp="2026-10-17T18:00:00Z",
                    status_category="server_error",
                ),
            ],
        ]
    )

    respx.get(f"{API_BASE}/issues").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{API_BASE}/labels/{ALERT_LABEL}").mock(
        return_value=httpx.Response(200, json={"name": ALERT_LABEL})
    )
    create_issue_route = respx.post(f"{API_BASE}/issues").mock(
        return_value=httpx.Response(201, json={"number": 50})
    )

    actions = process_alerts(
        history=history,
        monitors=monitors,
        repo=REPO,
        token="ghs_test_token",
        dry_run=False,
    )

    assert create_issue_route.call_count == 1
    by_name = {a.monitor_name: a for a in actions}
    assert by_name["Monitor Rapido"].action == "opened"
    assert by_name["Monitor Default"].action == "unchanged"


@respx.mock
def test_missing_label_is_created_when_opening_issue() -> None:
    """Label inexistente (404) -> se crea con POST /labels."""
    history = _make_history(
        [
            [_make_check(timestamp="2026-10-17T06:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T12:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T18:00:00Z", status_category="server_error")],
        ]
    )
    respx.get(f"{API_BASE}/issues").mock(return_value=httpx.Response(200, json=[]))
    get_label_route = respx.get(f"{API_BASE}/labels/{ALERT_LABEL}").mock(
        return_value=httpx.Response(404, json={"message": "Not Found"})
    )
    create_label_route = respx.post(f"{API_BASE}/labels").mock(
        return_value=httpx.Response(201, json={"name": ALERT_LABEL})
    )
    create_issue_route = respx.post(f"{API_BASE}/issues").mock(
        return_value=httpx.Response(201, json={"number": 77})
    )

    actions = process_alerts(
        history=history,
        monitors=[_default_monitor(alert_after=3)],
        repo=REPO,
        token="ghs_test_token",
        dry_run=False,
    )

    assert get_label_route.called
    assert create_label_route.call_count == 1
    label_payload = json.loads(create_label_route.calls.last.request.content.decode("utf-8"))
    assert label_payload["name"] == ALERT_LABEL
    assert create_issue_route.call_count == 1
    assert actions[0].action == "opened"


@respx.mock
def test_github_api_5xx_or_timeout_raises_alert_error_and_cli_returns_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """API de GitHub con 5xx o timeout -> error claro y código distinto de 0 sin traceback."""
    history = _make_history(
        [
            [_make_check(timestamp="2026-10-17T06:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T12:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T18:00:00Z", status_category="server_error")],
        ]
    )

    respx.get(f"{API_BASE}/issues").mock(
        return_value=httpx.Response(502, json={"message": "Bad Gateway"})
    )
    with pytest.raises(AlertError, match="502"):
        process_alerts(
            history=history,
            monitors=[_default_monitor(alert_after=3)],
            repo=REPO,
            token="ghs_test_token",
            dry_run=False,
        )

    respx.get(f"{API_BASE}/issues").mock(side_effect=httpx.ReadTimeout("timeout"))
    history_file = tmp_path / "history.json"
    history_file.write_text(json.dumps(history.model_dump()), encoding="utf-8")
    config_file = tmp_path / "monitors.yaml"
    config_file.write_text(
        "monitors:\n"
        f"  - name: {MONITOR_NAME}\n"
        "    url: https://dolarapi.com/v1/dolares/oficial\n"
        "    max_latency_ms: 2500\n"
        "    timeout_s: 5\n"
        "    retries: 1\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("GITHUB_TOKEN", "ghs_test_token")
    monkeypatch.setenv("GITHUB_REPOSITORY", REPO)

    exit_code = main(["--history", str(history_file), "--config", str(config_file)])
    assert exit_code == 1


@respx.mock
def test_dry_run_makes_no_http_calls_and_writes_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """dry-run no hace ninguna llamada HTTP y es el modo por defecto sin GITHUB_TOKEN."""
    history = _make_history(
        [
            [
                _make_check(
                    name="DolarApi - Dolar Oficial",
                    timestamp="2026-10-17T00:00:00Z",
                    status_category="server_error",
                ),
                _make_check(
                    name="Open-Meteo - Clima CABA",
                    timestamp="2026-10-17T00:00:00Z",
                    status_category="network_error",
                    status_code=None,
                ),
            ],
            [
                _make_check(
                    name="DolarApi - Dolar Oficial",
                    timestamp="2026-10-17T06:00:00Z",
                    status_category="server_error",
                ),
                _make_check(
                    name="Open-Meteo - Clima CABA",
                    timestamp="2026-10-17T06:00:00Z",
                    status_category="network_error",
                    status_code=None,
                ),
            ],
            [
                _make_check(
                    name="DolarApi - Dolar Oficial",
                    timestamp="2026-10-17T12:00:00Z",
                    status_category="server_error",
                ),
                _make_check(
                    name="Open-Meteo - Clima CABA",
                    timestamp="2026-10-17T12:00:00Z",
                    status_category="network_error",
                    status_code=None,
                ),
            ],
            [
                _make_check(
                    name="DolarApi - Dolar Oficial",
                    timestamp="2026-10-17T18:00:00Z",
                    status_category="server_error",
                ),
                _make_check(
                    name="Open-Meteo - Clima CABA",
                    timestamp="2026-10-17T18:00:00Z",
                    status_category="ok",
                ),
            ],
        ]
    )

    any_http = respx.route().mock(return_value=httpx.Response(500))

    history_file = tmp_path / "history.json"
    history_file.write_text(json.dumps(history.model_dump()), encoding="utf-8")
    summary_file = tmp_path / "summary.md"

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

    exit_code = main(
        [
            "--history",
            str(history_file),
            "--config",
            "config/monitors.yaml",
            "--dry-run",
        ]
    )

    assert exit_code == 0
    assert not any_http.called
    summary_text = summary_file.read_text(encoding="utf-8")
    assert "DolarApi - Dolar Oficial" in summary_text
    assert "Open-Meteo - Clima CABA" in summary_text
