"""Unit tests for scripts/healthcheck.py."""

from __future__ import annotations

import pytest

from scripts.healthcheck import run_healthcheck, format_report, CHECKS


def test_healthcheck_returns_structured_report():
    report = run_healthcheck()
    assert "summary" in report
    assert report["summary"] in ("ok", "degraded", "failed")
    assert isinstance(report["passed"], int)
    assert isinstance(report["failed"], int)
    assert isinstance(report["checks"], list)
    assert len(report["checks"]) == len(CHECKS)


def test_healthcheck_passes_in_clean_env():
    """In a clean install, every check should pass (or warn at worst)."""
    report = run_healthcheck()
    assert report["failed"] == 0, (
        f"healthcheck failed:\n{format_report(report)}"
    )


def test_format_report_mentions_summary_verdict():
    report = run_healthcheck()
    text = format_report(report)
    assert "FATS health check" in text
    # Pass/Fail/Warning counters appear
    assert "Passed:" in text


def test_each_check_has_unique_id():
    ids = [c[0] for c in CHECKS]
    assert len(ids) == len(set(ids)), "duplicate check IDs"


def test_each_check_has_callable():
    for check_id, name, fn in CHECKS:
        assert callable(fn), f"check {check_id} has non-callable function"
