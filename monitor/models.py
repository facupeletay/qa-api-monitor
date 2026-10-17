"""Modelos de datos de configuración y resultados para qa-api-monitor."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, computed_field, field_validator

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


class MonitorConfig(BaseModel):
    """Configuración de un endpoint a monitorear."""

    name: str = Field(min_length=1)
    url: str = Field(min_length=1)
    method: HttpMethod = "GET"
    expected_status: int = Field(default=200, ge=100, le=599)
    max_latency_ms: float = Field(gt=0)
    timeout_s: float = Field(gt=0)
    retries: int = Field(ge=0)
    backoff_base_s: float = Field(default=0.5, ge=0)
    contract: str | None = None

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


class MonitorsFile(BaseModel):
    """Estructura raíz del archivo YAML de configuración."""

    monitors: list[MonitorConfig] = Field(min_length=1)


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
