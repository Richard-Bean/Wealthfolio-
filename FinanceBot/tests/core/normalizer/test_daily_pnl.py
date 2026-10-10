# -*- coding: utf-8 -*-
"""
daily_pnl.py 的算法测试。

用 实现.jpg 中 025208「永赢先锋半导体智选混合A」的实测数字做锚点：
份额 1163.53、当日收益 -53.98、涨跌幅度约 -2.13%（图上板块 -2.12%）。
不依赖网络与 PDF。
"""

import pandas as pd
import pytest

from core.normalizer.daily_pnl import (
    Quote,
    compute_daily_pnl,
    effective_shares_before,
    fund_daily_pnl,
    portfolio_daily_pnl,
)


# 实现.jpg 锚点：由 持有金额 2476.34 / 份额 1163.53 反推今日净值，
# 由 当日收益 -53.98 反推昨日净值
ANCHOR = {
    "code": "025208",
    "name": "永赢先锋半导体智选混合A",
    "shares": 1163.53,
    "prev_nav": 2.1747,
    "today_nav": 2.1283,
    "expect_pnl": -53.98,
    "expect_pct": -2.13,
}


class TestFundDailyPnl:
    def test_matches_screenshot(self):
        """单只基金今日涨跌要能复现实现.jpg 的 -53.98 元 / -2.13%。"""
        r = fund_daily_pnl(
            ANCHOR["code"], ANCHOR["name"], ANCHOR["shares"],
            ANCHOR["prev_nav"], ANCHOR["today_nav"], is_estimate=True,
        )
        assert r.today_pnl == pytest.approx(ANCHOR["expect_pnl"], abs=0.05)
        assert r.change_pct * 100 == pytest.approx(ANCHOR["expect_pct"], abs=0.05)

    def test_change_pct_independent_of_shares(self):
        """涨跌幅度只取决于净值，与持有多少份额无关。"""
        a = fund_daily_pnl("X", "X", 100.0, 2.0, 2.2)
        b = fund_daily_pnl("X", "X", 9999.0, 2.0, 2.2)
        assert a.change_pct == b.change_pct == pytest.approx(0.1)

    def test_today_pnl_linear_in_shares(self):
        """今日涨跌金额与份额成正比。"""
        a = fund_daily_pnl("X", "X", 100.0, 2.0, 2.1)
        b = fund_daily_pnl("X", "X", 200.0, 2.0, 2.1)
        assert b.today_pnl == pytest.approx(a.today_pnl * 2)

    def test_flat_nav_gives_zero(self):
        """净值未更新（today_nav = prev_nav）时涨跌为 0。"""
        r = fund_daily_pnl("X", "X", 500.0, 1.5, 1.5)
        assert r.today_pnl == 0.0
        assert r.change_pct == 0.0

    def test_rise_is_positive(self):
        r = fund_daily_pnl("X", "X", 100.0, 1.0, 1.05)
        assert r.today_pnl == pytest.approx(5.0)
        assert r.change_pct == pytest.approx(0.05)

    def test_zero_prev_nav_no_division_error(self):
        r = fund_daily_pnl("X", "X", 100.0, 0.0, 1.0)
        assert r.change_pct == 0.0


class TestPortfolioDailyPnl:
    def test_weighted_by_prev_market_value(self):
        """
        组合幅度必须按昨收市值加权，不能是各基金涨跌幅的算术平均。
        这里两只基金涨跌幅 +10% 与 +1%，算术平均是 5.5%，
        但按昨收市值加权应接近 1.9%。
        """
        big = fund_daily_pnl("A", "A", 100.0, 1.0, 1.01)   # 昨收 100，+1%
        small = fund_daily_pnl("B", "B", 10.0, 1.0, 1.10)  # 昨收 10，+10%
        p = portfolio_daily_pnl([big, small])

        arithmetic_mean = (0.01 + 0.10) / 2
        assert p.change_pct != pytest.approx(arithmetic_mean, abs=0.005)
        # (1.0 + 1.0) / 110 = 0.01818...
        assert p.change_pct == pytest.approx(2.0 / 110.0)
        assert p.today_pnl == pytest.approx(2.0)
        assert p.prev_market_value == pytest.approx(110.0)

    def test_empty_portfolio(self):
        p = portfolio_daily_pnl([])
        assert p.today_pnl == 0.0
        assert p.change_pct == 0.0

    def test_zero_shares_do_not_break(self):
        r = fund_daily_pnl("X", "X", 0.0, 1.0, 1.2)
        p = portfolio_daily_pnl([r])
        assert p.today_pnl == 0.0
        assert p.change_pct == 0.0


class TestEffectiveSharesBefore:
    """今日有效份额 = 截至昨日收盘已确认的份额，今日新买入不能计入。"""

    @staticmethod
    def _trades():
        return pd.DataFrame([
            # T-2 买入 1000 份 —— 今日应计入
            {"确认日期": "2026-10-07", "基金代码": "025208", "基金名称": "测试",
             "业务类型": "用户买入", "申请金额": 1000.0, "申请份额": 0.0,
             "确认金额": 1000.0, "确认份额": 1000.0, "手续费": 0.0},
            # 今日买入 500 份 —— 今日不应计入（T 日申购 T+1 起才承担涨跌）
            {"确认日期": "2026-10-09", "基金代码": "025208", "基金名称": "测试",
             "业务类型": "用户买入", "申请金额": 500.0, "申请份额": 0.0,
             "确认金额": 500.0, "确认份额": 500.0, "手续费": 0.0},
        ])

    def test_excludes_same_day_buy(self):
        shares = effective_shares_before(self._trades(), "2026-10-09")
        assert shares["025208"] == pytest.approx(1000.0, abs=0.01)

    def test_includes_previous_day_buy(self):
        """把 as_of 拨到明天，今日那笔就该计入了。"""
        shares = effective_shares_before(self._trades(), "2026-10-10")
        assert shares["025208"] == pytest.approx(1500.0, abs=0.01)

    def test_empty_trades(self):
        assert effective_shares_before(pd.DataFrame(), "2026-10-09") == {}


class TestComputeDailyPnl:
    def test_end_to_end(self):
        holdings = {"025208": 1163.53}
        quotes = [Quote("025208", 2.1747, 2.1283, is_estimate=True)]
        names = {"025208": "永赢先锋半导体智选混合A"}

        p = compute_daily_pnl(holdings, quotes, names)
        assert p.today_pnl == pytest.approx(-53.98, abs=0.05)
        assert p.change_pct * 100 == pytest.approx(-2.13, abs=0.05)
        assert len(p.items) == 1
        assert p.items[0].name == "永赢先锋半导体智选混合A"

    def test_holding_without_quote_is_not_lost(self):
        """持有但缺行情的基金要占位，否则汇总份额会被漏掉。"""
        holdings = {"025208": 100.0, "000001": 50.0}
        quotes = [Quote("025208", 1.0, 1.1)]

        p = compute_daily_pnl(holdings, quotes)
        codes = {i.code for i in p.items}
        assert codes == {"025208", "000001"}

    def test_quote_without_holding_yields_zero_pnl(self):
        p = compute_daily_pnl({}, [Quote("025208", 1.0, 1.5)])
        assert p.today_pnl == 0.0
        assert p.change_pct == 0.0
