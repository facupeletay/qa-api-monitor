"""Carga y validación del archivo YAML de configuración de monitores."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from monitor.models import MonitorConfig, MonitorsFile


class ConfigError(ValueError):
    """Error al cargar o validar el archivo de configuración de monitores."""


def load_config(path: str | Path = Path("config/monitors.yaml")) -> list[MonitorConfig]:
    """Lee y valida el archivo YAML de monitores con modelos Pydantic v2."""
    config_path = Path(path)
    if not config_path.is_file():
        raise ConfigError(f"No se encontró el archivo de configuración: {config_path}")

    try:
        raw_text = config_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Error de sintaxis YAML en {config_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(
            f"Formato YAML inválido en {config_path}: se esperaba un objeto raíz con 'monitors'."
        )

    try:
        parsed = MonitorsFile.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"Configuración inválida en {config_path}:\n{exc}") from exc

    return parsed.monitors
