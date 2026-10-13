# -*- coding: utf-8 -*-

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from core.normalizer.snapshot_validation import (
    profit_rate_pct,
    select_profit_candidate,
    validate_snapshot_values,
)


def test_profit_rate_uses_cost_basis():
    assert round(profit_rate_pct(611.80, 11.80), 2) == 1.97


def test_select_profit_repairs_missing_leading_digit_from_cumulative_profit():
    selected, detail = select_profit_candidate(
        market_value=611.80,
        primary_profit=1.80,
        alternate_profit=11.80,
        ocr_rate_pct=2.03,
    )

    assert selected == 11.80
    assert detail["repaired"] is True
    assert detail["selected_source"] == "cumulative_profit"


def test_select_profit_keeps_primary_when_rate_matches_primary():
    selected, detail = select_profit_candidate(
        market_value=611.80,
        primary_profit=11.80,
        alternate_profit=1.80,
        ocr_rate_pct=2.03,
    )

    assert selected == 11.80
    assert detail["repaired"] is False


def test_rate_mismatch_requires_manual_review():
    issues, detail = validate_snapshot_values(
        market_value=611.80,
        profit=1.80,
        reported_rate_pct=0.30,
        ocr_rate_pct=2.03,
    )

    assert detail["status"] == "manual_review"
    assert any(issue["code"] == "ocr_rate_mismatch" for issue in issues)


def test_consistent_values_pass_validation():
    issues, detail = validate_snapshot_values(
        market_value=611.80,
        profit=11.80,
        reported_rate_pct=1.97,
        ocr_rate_pct=2.03,
    )

    assert issues == []
    assert detail["status"] == "ok"
