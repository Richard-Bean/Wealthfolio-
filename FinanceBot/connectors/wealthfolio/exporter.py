# -*- coding: utf-8 -*-
"""
exporter.py —— Wealthfolio 导入 CSV 导出（目标连接器：Wealthfolio）

Wealthfolio 导入格式说明（https://github.com/nnaumenko/wealthfolio 支持的 CSV 列）：
    date, account, activityType, symbol, isin, quantity, unitPrice,
    amount, currency, fee, tax, comment
- 导入的是「逐笔交易活动」（buy / sell / dividend），Wealthfolio 会自行累计出持仓；
- 买入活动 amount 取「确认金额 - 手续费」，fee 单独列，
  使 Wealthfolio 的成本基础 = 确认金额，与蚂蚁财富 APP 的持有成本口径一致；
- 卖出活动 amount 为卖出所得（确认金额），fee 为卖出手续费；
- 所有 CSV 均使用 utf-8-sig 编码（带 BOM），Excel 直接打开不乱码。
"""

import pandas as pd

WEALTHFOLIO_COLUMNS = [
    "date", "account", "activityType", "symbol", "isin",
    "quantity", "unitPrice", "amount", "currency", "fee", "tax", "comment",
]


def _classify(biz_type: str, apply_amount: float, apply_shares: float) -> str:
    """
    交易方向判定（与 core/normalizer/position_calculator 同口径，独立实现便于对照）：
    - 转换行业务类型为「用户跨TA转换」，不含「转入/转出」字样，
      必须用申请金额/申请份额判方向：申请份额>0=转出(sell)，申请金额>0=转入(buy)；
    - 含「卖出/转出」= sell；含「买入/转入/再投」= buy；
    - 现金分红（含「分红」且不含「再投」）= dividend；未知类型按 buy 处理不丢记录。
    """
    biz = str(biz_type)
    if "转换" in biz:
        if apply_shares > 0:
            return "sell"
        if apply_amount > 0:
            return "buy"
    if "卖出" in biz or "转出" in biz:
        return "sell"
    if "分红" in biz and "再投" not in biz:
        return "dividend"
    return "buy"


def export_wealthfolio_csv(trades: pd.DataFrame, out_path: str, account: str = "蚂蚁财富"):
    """
    交易明细 -> Wealthfolio 导入格式 CSV。

    参数:
        trades: 支付宝连接器输出的标准明细 DataFrame
        account: Wealthfolio 中的账户名（可在 config/config.yaml 的 alipay 段修改）
    """
    rows = []
    for _, r in trades.iterrows():
        action = _classify(r["业务类型"], r["申请金额"], r["申请份额"])
        shares = abs(r["确认份额"])
        amount = r["确认金额"]
        fee = r["手续费"]

        if action == "buy":
            # 成本口径：确认金额 = 实际支付（含手续费），故净额 = 确认金额 - 手续费
            net_amount = max(0.0, round(amount - fee, 2))
            unit_price = round(net_amount / shares, 4) if shares > 0 else 0.0
        elif action == "sell":
            net_amount = round(amount, 2)
            unit_price = round(amount / shares, 4) if shares > 0 else 0.0
        else:  # dividend 现金分红
            net_amount = round(amount, 2)
            shares, unit_price, fee = 0.0, 0.0, 0.0

        rows.append({
            "date": r["确认日期"],
            "account": account,
            "activityType": action,
            "symbol": r["基金代码"],
            "isin": "",
            "quantity": shares,
            "unitPrice": unit_price,
            "amount": net_amount,
            "currency": "CNY",
            "fee": fee,
            "tax": 0,
            "comment": f"{r['业务类型']} | {r['基金名称']}",
        })

    df = pd.DataFrame(rows, columns=WEALTHFOLIO_COLUMNS)
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"[导出] Wealthfolio 导入流水: {out_path}（共 {len(df)} 笔活动）")
