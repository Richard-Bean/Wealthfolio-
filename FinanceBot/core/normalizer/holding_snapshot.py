# -*- coding: utf-8 -*-
"""
holding_snapshot.py —— 持仓快照字段体系（对齐蚂蚁财富「持有」详情页）

职责：把「持有」列表页的稀疏字段（金额 / 昨日收益 / 持有收益 / 率）
补全为详情页的 9 字段快照，并导出与 基金持仓表.csv 同风格的 CSV。

字段口径（与蚂蚁财富 APP 持有详情页一致，已用实测截图对拍）：
    持有金额    当前持仓市值
    持有份额    已确认的持有份额
    持仓占比%   该基金市值 / 组合总市值
    持有收益    浮动盈亏（= 持有金额 - 持仓成本总额）
    持有收益率% 浮动盈亏 / 持仓成本总额
    持仓成本    摊薄成本单价（详情页显示的是每份成本，不是总成本）
    当日收益    今日涨跌金额（口径见 daily_pnl.py）
    昨日收益    昨日涨跌金额
    持有天数    APP 统计口径（非简单首买至今天数，以 APP 显示为准）

数据来源优先级（列表页是原始数据，详情页只补列表页没有的字段）：
    1. 列表页（测试.jpg 等）：持有金额 / 昨日收益 / 持有收益 / 持有收益率
    2. 详情页（实现.jpg 等）：持有份额 / 持仓占比 / 持仓成本 / 当日收益 / 持有天数
    3. 本模块推导：持仓成本总额、组合总市值、单位成本校验

口径差异说明（重要）：
    列表页「持有收益」与详情页「持有收益」可能不一致。实测 025208：
    列表页 -313.28，详情页 -350.26，差额 36.98 ≈ 当日收益 -36.87。
    原因是详情页把当日涨跌又并入了一次。本模块以【列表页】为准
    （用户指定的原始数据），详情页只用于补全列表页没有的字段。
    自洽校验：持仓成本单价 × 持有份额 = 持有金额 - 持有收益（列表口径）。

维护提示：
- 将来接行情 / 交易明细后，当日收益可改由 daily_pnl.compute_daily_pnl() 产出；
  持有天数若能找到 APP 统计规则，可换成从交易明细推算。
- 新增字段只改 HOLDING_SNAPSHOT_COLUMNS 与 to_dataframe()。
"""

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

import pandas as pd

# 输出列（每只基金一行，顺序与蚂蚁财富持有详情页字段一致）
HOLDING_SNAPSHOT_COLUMNS = [
    "基金代码", "基金名称",
    "持有金额", "持有份额", "持仓占比%",
    "持有收益", "持有收益率%", "持仓成本",
    "当日收益", "昨日收益", "持有天数",
]


@dataclass(frozen=True)
class HoldingSnapshot:
    """单只基金的持有快照。金额单位：元；比率为百分数数值（-10.22 表示 -10.22%）。"""
    code: str
    name: str
    market_value: float       # 持有金额
    shares: float             # 持有份额
    weight_pct: float         # 持仓占比%
    profit: float             # 持有收益（列表页口径）
    profit_pct: float         # 持有收益率%
    unit_cost: float          # 持仓成本（摊薄成本单价）
    today_pnl: float          # 当日收益
    yesterday_pnl: float      # 昨日收益
    holding_days: int         # 持有天数（APP 统计口径）

    @property
    def total_cost(self) -> float:
        """持仓成本总额 = 持有金额 - 持有收益。"""
        return self.market_value - self.profit


def portfolio_total_from_weight(market_value: float, weight_pct: float) -> float:
    """
    由单只基金的「金额 + 占比」反推组合总市值。

    实现.jpg 中 025208：金额 2751.83、占比 15.41% -> 总市值 ≈ 17858。
    用于给没有详情页截图的基金推算持仓占比。
    """
    if weight_pct <= 0:
        raise ValueError("持仓占比必须大于 0")
    return market_value / (weight_pct / 100.0)


def unit_cost_from_list(market_value: float, profit: float, shares: float) -> float:
    """
    由列表页字段推导摊薄成本单价。

    单位成本 = (持有金额 - 持有收益) / 持有份额
    实测 025208：(2751.83 - (-313.28)) / 1292.97 = 2.3706，与详情页一致。
    """
    if shares <= 0:
        raise ValueError("持有份额必须大于 0")
    return (market_value - profit) / shares


def weight_pct_of(market_value: float, total_market_value: float) -> float:
    """持仓占比% = 该基金市值 / 组合总市值 × 100。"""
    if total_market_value <= 0:
        raise ValueError("组合总市值必须大于 0")
    return market_value / total_market_value * 100.0


