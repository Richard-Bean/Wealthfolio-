# -*- coding: utf-8 -*-
"""
exporter.py —— 支付宝连接器导出（持仓汇总 CSV）

注：Wealthfolio 导入流水的导出在 connectors/wealthfolio/exporter.py，
两个导出函数按「目标归属」分开放置。
"""

import pandas as pd


def export_positions_csv(positions: pd.DataFrame, out_path: str):
    """持仓汇总 -> CSV（utf-8-sig，Excel 直接打开不乱码）。"""
    positions.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"[导出] 持仓汇总: {out_path}")
