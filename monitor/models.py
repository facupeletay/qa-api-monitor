"""Modelos de datos de configuración y resultados para qa-api-monitor."""

from __future__ import annotations

import re
import unicodedata
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from monitor.contracts import CONTRACTS, get_contract

HttpMethod = Literal["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]
StatusCategory = Literal[
    "ok",
    "degraded",
    "contract_error",
    "client_error",
    "server_error",
    "network_error",
]
ALL_STATUS_CATEGORIES: tuple[StatusCategory, ...] = (
    "ok",
    "degraded",
    "contract_error",
    "client_error",
    "server_error",
    "network_error",
)


def slugify_monitor_name(name: str) -> str:
    """Convierte el nombre de un monitor en un identificador estable (slug)."""
    normalized = unicodedata.normalize("NFKD", name)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    return slug or "monitor"


class AlertsConfig(BaseModel):
    """Configuración global de alertas por fallas consecutivas."""

    alert_after: int = Field(default=3, ge=1)
    alert_on_degraded: bool = False


class MonitorConfig(BaseModel):
    """Configuración de un endpoint a monitorear."""

    id: str | None = None
    name: str = Field(min_length=1)
    url: str = Field(min_length=1)
    method: HttpMethod = "GET"
    expected_status: int = Field(default=200, ge=100, le=599)
    max_latency_ms: float = Field(gt=0)
    timeout_s: float = Field(gt=0)
    retries: int = Field(ge=0)
    backoff_base_s: float = Field(default=0.5, ge=0)
    contract: str | None = None
    expected_text: str | None = None
    alert_after: int = Field(default=3, ge=1)
    alert_on_degraded: bool = False

    @property
    def monitor_id(self) -> str:
        """Devuelve el id explícito del YAML o un slug estable derivado del nombre."""
        if self.id and self.id.strip():
            return self.id.strip()
        return slugify_monitor_name(self.name)

    @field_validator("method", mode="before")
    @classmethod
    def normalize_method(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("url")
    @classmethod
    def validate_http_url(cls, value: str) -> str:
        parsed = urlparse(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"La URL '{value}' debe ser una URL HTTP/HTTPS válida.")
        return value.strip()

    @field_validator("contract")
    @classmethod
    def validate_contract_exists(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if get_contract(normalized) is None:
            available = ", ".join(sorted(CONTRACTS))
            raise ValueError(
                f"Contrato desconocido: '{normalized}'. Contratos disponibles: {available}"
            )
        return normalized

    @field_validator("expected_text")
    @classmethod
    def validate_expected_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("El campo 'expected_text' no puede estar vacío.")
        return normalized


class MonitorsFile(BaseModel):
    """Estructura raíz del archivo YAML de configuración."""

    alert_after: int = Field(default=3, ge=1)
    alert_on_degraded: bool = False
    alerts: AlertsConfig | None = None
    monitors: list[MonitorConfig] = Field(min_length=1)

    @model_validator(mode="after")
    def propagate_alert_defaults(self) -> MonitorsFile:
        default_after = (
            self.alerts.alert_after
            if self.alerts is not None and "alert_after" in self.alerts.model_fields_set
            else self.alert_after
        )
        default_degraded = (
            self.alerts.alert_on_degraded
            if self.alerts is not None and "alert_on_degraded" in self.alerts.model_fields_set
            else self.alert_on_degraded
        )
        for monitor in self.monitors:
            if "alert_after" not in monitor.model_fields_set:
                monitor.alert_after = default_after
            if "alert_on_degraded" not in monitor.model_fields_set:
                monitor.alert_on_degraded = default_degraded
        return self


class CheckResult(BaseModel):
    """Resultado de la ejecución de un check sobre un endpoint."""

    name: str
    url: str
    timestamp: str
    status_code: int | None
    latency_ms: float
    total_duration_ms: float
    status_category: StatusCategory
    error: str | None
    attempts: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ok(self) -> bool:
        """Campo derivado a partir de status_category (fuente de verdad)."""
        return self.status_category == "ok"


class RunSummary(BaseModel):
    """Resumen agregado de una corrida del monitor."""

    total: int
    ok: int
    failed: int
    by_category: dict[StatusCategory, int]


class RunReport(BaseModel):
    """Reporte completo de una corrida con su resumen y lista de resultados."""

    summary: RunSummary
    results: list[CheckResult]