def build_snapshot(
    code: str,
    name: str,
    *,
    market_value: float,
    profit: float,
    profit_pct: float,
    yesterday_pnl: float,
    shares: Optional[float] = None,
    unit_cost: Optional[float] = None,
    weight_pct: Optional[float] = None,
    total_market_value: Optional[float] = None,
    today_pnl: Optional[float] = None,
    holding_days: Optional[int] = None,
) -> HoldingSnapshot:
    """
    由列表页字段（必填）+ 详情页字段（选填）组装一条持仓快照。

    - 列表页字段是原始数据，照抄。
    - 详情页字段优先用实测值；缺份额时无法算单位成本，单位成本记 0。
    - 缺 weight_pct 但给了 total_market_value 时，占比按市值推算。
    - 缺 today_pnl / holding_days 时记 0，调用方后续可补。
    """
    if shares is not None and unit_cost is None:
        unit_cost = unit_cost_from_list(market_value, profit, shares)
    if weight_pct is None and total_market_value is not None:
        weight_pct = weight_pct_of(market_value, total_market_value)

    return HoldingSnapshot(
        code=code,
        name=name,
        market_value=float(market_value),
        shares=float(shares) if shares is not None else 0.0,
        weight_pct=float(weight_pct) if weight_pct is not None else 0.0,
        profit=float(profit),
        profit_pct=float(profit_pct),
        unit_cost=float(unit_cost) if unit_cost is not None else 0.0,
        today_pnl=float(today_pnl) if today_pnl is not None else 0.0,
        yesterday_pnl=float(yesterday_pnl),
        holding_days=int(holding_days) if holding_days is not None else 0,
    )


def to_dataframe(items: Iterable[HoldingSnapshot]) -> pd.DataFrame:
    """把快照列表转成 DataFrame，列见 HOLDING_SNAPSHOT_COLUMNS。"""
    records: List[dict] = []
    for s in items:
        records.append({
            "基金代码": s.code,
            "基金名称": s.name,
            "持有金额": round(s.market_value, 2),
            "持有份额": round(s.shares, 2),
            "持仓占比%": round(s.weight_pct, 2),
            "持有收益": round(s.profit, 2),
            "持有收益率%": round(s.profit_pct, 2),
            "持仓成本": round(s.unit_cost, 4),
            "当日收益": round(s.today_pnl, 2),
            "昨日收益": round(s.yesterday_pnl, 2),
            "持有天数": s.holding_days,
        })
    return pd.DataFrame(records, columns=HOLDING_SNAPSHOT_COLUMNS)


def export_csv(items: Iterable[HoldingSnapshot], out_path: str):
    """持仓快照 -> CSV（utf-8-sig，Excel 直接打开不乱码，与 基金持仓表.csv 同风格）。"""
    to_dataframe(items).to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"[导出] 持仓快照: {out_path}")


# ---------------------------------------------------------------------------
# 实测锚点（截图原始数据，测试与演示共用）
# ---------------------------------------------------------------------------

# 测试.jpg「我的持有」列表页（2026-10-09 17:21）——原始数据，字段以此为准
LIST_PAGE_ROWS = [
    # 名称（列表显示名）, 基金代码, 持有金额, 昨日收益, 持有收益, 持有收益率%
    ("永赢先锋半导体智选混合A", "025208", 2751.83, -153.94, -313.28, -10.22),
    ("华泰柏瑞南方东英恒生科技指数ETF联接(QDII)A", "015310", 1485.94, -60.40, -264.06, -15.09),
    ("广发中债7-10年期国开行债券指数A", "003376", 1259.86, -0.11, 9.83, 0.79),
    ("易方达恒生科技ETF联接(QDII)A", "013308", 1171.60, -49.16, -228.40, -16.31),
    ("永赢科技智选混合A", "022364", 1154.15, -27.95, -114.10, -9.00),
]

# 实现.jpg 持有详情页（2026-10-09 16:28）——只用于补全列表页没有的字段
DETAIL_PAGE_FIELDS = {
    "025208": {
        "shares": 1292.97,
        "weight_pct": 15.41,
        "unit_cost": 2.3706,
        "today_pnl": -36.87,
        "holding_days": 11,
    },
    # 用户复核值：013308 列表页金额 1171.60、收益 -228.40，
    # 成本总额 = 1400.00；实际持有份额 1207.96，单位成本自动推导为 1.1590。
    "013308": {
        "shares": 1207.96,
    },
}


def build_from_screenshots() -> List[HoldingSnapshot]:
    """
    由截图锚点组装持仓快照（演示 / 对拍用）。

    口径：列表页字段照抄；有详情页截图的基金补全 5 个详情字段；
    无详情页截图的基金，占比按组合总市值推算，其余详情字段留 0 待补。
    """
    # 组合总市值：由 025208 的金额 + 占比反推（约 17858 元）
    ref = DETAIL_PAGE_FIELDS["025208"]
    ref_row = next(r for r in LIST_PAGE_ROWS if r[1] == "025208")
    total = portfolio_total_from_weight(ref_row[2], ref["weight_pct"])

    items: List[HoldingSnapshot] = []
    for name, code, mv, y_pnl, profit, profit_pct in LIST_PAGE_ROWS:
        items.append(build_snapshot(
            code, name,
            market_value=mv, profit=profit, profit_pct=profit_pct,
            yesterday_pnl=y_pnl,
            total_market_value=total,          # 先按总市值推占比
            **DETAIL_PAGE_FIELDS.get(code, {}),  # 有详情页则覆盖/补全
        ))
    return items


if __name__ == "__main__":
    # 演示：从截图锚点补全字段并导出 CSV
    from pathlib import Path

    items = build_from_screenshots()
    df = to_dataframe(items)
    print(df.to_string(index=False))

    out = Path(__file__).resolve().parents[2] / "data" / "processed" / "alipay" / "持仓快照表.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    export_csv(items, str(out))
