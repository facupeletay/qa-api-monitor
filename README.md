# qa-api-monitor

[![CI](https://github.com/facupeletay/qa-api-monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/facupeletay/qa-api-monitor/actions/workflows/ci.yml)

Monitor de APIs en Python que lee endpoints desde un archivo YAML (`config/monitors.yaml`), ejecuta peticiones HTTP con reintentos y backoff exponencial, mide la latencia por intento y la duración total, valida esquemas/contratos JSON con Pydantic v2, clasifica las fallas por categoría y publica un reporte histórico en **GitHub Pages**.

🌐 **Sitio publicado (Estado e Historial):** [https://facupeletay.github.io/qa-api-monitor/](https://facupeletay.github.io/qa-api-monitor/)

---

## Cómo funciona

El flujo automatizado corre cada 6 horas en GitHub Actions sin ensuciar el historial de commits del repositorio:

```mermaid
flowchart LR
    A["python -m monitor"] --> B["results/run.json"]
    P["GitHub Pages (history.json previo)"] --> C["python -m monitor.history"]
    B --> C
    C --> D["site/history.json (30d + stats + max_latency_ms)"]
    F["dashboard/ (npm ci && npm run build)"] --> G["dashboard/dist/"]
    D --> G
    G --> E["GitHub Pages (Dashboard React + history.json)"]
    D --> H["python -m monitor.alerts"]
    H --> I["GitHub Issues (label: monitor-alert)"]
```

1. **`python -m monitor`** consulta cada API configurada en `config/monitors.yaml`, valida status HTTP, contrato JSON y SLA de latencia, genera `results/run.json` y opcionalmente escribe una tabla resumen en Markdown (`--summary-md`).
2. **`python -m monitor.history`** descarga el `history.json` publicado actualmente en GitHub Pages con cache-busting y `Cache-Control: no-cache` (o arranca vacío si devuelve `404` en la primera corrida; si hay error `5xx`, timeout o JSON corrupto, aborta para proteger el historial), agrega la corrida nueva, descarta registros de más de 30 días y calcula métricas de las últimas **24 horas** y **7 días** (uptime %, p50, p95, SLA `max_latency_ms` y conteo por categoría).
3. **`dashboard/` (React + Vite + TypeScript + Tailwind + Recharts)** compila el sitio estático con `base: "/qa-api-monitor/"`, copia el `history.json` actualizado dentro de `dashboard/dist/history.json` y **GitHub Pages** publica ese directorio.
4. **`python -m monitor.alerts`** evalúa las corridas consecutivas del `history.json` actualizado y gestiona automáticamente incidentes en **GitHub Issues** (abre, comenta cambios de categoría o cierra al recuperarse).

![Vista previa del Dashboard](./docs/dashboard-preview.png)

---

## Requisitos

- Python 3.12+
- Node.js 22+ y npm

## Instalación (Backend Python)

1. Crear y activar el entorno virtual:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Instalar el proyecto y sus dependencias de desarrollo:

```powershell
python -m pip install -e ".[dev]"
```

## Cómo correr el monitor y el historial localmente

Ejecutar los checks:

```powershell
python -m monitor
```

Opcionalmente con rutas personalizadas y resumen Markdown:

```powershell
python -m monitor --config config/monitors.yaml --output results/run.json --summary-md results/summary.md
```

### Códigos de salida de `python -m monitor`

| Código | Significado |
| :---: | :--- |
| `0` | Todos los checks finalizaron en categoría `ok`. |
| `1` | Al menos un check finalizó en estado distinto de `ok` (`degraded`, `contract_error`, `client_error`, `server_error`, `network_error`). |
| `2` | Error de configuración (`ConfigError`, archivo YAML inexistente o inválido) o error interno no esperado. |

Actualizar el historial (usando un archivo previo local o la URL de GitHub Pages):

```powershell
python -m monitor.history --previous https://facupeletay.github.io/qa-api-monitor/history.json --run results/run.json --output site/history.json
```

## APIs monitoreadas y contratos (`monitor/contracts/`)

| Monitor | Endpoint | Contrato Pydantic |
| :--- | :--- | :--- |
| **DolarApi - Dolar Oficial** | `https://dolarapi.com/v1/dolares/oficial` | `dolar_api` |
| **DolarApi - Dolar Blue** | `https://dolarapi.com/v1/dolares/blue` | `dolar_api` |
| **DolarApi - Dolar MEP** | `https://dolarapi.com/v1/dolares/bolsa` | `dolar_api` |
| **Open-Meteo - Clima CABA** | `https://api.open-meteo.com/v1/forecast?...` | `open_meteo` |
| **ArgentinaDatos - Riesgo Pais** | `https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais/ultimo` | `argentina_datos_riesgo_pais` |
| **GeoRef AR - Provincias** | `https://apis.datos.gob.ar/georef/api/provincias?campos=id,nombre&max=5` | `georef_provincias` |
| **GitHub Status - Estado Global** | `https://www.githubstatus.com/api/v2/status.json` | `github_status` |
| **CoinGecko - Bitcoin (BTC/USD)** | `https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd` | `coingecko_price` |

## Alertas (`monitor/alerts.py`)

El módulo `monitor.alerts` analiza las fallas consecutivas de cada monitor a partir del `history.json` ya mergeado (sin estado externo adicional) mediante la función pura `decide_action(monitor, history, alert_cfg, open_issue)` y sincroniza incidentes con **GitHub Issues** vía la API REST de GitHub (`httpx`):

- **Apertura automática (`OPEN`):** Cuando un monitor acumula `alert_after` corridas consecutivas fallidas y no tiene un Issue abierto, asegura que exista el label `monitor-alert` y abre un Issue con título `[ALERTA] <nombre del monitor>`, incluyendo el marcador oculto `<!-- monitor-id: <id estable> -->` (usando `id` del YAML o el slug del nombre), categoría, inicio de la falla, corridas fallidas, último status HTTP/error y enlaces al dashboard y al run de Actions.
- **Búsqueda paginada por marcador (`monitor-id`):** Los Issues abiertos se listan paginando `GET /repos/{owner}/{repo}/issues?state=open&labels=monitor-alert` y se identifican por el marcador oculto `<!-- monitor-id: ... -->` (nunca por título). Si hubiera más de un Issue abierto para el mismo monitor, se usa el más antiguo y se emite un warning sin abrir otro.
- **Sin duplicados ni spam (`COMMENT_CATEGORY_CHANGE` / `NOOP`):** Si ya existe un Issue abierto para ese monitor, no crea otro. Solo agrega un comentario si cambió la categoría de la falla (por ejemplo, de `server_error` a `network_error`).
- **Cierre por recuperación (`CLOSE_RECOVERED`):** Cuando la última corrida del monitor vuelve a `ok` y existe un Issue abierto, comenta la duración total del incidente y cierra el Issue.
- **Modo `--dry-run`:** Comparte exactamente la misma función `decide_action`, infiriendo `open_issue` desde las corridas previas del historial y usando un cliente que nunca realiza llamadas HTTP.

### Configuración en `config/monitors.yaml`

Se pueden definir valores globales en la raíz del archivo y sobrescribirlos opcionalmente en cada monitor:

```yaml
alert_after: 3            # Corridas fallidas seguidas para abrir Issue (default: 3)
alert_on_degraded: false  # Si degraded cuenta como falla para alertas (default: false)

monitors:
  - name: "DolarApi - Dolar Oficial"
    url: "https://dolarapi.com/v1/dolares/oficial"
    max_latency_ms: 2500
    timeout_s: 5.0
    retries: 2
    contract: "dolar_api"
    alert_after: 2        # (Opcional) pisa el valor global para este monitor
```

### Ejecución del comando de alertas

```powershell
python -m monitor.alerts --history site/history.json --config config/monitors.yaml --dry-run
```

## Cómo correr el Dashboard localmente (`dashboard/`)

En modo desarrollo (`npm run dev`), Vite sirve automáticamente el fixture de ejemplo `dashboard/sample-history.json` (con múltiples días e incidentes de distintas categorías) sin incluirlo en el build de producción:

```powershell
cd dashboard
npm install
npm run dev
```

Abrir en el navegador: `http://localhost:5173/qa-api-monitor/`

Para ejecutar linter, tests unitarios (Vitest) y el build de producción del dashboard:

```powershell
cd dashboard
npm run lint
npm test
npm run build
```

## Cómo correr los tests y el linter (Python)

Ejecutar la suite de pruebas con cobertura (`pytest`, `respx` y `pytest-cov`):

```powershell
pytest --cov=monitor --cov-report=term-missing
```

Ejecutar `ruff` para lint y formato:

```powershell
ruff check .
ruff format --check .
```
