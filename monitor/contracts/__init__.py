"""Registro de contratos de APIs y validación legible de esquemas JSON."""

from __future__ import annotations

from pydantic import BaseModel, ValidationError

from monitor.contracts.models import (
    ArgentinaDatosRiesgoPaisContract,
    CoinGeckoBitcoinUsd,
    CoinGeckoPriceContract,
    DolarApiContract,
    GeorefProvinciaItem,
    GeorefProvinciasContract,
    GitHubStatusContract,
    GitHubStatusInfo,
    GitHubStatusPage,
    OpenMeteoContract,
    OpenMeteoCurrent,
)

CONTRACTS: dict[str, type[BaseModel]] = {
    "dolar_api": DolarApiContract,
    "open_meteo": OpenMeteoContract,
    "argentina_datos_riesgo_pais": ArgentinaDatosRiesgoPaisContract,
    "georef_provincias": GeorefProvinciasContract,
    "github_status": GitHubStatusContract,
    "coingecko_price": CoinGeckoPriceContract,
}


def get_contract(name: str) -> type[BaseModel] | None:
    """Devuelve el modelo de contrato registrado bajo `name`, o None si no existe."""
    return CONTRACTS.get(name)


def validate_contract(contract_name: str, payload: object) -> str | None:
    """Valida `payload` contra el contrato indicado.

    Retorna None si el payload cumple el contrato, o un resumen legible
    de los campos que fallaron y el motivo (sin traceback) si no cumple.
    """
    model = get_contract(contract_name)
    if model is None:
        raise ValueError(f"Contrato no registrado: '{contract_name}'")

    try:
        model.model_validate(payload)
    except ValidationError as exc:
        issues: list[str] = []
        for err in exc.errors():
            loc = ".".join(str(part) for part in err.get("loc", ())) or "<root>"
            msg = err.get("msg", "valor inválido")
            issues.append(f"{loc} ({msg})")
        return f"Contrato '{contract_name}' inválido: " + ", ".join(issues)

    return None


__all__ = [
    "CONTRACTS",
    "ArgentinaDatosRiesgoPaisContract",
    "CoinGeckoBitcoinUsd",
    "CoinGeckoPriceContract",
    "DolarApiContract",
    "GeorefProvinciaItem",
    "GeorefProvinciasContract",
    "GitHubStatusContract",
    "GitHubStatusInfo",
    "GitHubStatusPage",
    "OpenMeteoContract",
    "OpenMeteoCurrent",
    "get_contract",
    "validate_contract",
]
