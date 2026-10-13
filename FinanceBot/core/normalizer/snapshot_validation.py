# -*- coding: utf-8 -*-
"""持仓截图金额、收益和收益率的一致性校验。"""

from __future__ import annotations

from typing import Any

RATE_ABS_TOLERANCE = 0.25
RATE_REL_TOLERANCE = 0.05
MIN_COST = 0.01


def profit_rate_pct(market_value: float, profit: float) -> float | None:
    """按“收益率 = 持有收益 / 持仓成本”计算收益率。"""
    cost = float(market_value) - float(profit)
    if abs(cost) < MIN_COST:
        return None
    return float(profit) / cost * 100.0


def rate_tolerance(rate_pct: float) -> float:
    return max(RATE_ABS_TOLERANCE, abs(float(rate_pct)) * RATE_REL_TOLERANCE)


def _rate_issue(
    field: str,
    calculated_rate_pct: float | None,
    reported_rate_pct: float | None,
) -> dict[str, Any] | None:
    if calculated_rate_pct is None or reported_rate_pct is None:
        return None
    delta = abs(calculated_rate_pct - float(reported_rate_pct))
    tolerance = rate_tolerance(reported_rate_pct)
    if delta <= tolerance:
        return None
    return {
        "code": f"{field}_mismatch",
        "message": (
            f"{field} 与按持有金额/持有收益计算的收益率不一致"
        ),
        "calculated_rate_pct": round(calculated_rate_pct, 4),
        "reported_rate_pct": round(float(reported_rate_pct), 4),
        "delta_percentage_points": round(delta, 4),
        "tolerance_percentage_points": round(tolerance, 4),
    }


def validate_snapshot_values(
    market_value: float,
    profit: float,
    reported_rate_pct: float | None = None,
    ocr_rate_pct: float | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """返回校验问题和可写入结构化输入的校验明细。"""
    market_value = float(market_value)
    profit = float(profit)
    cost = round(market_value - profit, 6)
    calculated_rate_pct = profit_rate_pct(market_value, profit)

    issues: list[dict[str, Any]] = []
    if market_value <= 0:
        issues.append({
            "code": "invalid_market_value",
            "message": "持有金额必须大于 0",
            "market_value": market_value,
        })
    if cost < 0:
        issues.append({
            "code": "invalid_cost_basis",
            "message": "持仓成本不能小于 0",
            "market_value": market_value,
            "profit": profit,
            "cost_basis": cost,
        })

    for field, value in (
        ("reported_rate", reported_rate_pct),
        ("ocr_rate", ocr_rate_pct),
    ):
        issue = _rate_issue(field, calculated_rate_pct, value)
        if issue:
            issues.append(issue)

    detail = {
        "status": "manual_review" if issues else "ok",
        "cost_basis": round(cost, 2),
        "calculated_rate_pct": (
            round(calculated_rate_pct, 4) if calculated_rate_pct is not None else None
        ),
        "reported_rate_pct": (
            round(float(reported_rate_pct), 4) if reported_rate_pct is not None else None
        ),
        "ocr_rate_pct": (
            round(float(ocr_rate_pct), 4) if ocr_rate_pct is not None else None
        ),
        "rate_abs_tolerance": RATE_ABS_TOLERANCE,
        "rate_rel_tolerance": RATE_REL_TOLERANCE,
        "issues": issues,
    }
    return issues, detail


def select_profit_candidate(
    market_value: float,
    primary_profit: float,
    alternate_profit: float | None,
    ocr_rate_pct: float | None,
) -> tuple[float, dict[str, Any]]:
    """
    在“持有收益”和“累计收益”之间选择与 OCR 收益率更一致的值。

    只有当主值明显不一致、备选值落在收益率容差内时才自动修复；
    两个值都不可信时保留主值并交由人工复核。
    """
    primary_profit = float(primary_profit)
    if alternate_profit is None or ocr_rate_pct is None:
        return primary_profit, {
            "repaired": False,
            "selected_source": "holding_profit",
            "primary_profit": round(primary_profit, 2),
            "alternate_profit": (
                round(float(alternate_profit), 2) if alternate_profit is not None else None
            ),
            "reason": "缺少可交叉验证的累计收益或 OCR 收益率",
        }

    alternate_profit = float(alternate_profit)
    if abs(primary_profit - alternate_profit) <= 0.01:
        return primary_profit, {
            "repaired": False,
            "selected_source": "holding_profit",
            "primary_profit": round(primary_profit, 2),
            "alternate_profit": round(alternate_profit, 2),
            "reason": "持有收益与累计收益一致",
        }

    primary_rate = profit_rate_pct(market_value, primary_profit)
    alternate_rate = profit_rate_pct(market_value, alternate_profit)
    if primary_rate is None or alternate_rate is None:
        return primary_profit, {
            "repaired": False,
            "selected_source": "holding_profit",
            "primary_profit": round(primary_profit, 2),
            "alternate_profit": round(alternate_profit, 2),
            "reason": "无法计算候选收益率",
        }

    primary_delta = abs(primary_rate - float(ocr_rate_pct))
    alternate_delta = abs(alternate_rate - float(ocr_rate_pct))
    tolerance = rate_tolerance(ocr_rate_pct)

    if alternate_delta <= tolerance and primary_delta > tolerance:
        return alternate_profit, {
            "repaired": True,
            "selected_source": "cumulative_profit",
            "primary_profit": round(primary_profit, 2),
            "alternate_profit": round(alternate_profit, 2),
            "ocr_rate_pct": round(float(ocr_rate_pct), 4),
            "primary_rate_pct": round(primary_rate, 4),
            "alternate_rate_pct": round(alternate_rate, 4),
            "tolerance_percentage_points": round(tolerance, 4),
            "reason": "累计收益与 OCR 收益率一致，持有收益疑似 OCR 漏位",
        }

    return primary_profit, {
        "repaired": False,
        "selected_source": "holding_profit",
        "primary_profit": round(primary_profit, 2),
        "alternate_profit": round(alternate_profit, 2),
        "ocr_rate_pct": round(float(ocr_rate_pct), 4),
        "primary_rate_pct": round(primary_rate, 4),
        "alternate_rate_pct": round(alternate_rate, 4),
        "tolerance_percentage_points": round(tolerance, 4),
        "reason": "未找到可信的收益修复值",
    }
