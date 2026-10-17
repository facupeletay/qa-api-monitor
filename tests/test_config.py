"""Tests para la carga y validación de configuración YAML."""

from __future__ import annotations

from pathlib import Path

import pytest

from monitor.config import ConfigError, load_config


def test_load_valid_config_with_and_without_contract(tmp_path: Path) -> None:
    """Carga correctamente monitores con contrato válido y sin contrato."""
    yaml_file = tmp_path / "monitors.yaml"
    yaml_file.write_text(
        "monitors:\n"
        "  - name: Dolar\n"
        "    url: https://dolarapi.com/v1/dolares/oficial\n"
        "    max_latency_ms: 1000\n"
        "    timeout_s: 3\n"
        "    retries: 1\n"
        "    contract: dolar_api\n"
        "  - name: Sin Contrato\n"
        "    url: https://example.com/health\n"
        "    max_latency_ms: 500\n"
        "    timeout_s: 2\n"
        "    retries: 0\n",
        encoding="utf-8",
    )

    monitors = load_config(yaml_file)

    assert len(monitors) == 2
    assert monitors[0].contract == "dolar_api"
    assert monitors[1].contract is None


def test_unknown_contract_name_raises_config_error(tmp_path: Path) -> None:
    """contract con un nombre inexistente -> ConfigError."""
    yaml_file = tmp_path / "unknown_contract.yaml"
    yaml_file.write_text(
        "monitors:\n"
        "  - name: API con contrato inexistente\n"
        "    url: https://api.example.com/v1\n"
        "    max_latency_ms: 500\n"
        "    timeout_s: 2\n"
        "    retries: 0\n"
        "    contract: contrato_fantasma\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="contrato_fantasma"):
        load_config(yaml_file)


def test_invalid_yaml_or_missing_fields_raises_clear_error(tmp_path: Path) -> None:
    """YAML inválido o con campos faltantes -> ConfigError claro."""
    # Caso 1: Sintaxis YAML inválida
    broken_yaml = tmp_path / "broken.yaml"
    broken_yaml.write_text("monitors:\n  - name: [unclosed\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="YAML"):
        load_config(broken_yaml)

    # Caso 2: Campos obligatorios faltantes
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

    # Caso 5: Raíz del YAML no es un diccionario
    list_root_yaml = tmp_path / "list_root.yaml"
    list_root_yaml.write_text("- item1\n- item2\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="objeto raíz"):
        load_config(list_root_yaml)
