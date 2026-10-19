# -*- coding: utf-8 -*-
"""
test_pipeline.py —— 支付宝连接器冒烟测试（不依赖真实 PDF 与网络）

运行: python -m pytest tests/ -v   或   python tests/connectors/alipay/test_pipeline.py
覆盖:
  1. 摊薄成本计算：买入/卖出/转换转入转出
  2. Wealthfolio 导出：buy/sell 活动与成本口径
  3. 对账校验通过
"""

import os
import sys
import tempfile
from pathlib import Path

# 仓库根 = tests -> connectors -> alipay -> 仓库根（向上 3 级）
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402

from core.normalizer import position_calculator, validator  # noqa: E402
from connectors.wealthfolio import exporter as wf_exporter  # noqa: E402


def _sample_trades() -> pd.DataFrame:
    """构造覆盖主要业务类型的样例明细（蚂蚁交割单标准格式）。"""
    rows = [
        # 基金A：两次买入
        ("2026-01-05", "000001", "测试基金A", "定投买入", 10.00, 0.0, 10.00, 4.25, 0.01),
        ("2026-03-10", "000001", "测试基金A", "定投买入", 10.00, 0.0, 10.00, 4.20, 0.01),
        # 基金A：卖出一部分（摊薄成本）
        ("2026-05-08", "000001", "测试基金A", "用户卖出", 0.00, 2.00, 4.76, 2.00, 0.00),
        # 基金B：转换转入（申请金额有值）
        ("2026-07-01", "000002", "测试基金B", "用户跨TA转换", 50.00, 0.0, 50.00, 10.00, 0.05),
        # 基金C：转换转出（申请份额有值）
        ("2026-07-02", "000003", "测试基金C", "用户跨TA转换", 0.00, 10.00, 55.00, 10.00, 0.05),
        # 基金C：买入后转出，检查份额归零
        ("2026-06-01", "000003", "测试基金C", "定投买入", 50.00, 0.0, 50.00, 10.00, 0.05),
    ]
    return pd.DataFrame(
        rows,
        columns=["确认日期", "基金代码", "基金名称", "业务类型",
                 "申请金额", "申请份额", "确认金额", "确认份额", "手续费"],
    )


def test_positions():
    trades = _sample_trades()
    pos = position_calculator.compute_positions(trades)

    row_a = pos[pos["基金代码"] == "000001"].iloc[0]
    # 份额 = 4.25 + 4.20 - 2.00 = 6.45
    assert abs(row_a["持有份额"] - 6.45) < 1e-6, f"份额错误: {row_a['持有份额']}"
    # 成本 = 20.00 * (1 - 2/8.45) = 15.27（摊薄）
    assert abs(row_a["持仓成本"] - 15.27) < 0.01, f"成本错误: {row_a['持仓成本']}"

    row_b = pos[pos["基金代码"] == "000002"].iloc[0]
    assert abs(row_b["持有份额"] - 10.00) < 1e-6

    row_c = pos[pos["基金代码"] == "000003"].iloc[0]
    assert row_c["持有份额"] == 0.0 and row_c["持仓成本"] == 0.0
    print("test_positions ✔")


def test_wealthfolio_export(tmp_path=None):
    trades = _sample_trades()
    out = os.path.join(str(tmp_path) if tmp_path else tempfile.gettempdir(), "临时测试导入表.csv")
    wf_exporter.export_wealthfolio_csv(trades, out, account="测试账户")

    wf = pd.read_csv(out, dtype={"symbol": str})  # symbol 是基金代码，必须按文本读，避免前导零丢失
    assert set(wf.columns) == set(wf_exporter.WEALTHFOLIO_COLUMNS)
    assert (wf["activityType"].value_counts().to_dict()) == {"buy": 4, "sell": 2}
    # 买入成本口径：amount = 确认金额 - 手续费
    buy_a = wf[(wf["symbol"] == "000001") & (wf["activityType"] == "buy")].iloc[0]
    assert abs(buy_a["amount"] - 9.99) < 1e-6
    assert abs(buy_a["fee"] - 0.01) < 1e-6
    print("test_wealthfolio_export ✔")


def test_validator():
    trades = _sample_trades()
    pos = position_calculator.compute_positions(trades)
    assert validator.validate(trades, pos) is True
    print("test_validator ✔")


if __name__ == "__main__":
    test_positions()
    test_wealthfolio_export()
    test_validator()
    print("\n全部冒烟测试通过 ✔")
