"""Modelos Pydantic de contratos de respuesta para las APIs monitoreadas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr

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


class DatosGobPackageItem(BaseModel):
    """Dataset individual dentro de la búsqueda CKAN de datos.gob.ar."""

    model_config = ConfigDict(extra="ignore")

    id: StrictStr
    title: StrictStr


class DatosGobSearchResult(BaseModel):
    """Bloque 'result' de la API CKAN package_search de datos.gob.ar."""

    model_config = ConfigDict(extra="ignore")

    count: StrictInt
    results: list[DatosGobPackageItem] = Field(min_length=1)


class DatosGobSgrContract(BaseModel):
    """Contrato esperado para el dataset de SGR en https://datos.gob.ar/api/3/action/package_search."""

    model_config = ConfigDict(extra="ignore")

    success: StrictBool
    result: DatosGobSearchResult


class MavRouteEntry(BaseModel):
    """Entrada de ruta dentro del namespace mav/v1 de Mercado Argentino de Valores."""

    model_config = ConfigDict(extra="ignore")

    namespace: StrictStr
    methods: list[StrictStr] = Field(min_length=1)


class MavApiIndexContract(BaseModel):
    """Contrato esperado para https://www.mav-sa.com.ar/wp-json/mav/v1."""

    model_config = ConfigDict(extra="ignore")

    namespace: StrictStr
    routes: dict[StrictStr, MavRouteEntry] = Field(min_length=1)


class BcraMonetariaItem(BaseModel):
    """Variable monetaria informada por la API Estadísticas v4 del BCRA."""

    model_config = ConfigDict(extra="ignore")

    idVariable: StrictInt
    descripcion: StrictStr
    ultFechaInformada: StrictStr
    ultValorInformado: JsonNumber


class BcraMonetariasContract(BaseModel):
    """Contrato esperado para https://api.bcra.gob.ar/estadisticas/v4.0/monetarias."""

    model_config = ConfigDict(extra="ignore")

    status: StrictInt
    results: list[BcraMonetariaItem] = Field(min_length=1)


class BcraDeudorEntidad(BaseModel):
    """Entidad informante dentro de un período en la Central de Deudores del BCRA."""

    model_config = ConfigDict(extra="ignore")

    entidad: StrictStr
    situacion: StrictInt
    monto: JsonNumber


class BcraDeudorPeriodo(BaseModel):
    """Período informado para un CUIT en la Central de Deudores del BCRA."""

    model_config = ConfigDict(extra="ignore")

    periodo: StrictStr
    entidades: list[BcraDeudorEntidad] = Field(min_length=1)


class BcraDeudorResultado(BaseModel):
    """Objeto 'results' devuelto por la API Central de Deudores v1.0 del BCRA."""

    model_config = ConfigDict(extra="ignore")

    identificacion: StrictInt
    denominacion: StrictStr
    periodos: list[BcraDeudorPeriodo] = Field(min_length=1)


class BcraDeudoresContract(BaseModel):
    """Contrato esperado para https://api.bcra.gob.ar/centraldedeudores/v1.0/Deudas/{cuit}."""

    model_config = ConfigDict(extra="ignore")

    status: StrictInt
    results: BcraDeudorResultado
