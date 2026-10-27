"""Tests unitarios y de integración para monitor/alerts.py (con respx, sin internet)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from monitor.alerts import (
    ALERT_LABEL,
    AlertError,
    decide_action,
    issue_title_for_monitor,
    main,
    monitor_id_marker,
    process_alerts,
)
from monitor.history import HistoryReport, HistoryRun
from monitor.models import AlertsConfig, CheckResult, MonitorConfig, StatusCategory

REPO = "facupeletay/qa-api-monitor"
API_BASE = f"https://api.github.com/repos/{REPO}"
MONITOR_NAME = "DolarApi - Dolar Oficial"
MONITOR_URL = "https://dolarapi.com/v1/dolares/oficial"
MONITOR_SLUG = "dolarapi-dolar-oficial"


def _make_check(
    *,
    name: str = MONITOR_NAME,
    url: str = MONITOR_URL,
    timestamp: str,
    status_category: StatusCategory,
    status_code: int | None = 503,
    latency_ms: float = 420.0,
    error: str | None = "Status HTTP inesperado: recibido 503, esperado 200",
    attempts: int = 3,
) -> CheckResult:
    if status_category == "ok":
        status_code = 200
        error = None
        attempts = 1
    elif status_category == "degraded":
        status_code = 200
        error = "Latencia excedida: 2500.0ms > 2000.0ms"
        attempts = 1
    return CheckResult(
        name=name,
        url=url,
        timestamp=timestamp,
        status_code=status_code,
        latency_ms=latency_ms,
        total_duration_ms=latency_ms,
        status_category=status_category,
        error=error,
        attempts=attempts,
    )


def _make_history(runs_checks: list[list[CheckResult]]) -> HistoryReport:
    runs: list[HistoryRun] = []
    for checks in runs_checks:
        ts = checks[0].timestamp if checks else "2026-10-17T12:00:00Z"
        runs.append(HistoryRun(timestamp=ts, results=checks))
    gen_at = runs[-1].timestamp if runs else "2026-10-17T12:00:00Z"
    return HistoryReport(generated_at=gen_at, runs=runs, stats={})


def _default_monitor(
    *,
    id: str | None = None,
    name: str = MONITOR_NAME,
    alert_after: int = 3,
    alert_on_degraded: bool = False,
) -> MonitorConfig:
    return MonitorConfig(
        id=id,
        name=name,
        url=MONITOR_URL,
        method="GET",
        expected_status=200,
        max_latency_ms=2000,
        timeout_s=5,
        retries=2,
        backoff_base_s=0.5,
        contract="dolar_api",
        alert_after=alert_after,
        alert_on_degraded=alert_on_degraded,
    )


def _issue_body_with_markers(
    *,
    monitor_id: str = MONITOR_SLUG,
    category: StatusCategory = "server_error",
    failing_since: str = "2026-10-17T06:00:00Z",
) -> str:
    return "\n".join(
        [
            f"- **ID del monitor:** `{monitor_id}`",
            f"- **Categoría:** `{category}`",
            f"- **Falla desde:** `{failing_since}`",
            monitor_id_marker(monitor_id),
            f"<!-- monitor-category: {category} -->",
            f"<!-- failing-since: {failing_since} -->",
        ]
    )


@respx.mock
def test_2_consecutive_failures_with_alert_after_3_does_not_open_issue() -> None:
    """2 fallas seguidas con alert_after=3 -> NOOP y no abre Issue."""
    monitor = _default_monitor(alert_after=3)
    history = _make_history(
        [
            [_make_check(timestamp="2026-10-17T00:00:00Z", status_category="ok")],
            [_make_check(timestamp="2026-10-17T06:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T12:00:00Z", status_category="server_error")],
        ]
    )
    decision = decide_action(monitor, history)
    assert decision.kind == "NOOP"

    list_issues_route = respx.get(f"{API_BASE}/issues").mock(
        return_value=httpx.Response(200, json=[])
    )
    create_issue_route = respx.post(f"{API_BASE}/issues").mock(
        return_value=httpx.Response(201, json={"number": 1})
    )

    actions = process_alerts(
        history=history,
        monitors=[monitor],
        repo=REPO,
        token="ghs_test_token",
        dry_run=False,
    )

    assert list_issues_route.called
    assert not create_issue_route.called
    assert len(actions) == 1
    assert actions[0].kind == "NOOP"
    assert actions[0].action == "unchanged"


@respx.mock
def test_3_consecutive_failures_opens_issue_with_label_title_and_marker() -> None:
    """3 fallas seguidas -> OPEN y abre Issue con label, título y marcador monitor-id."""
    monitor = _default_monitor(alert_after=3)
    history = _make_history(
        [
            [_make_check(timestamp="2026-10-17T06:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T12:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T18:00:00Z", status_category="server_error")],
        ]
    )
    decision = decide_action(monitor, history)
    assert decision.kind == "OPEN"
    assert decision.failing_since == "2026-10-17T06:00:00Z"

    respx.get(f"{API_BASE}/issues").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{API_BASE}/labels/{ALERT_LABEL}").mock(
        return_value=httpx.Response(200, json={"name": ALERT_LABEL})
    )
    create_issue_route = respx.post(f"{API_BASE}/issues").mock(
        return_value=httpx.Response(
            201,
            json={"number": 42, "html_url": f"https://github.com/{REPO}/issues/42"},
        )
    )

    actions = process_alerts(
        history=history,
        monitors=[monitor],
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
    assert monitor_id_marker(MONITOR_SLUG) in payload["body"]
    assert "server_error" in payload["body"]
    assert "2026-10-17T06:00:00Z" in payload["body"]
    assert "https://facupeletay.github.io/qa-api-monitor/" in payload["body"]
    assert "https://github.com/facupeletay/qa-api-monitor/actions/runs/999" in payload["body"]
    assert actions[0].kind == "OPEN"
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
                    "body": _issue_body_with_markers(
                        monitor_id=MONITOR_SLUG, category="server_error"
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
    assert actions[0].kind == "NOOP"
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
                    "body": _issue_body_with_markers(
                        monitor_id=MONITOR_SLUG, category="server_error"
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
    assert actions_changed[0].kind == "COMMENT_CATEGORY_CHANGE"
    assert actions_changed[0].action == "commented"

    # Misma categoría en la corrida siguiente -> no vuelve a comentar
    comment_route.reset()
    history_same = _make_history(
        [
            [_make_check(timestamp="2026-10-17T00:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T06:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T12:00:00Z", status_category="network_error")],
            [_make_check(timestamp="2026-10-17T18:00:00Z", status_category="network_error")],
        ]
    )
    actions_same = process_alerts(
        history=history_same,
        monitors=[_default_monitor(alert_after=3)],
        repo=REPO,
        token="ghs_test_token",
        dry_run=False,
    )
    assert not comment_route.called
    assert actions_same[0].kind == "NOOP"
    assert actions_same[0].action == "unchanged"


@respx.mock
def test_recovery_with_open_issue_comments_duration_and_closes() -> None:
    """Recuperación con Issue abierto -> comenta duración del incidente y cierra el Issue."""
    history = _make_history(
        [
            [_make_check(timestamp="2026-10-17T00:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T06:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T12:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T18:30:00Z", status_category="ok")],
        ]
    )
    respx.get(f"{API_BASE}/issues").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "number": 21,
                    "title": issue_title_for_monitor(MONITOR_NAME),
                    "body": _issue_body_with_markers(
                        monitor_id=MONITOR_SLUG,
                        category="server_error",
                        failing_since="2026-10-17T00:00:00Z",
                    ),
                    "created_at": "2026-10-17T12:00:00Z",
                }
            ],
        )
    )
    comment_route = respx.post(f"{API_BASE}/issues/21/comments").mock(
        return_value=httpx.Response(201, json={"id": 201})
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
    assert "18h 30m" in comment_body
    assert close_route.call_count == 1
    patch_payload = json.loads(close_route.calls.last.request.content.decode("utf-8"))
    assert patch_payload == {"state": "closed"}
    assert actions[0].kind == "CLOSE_RECOVERED"
    assert actions[0].action == "closed"
    assert actions[0].issue_number == 21


@respx.mock
def test_degraded_respects_alert_on_degraded_flag() -> None:
    """degraded con alert_on_degraded=false no cuenta; con true sí cuenta."""
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
    assert actions_false[0].kind == "NOOP"

    actions_true = process_alerts(
        history=history,
        monitors=[_default_monitor(alert_after=3, alert_on_degraded=True)],
        repo=REPO,
        token="ghs_test_token",
        dry_run=False,
    )
    assert create_issue_route.call_count == 1
    assert actions_true[0].kind == "OPEN"


@respx.mock
def test_per_monitor_override_of_alert_after() -> None:
    """Override por monitor de alert_after abre Issue con 2 fallas mientras global pide 3."""
    mon_global = _default_monitor(name="API Global (3)", alert_after=3)
    mon_custom = _default_monitor(name="API Crítica (2)", alert_after=2)

    history = _make_history(
        [
            [
                _make_check(
                    name="API Global (3)",
                    timestamp="2026-10-17T06:00:00Z",
                    status_category="server_error",
                ),
                _make_check(
                    name="API Crítica (2)",
                    timestamp="2026-10-17T06:00:00Z",
                    status_category="server_error",
                ),
            ],
            [
                _make_check(
                    name="API Global (3)",
                    timestamp="2026-10-17T12:00:00Z",
                    status_category="server_error",
                ),
                _make_check(
                    name="API Crítica (2)",
                    timestamp="2026-10-17T12:00:00Z",
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
        return_value=httpx.Response(201, json={"number": 55})
    )

    actions = process_alerts(
        history=history,
        monitors=[mon_global, mon_custom],
        repo=REPO,
        token="ghs_test_token",
        dry_run=False,
    )

    assert create_issue_route.call_count == 1
    by_name = {a.monitor_name: a for a in actions}
    assert by_name["API Global (3)"].kind == "NOOP"
    assert by_name["API Crítica (2)"].kind == "OPEN"


@respx.mock
def test_missing_label_is_created_when_opening_issue() -> None:
    """Label inexistente (404) -> se crea antes de abrir el Issue."""
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

    assert get_label_route.call_count == 1
    assert create_label_route.call_count == 1
    assert create_issue_route.call_count == 1
    assert actions[0].kind == "OPEN"


@respx.mock
def test_github_api_5xx_or_timeout_raises_alert_error_and_cli_returns_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Falla de la API de GitHub (5xx o timeout) -> error claro en stderr y exit code 1."""
    history = _make_history(
        [
            [_make_check(timestamp="2026-10-17T06:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T12:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T18:00:00Z", status_category="server_error")],
        ]
    )
    respx.get(f"{API_BASE}/issues").mock(return_value=httpx.Response(502, text="Bad Gateway"))

    with pytest.raises(AlertError, match="502"):
        process_alerts(
            history=history,
            monitors=[_default_monitor(alert_after=3)],
            repo=REPO,
            token="ghs_test_token",
            dry_run=False,
        )

    respx.get(f"{API_BASE}/issues").mock(side_effect=httpx.ConnectTimeout("GitHub API timeout"))
    history_file = tmp_path / "history.json"
    history_file.write_text(history.model_dump_json(indent=2), encoding="utf-8")

    config_file = tmp_path / "monitors.yaml"
    config_file.write_text(
        "alert_after: 3\n"
        "monitors:\n"
        f"  - name: {MONITOR_NAME}\n"
        f"    url: {MONITOR_URL}\n"
        "    method: GET\n"
        "    expected_status: 200\n"
        "    max_latency_ms: 2000\n"
        "    timeout_s: 5\n"
        "    retries: 2\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("GITHUB_TOKEN", "ghs_test_token")
    monkeypatch.setenv("GITHUB_REPOSITORY", REPO)

    exit_code = main(["--history", str(history_file), "--config", str(config_file)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Error en alertas" in captured.err


@respx.mock
def test_dry_run_makes_no_http_calls_and_writes_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """dry-run -> no hace ninguna llamada HTTP y reporta apertura y cierre."""
    mon_fail = _default_monitor(name="DolarApi - Dolar Oficial", alert_after=3)
    mon_rec = _default_monitor(name="Open-Meteo - Clima CABA", alert_after=3)

    history = _make_history(
        [
            [
                _make_check(
                    name=mon_fail.name,
                    timestamp="2026-10-17T00:00:00Z",
                    status_category="ok",
                ),
                _make_check(
                    name=mon_rec.name,
                    timestamp="2026-10-17T00:00:00Z",
                    status_category="network_error",
                ),
            ],
            [
                _make_check(
                    name=mon_fail.name,
                    timestamp="2026-10-17T06:00:00Z",
                    status_category="server_error",
                ),
                _make_check(
                    name=mon_rec.name,
                    timestamp="2026-10-17T06:00:00Z",
                    status_category="network_error",
                ),
            ],
            [
                _make_check(
                    name=mon_fail.name,
                    timestamp="2026-10-17T12:00:00Z",
                    status_category="server_error",
                ),
                _make_check(
                    name=mon_rec.name,
                    timestamp="2026-10-17T12:00:00Z",
                    status_category="network_error",
                ),
            ],
            [
                _make_check(
                    name=mon_fail.name,
                    timestamp="2026-10-17T18:00:00Z",
                    status_category="server_error",
                ),
                _make_check(
                    name=mon_rec.name,
                    timestamp="2026-10-17T18:00:00Z",
                    status_category="ok",
                ),
            ],
        ]
    )

    any_http_route = respx.route().mock(return_value=httpx.Response(500))

    history_file = tmp_path / "history.json"
    history_file.write_text(history.model_dump_json(indent=2), encoding="utf-8")
    summary_file = tmp_path / "summary.md"

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_REPOSITORY", REPO)

    exit_code = main(
        [
            "--history",
            str(history_file),
            "--config",
            "config/monitors.yaml",
            "--dry-run",
            "--summary-md",
            str(summary_file),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert not any_http_route.called
    assert "[DRY-RUN]" in captured.out
    assert "DolarApi - Dolar Oficial" in captured.out
    assert "Open-Meteo - Clima CABA" in captured.out
    assert summary_file.is_file()


@respx.mock
def test_existing_issue_found_by_marker_even_if_title_changed() -> None:
    """Encuentra el Issue abierto por marcador <!-- monitor-id: ... --> aunque el título cambió."""
    monitor = _default_monitor(id="dolar_oficial_custom", alert_after=3)
    history = _make_history(
        [
            [_make_check(timestamp="2026-10-17T00:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T06:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T12:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T18:00:00Z", status_category="network_error")],
        ]
    )
    respx.get(f"{API_BASE}/issues").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "number": 88,
                    "title": "[En investigación] Título cambiado manualmente por un humano",
                    "body": _issue_body_with_markers(
                        monitor_id="dolar_oficial_custom",
                        category="server_error",
                        failing_since="2026-10-17T00:00:00Z",
                    ),
                    "created_at": "2026-10-17T12:00:00Z",
                }
            ],
        )
    )
    create_issue_route = respx.post(f"{API_BASE}/issues").mock(
        return_value=httpx.Response(201, json={"number": 89})
    )
    comment_route = respx.post(f"{API_BASE}/issues/88/comments").mock(
        return_value=httpx.Response(201, json={"id": 500})
    )

    actions = process_alerts(
        history=history,
        monitors=[monitor],
        repo=REPO,
        token="ghs_test_token",
        dry_run=False,
    )

    assert not create_issue_route.called
    assert comment_route.call_count == 1
    assert actions[0].kind == "COMMENT_CATEGORY_CHANGE"
    assert actions[0].issue_number == 88


@respx.mock
def test_open_issues_pagination_across_multiple_pages() -> None:
    """Pagina GET /repos/{owner}/{repo}/issues?state=open&labels=monitor-alert."""
    monitor = _default_monitor(alert_after=3)
    history = _make_history(
        [
            [_make_check(timestamp="2026-10-17T06:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T12:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T18:00:00Z", status_category="server_error")],
        ]
    )

    def _paginated_issues(request: httpx.Request) -> httpx.Response:
        page = request.url.params.get("page", "1")
        if page == "1":
            return httpx.Response(
                200,
                headers={"Link": f'<{API_BASE}/issues?page=2>; rel="next"'},
                json=[
                    {
                        "number": 1,
                        "title": "[ALERTA] Otro Monitor",
                        "body": _issue_body_with_markers(
                            monitor_id="otro-monitor", category="server_error"
                        ),
                        "created_at": "2026-10-17T01:00:00Z",
                    }
                ],
            )
        if page == "2":
            return httpx.Response(
                200,
                json=[
                    {
                        "number": 2,
                        "title": issue_title_for_monitor(MONITOR_NAME),
                        "body": _issue_body_with_markers(
                            monitor_id=MONITOR_SLUG, category="server_error"
                        ),
                        "created_at": "2026-10-17T06:00:00Z",
                    }
                ],
            )
        return httpx.Response(200, json=[])

    issues_route = respx.get(f"{API_BASE}/issues").mock(side_effect=_paginated_issues)
    create_issue_route = respx.post(f"{API_BASE}/issues").mock(
        return_value=httpx.Response(201, json={"number": 99})
    )

    actions = process_alerts(
        history=history,
        monitors=[monitor],
        repo=REPO,
        token="ghs_test_token",
        dry_run=False,
        per_page=1,
    )

    assert issues_route.call_count == 2
    assert not create_issue_route.called
    assert actions[0].kind == "NOOP"
    assert actions[0].issue_number == 2


@respx.mock
def test_duplicate_open_issues_uses_oldest_and_warns_without_opening_another(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Si hay más de un Issue abierto para el mismo monitor, usa el más viejo y emite warning."""
    monitor = _default_monitor(alert_after=3)
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
                    "number": 50,
                    "title": "[ALERTA] Duplicado más nuevo",
                    "body": _issue_body_with_markers(
                        monitor_id=MONITOR_SLUG,
                        category="server_error",
                        failing_since="2026-10-17T06:00:00Z",
                    ),
                    "created_at": "2026-10-17T12:00:00Z",
                },
                {
                    "number": 33,
                    "title": "[ALERTA] Original más viejo",
                    "body": _issue_body_with_markers(
                        monitor_id=MONITOR_SLUG,
                        category="server_error",
                        failing_since="2026-10-17T00:00:00Z",
                    ),
                    "created_at": "2026-10-17T06:00:00Z",
                },
            ],
        )
    )
    comment_oldest_route = respx.post(f"{API_BASE}/issues/33/comments").mock(
        return_value=httpx.Response(201, json={"id": 1})
    )
    close_oldest_route = respx.patch(f"{API_BASE}/issues/33").mock(
        return_value=httpx.Response(200, json={"number": 33, "state": "closed"})
    )

    actions = process_alerts(
        history=history,
        monitors=[monitor],
        repo=REPO,
        token="ghs_test_token",
        dry_run=False,
    )
    captured = capsys.readouterr()

    assert "Warning: se encontraron múltiples Issues abiertos" in captured.err
    assert "#33" in captured.err
    assert "#50" in captured.err
    assert comment_oldest_route.call_count == 1
    assert close_oldest_route.call_count == 1
    assert actions[0].kind == "CLOSE_RECOVERED"
    assert actions[0].issue_number == 33


@respx.mock
def test_parity_real_vs_dry_run_same_action_sequence() -> None:
    """Sobre los mismos historiales, la corrida real y el dry-run producen la misma secuencia."""
    monitor = _default_monitor(alert_after=3, alert_on_degraded=False)
    cfg = AlertsConfig(alert_after=3, alert_on_degraded=False)

    timeline_checks = [
        _make_check(timestamp="2026-10-17T00:00:00Z", status_category="ok"),
        _make_check(timestamp="2026-10-17T02:00:00Z", status_category="server_error"),
        _make_check(timestamp="2026-10-17T04:00:00Z", status_category="server_error"),
        _make_check(timestamp="2026-10-17T06:00:00Z", status_category="server_error"),
        _make_check(timestamp="2026-10-17T08:00:00Z", status_category="server_error"),
        _make_check(
            timestamp="2026-10-17T10:00:00Z",
            status_category="network_error",
            status_code=None,
            error="Timeout",
        ),
        _make_check(
            timestamp="2026-10-17T12:00:00Z",
            status_category="network_error",
            status_code=None,
            error="Timeout",
        ),
        _make_check(timestamp="2026-10-17T14:00:00Z", status_category="ok"),
        _make_check(timestamp="2026-10-17T16:00:00Z", status_category="ok"),
    ]

    # Estado simulado en memoria del servidor de GitHub Issues para la corrida real
    server_issues: list[dict[str, Any]] = []

    def _list_issues_handler(request: httpx.Request) -> httpx.Response:
        del request
        open_items = [i for i in server_issues if i["state"] == "open"]
        return httpx.Response(200, json=open_items)

    def _create_issue_handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        new_num = len(server_issues) + 1
        issue_obj = {
            "number": new_num,
            "title": payload["title"],
            "body": payload["body"],
            "state": "open",
            "created_at": "2026-10-17T06:00:00Z",
        }
        server_issues.append(issue_obj)
        return httpx.Response(201, json=issue_obj)

    def _comment_issue_handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        # Actualizar marcador de categoría en el issue simulado si el comentario lo incluye
        for issue_obj in server_issues:
            if f"/issues/{issue_obj['number']}/comments" in str(request.url):
                issue_obj["body"] = issue_obj["body"] + "\n" + payload["body"]
        return httpx.Response(201, json={"id": 1})

    def _patch_issue_handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        for issue_obj in server_issues:
            if str(request.url).endswith(f"/issues/{issue_obj['number']}"):
                issue_obj["state"] = payload.get("state", issue_obj["state"])
                return httpx.Response(200, json=issue_obj)
        return httpx.Response(404)

    respx.get(f"{API_BASE}/issues").mock(side_effect=_list_issues_handler)
    respx.get(f"{API_BASE}/labels/{ALERT_LABEL}").mock(
        return_value=httpx.Response(200, json={"name": ALERT_LABEL})
    )
    respx.post(f"{API_BASE}/issues").mock(side_effect=_create_issue_handler)
    respx.post(url__regex=rf"{API_BASE}/issues/\d+/comments").mock(
        side_effect=_comment_issue_handler
    )
    respx.patch(url__regex=rf"{API_BASE}/issues/\d+").mock(side_effect=_patch_issue_handler)

    real_kinds: list[str] = []
    dry_run_kinds: list[str] = []

    for idx in range(1, len(timeline_checks) + 1):
        prefix_history = _make_history([[c] for c in timeline_checks[:idx]])

        real_res = process_alerts(
            history=prefix_history,
            monitors=[monitor],
            repo=REPO,
            token="ghs_test_token",
            dry_run=False,
        )
        dry_res = process_alerts(
            history=prefix_history,
            monitors=[monitor],
            repo=REPO,
            token=None,
            dry_run=True,
        )

        assert real_res[0].kind == dry_res[0].kind
        assert real_res[0].action == dry_res[0].action
        real_kinds.append(real_res[0].kind)
        dry_run_kinds.append(dry_res[0].kind)

    expected_sequence = [
        "NOOP",  # 1: ok
        "NOOP",  # 2: 1/3 server_error
        "NOOP",  # 3: 2/3 server_error
        "OPEN",  # 4: 3/3 server_error -> abre Issue
        "NOOP",  # 5: 4/3 server_error (misma categoría)
        "COMMENT_CATEGORY_CHANGE",  # 6: cambia a network_error -> comenta
        "NOOP",  # 7: sigue en network_error -> sin cambios
        "CLOSE_RECOVERED",  # 8: vuelve a ok -> comenta duración y cierra
        "NOOP",  # 9: sigue en ok -> sin cambios
    ]
    assert real_kinds == expected_sequence
    assert dry_run_kinds == expected_sequence
    assert cfg.alert_after == 3


@respx.mock
def test_recovery_without_prior_history_uses_issue_created_at_fallback() -> None:
    """Si el historial no contiene corridas fallidas previas, usa created_at del Issue."""
    monitor = _default_monitor(id="zz-prueba-alertas", name="ZZ Prueba alertas", alert_after=1)
    # Solo la corrida actual en ok (como ocurre en una rama que no despliega a Pages)
    history = _make_history(
        [
            [
                _make_check(
                    name=monitor.name,
                    timestamp="2026-10-18T15:45:00Z",
                    status_category="ok",
                )
            ]
        ]
    )
    respx.get(f"{API_BASE}/issues").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "number": 77,
                    "title": issue_title_for_monitor(monitor.name),
                    # Sin marcador failing-since para verificar el respaldo directo a created_at
                    "body": f"Incidente abierto\n{monitor_id_marker('zz-prueba-alertas')}",
                    "created_at": "2026-10-18T13:15:00Z",
                }
            ],
        )
    )
    comment_route = respx.post(f"{API_BASE}/issues/77/comments").mock(
        return_value=httpx.Response(201, json={"id": 701})
    )
    close_route = respx.patch(f"{API_BASE}/issues/77").mock(
        return_value=httpx.Response(200, json={"number": 77, "state": "closed"})
    )

    actions = process_alerts(
        history=history,
        monitors=[monitor],
        repo=REPO,
        token="ghs_test_token",
        dry_run=False,
    )

    assert comment_route.call_count == 1
    comment_body = json.loads(comment_route.calls.last.request.content.decode("utf-8"))["body"]
    assert "2h 30m" in comment_body
    assert "2026-10-18T13:15:00Z" in comment_body
    assert close_route.call_count == 1
    assert actions[0].kind == "CLOSE_RECOVERED"
    assert actions[0].issue_number == 77


def test_workflow_monitor_yml_cli_flags_match_real_parsers() -> None:
    """Verifica que los flags de monitor.yml existan en los parsers reales de argparse."""
    import re
    import shlex

    import yaml

    from monitor.__main__ import build_parser as build_monitor_parser
    from monitor.alerts import build_parser as build_alerts_parser
    from monitor.history import build_parser as build_history_parser

    workflow_path = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "monitor.yml"
    workflow_data = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    parsers = {
        "monitor": build_monitor_parser(),
        "monitor.history": build_history_parser(),
        "monitor.alerts": build_alerts_parser(),
    }
    found_modules: set[str] = set()

    for job in workflow_data.get("jobs", {}).values():
        for step in job.get("steps", []):
            run_script = step.get("run")
            if not run_script:
                continue
            joined_script = re.sub(r"\\\r?\n\s*", " ", str(run_script))
            for raw_line in joined_script.splitlines():
                line = raw_line.strip()
                if not line.startswith("python -m monitor"):
                    continue
                sanitized = re.sub(r"\$\{\{.*?\}\}", "placeholder", line)
                sanitized = re.sub(r"\$[A-Z_][A-Z0-9_]*", "placeholder", sanitized)
                tokens = shlex.split(sanitized)
                assert len(tokens) >= 3
                assert tokens[0] == "python"
                assert tokens[1] == "-m"
                module_name = tokens[2]
                assert module_name in parsers, f"Módulo inesperado en workflow: {module_name}"
                found_modules.add(module_name)

                cli_args = tokens[3:]
                parser = parsers[module_name]
                valid_options = set(parser._option_string_actions.keys())
                for token in cli_args:
                    if token.startswith("-"):
                        flag = token.split("=", 1)[0]
                        assert flag in valid_options, (
                            f"El flag '{flag}' usado en monitor.yml para '{module_name}' "
                            f"no existe en su argparse ({sorted(valid_options)})"
                        )
                # Además validar el parseo completo sin SystemExit
                parser.parse_args(cli_args)

    assert found_modules == {"monitor", "monitor.history", "monitor.alerts"}


@respx.mock
def test_external_notifications_sent_on_open_and_close_for_discord_and_telegram() -> None:
    """Envía notificaciones a Discord Webhook y Telegram al abrir y cerrar un Issue."""
    monitor = _default_monitor(alert_after=3)
    history_open = _make_history(
        [
            [_make_check(timestamp="2026-10-17T06:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T12:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T18:00:00Z", status_category="server_error")],
        ]
    )

    respx.get(f"{API_BASE}/issues").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{API_BASE}/labels/{ALERT_LABEL}").mock(
        return_value=httpx.Response(200, json={"name": ALERT_LABEL})
    )
    respx.post(f"{API_BASE}/issues").mock(return_value=httpx.Response(201, json={"number": 42}))

    discord_url = "https://discord.com/api/webhooks/123456/abcdef"
    telegram_url = "https://api.telegram.org/bot123:TOKEN_TEST/sendMessage"

    discord_route = respx.post(discord_url).mock(return_value=httpx.Response(204))
    telegram_route = respx.post(telegram_url).mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    actions = process_alerts(
        history=history_open,
        monitors=[monitor],
        repo=REPO,
        token="ghs_test_token",
        dry_run=False,
        webhook_url=discord_url,
        telegram_bot_token="123:TOKEN_TEST",
        telegram_chat_id="-100999888",
    )

    assert len(actions) == 1
    assert actions[0].kind == "OPEN"
    assert actions[0].notified_channels == ["webhook", "telegram"]
    assert discord_route.call_count == 1
    assert telegram_route.call_count == 1

    # Verificar que no se filtra el GITHUB_TOKEN a servicios externos
    assert "authorization" not in discord_route.calls.last.request.headers
    assert "authorization" not in telegram_route.calls.last.request.headers

    discord_payload = json.loads(discord_route.calls.last.request.content.decode("utf-8"))
    assert "ALERTA ABIERTA" in discord_payload["content"]
    assert "#42" in discord_payload["content"]

    tg_payload = json.loads(telegram_route.calls.last.request.content.decode("utf-8"))
    assert tg_payload["chat_id"] == "-100999888"
    assert "ALERTA ABIERTA" in tg_payload["text"]


@respx.mock
def test_external_notifications_slack_and_generic_webhook_and_not_sent_on_noop() -> None:
    """Soporta formato Slack/JSON genérico en cambios y no envía notificaciones en NOOP."""
    monitor = _default_monitor(alert_after=3)
    history_noop = _make_history(
        [
            [_make_check(timestamp="2026-10-17T06:00:00Z", status_category="ok")],
        ]
    )
    respx.get(f"{API_BASE}/issues").mock(return_value=httpx.Response(200, json=[]))

    slack_url = "https://hooks.slack.com/services/T000/B000/X000"
    slack_route = respx.post(slack_url).mock(return_value=httpx.Response(200, text="ok"))

    actions_noop = process_alerts(
        history=history_noop,
        monitors=[monitor],
        repo=REPO,
        token="ghs_test_token",
        dry_run=False,
        webhook_url=slack_url,
    )
    assert actions_noop[0].kind == "NOOP"
    assert actions_noop[0].notified_channels == []
    assert not slack_route.called

    # Ahora probar con cambio de categoría y webhook Slack
    history_change = _make_history(
        [
            [_make_check(timestamp="2026-10-17T00:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T06:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T12:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T18:00:00Z", status_category="network_error")],
        ]
    )
    respx.get(f"{API_BASE}/issues").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "number": 15,
                    "title": issue_title_for_monitor(MONITOR_NAME),
                    "body": _issue_body_with_markers(
                        monitor_id=MONITOR_SLUG, category="server_error"
                    ),
                    "created_at": "2026-10-17T12:00:00Z",
                }
            ],
        )
    )
    respx.post(f"{API_BASE}/issues/15/comments").mock(
        return_value=httpx.Response(201, json={"id": 101})
    )

    actions_change = process_alerts(
        history=history_change,
        monitors=[monitor],
        repo=REPO,
        token="ghs_test_token",
        dry_run=False,
        webhook_url=slack_url,
    )
    assert actions_change[0].kind == "COMMENT_CATEGORY_CHANGE"
    assert actions_change[0].notified_channels == ["webhook"]
    assert slack_route.call_count == 1
    slack_payload = json.loads(slack_route.calls.last.request.content.decode("utf-8"))
    assert "CAMBIO DE CATEGORÍA" in slack_payload["text"]


@respx.mock
def test_external_notification_failure_is_isolated_and_does_not_fail_github_issue_action(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Si el webhook externo o Telegram falla (500), emite Warning pero no aborta el Issue."""
    monitor = _default_monitor(alert_after=3)
    history_open = _make_history(
        [
            [_make_check(timestamp="2026-10-17T06:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T12:00:00Z", status_category="server_error")],
            [_make_check(timestamp="2026-10-17T18:00:00Z", status_category="server_error")],
        ]
    )
    respx.get(f"{API_BASE}/issues").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{API_BASE}/labels/{ALERT_LABEL}").mock(
        return_value=httpx.Response(200, json={"name": ALERT_LABEL})
    )
    respx.post(f"{API_BASE}/issues").mock(return_value=httpx.Response(201, json={"number": 99}))

    custom_webhook = "https://example.org/alerts-hook"
    telegram_url = "https://api.telegram.org/botSECRET_TOKEN_999/sendMessage"
    respx.post(custom_webhook).mock(return_value=httpx.Response(500, text="Hook Down"))
    respx.post(telegram_url).mock(return_value=httpx.Response(502, text="Bad Gateway"))

    actions = process_alerts(
        history=history_open,
        monitors=[monitor],
        repo=REPO,
        token="ghs_test_token",
        dry_run=False,
        webhook_url=custom_webhook,
        telegram_bot_token="SECRET_TOKEN_999",
        telegram_chat_id="12345",
    )
    captured = capsys.readouterr()

    assert actions[0].kind == "OPEN"
    assert actions[0].issue_number == 99
    assert actions[0].notified_channels == []
    assert "Warning: respuesta inesperada del webhook: HTTP 500" in captured.err
    assert "Warning: respuesta inesperada de Telegram API" in captured.err
    # Asegurar que el token secreto nunca se filtre en stderr
    assert "SECRET_TOKEN_999" not in captured.err
