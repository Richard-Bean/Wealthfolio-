# -*- coding: utf-8 -*-
"""
position_calculator.py —— 持仓计算器（摊薄成本法）

职责：把交易明细 DataFrame 按基金逐笔记账，得到每只基金的当前持仓。

记账规则（与蚂蚁财富 APP 持有口径一致）：
1. 买入类（定投买入 / 用户买入 / 转换转入）
   - 份额 += 确认份额
   - 成本 += 确认金额（蚂蚁口径：确认金额即实际支付金额，含手续费）
2. 卖出类（用户卖出 / 定投卖出 / 转换转出）
   - 份额 -= 确认份额（取绝对值，兼容正负号）
   - 成本按摊薄成本法比例扣减：成本 -= 成本 × (卖出份额 / 卖出前份额)
3. 转换的转出/转入判定：
   - 「申请份额」列有数值 -> 转出（按卖出记）
   - 「申请金额」列有数值且申请份额为空 -> 转入（按买入记）
   - 依据：蚂蚁交割单中按金额申购的申请份额显示 "/"，
     按份额卖出/转出的申请金额显示 0.00，二者互斥，可用作方向判据。
4. 现金分红：不影响份额与成本（分红来自收益分配）。
   说明：蚂蚁交割单样例中未出现现金分红行；如未来出现，
   本规则已覆盖，无需改代码。

维护提示：
- 新增业务类型只需在 _BUY_KEYWORDS / _SELL_KEYWORDS 中追加关键词；
- 若要改成「先进先出」等其他成本法，只改 _apply_sell() 一个函数。
"""

import pandas as pd

# 业务类型关键词（按「包含」匹配，兼容「定投买入/用户买入/转换转入」等变体）
_BUY_KEYWORDS = ("买入", "转入", "红利再投", "分红再投")
_SELL_KEYWORDS = ("卖出", "转出")

# 持仓输出列
POSITION_COLUMNS = [
    "基金代码", "基金名称", "持有份额", "持仓成本", "单位成本",
    "最新净值", "净值日期", "持仓市值", "浮动盈亏", "盈亏率%",
]


def _classify(biz_type: str, apply_amount: float, apply_shares: float) -> str:
    """
    把蚂蚁交割单的业务类型归为三类：buy / sell / ignore。
    转换类按申请份额/申请金额判方向；未知类型按买入处理并打印提示（不丢记录）。
    """
    biz = str(biz_type)
    if "转换" in biz:
        if apply_shares > 0:      # 有申请份额 -> 转出
            return "sell"
        if apply_amount > 0:      # 有申请金额 -> 转入
            return "buy"
    if any(k in biz for k in _SELL_KEYWORDS):
        return "sell"
    if "分红" in biz and "再投" not in biz:   # 现金分红
        return "ignore"
    if any(k in biz for k in _BUY_KEYWORDS):
        return "buy"
    # 未知类型：按买入处理，宁可多算也不丢份额，同时打印提示便于发现
    print(f"[提示] 未识别业务类型「{biz}」，已按买入处理。")
    return "buy"


def _apply_buy(state: dict, row: pd.Series):
    """买入/转入/红利再投：份额与成本都增加。"""
    state["shares"] += abs(row["确认份额"])
    state["cost"] += row["确认金额"]


def _apply_sell(state: dict, row: pd.Series):
    """卖出/转出：份额减少，成本按摊薄比例扣减。"""
    qty = abs(row["确认份额"])
    if state["shares"] > 1e-8:
        state["cost"] -= state["cost"] * (qty / state["shares"])
    state["shares"] = max(0.0, state["shares"] - qty)
    # 清理浮点残差：多次加减后可能残留 ~1e-13，导致卖光后出现假的小份额/小成本
    if state["shares"] < 1e-8:
        state["shares"] = 0.0
    if abs(state["cost"]) < 1e-6:
        state["cost"] = 0.0


def _apply_ignore(state: dict, row: pd.Series):
    """现金分红：份额与成本不变。"""


def compute_positions(trades: pd.DataFrame, nav_map: dict = None) -> pd.DataFrame:
    """
    由交易明细计算持仓。

    参数:
        trades: statement_parser 输出的标准明细 DataFrame
        nav_map: {基金代码: (最新净值, 净值日期)}，可选；
                 不传则用交割单中该基金最后一笔的确认净值兜底，
                 并在「净值日期」标为交割单日期。
    返回:
        每只基金一行的持仓 DataFrame（列见 POSITION_COLUMNS）
    """
    nav_map = nav_map or {}
    records = []

    for code, group in trades.groupby("基金代码"):
        group = group.sort_values("确认日期")
        name = group["基金名称"].iloc[0] or code

        state = {"shares": 0.0, "cost": 0.0}
        last_confirm_nav_date = ""

        for _, row in group.iterrows():
            action = _classify(row["业务类型"], row["申请金额"], row["申请份额"])
            if action == "buy":
                _apply_buy(state, row)
            elif action == "sell":
                _apply_sell(state, row)
            elif action == "ignore":
                _apply_ignore(state, row)
            # 记录最后一笔确认日期（用于净值兜底标注）
            if row["确认日期"]:
                last_confirm_nav_date = row["确认日期"]

        # 最新净值：优先用外部净值接口，否则用交割单最后一笔确认净值兜底
        if code in nav_map:
            nav, nav_date = nav_map[code]
        else:
            last_row = group.iloc[-1]
            nav = last_row["确认金额"] / last_row["确认份额"] if last_row["确认份额"] else 0.0
            nav_date = last_confirm_nav_date

        shares = state["shares"]
        cost = state["cost"]
        unit_cost = cost / shares if shares > 0 else 0.0
        market_value = shares * nav
        profit = market_value - cost
        profit_pct = (profit / cost * 100) if cost > 0 else 0.0

        records.append({
            "基金代码": code,
            "基金名称": name,
            "持有份额": round(shares, 4),
            "持仓成本": round(cost, 2),
            "单位成本": round(unit_cost, 4),
            "最新净值": round(nav, 4),
            "净值日期": nav_date,
            "持仓市值": round(market_value, 2),
            "浮动盈亏": round(profit, 2),
            "盈亏率%": round(profit_pct, 2),
        })

    result = pd.DataFrame(records, columns=POSITION_COLUMNS)
    return result.sort_values("基金代码").reset_index(drop=True)
