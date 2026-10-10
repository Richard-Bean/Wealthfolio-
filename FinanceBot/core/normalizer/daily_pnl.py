# -*- coding: utf-8 -*-
"""
daily_pnl.py —— 今日持仓涨跌算法

职责：给定持有份额与「昨日净值 / 今日净值（或盘中估值）」，算出单只基金与整个组合
的今日涨跌金额、涨跌幅度。与具体金融机构无关；行情数据由调用方注入（API / 缓存 /
交割单兜底），本模块自身不联网，便于日后换数据源而不动算法。

口径（与蚂蚁财富「持有」页一致，已用实测数字反推验证）：
1. 单只基金涨跌幅度 = (今日净值 - 昨日净值) / 昨日净值        —— 即「看涨跌」
2. 单只基金今日涨跌 = 今日有效份额 × (今日净值 - 昨日净值)
3. 组合今日涨跌     = Σ 各基金今日涨跌
4. 组合涨跌幅度     = 组合今日涨跌 / Σ(今日有效份额 × 昨日净值)
   分母是「昨收市值」，等价于按昨收市值对各基金涨跌幅加权平均。
   注意：绝不能把各基金涨跌幅做算术平均，否则大仓位与小仓位被等同看待，
   组合幅度会严重偏离真实盈亏。

关键口径：今日有效份额
- 场外基金 T 日 15:00 前申购，按 T 日净值确认，自 T+1 日起才承担涨跌；
  因此今日新买入的份额，今日涨跌为 0，不能并入今日涨跌的乘数。
- 「今日有效份额」= 截至昨日收盘已确认的份额（确认日期 < 今日）。
- 见 effective_shares_before()。

净值来源约定（调用方负责取数，本模块不关心出处）：
- 收盘后：当日实际单位净值，is_estimate=False
- 盘中：估值，is_estimate=True（算法完全相同，结果可能与最终净值有偏差）
- 未更新（节假日 / QDII 暂停申赎）：today_nav = prev_nav，涨跌自然为 0

维护提示：
- 将来接实时行情 API：只需产出 Quote 序列喂给 compute_daily_pnl，本文件不用改。
- 货币基金是万份收益制、无净值涨跌概念，若要支持需在 fund_daily_pnl 加分支。
- 若要改成「今日涨跌含今日买入」的口径，只改 effective_shares_before() 一处。
"""

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

import pandas as pd

from core.normalizer import position_calculator

# 输出列（每只基金一行；组合汇总另见 PortfolioDailyPnl）
DAILY_PNL_COLUMNS = [
    "基金代码", "基金名称", "今日有效份额",
    "昨日净值", "今日净值", "净值涨跌", "涨跌幅度%",
    "今日涨跌", "昨收市值", "今日市值", "是否估值",
]


@dataclass(frozen=True)
class Quote:
    """
    单只基金行情：昨收 / 今收（或盘中估值）。数据源无关，由调用方构造。

    prev_nav / today_nav 为单位净值；is_estimate 标记 today_nav 是否为盘中估值。
    """
    code: str
    prev_nav: float
    today_nav: float
    is_estimate: bool = False


@dataclass(frozen=True)
class FundDailyPnl:
    """单只基金的今日涨跌结果。金额单位：元；涨跌幅度为小数（0.0134 = +1.34%）。"""
    code: str
    name: str
    shares: float            # 今日有效份额
    prev_nav: float
    today_nav: float
    nav_change: float        # 单位净值涨跌 = today_nav - prev_nav
    change_pct: float        # 涨跌幅度（小数）
    today_pnl: float         # 今日涨跌金额
    prev_market_value: float # 昨收市值
    today_market_value: float
    is_estimate: bool


@dataclass(frozen=True)
class PortfolioDailyPnl:
    """组合汇总。change_pct 按昨收市值加权，不是各基金涨跌幅的算术平均。"""
    today_pnl: float
    change_pct: float
    prev_market_value: float
    today_market_value: float
    items: List[FundDailyPnl] = field(default_factory=list)


def fund_daily_pnl(
    code: str,
    name: str,
    shares: float,
    prev_nav: float,
    today_nav: float,
    is_estimate: bool = False,
) -> FundDailyPnl:
    """
    单只基金今日涨跌（纯算法，无 IO）。

    参数:
        shares:     今日有效份额（截至昨日收盘已确认的份额，不是当前总份额）
        prev_nav:   昨日单位净值
        today_nav:  今日单位净值（盘中传估值）
    返回:
        FundDailyPnl
    """
    shares = float(shares)
    prev_nav = float(prev_nav)
    today_nav = float(today_nav)

    nav_change = today_nav - prev_nav
    # 昨日净值为 0（理论上不应出现）时避免除零，幅度记 0
    change_pct = (nav_change / prev_nav) if prev_nav > 0 else 0.0

    return FundDailyPnl(
        code=code,
        name=name,
        shares=shares,
        prev_nav=prev_nav,
        today_nav=today_nav,
        nav_change=nav_change,
        change_pct=change_pct,
        today_pnl=shares * nav_change,
        prev_market_value=shares * prev_nav,
        today_market_value=shares * today_nav,
        is_estimate=is_estimate,
    )


