"""Modelos Pydantic de contratos de respuesta para las APIs monitoreadas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr

JsonNumber = StrictInt | StrictFloat


class DolarApiContract(BaseModel):
    """Contrato esperado para https://dolarapi.com/v1/dolares/*."""

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


class ArgentinaDatosRiesgoPaisContract(BaseModel):
    """Contrato esperado para https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais/ultimo."""

    model_config = ConfigDict(extra="ignore")

    valor: JsonNumber
    fecha: StrictStr


class GeorefProvinciaItem(BaseModel):
    """Item de provincia devuelto por la API GeoRef AR."""

    model_config = ConfigDict(extra="ignore")

    id: StrictStr
    nombre: StrictStr


class GeorefProvinciasContract(BaseModel):
    """Contrato esperado para https://apis.datos.gob.ar/georef/api/provincias."""

    model_config = ConfigDict(extra="ignore")

    cantidad: StrictInt
    total: StrictInt
    provincias: list[GeorefProvinciaItem] = Field(min_length=1)


class GitHubStatusPage(BaseModel):
    """Sub-bloque 'page' de la API de estado de GitHub."""

    model_config = ConfigDict(extra="ignore")

    id: StrictStr
    name: StrictStr
    url: StrictStr
    updated_at: StrictStr


class GitHubStatusInfo(BaseModel):
    """Sub-bloque 'status' de la API de estado de GitHub."""

    model_config = ConfigDict(extra="ignore")

    indicator: StrictStr
    description: StrictStr


class GitHubStatusContract(BaseModel):
    """Contrato esperado para https://www.githubstatus.com/api/v2/status.json."""

    model_config = ConfigDict(extra="ignore")

    page: GitHubStatusPage
    status: GitHubStatusInfo


class CoinGeckoBitcoinUsd(BaseModel):
    """Sub-bloque 'bitcoin' de la respuesta Simple Price de CoinGecko."""

    model_config = ConfigDict(extra="ignore")

    usd: JsonNumber


class CoinGeckoPriceContract(BaseModel):
    """Contrato esperado para https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd."""

    model_config = ConfigDict(extra="ignore")

    bitcoin: CoinGeckoBitcoinUsd
