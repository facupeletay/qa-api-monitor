"""Gestión automática de alertas mediante GitHub Issues ante fallas consecutivas (Fase 5)."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ValidationError

from monitor.config import ConfigError, load_config
from monitor.history import HistoryError, HistoryReport, _parse_iso_utc
from monitor.models import ALL_STATUS_CATEGORIES, CheckResult, MonitorConfig, StatusCategory

ALERT_LABEL = "monitor-alert"
DEFAULT_REPO = "facupeletay/qa-api-monitor"
AlertActionType = Literal["opened", "commented", "closed", "unchanged"]


class AlertError(RuntimeError):
    """Error al interactuar con la API de GitHub o al procesar el archivo de historial."""


class AlertAction(BaseModel):
    """Resultado de la evaluación/acción de alerta para un monitor."""

    monitor_name: str
    action: AlertActionType
    summary_line: str
    issue_number: int | None = None
    dry_run: bool = False


def issue_title_for_monitor(monitor_name: str) -> str:
    """Devuelve el título fijo del Issue de alerta para un monitor."""
    return f"[ALERTA] {monitor_name}"


def is_alert_failure(category: StatusCategory, alert_on_degraded: bool = False) -> bool:
    """Indica si una categoría cuenta como falla para el umbral de alerta."""
    if category == "ok":
        return False
    if category == "degraded":
        return bool(alert_on_degraded)
    return True


def format_incident_duration(start_iso: str, end_iso: str) -> str:
    """Formatea la duración de un incidente entre dos timestamps ISO-8601 UTC."""
    start_dt = _parse_iso_utc(start_iso)
    end_dt = _parse_iso_utc(end_iso)
    total_seconds = max(0, int((end_dt - start_dt).total_seconds()))
    hours, remainder = divmod(total_seconds, 3600)
    minutes = remainder // 60
    return f"{hours}h {minutes}m"


def _extract_category_from_issue_body(body: str | None) -> StatusCategory | None:
    if not body:
        return None
    marker_match = re.search(r"<!--\s*monitor-category:\s*([a-z_]+)\s*-->", body)
    if marker_match:
        candidate = marker_match.group(1)
        if candidate in ALL_STATUS_CATEGORIES:
            return candidate  # type: ignore[return-value]
    for cat in ALL_STATUS_CATEGORIES:
        if cat != "ok" and cat in body:
            return cat
    return None


def _build_issue_body(
    *,
    monitor: MonitorConfig,
    streak: list[CheckResult],
    dashboard_url: str,
    run_url: str | None,
) -> str:
    last_check = streak[-1]
    failing_since = streak[0].timestamp
    status_display = (
        str(last_check.status_code) if last_check.status_code is not None else "Sin respuesta"
    )
    error_display = last_check.error or "Sin detalle de error"
    actions_line = (
        f"- **Run de GitHub Actions:** [{run_url}]({run_url})"
        if run_url
        else "- **Run de GitHub Actions:** Ejecución local / no disponible"
    )

    return "\n".join(
        [
            f"## 🚨 Alerta de Monitor: {monitor.name}",
            "",
            (
                f"El monitor **{monitor.name}** (`{monitor.url}`) alcanzó "
                f"**{len(streak)} corridas fallidas consecutivas** "
                f"(umbral configurado: `{monitor.alert_after}`)."
            ),
            "",
            f"- **Categoría:** `{last_check.status_category}`",
            f"- **Falla desde:** `{failing_since}`",
            f"- **Corridas fallidas consecutivas:** `{len(streak)}`",
            f"- **Último status HTTP:** `{status_display}`",
            f"- **Último error:** `{error_display}`",
            f"- **Dashboard:** [{dashboard_url}]({dashboard_url})",
            actions_line,
            "",
            f"<!-- monitor-category: {last_check.status_category} -->",
            f"<!-- failing-since: {failing_since} -->",
        ]
    )


def _build_category_change_comment(
    *,
    previous_category: StatusCategory,
    last_check: CheckResult,
    streak_len: int,
    run_url: str | None,
) -> str:
    status_display = (
        str(last_check.status_code) if last_check.status_code is not None else "Sin respuesta"
    )
    error_display = last_check.error or "Sin detalle de error"
    lines = [
        "### 🔄 Cambio de categoría de falla",
        "",
        (
            f"La categoría del incidente cambió de `{previous_category}` "
            f"a `{last_check.status_category}` en la corrida `{last_check.timestamp}`."
        ),
        "",
        f"- **Corridas fallidas acumuladas:** `{streak_len}`",
        f"- **Último status HTTP:** `{status_display}`",
        f"- **Último error:** `{error_display}`",
    ]
    if run_url:
        lines.append(f"- **Run de GitHub Actions:** [{run_url}]({run_url})")
    lines.extend(["", f"<!-- monitor-category: {last_check.status_category} -->"])
    return "\n".join(lines)


def _build_recovery_comment(
    *,
    monitor: MonitorConfig,
    incident_start_iso: str,
    recovery_check: CheckResult,
    prior_failures_count: int,
) -> str:
    duration_str = format_incident_duration(incident_start_iso, recovery_check.timestamp)
    return "\n".join(
        [
            "### ✅ Servicio recuperado",
            "",
            (
                f"El monitor **{monitor.name}** volvió a estado `ok` "
                f"en la corrida `{recovery_check.timestamp}`."
            ),
            "",
            (
                f"- **Duración del incidente:** `{duration_str}` "
                f"(desde `{incident_start_iso}` hasta `{recovery_check.timestamp}`)"
            ),
            f"- **Corridas fallidas previas:** `{prior_failures_count}`",
            f"- **Latencia de recuperación:** `{recovery_check.latency_ms:.1f} ms`",
        ]
    )


def _github_request(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    json_body: dict[str, Any] | None = None,
    params: dict[str, str] | None = None,
    expected_statuses: tuple[int, ...] = (200,),
) -> httpx.Response:
    try:
        response = client.request(method, url, json=json_body, params=params)
    except httpx.HTTPError as exc:
        raise AlertError(
            f"Error de red al consultar GitHub API ({method} {url}): {type(exc).__name__}: {exc}"
        ) from exc

    if response.status_code not in expected_statuses:
        raise AlertError(
            f"Respuesta inesperada de GitHub API ({method} {url}): "
            f"HTTP {response.status_code} - {response.text[:200]}"
        )
    return response


def _ensure_label_exists(client: httpx.Client, api_base: str) -> None:
    label_url = f"{api_base}/labels/{ALERT_LABEL}"
    resp = _github_request(client, "GET", label_url, expected_statuses=(200, 404))
    if resp.status_code == 404:
        _github_request(
            client,
            "POST",
            f"{api_base}/labels",
            json_body={
                "name": ALERT_LABEL,
                "color": "d73a4a",
                "description": "Alerta automática por fallas consecutivas en qa-api-monitor",
            },
            expected_statuses=(201,),
        )


def _extract_monitor_checks(history: HistoryReport, monitor_name: str) -> list[CheckResult]:
    checks: list[CheckResult] = []
    for run in history.runs:
        for check in run.results:
            if check.name == monitor_name:
                checks.append(check)
    checks.sort(key=lambda c: _parse_iso_utc(c.timestamp))
    return checks


def _trailing_failure_streak(
    checks: Sequence[CheckResult], alert_on_degraded: bool
) -> list[CheckResult]:
    streak: list[CheckResult] = []
    for check in reversed(checks):
        if is_alert_failure(check.status_category, alert_on_degraded):
            streak.append(check)
        else:
            break
    streak.reverse()
    return streak


def process_alerts(
    *,
    history: HistoryReport,
    monitors: Sequence[MonitorConfig],
    repo: str = DEFAULT_REPO,
    token: str | None = None,
    dry_run: bool = False,
    dashboard_url: str | None = None,
    run_url: str | None = None,
) -> list[AlertAction]:
    """Evalúa el historial por monitor y abre, comenta o cierra Issues en GitHub."""
    owner_repo = repo.strip()
    if "/" not in owner_repo:
        raise AlertError(f"Formato de repositorio inválido: '{repo}'. Se esperaba 'owner/repo'.")

    owner, repo_name = owner_repo.split("/", 1)
    resolved_dashboard_url = dashboard_url or f"https://{owner}.github.io/{repo_name}/"
    api_base = f"https://api.github.com/repos/{owner_repo}"

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    actions: list[AlertAction] = []
    open_issues_by_title: dict[str, dict[str, Any]] = {}
    label_ensured = False

    with httpx.Client(headers=headers, timeout=10.0) as client:
        if not dry_run:
            resp = _github_request(
                client,
                "GET",
                f"{api_base}/issues",
                params={"state": "open", "labels": ALERT_LABEL, "per_page": "100"},
                expected_statuses=(200,),
            )
            raw_issues = resp.json()
            if isinstance(raw_issues, list):
                for item in raw_issues:
                    if isinstance(item, dict) and "pull_request" not in item:
                        title = str(item.get("title", ""))
                        if title and title not in open_issues_by_title:
                            open_issues_by_title[title] = item

        for monitor in monitors:
            checks = _extract_monitor_checks(history, monitor.name)
            title = issue_title_for_monitor(monitor.name)

            if not checks:
                actions.append(
                    AlertAction(
                        monitor_name=monitor.name,
                        action="unchanged",
                        summary_line=f"{monitor.name}: sin cambios (sin corridas registradas)",
                        dry_run=dry_run,
                    )
                )
                continue

            last_check = checks[-1]
            current_streak = _trailing_failure_streak(checks, monitor.alert_on_degraded)

            # Caso 1: La última corrida del monitor es una falla contabilizable
            if current_streak:
                streak_len = len(current_streak)
                if streak_len < monitor.alert_after:
                    actions.append(
                        AlertAction(
                            monitor_name=monitor.name,
                            action="unchanged",
                            summary_line=(
                                f"{monitor.name}: sin cambios "
                                f"({streak_len}/{monitor.alert_after} fallas consecutivas)"
                            ),
                            dry_run=dry_run,
                        )
                    )
                    continue

                if dry_run:
                    # En dry-run inferimos del propio historial sin llamar a la API
                    if streak_len == monitor.alert_after:
                        actions.append(
                            AlertAction(
                                monitor_name=monitor.name,
                                action="opened",
                                summary_line=(
                                    f"[DRY-RUN] {monitor.name}: abriría Issue '{title}' "
                                    f"({streak_len} fallas seguidas, "
                                    f"categoría={last_check.status_category}, "
                                    f"desde={current_streak[0].timestamp})"
                                ),
                                dry_run=True,
                            )
                        )
                    else:
                        prev_cat = current_streak[-2].status_category
                        if prev_cat != last_check.status_category:
                            actions.append(
                                AlertAction(
                                    monitor_name=monitor.name,
                                    action="commented",
                                    summary_line=(
                                        f"[DRY-RUN] {monitor.name}: comentaría cambio de categoría "
                                        f"({prev_cat} -> {last_check.status_category}) en '{title}'"
                                    ),
                                    dry_run=True,
                                )
                            )
                        else:
                            actions.append(
                                AlertAction(
                                    monitor_name=monitor.name,
                                    action="unchanged",
                                    summary_line=(
                                        f"[DRY-RUN] {monitor.name}: sin cambios "
                                        f"(Issue '{title}' ya abierto con "
                                        f"categoría {last_check.status_category})"
                                    ),
                                    dry_run=True,
                                )
                            )
                    continue

                existing_issue = open_issues_by_title.get(title)
                if existing_issue is None:
                    if not label_ensured:
                        _ensure_label_exists(client, api_base)
                        label_ensured = True

                    body = _build_issue_body(
                        monitor=monitor,
                        streak=current_streak,
                        dashboard_url=resolved_dashboard_url,
                        run_url=run_url,
                    )
                    created_resp = _github_request(
                        client,
                        "POST",
                        f"{api_base}/issues",
                        json_body={
                            "title": title,
                            "body": body,
                            "labels": [ALERT_LABEL],
                        },
                        expected_statuses=(201,),
                    )
                    created_data = created_resp.json()
                    issue_num = int(created_data.get("number", 0))
                    actions.append(
                        AlertAction(
                            monitor_name=monitor.name,
                            action="opened",
                            issue_number=issue_num,
                            summary_line=(
                                f"{monitor.name}: abrió Issue #{issue_num} "
                                f"({streak_len} fallas consecutivas, "
                                f"categoría={last_check.status_category})"
                            ),
                            dry_run=False,
                        )
                    )
                else:
                    issue_num = int(existing_issue["number"])
                    if streak_len > monitor.alert_after:
                        prev_cat = current_streak[-2].status_category
                    else:
                        body_cat = _extract_category_from_issue_body(existing_issue.get("body"))
                        prev_cat = (
                            body_cat if body_cat is not None else current_streak[-2].status_category
                        )

                    if prev_cat != last_check.status_category:
                        comment_body = _build_category_change_comment(
                            previous_category=prev_cat,
                            last_check=last_check,
                            streak_len=streak_len,
                            run_url=run_url,
                        )
                        _github_request(
                            client,
                            "POST",
                            f"{api_base}/issues/{issue_num}/comments",
                            json_body={"body": comment_body},
                            expected_statuses=(201,),
                        )
                        actions.append(
                            AlertAction(
                                monitor_name=monitor.name,
                                action="commented",
                                issue_number=issue_num,
                                summary_line=(
                                    f"{monitor.name}: comentó en Issue #{issue_num} "
                                    f"por cambio de categoría "
                                    f"({prev_cat} -> {last_check.status_category})"
                                ),
                                dry_run=False,
                            )
                        )
                    else:
                        actions.append(
                            AlertAction(
                                monitor_name=monitor.name,
                                action="unchanged",
                                issue_number=issue_num,
                                summary_line=(
                                    f"{monitor.name}: sin cambios "
                                    f"(Issue #{issue_num} ya abierto, "
                                    f"categoría={last_check.status_category})"
                                ),
                                dry_run=False,
                            )
                        )
                continue

            # Caso 2: La última corrida del monitor es "ok"
            if last_check.status_category == "ok":
                prior_streak = _trailing_failure_streak(checks[:-1], monitor.alert_on_degraded)
                if dry_run:
                    if len(prior_streak) >= monitor.alert_after:
                        duration_str = format_incident_duration(
                            prior_streak[0].timestamp, last_check.timestamp
                        )
                        actions.append(
                            AlertAction(
                                monitor_name=monitor.name,
                                action="closed",
                                summary_line=(
                                    f"[DRY-RUN] {monitor.name}: comentaría recuperación "
                                    f"(duración: {duration_str}) y cerraría Issue '{title}'"
                                ),
                                dry_run=True,
                            )
                        )
                    else:
                        actions.append(
                            AlertAction(
                                monitor_name=monitor.name,
                                action="unchanged",
                                summary_line=f"[DRY-RUN] {monitor.name}: sin cambios (estado ok)",
                                dry_run=True,
                            )
                        )
                    continue

                existing_issue = open_issues_by_title.get(title)
                if existing_issue is not None:
                    issue_num = int(existing_issue["number"])
                    incident_start_iso = (
                        prior_streak[0].timestamp
                        if prior_streak
                        else str(existing_issue.get("created_at") or last_check.timestamp)
                    )
                    duration_str = format_incident_duration(
                        incident_start_iso, last_check.timestamp
                    )
                    comment_body = _build_recovery_comment(
                        monitor=monitor,
                        incident_start_iso=incident_start_iso,
                        recovery_check=last_check,
                        prior_failures_count=len(prior_streak),
                    )
                    _github_request(
                        client,
                        "POST",
                        f"{api_base}/issues/{issue_num}/comments",
                        json_body={"body": comment_body},
                        expected_statuses=(201,),
                    )
                    _github_request(
                        client,
                        "PATCH",
                        f"{api_base}/issues/{issue_num}",
                        json_body={"state": "closed"},
                        expected_statuses=(200,),
                    )
                    actions.append(
                        AlertAction(
                            monitor_name=monitor.name,
                            action="closed",
                            issue_number=issue_num,
                            summary_line=(
                                f"{monitor.name}: cerró Issue #{issue_num} tras recuperación "
                                f"(duración del incidente: {duration_str})"
                            ),
                            dry_run=False,
                        )
                    )
                else:
                    actions.append(
                        AlertAction(
                            monitor_name=monitor.name,
                            action="unchanged",
                            summary_line=f"{monitor.name}: sin cambios (estado ok)",
                            dry_run=False,
                        )
                    )
                continue

            # Caso 3: degraded cuando alert_on_degraded=False
            actions.append(
                AlertAction(
                    monitor_name=monitor.name,
                    action="unchanged",
                    summary_line=(
                        f"{monitor.name}: sin cambios "
                        f"(estado {last_check.status_category} ignorado "
                        "por alert_on_degraded=false)"
                    ),
                    dry_run=dry_run,
                )
            )

    return actions


def _load_history_file(path: str | Path) -> HistoryReport:
    history_path = Path(path)
    if not history_path.is_file():
        raise HistoryError(f"No se encontró el archivo de historial: {history_path}")
    try:
        raw = json.loads(history_path.read_text(encoding="utf-8-sig"))
        return HistoryReport.model_validate(raw)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise HistoryError(f"Historial inválido en {history_path}: {exc}") from exc


def _write_summary_lines(actions: Sequence[AlertAction], summary_path: str | Path) -> None:
    target = Path(summary_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = ["", "### Alertas (GitHub Issues)", ""]
    for act in actions:
        lines.append(f"- {act.summary_line}")
    lines.append("")
    with target.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m monitor.alerts",
        description=(
            "Abre, comenta o cierra GitHub Issues ante fallas consecutivas en history.json."
        ),
    )
    parser.add_argument(
        "--history",
        default="site/history.json",
        help="Ruta al archivo history.json ya mergeado (default: site/history.json).",
    )
    parser.add_argument(
        "--config",
        default="config/monitors.yaml",
        help="Ruta al archivo YAML de configuración (default: config/monitors.yaml).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra qué acciones tomaría sin llamar a la API de GitHub.",
    )
    parser.add_argument(
        "--summary-md",
        default=None,
        help="Ruta opcional donde agregar el resumen Markdown de acciones tomadas.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    token = os.environ.get("GITHUB_TOKEN", "").strip() or None
    repo = os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPO).strip() or DEFAULT_REPO
    server_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
    run_id = os.environ.get("GITHUB_RUN_ID", "").strip()
    run_url = f"{server_url}/{repo}/actions/runs/{run_id}" if run_id else None

    effective_dry_run = bool(args.dry_run or not token)

    try:
        monitors = load_config(args.config)
        history = _load_history_file(args.history)
        actions = process_alerts(
            history=history,
            monitors=monitors,
            repo=repo,
            token=token,
            dry_run=effective_dry_run,
            run_url=run_url,
        )
    except (ConfigError, HistoryError, AlertError, OSError) as exc:
        print(f"Error en alertas: {exc}", file=sys.stderr)
        return 1

    for act in actions:
        print(act.summary_line)

    summary_target = args.summary_md or os.environ.get("GITHUB_STEP_SUMMARY", "").strip() or None
    if summary_target:
        try:
            _write_summary_lines(actions, summary_target)
        except OSError as exc:
            print(f"Error al escribir resumen de alertas: {exc}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
