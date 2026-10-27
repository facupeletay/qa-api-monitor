# 📋 Backlog de Evolución — `qa-api-monitor`

Este backlog registra las 3 etapas de evolución acordadas para el monitor de APIs y su dashboard en GitHub Pages. Se actualiza a medida que completamos y verificamos cada ítem.

---

## Etapa 1 — Mejoras en el Dashboard (`dashboard/`)
> **Objetivo:** Facilitar la lectura, agrupación por rubro y filtrado rápido de los monitores en la interfaz React.

- [x] **1.1 Clasificación por rubro/categoría funcional:** Inferir o asignar el rubro de cada monitor (*Finanzas & BCRA*, *Ecosistema SGR / PyME / MAV*, *Datos Públicos & Clima*, *Infraestructura & Cripto*) y mostrar una etiqueta visual en cada tarjeta (`MonitorCard.tsx`).
- [x] **1.2 Buscador en tiempo real y filtros rápidos:** Agregar barra de búsqueda por nombre/URL, selector de rubro y filtro rápido por estado (*Todos*, *OK*, *Con incidentes*, *Degradado (SLA)*), además de opción para agrupar visualmente las tarjetas por rubro (`App.tsx`).
- [x] **1.3 Sincronización con gráficos e incidentes:** Hacer que el filtro activo de rubro/búsqueda también pueda reflejarse de forma clara en el conteo de monitores visibles y en las vistas del dashboard.
- [x] **1.4 Tests unitarios y de componentes (`Vitest`):** Agregar pruebas en `dashboard/src/__tests__/` para la clasificación por rubro, búsqueda por texto y filtrado por estado.
- [x] **1.5 Verificación de build y linter frontend:** Ejecutar `npm run lint`, `npm test` y `npm run build` sin errores.

---

## Etapa 2 — Notificaciones Externas en Tiempo Real (Fase 6 — `monitor/alerts.py`)
> **Objetivo:** Complementar la gestión de GitHub Issues con notificaciones opcionales vía Webhook (Discord / Slack / genérico) y Telegram cuando se abre una alerta (`OPEN`), cambia de categoría (`COMMENT_CATEGORY_CHANGE`) o el servicio se recupera (`CLOSE_RECOVERED`).

- [x] **2.1 Soporte de Webhook (Discord / Slack / JSON genérico):** Implementar envío opcional en `monitor/alerts.py` cuando esté definida la variable de entorno `ALERT_WEBHOOK_URL` (o flag CLI), respetando `--dry-run` y aislando errores para que una falla del webhook nunca rompa la corrida.
- [x] **2.2 Soporte de Telegram Bot API:** Implementar envío opcional en `monitor/alerts.py` cuando estén definidas `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`.
- [x] **2.3 Integración en GitHub Actions (`.github/workflows/monitor.yml`):** Pasar las variables opcionales `ALERT_WEBHOOK_URL`, `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` desde `secrets` al paso de alertas.
- [x] **2.4 Tests con `respx` en `tests/test_alerts.py`:** Cubrir el envío de notificaciones en apertura y recuperación, omisión en `NOOP`/`--dry-run` y tolerancia a fallos HTTP del webhook/Telegram.

---

## Etapa 3 — Nuevos Endpoints y Validación de Contenido HTML (`monitor/`)
> **Objetivo:** Validar que los portales web SGR/PyME no devuelvan páginas de mantenimiento con código `200` y sumar nuevos endpoints financieros/públicos.

- [x] **3.1 Validación `expected_text` en `MonitorConfig` y `execute_check`:** Permitir configurar una subcadena esperada (`expected_text`) en `config/monitors.yaml` para portales HTML o endpoints de texto; si el status es `200` pero el texto no aparece en el body, clasificar como `contract_error` con detalle claro.
- [x] **3.2 Configurar `expected_text` en los 5 portales SGR/PyME:** Agregar palabras clave verificables en `ePyme`, `MAV Data`, `CASFOG`, `Garantizar SGR` y `Acindar Pymes SGR`.
- [x] **3.3 Sumar nuevos endpoints y contratos al catálogo (`config/monitors.yaml`):** Incorporar `DolarApi - Dolar Contado con Liqui (CCL)` (`contract: dolar_api`) y `BCRA - Central de Deudores (v1)` (con nuevo contrato Pydantic `bcra_deudores`), alcanzando **18 monitores** y **10 contratos Pydantic**.
- [x] **3.4 Tests, cobertura y despliegue final:** Agregar tests unitarios en `tests/test_contracts.py` y `tests/test_config.py`, actualizar `README.md`, pushear a `main` y disparar el workflow de GitHub Actions para publicar en GitHub Pages.
