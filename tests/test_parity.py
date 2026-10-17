"""Test de paridad de métricas (uptime, p50, p95) entre Python y TypeScript."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from monitor.history import HistoryReport, merge_history
from monitor.models import ALL_STATUS_CATEGORIES, RunReport, RunSummary

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_python_metrics_match_shared_parity_fixture() -> None:
    """Verifica que monitor/history.py calcule exactamente los valores de paridad esperados."""
    raw_input = json.loads((FIXTURES_DIR / "parity_history_input.json").read_text(encoding="utf-8"))
    expected = json.loads(
        (FIXTURES_DIR / "parity_expected_metrics.json").read_text(encoding="utf-8")
    )

    full_report = HistoryReport.model_validate(raw_input)
    previous = HistoryReport(
        generated_at=full_report.generated_at,
        runs=full_report.runs[:-1],
        stats={},
    )
    last_run_results = full_report.runs[-1].results
    by_category = {cat: 0 for cat in ALL_STATUS_CATEGORIES}
    for check in last_run_results:
        by_category[check.status_category] += 1

    last_run_report = RunReport(
        summary=RunSummary(
            total=len(last_run_results),
            ok=by_category["ok"],
            failed=len(last_run_results) - by_category["ok"],
            by_category=by_category,
        ),
        results=last_run_results,
    )

    now = datetime.fromisoformat(full_report.generated_at.replace("Z", "+00:00")).astimezone(UTC)
    merged = merge_history(previous, last_run_report, now=now)

    for monitor_name, expected_windows in expected.items():
        monitor_stats = merged.stats[monitor_name]

        w24 = monitor_stats.window_24h
        exp24 = expected_windows["window_24h"]
        assert w24.total_checks == exp24["total_checks"]
        assert w24.uptime_pct == exp24["uptime_pct"]
        assert w24.latency_p50_ms == exp24["latency_p50_ms"]
        assert w24.latency_p95_ms == exp24["latency_p95_ms"]

        w7d = monitor_stats.window_7d
        exp7d = expected_windows["window_7d"]
        assert w7d.total_checks == exp7d["total_checks"]
        assert w7d.uptime_pct == exp7d["uptime_pct"]
        assert w7d.latency_p50_ms == exp7d["latency_p50_ms"]
        assert w7d.latency_p95_ms == exp7d["latency_p95_ms"]
