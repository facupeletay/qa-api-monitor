"""Modelos de datos de configuración y resultados para qa-api-monitor."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

HttpMethod = Literal["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]


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
    ok: bool
    error: str | None
    attempts: int


class RunSummary(BaseModel):
    """Resumen agregado de una corrida del monitor."""

    total: int
    ok: int
    failed: int


class RunReport(BaseModel):
    """Reporte completo de una corrida con su resumen y lista de resultados."""

    summary: RunSummary
    results: list[CheckResult]
