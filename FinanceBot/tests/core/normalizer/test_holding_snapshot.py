# -*- coding: utf-8 -*-
"""
holding_snapshot.py 的字段体系测试。

锚点：
- 测试.jpg 列表页（原始数据）——5 只基金的金额/昨日收益/持有收益/率
- 实现.jpg 详情页（025208）——份额/占比/成本/当日收益/持有天数

重点验证「补全」逻辑：
1. 列表页字段照抄，不被详情页改写（详情页收益口径不同，以列表为准）
2. 详情页字段补全后能通过自洽校验：成本单价 × 份额 = 金额 - 持有收益
3. 组合总市值可由单只基金的金额+占比反推
"""

import pytest

from core.normalizer.holding_snapshot import (
    DETAIL_PAGE_FIELDS,
    HOLDING_SNAPSHOT_COLUMNS,
    LIST_PAGE_ROWS,
    build_snapshot,
    portfolio_total_from_weight,
    to_dataframe,
    unit_cost_from_list,
    weight_pct_of,
)

# 实现.jpg 详情页实测（025208）
D025208 = DETAIL_PAGE_FIELDS["025208"]


class TestUnitCostFromList:
    def test_matches_detail_page(self):
        """由列表页字段推导的单位成本，应与详情页 2.3706 一致。"""
        uc = unit_cost_from_list(market_value=2751.83, profit=-313.28, shares=1292.97)
        assert uc == pytest.approx(2.3706, abs=0.0001)

    def test_total_cost_consistency(self):
        """成本单价 × 份额 = 金额 - 持有收益（列表口径）。"""
        total_cost = 2751.83 - (-313.28)
        assert D025208["unit_cost"] * D025208["shares"] == pytest.approx(total_cost, abs=0.05)

    def test_zero_shares_raises(self):
        with pytest.raises(ValueError):
            unit_cost_from_list(100.0, 1.0, 0.0)


class TestPortfolioTotal:
    def test_reverse_from_weight(self):
        """025208 金额 2751.83、占比 15.41% -> 组合总市值约 17858。"""
        total = portfolio_total_from_weight(2751.83, 15.41)
        assert total == pytest.approx(17858.0, rel=0.001)

    def test_weight_roundtrip(self):
        total = portfolio_total_from_weight(2751.83, 15.41)
        assert weight_pct_of(2751.83, total) == pytest.approx(15.41, abs=0.01)

    def test_zero_weight_raises(self):
        with pytest.raises(ValueError):
            portfolio_total_from_weight(100.0, 0.0)


class TestBuildSnapshot:
    def test_list_fields_authoritative(self):
        """列表页是原始数据：持有收益用 -313.28，不是详情页的 -350.26。"""
        s = build_snapshot(
            "025208", "永赢先锋半导体智选混合A",
            market_value=2751.83, profit=-313.28, profit_pct=-10.22,
            yesterday_pnl=-153.94,
            **D025208,
        )
        assert s.profit == -313.28
        assert s.profit_pct == -10.22
        assert s.market_value == 2751.83

    def test_detail_fields_filled(self):
        """详情页字段应完整补入。"""
        s = build_snapshot(
            "025208", "永赢先锋半导体智选混合A",
            market_value=2751.83, profit=-313.28, profit_pct=-10.22,
            yesterday_pnl=-153.94,
            **D025208,
        )
        assert s.shares == 1292.97
        assert s.weight_pct == 15.41
        assert s.unit_cost == 2.3706
        assert s.today_pnl == -36.87
        assert s.holding_days == 11

    def test_unit_cost_derived_when_missing(self):
        """给份额不给成本单价时，自动按列表口径推导。"""
        s = build_snapshot(
            "X", "X",
            market_value=2751.83, profit=-313.28, profit_pct=-10.22,
            yesterday_pnl=-153.94, shares=1292.97,
        )
        assert s.unit_cost == pytest.approx(2.3706, abs=0.0001)

    def test_weight_derived_from_total(self):
        """给组合总市值不给占比时，自动推算占比。"""
        total = portfolio_total_from_weight(2751.83, 15.41)
        s = build_snapshot(
            "X", "X",
            market_value=2751.83, profit=-313.28, profit_pct=-10.22,
            yesterday_pnl=-153.94, total_market_value=total,
        )
        assert s.weight_pct == pytest.approx(15.41, abs=0.01)

    def test_missing_detail_fields_default_zero(self):
        """详情页字段缺失时记 0，不抛异常。"""
        s = build_snapshot(
            "X", "X",
            market_value=100.0, profit=-5.0, profit_pct=-5.0,
            yesterday_pnl=-1.0,
        )
        assert s.shares == 0.0
        assert s.today_pnl == 0.0
        assert s.holding_days == 0


class TestListPageAnchors:
    def test_all_five_funds_present(self):
        """测试.jpg 列表页 5 只基金都应在锚点里。"""
        codes = {row[1] for row in LIST_PAGE_ROWS}
        assert codes == {"025208", "015310", "003376", "013308", "022364"}

    def test_top_holding_amount(self):
        """金额排序第一的是 025208，2751.83。"""
        top = LIST_PAGE_ROWS[0]
        assert top[1] == "025208"
        assert top[2] == 2751.83

    def test_bond_fund_is_positive(self):
        """广发中债是列表里唯一持有收益为正的（+9.83 / +0.79%）。"""
        row = next(r for r in LIST_PAGE_ROWS if r[1] == "003376")
        assert row[4] == 9.83
        assert row[5] == 0.79


class TestToDataframe:
    def test_columns_match_schema(self):
        s = build_snapshot(
            "025208", "永赢先锋半导体智选混合A",
            market_value=2751.83, profit=-313.28, profit_pct=-10.22,
            yesterday_pnl=-153.94, **D025208,
        )
        df = to_dataframe([s])
        assert list(df.columns) == HOLDING_SNAPSHOT_COLUMNS
        assert len(df) == 1

    def test_row_values(self):
        s = build_snapshot(
            "025208", "永赢先锋半导体智选混合A",
            market_value=2751.83, profit=-313.28, profit_pct=-10.22,
            yesterday_pnl=-153.94, **D025208,
        )
        row = to_dataframe([s]).iloc[0]
        assert row["基金代码"] == "025208"
        assert row["持有金额"] == 2751.83
        assert row["持有份额"] == 1292.97
        assert row["持仓成本"] == 2.3706
        assert row["当日收益"] == -36.87
        assert row["昨日收益"] == -153.94
        assert row["持有天数"] == 11
