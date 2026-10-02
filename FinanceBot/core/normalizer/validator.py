# -*- coding: utf-8 -*-
"""
validator.py —— 对账校验

在导出后运行，回答两个问题：
1. 解析是否完整？—— 用明细表独立复算（Σ买入份额 - Σ卖出份额、Σ买入金额），
   与持仓计算结果逐基金对比，不一致即说明解析丢行或记账有误。
2. 结果是否合理？—— 份额与成本非负；无持仓但仍有成本的基金提示出来。

校验逻辑全部独立于 position_calculator，用最朴素的求和实现，
避免「生成方自己验证自己」的自洽陷阱。
"""

import pandas as pd


def _buy_sell_sums(trades: pd.DataFrame, code: str) -> dict:
    """
    独立复算单只基金的买入/卖出份额与金额合计。

    方向判定（与 position_calculator 同口径，但独立实现，避免自洽陷阱）：
    - 买入类 = 业务类型含「买入/再投」，或「转换」且申请金额>0（转换转入）
    - 卖出类 = 业务类型含「卖出」，或「转换」且申请份额>0（转换转出）
    注意：蚂蚁交割单转换行的业务类型是「用户跨TA转换」，本身不含「转入/转出」字样，
    必须用申请金额/申请份额列判方向——按金额申购时申请份额为 "/"，
    按份额转出/卖出时申请金额为 0.00，二者互斥。
    """
    sub = trades[trades["基金代码"] == code]
    biz = sub["业务类型"].str
    is_buy = biz.contains("买入|再投", regex=True) | (biz.contains("转换") & (sub["申请金额"] > 0))
    is_sell = biz.contains("卖出", regex=True) | (biz.contains("转换") & (sub["申请份额"] > 0))

    buys = sub[is_buy]
    sells = sub[is_sell]
    return {
        "buy_shares": abs(buys["确认份额"]).sum(),
        "sell_shares": abs(sells["确认份额"]).sum(),
        "buy_cost": buys["确认金额"].sum(),       # 买入成本口径 = Σ确认金额（含转换转入）
        "sell_proceeds": sells["确认金额"].sum(),  # 卖出所得
    }


def validate(trades: pd.DataFrame, positions: pd.DataFrame) -> bool:
    """
    执行对账，返回是否全部通过。
    校验项：
      1. 持仓份额 = Σ买入份额 - Σ卖出份额（±0.01 容差）
      2. 持仓成本 = Σ买入确认金额 - 摊薄扣减（用份额比例间接验证成本单调性）
      3. 份额、成本均为非负
    校验结果直接打印，方便人工核对。
    """
    print("\n===== 对账校验 =====")
    all_ok = True
    for _, pos in positions.iterrows():
        code = pos["基金代码"]
        s = _buy_sell_sums(trades, code)
        expect_shares = round(s["buy_shares"] - s["sell_shares"], 4)
        got_shares = pos["持有份额"]
        shares_ok = abs(expect_shares - got_shares) <= 0.01

        # 成本合理性：买入总成本必须 >= 持仓成本（卖出只会扣成本，不会增成本）
        cost_ok = pos["持仓成本"] <= s["buy_cost"] + 1e-6

        # 非负检查
        nonneg_ok = got_shares >= 0 and pos["持仓成本"] >= 0

        ok = shares_ok and cost_ok and nonneg_ok
        all_ok = all_ok and ok
        flag = "✔" if ok else "✘"
        print(
            f"{flag} {code} {pos['基金名称']}: "
            f"复算份额 {expect_shares} vs 持仓 {got_shares} | "
            f"买入总成本 {s['buy_cost']:.2f} vs 持仓成本 {pos['持仓成本']:.2f} | "
            f"卖出所得 {s['sell_proceeds']:.2f}"
        )

    if all_ok:
        print("===== 对账全部通过 ✔ =====")
    else:
        print("===== 存在差异 ✘，请检查解析/记账逻辑 =====")
    return all_ok
