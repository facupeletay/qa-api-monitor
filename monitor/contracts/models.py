"""Modelos Pydantic de contratos de respuesta para las APIs monitoreadas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, StrictFloat, StrictInt, StrictStr

JsonNumber = StrictInt | StrictFloat


class DolarApiContract(BaseModel):
    """Contrato esperado para https://dolarapi.com/v1/dolares/oficial."""

    model_config = ConfigDict(extra="ignore")

    moneda: StrictStr
    casa: StrictStr
    nombre: StrictStr
    compra: JsonNumber
    venta: JsonNumber
    fechaActualizacion: StrictStr


class OpenMeteoCurrent(BaseModel):
    """Sub-bloque 'current' de la respuesta de Open-Meteo."""

    model_config = ConfigDict(extra="ignore")

    time: StrictStr
    temperature_2m: JsonNumber


class OpenMeteoContract(BaseModel):
    """Contrato esperado para https://api.open-meteo.com/v1/forecast."""

    model_config = ConfigDict(extra="ignore")

    latitude: JsonNumber
    longitude: JsonNumber
    current: OpenMeteoCurrent
