# qa-api-monitor

Monitor de APIs en Python que lee endpoints desde un archivo YAML (`config/monitors.yaml`), ejecuta peticiones HTTP, mide la latencia, valida el código de estado esperado y guarda el reporte de resultados en `results/run.json`.

## Requisitos

- Python 3.12+

## Instalación

1. Crear y activar el entorno virtual:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Instalar el proyecto y sus dependencias de desarrollo:

```powershell
python -m pip install -e ".[dev]"
```

## Cómo correr el monitor

Desde la raíz del proyecto:

```powershell
python -m monitor
```

Opcionalmente se puede especificar otra ruta de configuración o de salida:

```powershell
python -m monitor --config config/monitors.yaml --output results/run.json
```

- Genera `results/run.json` con el detalle de cada check y el resumen (`total`, `ok`, `failed`).
- Imprime un resumen legible por consola.
- Devuelve código de salida `0` si todos los checks pasaron, o `1` si alguno falló.

## Cómo correr los tests y el linter

Ejecutar la suite de pruebas con cobertura (usando `pytest`, `respx` y `pytest-cov`):

```powershell
pytest --cov=monitor --cov-report=term-missing
```

Ejecutar `ruff` para lint y formato:

```powershell
ruff check .
ruff format --check .
```