def portfolio_daily_pnl(items: Iterable[FundDailyPnl]) -> PortfolioDailyPnl:
    """
    把多只基金的今日涨跌聚合成组合汇总。

    组合涨跌幅度 = Σ今日涨跌 / Σ昨收市值 —— 按昨收市值加权。
    份额为 0 的基金不产生盈亏，但会自然进入分母贡献 0，不影响结果。
    """
    items = list(items)
    today_pnl = sum(i.today_pnl for i in items)
    prev_mv = sum(i.prev_market_value for i in items)
    today_mv = sum(i.today_market_value for i in items)
    change_pct = (today_pnl / prev_mv) if prev_mv > 0 else 0.0

    return PortfolioDailyPnl(
        today_pnl=today_pnl,
        change_pct=change_pct,
        prev_market_value=prev_mv,
        today_market_value=today_mv,
        items=items,
    )


def effective_shares_before(trades: pd.DataFrame, as_of_date: str) -> Dict[str, float]:
    """
    计算「今日有效份额」：截至 as_of_date 前一日收盘已确认的持有份额。

    实现方式是把交割单截断到 as_of_date 之前，再走一遍 position_calculator 的
    逐笔记账（买入加 / 卖出按摊薄比例扣），从而与持仓口径完全一致。

    参数:
        trades:      statement_parser 输出的标准明细 DataFrame
        as_of_date:  「今日」，格式 2026-10-09；只累加确认日期 < 该日的交易
    返回:
        {基金代码: 今日有效份额}；该日之前无持仓的基金不出现在结果里
    """
    if trades is None or trades.empty:
        return {}

    before = trades[trades["确认日期"] < as_of_date]
    if before.empty:
        return {}

    # nav_map 留空：这里只需要份额，不需要净值
    positions = position_calculator.compute_positions(before, nav_map={})
    return dict(zip(positions["基金代码"], positions["持有份额"]))


def compute_daily_pnl(
    holdings: Dict[str, float],
    quotes: Iterable[Quote],
    names: Optional[Dict[str, str]] = None,
) -> PortfolioDailyPnl:
    """
    完整计算入口：份额 + 行情 -> 单只基金明细 + 组合汇总。

    参数:
        holdings: {基金代码: 今日有效份额}
                  用 effective_shares_before() 从交割单算出，或直接给手填份额
        quotes:   每只基金一条 Quote（prev_nav / today_nav）
        names:    {基金代码: 基金名称}，可选，仅用于展示
    返回:
        PortfolioDailyPnl（内含每只基金的 FundDailyPnl）
    """
    names = names or {}
    results: List[FundDailyPnl] = []

    for q in quotes:
        shares = float(holdings.get(q.code, 0.0))
        results.append(fund_daily_pnl(
            code=q.code,
            name=names.get(q.code, q.code),
            shares=shares,
            prev_nav=q.prev_nav,
            today_nav=q.today_nav,
            is_estimate=q.is_estimate,
        ))

    # 持有但行情缺失的基金也要占位，避免汇总时份额被漏掉
    quoted_codes = {q.code for q in quotes}
    for code, shares in holdings.items():
        if code in quoted_codes or shares == 0:
            continue
        results.append(fund_daily_pnl(
            code=code,
            name=names.get(code, code),
            shares=shares,
            prev_nav=0.0,
            today_nav=0.0,
            is_estimate=False,
        ))

    return portfolio_daily_pnl(results)


def to_dataframe(pnl: PortfolioDailyPnl) -> pd.DataFrame:
    """把结果转成 DataFrame，便于导出 CSV / 打印。涨跌幅度已转为百分数数值。"""
    records = []
    for i in pnl.items:
        records.append({
            "基金代码": i.code,
            "基金名称": i.name,
            "今日有效份额": round(i.shares, 4),
            "昨日净值": round(i.prev_nav, 4),
            "今日净值": round(i.today_nav, 4),
            "净值涨跌": round(i.nav_change, 4),
            "涨跌幅度%": round(i.change_pct * 100, 2),
            "今日涨跌": round(i.today_pnl, 2),
            "昨收市值": round(i.prev_market_value, 2),
            "今日市值": round(i.today_market_value, 2),
            "是否估值": "是" if i.is_estimate else "否",
        })
    return pd.DataFrame(records, columns=DAILY_PNL_COLUMNS)


if __name__ == "__main__":
    # 演示：用 实现.jpg 中 025208 的实测数字验证算法
    # 份额 1163.53、当日收益 -53.98、涨跌幅度约 -2.13%（图上板块 -2.12%）
    q = Quote(code="025208", prev_nav=2.1747, today_nav=2.1283, is_estimate=True)
    r = fund_daily_pnl("025208", "永赢先锋半导体智选混合A", 1163.53, q.prev_nav, q.today_nav, True)
    print(f"今日涨跌   : {r.today_pnl:.2f} 元")
    print(f"涨跌幅度   : {r.change_pct * 100:.2f}%")
    print(f"昨收市值   : {r.prev_market_value:.2f}")
    print(f"今日市值   : {r.today_market_value:.2f}")
