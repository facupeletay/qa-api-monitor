"""Gestión automática de alertas mediante GitHub Issues y notificaciones externas (Fases 5 y 6)."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel, Field, ValidationError

from monitor.config import ConfigError, load_config
from monitor.history import HistoryError, HistoryReport, _parse_iso_utc
from monitor.models import (
    ALL_STATUS_CATEGORIES,
    AlertsConfig,
    CheckResult,
    MonitorConfig,
    StatusCategory,
)

ALERT_LABEL = "monitor-alert"
DEFAULT_REPO = "facupeletay/qa-api-monitor"

ActionKind = Literal["OPEN", "COMMENT_CATEGORY_CHANGE", "CLOSE_RECOVERED", "NOOP"]
AlertActionType = Literal["opened", "commented", "closed", "unchanged"]

_KIND_TO_LEGACY_ACTION: dict[ActionKind, AlertActionType] = {
    "OPEN": "opened",
    "COMMENT_CATEGORY_CHANGE": "commented",
    "CLOSE_RECOVERED": "closed",
    "NOOP": "unchanged",
}


class AlertError(RuntimeError):
    """Error al interactuar con la API de GitHub o al procesar el archivo de historial."""


class OpenIssue(BaseModel):
    """Representación tipada de un Issue de alerta abierto para un monitor."""

    number: int
    title: str
    monitor_id: str
    category: StatusCategory | None = None
    failing_since: str | None = None
    created_at: str | None = None
    body: str | None = None


class Action(BaseModel):
    """Decisión tipada producida por decide_action para un monitor."""

    kind: ActionKind
    monitor_id: str
    monitor_name: str
    monitor_url: str
    alert_after: int
    title: str
    category: StatusCategory | None = None
    previous_category: StatusCategory | None = None
    failing_since: str | None = None
    recovered_at: str | None = None
    duration: str | None = None
    streak_count: int = 0
    last_status_code: int | None = None
    last_error: str | None = None
    last_latency_ms: float | None = None
    last_timestamp: str | None = None
    open_issue_number: int | None = None
    reason: str = ""


class AlertAction(BaseModel):
    """Resultado final de la ejecución (real o dry-run) de una decisión de alerta."""

    monitor_id: str = ""
    monitor_name: str
    kind: ActionKind = "NOOP"
    action: AlertActionType
    summary_line: str
    issue_number: int | None = None
    dry_run: bool = False
    notified_channels: list[str] = Field(default_factory=list)


def issue_title_for_monitor(monitor_name: str) -> str:
    """Devuelve el título fijo del Issue de alerta para un monitor."""
    return f"[ALERTA] {monitor_name}"


def monitor_id_marker(monitor_id: str) -> str:
    """Construye el marcador HTML oculto que identifica de forma estable al monitor."""
    return f"<!-- monitor-id: {monitor_id} -->"


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


def _extract_monitor_id_from_issue_body(body: str | None) -> str | None:
    """Extrae el monitor-id del marcador HTML oculto en el cuerpo del Issue."""
    if not body:
        return None
    match = re.search(r"<!--\s*monitor-id:\s*([^\s>]+?)\s*-->", body)
    if match:
        return match.group(1).strip()
    return None


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


def _extract_failing_since_from_issue_body(body: str | None) -> str | None:
    if not body:
        return None
    marker_match = re.search(r"<!--\s*failing-since:\s*([^\s>]+?)\s*-->", body)
    if marker_match:
        return marker_match.group(1).strip()
    return None


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


def _resolve_alert_cfg(
    monitor: MonitorConfig, alert_cfg: AlertsConfig | None = None
) -> AlertsConfig:
    if alert_cfg is not None:
        return alert_cfg
    return AlertsConfig(
        alert_after=monitor.alert_after,
        alert_on_degraded=monitor.alert_on_degraded,
    )


def infer_open_issue_from_history(
    monitor: MonitorConfig,
    history: HistoryReport,
    alert_cfg: AlertsConfig | None = None,
) -> OpenIssue | None:
    """Infiere en modo dry-run si existe un Issue abierto a partir del historial previo.

    Como en `--dry-run` no hay acceso a la API de GitHub, `open_issue` se infiere
    recorriendo las corridas previas a la última (`checks[:-1]`): se considera que hay
    un Issue abierto si existe una racha previa de fallas contabilizables `>= alert_after`
    que todavía no se recuperó (es decir, que no tuvo ninguna corrida posterior en estado
    `ok`). Si durante ese incidente abierto hubo un cambio de categoría en corridas
    previas, se conserva la última categoría observada antes de la corrida actual.
    """
    cfg = _resolve_alert_cfg(monitor, alert_cfg)
    checks = _extract_monitor_checks(history, monitor.name)
    if len(checks) <= 1:
        return None

    prior_checks = checks[:-1]
    streak: list[CheckResult] = []
    inferred: OpenIssue | None = None

    for check in prior_checks:
        if is_alert_failure(check.status_category, cfg.alert_on_degraded):
            streak.append(check)
            if inferred is None and len(streak) >= cfg.alert_after:
                inferred = OpenIssue(
                    number=0,
                    title=issue_title_for_monitor(monitor.name),
                    monitor_id=monitor.monitor_id,
                    category=check.status_category,
                    failing_since=streak[0].timestamp,
                    created_at=check.timestamp,
                )
            elif inferred is not None:
                inferred.category = check.status_category
        elif check.status_category == "ok":
            streak = []
            inferred = None
        else:
            # Estado degraded con alert_on_degraded=False: corta racha previa si no abrió
            # issue aún, pero no cierra un issue ya abierto porque no se recuperó a ok.
            streak = []

    return inferred


def decide_action(
    monitor: MonitorConfig,
    history: HistoryReport,
    alert_cfg: AlertsConfig | None = None,
    open_issue: OpenIssue | None = None,
) -> Action:
    """Función pura que decide la acción de alerta a tomar para un monitor.

    Es compartida de forma idéntica entre la corrida real y `--dry-run`. Devuelve una
    instancia de `Action` con `kind` en `{"OPEN", "COMMENT_CATEGORY_CHANGE",
    "CLOSE_RECOVERED", "NOOP"}` y todos los metadatos necesarios para ejecutarla.
    """
    cfg = _resolve_alert_cfg(monitor, alert_cfg)
    checks = _extract_monitor_checks(history, monitor.name)
    title = issue_title_for_monitor(monitor.name)
    mon_id = monitor.monitor_id

    if not checks:
        return Action(
            kind="NOOP",
            monitor_id=mon_id,
            monitor_name=monitor.name,
            monitor_url=monitor.url,
            alert_after=cfg.alert_after,
            title=title,
            reason="sin corridas registradas",
        )

    last_check = checks[-1]
    current_streak = _trailing_failure_streak(checks, cfg.alert_on_degraded)

    # Caso 1: La última corrida del monitor es una falla contabilizable
    if current_streak:
        streak_len = len(current_streak)
        if streak_len < cfg.alert_after and open_issue is None:
            return Action(
                kind="NOOP",
                monitor_id=mon_id,
                monitor_name=monitor.name,
                monitor_url=monitor.url,
                alert_after=cfg.alert_after,
                title=title,
                category=last_check.status_category,
                streak_count=streak_len,
                last_status_code=last_check.status_code,
                last_error=last_check.error,
                last_latency_ms=last_check.latency_ms,
                last_timestamp=last_check.timestamp,
                reason=f"{streak_len}/{cfg.alert_after} fallas consecutivas",
            )

        if open_issue is None:
            return Action(
                kind="OPEN",
                monitor_id=mon_id,
                monitor_name=monitor.name,
                monitor_url=monitor.url,
                alert_after=cfg.alert_after,
                title=title,
                category=last_check.status_category,
                failing_since=current_streak[0].timestamp,
                streak_count=streak_len,
                last_status_code=last_check.status_code,
                last_error=last_check.error,
                last_latency_ms=last_check.latency_ms,
                last_timestamp=last_check.timestamp,
            )

        # Ya existe un Issue abierto: evaluar si cambió la categoría
        if streak_len > cfg.alert_after and len(current_streak) >= 2:
            prev_cat: StatusCategory | None = current_streak[-2].status_category
        elif open_issue.category is not None:
            prev_cat = open_issue.category
        elif len(current_streak) >= 2:
            prev_cat = current_streak[-2].status_category
        else:
            prev_cat = last_check.status_category

        if prev_cat != last_check.status_category:
            return Action(
                kind="COMMENT_CATEGORY_CHANGE",
                monitor_id=mon_id,
                monitor_name=monitor.name,
                monitor_url=monitor.url,
                alert_after=cfg.alert_after,
                title=title,
                category=last_check.status_category,
                previous_category=prev_cat,
                failing_since=open_issue.failing_since or current_streak[0].timestamp,
                streak_count=streak_len,
                last_status_code=last_check.status_code,
                last_error=last_check.error,
                last_latency_ms=last_check.latency_ms,
                last_timestamp=last_check.timestamp,
                open_issue_number=open_issue.number,
            )

        return Action(
            kind="NOOP",
            monitor_id=mon_id,
            monitor_name=monitor.name,
            monitor_url=monitor.url,
            alert_after=cfg.alert_after,
            title=title,
            category=last_check.status_category,
            failing_since=open_issue.failing_since or current_streak[0].timestamp,
            streak_count=streak_len,
            last_status_code=last_check.status_code,
            last_error=last_check.error,
            last_latency_ms=last_check.latency_ms,
            last_timestamp=last_check.timestamp,
            open_issue_number=open_issue.number,
            reason=f"Issue ya abierto, categoría={last_check.status_category}",
        )

    # Caso 2: La última corrida del monitor es "ok"
    if last_check.status_category == "ok":
        if open_issue is not None:
            prior_streak = _trailing_failure_streak(checks[:-1], cfg.alert_on_degraded)
            incident_start_iso = (
                prior_streak[0].timestamp
                if prior_streak
                else (open_issue.failing_since or open_issue.created_at or last_check.timestamp)
            )
            duration_str = format_incident_duration(incident_start_iso, last_check.timestamp)
            return Action(
                kind="CLOSE_RECOVERED",
                monitor_id=mon_id,
                monitor_name=monitor.name,
                monitor_url=monitor.url,
                alert_after=cfg.alert_after,
                title=title,
                category="ok",
                failing_since=incident_start_iso,
                recovered_at=last_check.timestamp,
                duration=duration_str,
                streak_count=len(prior_streak),
                last_status_code=last_check.status_code,
                last_latency_ms=last_check.latency_ms,
                last_timestamp=last_check.timestamp,
                open_issue_number=open_issue.number,
            )

        return Action(
            kind="NOOP",
            monitor_id=mon_id,
            monitor_name=monitor.name,
            monitor_url=monitor.url,
            alert_after=cfg.alert_after,
            title=title,
            category="ok",
            last_status_code=last_check.status_code,
            last_latency_ms=last_check.latency_ms,
            last_timestamp=last_check.timestamp,
            reason="estado ok",
        )

    # Caso 3: degraded cuando alert_on_degraded=False
    return Action(
        kind="NOOP",
        monitor_id=mon_id,
        monitor_name=monitor.name,
        monitor_url=monitor.url,
        alert_after=cfg.alert_after,
        title=title,
        category=last_check.status_category,
        last_status_code=last_check.status_code,
        last_latency_ms=last_check.latency_ms,
        last_timestamp=last_check.timestamp,
        open_issue_number=open_issue.number if open_issue is not None else None,
        reason=f"estado {last_check.status_category} ignorado por alert_on_degraded=false",
    )


def _build_issue_body(
    *,
    decision: Action,
    dashboard_url: str,
    run_url: str | None,
) -> str:
    status_display = (
        str(decision.last_status_code) if decision.last_status_code is not None else "Sin respuesta"
    )
    error_display = decision.last_error or "Sin detalle de error"
    actions_line = (
        f"- **Run de GitHub Actions:** [{run_url}]({run_url})"
        if run_url
        else "- **Run de GitHub Actions:** Ejecución local / no disponible"
    )

    return "\n".join(
        [
            f"## 🚨 Alerta de Monitor: {decision.monitor_name}",
            "",
            (
                f"El monitor **{decision.monitor_name}** (`{decision.monitor_url}`) alcanzó "
                f"**{decision.streak_count} corridas fallidas consecutivas** "
                f"(umbral configurado: `{decision.alert_after}`)."
            ),
            "",
            f"- **ID del monitor:** `{decision.monitor_id}`",
            f"- **Categoría:** `{decision.category}`",
            f"- **Falla desde:** `{decision.failing_since}`",
            f"- **Corridas fallidas consecutivas:** `{decision.streak_count}`",
            f"- **Último status HTTP:** `{status_display}`",
            f"- **Último error:** `{error_display}`",
            f"- **Dashboard:** [{dashboard_url}]({dashboard_url})",
            actions_line,
            "",
            monitor_id_marker(decision.monitor_id),
            f"<!-- monitor-category: {decision.category} -->",
            f"<!-- failing-since: {decision.failing_since} -->",
        ]
    )


def _build_category_change_comment(
    *,
    decision: Action,
    run_url: str | None,
) -> str:
    status_display = (
        str(decision.last_status_code) if decision.last_status_code is not None else "Sin respuesta"
    )
    error_display = decision.last_error or "Sin detalle de error"
    lines = [
        "### 🔄 Cambio de categoría de falla",
        "",
        (
            f"La categoría del incidente cambió de `{decision.previous_category}` "
            f"a `{decision.category}` en la corrida `{decision.last_timestamp}`."
        ),
        "",
        f"- **Corridas fallidas acumuladas:** `{decision.streak_count}`",
        f"- **Último status HTTP:** `{status_display}`",
        f"- **Último error:** `{error_display}`",
    ]
    if run_url:
        lines.append(f"- **Run de GitHub Actions:** [{run_url}]({run_url})")
    lines.extend(["", f"<!-- monitor-category: {decision.category} -->"])
    return "\n".join(lines)


def _build_recovery_comment(*, decision: Action) -> str:
    latency_val = decision.last_latency_ms if decision.last_latency_ms is not None else 0.0
    lines = [
        "### ✅ Servicio recuperado",
        "",
        (
            f"El monitor **{decision.monitor_name}** volvió a estado `ok` "
            f"en la corrida `{decision.recovered_at}`."
        ),
        "",
        (
            f"- **Duración del incidente:** `{decision.duration}` "
            f"(desde `{decision.failing_since}` hasta `{decision.recovered_at}`)"
        ),
    ]
    if decision.streak_count > 0:
        lines.append(f"- **Corridas fallidas previas:** `{decision.streak_count}`")
    lines.append(f"- **Latencia de recuperación:** `{latency_val:.1f} ms`")
    return "\n".join(lines)


def _build_external_notification_message(
    *,
    decision: Action,
    issue_number: int | None,
    dashboard_url: str,
    repo: str,
) -> str:
    """Construye un mensaje conciso para notificaciones externas (Webhook / Telegram)."""
    issue_ref = (
        f"#{issue_number} (https://github.com/{repo}/issues/{issue_number})"
        if issue_number
        else "N/A"
    )
    if decision.kind == "OPEN":
        return "\n".join(
            [
                f"🚨 [ALERTA ABIERTA] {decision.monitor_name}",
                f"• Estado: {decision.category} ({decision.streak_count} fallas consecutivas)",
                f"• Error: {decision.last_error or 'Sin detalle'}",
                f"• Issue: {issue_ref}",
                f"• Dashboard: {dashboard_url}",
            ]
        )
    if decision.kind == "COMMENT_CATEGORY_CHANGE":
        return "\n".join(
            [
                f"🔄 [CAMBIO DE CATEGORÍA] {decision.monitor_name}",
                (
                    f"• Cambio: {decision.previous_category} -> {decision.category} "
                    f"({decision.streak_count} fallas consecutivas)"
                ),
                f"• Error: {decision.last_error or 'Sin detalle'}",
                f"• Issue: {issue_ref}",
                f"• Dashboard: {dashboard_url}",
            ]
        )
    latency_val = decision.last_latency_ms if decision.last_latency_ms is not None else 0.0
    return "\n".join(
        [
            f"✅ [SERVICIO RECUPERADO] {decision.monitor_name}",
            f"• Duración del incidente: {decision.duration}",
            f"• Latencia actual: {latency_val:.1f} ms",
            f"• Issue cerrado: {issue_ref}",
            f"• Dashboard: {dashboard_url}",
        ]
    )


def send_webhook_notification(
    client: httpx.Client,
    webhook_url: str,
    *,
    message: str,
    decision: Action,
    issue_number: int | None,
) -> bool:
    """Envía una notificación a un Webhook (Discord, Slack o JSON genérico).

    Aísla fallas: si el servidor externo devuelve error o timeout, registra un
    Warning en stderr y devuelve False para no interrumpir la gestión de Issues.
    """
    lower_url = webhook_url.lower()
    if "discord.com/api/webhooks" in lower_url or "discordapp.com/api/webhooks" in lower_url:
        payload: dict[str, Any] = {"content": message}
    elif "hooks.slack.com" in lower_url:
        payload = {"text": message}
    else:
        payload = {
            "text": message,
            "content": message,
            "kind": decision.kind,
            "monitor_id": decision.monitor_id,
            "monitor_name": decision.monitor_name,
            "category": decision.category,
            "issue_number": issue_number,
        }

    try:
        response = client.post(webhook_url, json=payload)
    except httpx.HTTPError as exc:
        print(
            f"Warning: error de red al enviar notificación webhook: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return False

    if not (200 <= response.status_code < 300):
        print(
            f"Warning: respuesta inesperada del webhook: HTTP {response.status_code} "
            f"- {response.text[:200]}",
            file=sys.stderr,
        )
        return False
    return True


def send_telegram_notification(
    client: httpx.Client,
    bot_token: str,
    chat_id: str,
    *,
    message: str,
) -> bool:
    """Envía una notificación mediante Telegram Bot API (sendMessage).

    Aísla fallas sin exponer el token del bot en stderr si ocurre un error.
    """
    telegram_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": True,
    }
    try:
        response = client.post(telegram_url, json=payload)
    except httpx.HTTPError as exc:
        print(
            f"Warning: error de red al enviar notificación de Telegram (chat_id={chat_id}): "
            f"{type(exc).__name__}",
            file=sys.stderr,
        )
        return False

    if not (200 <= response.status_code < 300):
        print(
            f"Warning: respuesta inesperada de Telegram API (chat_id={chat_id}): "
            f"HTTP {response.status_code} - {response.text[:200]}",
            file=sys.stderr,
        )
        return False
    return True


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


def _list_open_alert_issues(
    client: httpx.Client,
    api_base: str,
    *,
    per_page: int = 100,
) -> list[OpenIssue]:
    """Lista los Issues abiertos con el label de alerta usando paginación REST (sin /search)."""
    collected: list[OpenIssue] = []
    page = 1
    saw_link_header = False
    while True:
        resp = _github_request(
            client,
            "GET",
            f"{api_base}/issues",
            params={
                "state": "open",
                "labels": ALERT_LABEL,
                "per_page": str(per_page),
                "page": str(page),
            },
            expected_statuses=(200,),
        )
        raw_page = resp.json()
        if not isinstance(raw_page, list) or not raw_page:
            break

        for item in raw_page:
            if not isinstance(item, dict) or "pull_request" in item:
                continue
            body = item.get("body")
            body_str = str(body) if body is not None else ""
            mon_id = _extract_monitor_id_from_issue_body(body_str)
            if not mon_id:
                continue
            collected.append(
                OpenIssue(
                    number=int(item.get("number", 0)),
                    title=str(item.get("title", "")),
                    monitor_id=mon_id,
                    category=_extract_category_from_issue_body(body_str),
                    failing_since=_extract_failing_since_from_issue_body(body_str),
                    created_at=(
                        str(item.get("created_at")) if item.get("created_at") is not None else None
                    ),
                    body=body_str,
                )
            )

        link_header = resp.headers.get("Link", "")
        if link_header:
            saw_link_header = True
        has_next_link = 'rel="next"' in link_header
        if saw_link_header:
            if not has_next_link:
                break
        elif len(raw_page) < per_page:
            break
        page += 1

    return collected


class AlertsGitHubClientProtocol(Protocol):
    """Interfaz común entre el cliente real de GitHub y el cliente de dry-run."""

    def find_open_issue(
        self, monitor: MonitorConfig, history: HistoryReport, alert_cfg: AlertsConfig
    ) -> OpenIssue | None: ...

    def execute(self, decision: Action) -> AlertAction: ...


class RealGitHubAlertsClient:
    """Cliente real de GitHub Issues que ejecuta las acciones vía HTTP (httpx)."""

    def __init__(
        self,
        *,
        client: httpx.Client,
        api_base: str,
        dashboard_url: str,
        run_url: str | None,
        per_page: int = 100,
    ) -> None:
        self._client = client
        self._api_base = api_base
        self._dashboard_url = dashboard_url
        self._run_url = run_url
        self._per_page = per_page
        self._open_issues_loaded = False
        self._issues_by_monitor_id: dict[str, list[OpenIssue]] = {}
        self._label_ensured = False

    def _ensure_issues_loaded(self) -> None:
        if self._open_issues_loaded:
            return
        all_open = _list_open_alert_issues(self._client, self._api_base, per_page=self._per_page)
        for issue in all_open:
            self._issues_by_monitor_id.setdefault(issue.monitor_id, []).append(issue)
        self._open_issues_loaded = True

    def _ensure_label_exists(self) -> None:
        if self._label_ensured:
            return
        label_url = f"{self._api_base}/labels/{ALERT_LABEL}"
        resp = _github_request(self._client, "GET", label_url, expected_statuses=(200, 404))
        if resp.status_code == 404:
            _github_request(
                self._client,
                "POST",
                f"{self._api_base}/labels",
                json_body={
                    "name": ALERT_LABEL,
                    "color": "d73a4a",
                    "description": ("Alerta automática por fallas consecutivas en qa-api-monitor"),
                },
                expected_statuses=(201,),
            )
        self._label_ensured = True

    def find_open_issue(
        self, monitor: MonitorConfig, history: HistoryReport, alert_cfg: AlertsConfig
    ) -> OpenIssue | None:
        del history, alert_cfg
        self._ensure_issues_loaded()
        matches = self._issues_by_monitor_id.get(monitor.monitor_id, [])
        if not matches:
            return None
        if len(matches) > 1:
            sorted_matches = sorted(
                matches,
                key=lambda i: (
                    _parse_iso_utc(i.created_at)
                    if i.created_at
                    else _parse_iso_utc("1970-01-01T00:00:00Z"),
                    i.number,
                ),
            )
            oldest = sorted_matches[0]
            dup_numbers = ", ".join(f"#{i.number}" for i in sorted_matches)
            print(
                f"Warning: se encontraron múltiples Issues abiertos para el monitor "
                f"'{monitor.name}' (monitor-id: {monitor.monitor_id}): {dup_numbers}. "
                f"Se usará el más viejo (#{oldest.number}).",
                file=sys.stderr,
            )
            return oldest
        return matches[0]

    def execute(self, decision: Action) -> AlertAction:
        legacy = _KIND_TO_LEGACY_ACTION[decision.kind]

        if decision.kind == "OPEN":
            self._ensure_label_exists()
            body = _build_issue_body(
                decision=decision,
                dashboard_url=self._dashboard_url,
                run_url=self._run_url,
            )
            created_resp = _github_request(
                self._client,
                "POST",
                f"{self._api_base}/issues",
                json_body={
                    "title": decision.title,
                    "body": body,
                    "labels": [ALERT_LABEL],
                },
                expected_statuses=(201,),
            )
            created_data = created_resp.json()
            issue_num = int(created_data.get("number", 0))
            return AlertAction(
                monitor_id=decision.monitor_id,
                monitor_name=decision.monitor_name,
                kind=decision.kind,
                action=legacy,
                issue_number=issue_num,
                summary_line=(
                    f"{decision.monitor_name}: abrió Issue #{issue_num} "
                    f"({decision.streak_count} fallas consecutivas, "
                    f"categoría={decision.category})"
                ),
                dry_run=False,
            )

        if decision.kind == "COMMENT_CATEGORY_CHANGE":
            issue_num = int(decision.open_issue_number or 0)
            comment_body = _build_category_change_comment(
                decision=decision,
                run_url=self._run_url,
            )
            _github_request(
                self._client,
                "POST",
                f"{self._api_base}/issues/{issue_num}/comments",
                json_body={"body": comment_body},
                expected_statuses=(201,),
            )
            return AlertAction(
                monitor_id=decision.monitor_id,
                monitor_name=decision.monitor_name,
                kind=decision.kind,
                action=legacy,
                issue_number=issue_num,
                summary_line=(
                    f"{decision.monitor_name}: comentó en Issue #{issue_num} "
                    f"por cambio de categoría "
                    f"({decision.previous_category} -> {decision.category})"
                ),
                dry_run=False,
            )

        if decision.kind == "CLOSE_RECOVERED":
            issue_num = int(decision.open_issue_number or 0)
            comment_body = _build_recovery_comment(decision=decision)
            _github_request(
                self._client,
                "POST",
                f"{self._api_base}/issues/{issue_num}/comments",
                json_body={"body": comment_body},
                expected_statuses=(201,),
            )
            _github_request(
                self._client,
                "PATCH",
                f"{self._api_base}/issues/{issue_num}",
                json_body={"state": "closed"},
                expected_statuses=(200,),
            )
            return AlertAction(
                monitor_id=decision.monitor_id,
                monitor_name=decision.monitor_name,
                kind=decision.kind,
                action=legacy,
                issue_number=issue_num,
                summary_line=(
                    f"{decision.monitor_name}: cerró Issue #{issue_num} tras recuperación "
                    f"(duración del incidente: {decision.duration})"
                ),
                dry_run=False,
            )

        return AlertAction(
            monitor_id=decision.monitor_id,
            monitor_name=decision.monitor_name,
            kind=decision.kind,
            action=legacy,
            issue_number=decision.open_issue_number,
            summary_line=f"{decision.monitor_name}: sin cambios ({decision.reason})",
            dry_run=False,
        )


class DryRunGitHubAlertsClient:
    """Cliente dry-run que infiere el estado desde el historial y nunca realiza llamadas HTTP."""

    def find_open_issue(
        self, monitor: MonitorConfig, history: HistoryReport, alert_cfg: AlertsConfig
    ) -> OpenIssue | None:
        return infer_open_issue_from_history(monitor, history, alert_cfg)

    def execute(self, decision: Action) -> AlertAction:
        legacy = _KIND_TO_LEGACY_ACTION[decision.kind]

        if decision.kind == "OPEN":
            return AlertAction(
                monitor_id=decision.monitor_id,
                monitor_name=decision.monitor_name,
                kind=decision.kind,
                action=legacy,
                summary_line=(
                    f"[DRY-RUN] {decision.monitor_name}: abriría Issue '{decision.title}' "
                    f"({decision.streak_count} fallas seguidas, "
                    f"categoría={decision.category}, "
                    f"desde={decision.failing_since})"
                ),
                dry_run=True,
            )

        if decision.kind == "COMMENT_CATEGORY_CHANGE":
            return AlertAction(
                monitor_id=decision.monitor_id,
                monitor_name=decision.monitor_name,
                kind=decision.kind,
                action=legacy,
                summary_line=(
                    f"[DRY-RUN] {decision.monitor_name}: comentaría cambio de categoría "
                    f"({decision.previous_category} -> {decision.category}) "
                    f"en '{decision.title}'"
                ),
                dry_run=True,
            )

        if decision.kind == "CLOSE_RECOVERED":
            return AlertAction(
                monitor_id=decision.monitor_id,
                monitor_name=decision.monitor_name,
                kind=decision.kind,
                action=legacy,
                summary_line=(
                    f"[DRY-RUN] {decision.monitor_name}: comentaría recuperación "
                    f"(duración: {decision.duration}) y cerraría Issue '{decision.title}'"
                ),
                dry_run=True,
            )

        return AlertAction(
            monitor_id=decision.monitor_id,
            monitor_name=decision.monitor_name,
            kind=decision.kind,
            action=legacy,
            summary_line=(f"[DRY-RUN] {decision.monitor_name}: sin cambios ({decision.reason})"),
            dry_run=True,
        )


def process_alerts(
    *,
    history: HistoryReport,
    monitors: Sequence[MonitorConfig],
    repo: str = DEFAULT_REPO,
    token: str | None = None,
    dry_run: bool = False,
    dashboard_url: str | None = None,
    run_url: str | None = None,
    per_page: int = 100,
    webhook_url: str | None = None,
    telegram_bot_token: str | None = None,
    telegram_chat_id: str | None = None,
) -> list[AlertAction]:
    """Evalúa el historial por monitor usando decide_action y el cliente correspondiente."""
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

    clean_webhook = webhook_url.strip() if webhook_url else None
    clean_tg_token = telegram_bot_token.strip() if telegram_bot_token else None
    clean_tg_chat = telegram_chat_id.strip() if telegram_chat_id else None

    actions: list[AlertAction] = []

    with (
        httpx.Client(headers=headers, timeout=10.0) as http_client,
        httpx.Client(timeout=10.0) as notify_client,
    ):
        gh_client: AlertsGitHubClientProtocol
        if dry_run:
            gh_client = DryRunGitHubAlertsClient()
        else:
            gh_client = RealGitHubAlertsClient(
                client=http_client,
                api_base=api_base,
                dashboard_url=resolved_dashboard_url,
                run_url=run_url,
                per_page=per_page,
            )

        for monitor in monitors:
            cfg = _resolve_alert_cfg(monitor)
            open_issue = gh_client.find_open_issue(monitor, history, cfg)
            decision = decide_action(monitor, history, cfg, open_issue)
            alert_action = gh_client.execute(decision)

            if decision.kind in {"OPEN", "COMMENT_CATEGORY_CHANGE", "CLOSE_RECOVERED"}:
                if dry_run:
                    if clean_webhook:
                        alert_action.notified_channels.append("webhook")
                    if clean_tg_token and clean_tg_chat:
                        alert_action.notified_channels.append("telegram")
                else:
                    msg = _build_external_notification_message(
                        decision=decision,
                        issue_number=alert_action.issue_number,
                        dashboard_url=resolved_dashboard_url,
                        repo=owner_repo,
                    )
                    if clean_webhook and send_webhook_notification(
                        notify_client,
                        clean_webhook,
                        message=msg,
                        decision=decision,
                        issue_number=alert_action.issue_number,
                    ):
                        alert_action.notified_channels.append("webhook")
                    if (
                        clean_tg_token
                        and clean_tg_chat
                        and send_telegram_notification(
                            notify_client,
                            clean_tg_token,
                            clean_tg_chat,
                            message=msg,
                        )
                    ):
                        alert_action.notified_channels.append("telegram")

            actions.append(alert_action)

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
            "Abre, comenta o cierra GitHub Issues y envía notificaciones externas "
            "ante fallas consecutivas en history.json."
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
        help="Muestra qué acciones tomaría sin llamar a la API de GitHub ni a webhooks.",
    )
    parser.add_argument(
        "--summary-md",
        default=None,
        help="Ruta opcional donde agregar el resumen Markdown de acciones tomadas.",
    )
    parser.add_argument(
        "--webhook-url",
        default=None,
        help="URL opcional de Webhook (Discord / Slack / JSON) o env ALERT_WEBHOOK_URL.",
    )
    parser.add_argument(
        "--telegram-bot-token",
        default=None,
        help="Token opcional del bot de Telegram o env TELEGRAM_BOT_TOKEN.",
    )
    parser.add_argument(
        "--telegram-chat-id",
        default=None,
        help="Chat ID opcional de Telegram o env TELEGRAM_CHAT_ID.",
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

    webhook_url = (args.webhook_url or os.environ.get("ALERT_WEBHOOK_URL", "")).strip() or None
    telegram_bot_token = (
        args.telegram_bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    ).strip() or None
    telegram_chat_id = (
        args.telegram_chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
    ).strip() or None

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
            webhook_url=webhook_url,
            telegram_bot_token=telegram_bot_token,
            telegram_chat_id=telegram_chat_id,
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
