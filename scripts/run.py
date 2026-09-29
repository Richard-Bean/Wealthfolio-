# -*- coding: utf-8 -*-
"""
run.py —— 一键运行入口

用法:
    python3 scripts/run.py                 # 使用 config.py 中的默认交割单
    python3 scripts/run.py /path/to/xxx.pdf   # 指定交割单 PDF

流程:
    解析PDF -> 拉取最新净值(可关) -> 计算持仓 -> 导出CSV -> 对账校验
产物（data/output/ 下）:
    fund_positions.csv       持仓汇总（每只基金一行）
    wealthfolio_import.csv   Wealthfolio 可导入的交易流水
"""

import os
import sys

# 把项目根目录加入模块搜索路径（保证 scripts/ 下可直接运行）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import config  # noqa: E402
from src import statement_parser, position_calculator, nav_provider, exporter, validator  # noqa: E402


def main():
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else config.PDF_PATH
    if not os.path.exists(pdf_path):
        print(f"[错误] 找不到交割单文件: {pdf_path}")
        print("请把支付宝下载的 PDF 放到 data/input/，或传入文件路径。")
        sys.exit(1)

    os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    # 1. 解析 PDF -> 交易明细
    print(f"[1/5] 解析交割单: {pdf_path}")
    trades = statement_parser.parse_statement_pdf(pdf_path)
    print(f"      共 {len(trades)} 笔交易，涉及 {trades['基金代码'].nunique()} 只基金")
    print("      业务类型分布:", dict(trades["业务类型"].value_counts()))

    # 2. 拉取最新净值（可选；失败自动降级为交割单确认净值）
    codes = sorted(trades["基金代码"].unique())
    nav_map = {}
    if config.FETCH_NAV:
        print(f"[2/5] 拉取 {len(codes)} 只基金的最新净值 ...")
        fetched = nav_provider.fetch_batch(codes)
        nav_map = {c: (info[1], info[2]) for c, info in fetched.items()}
        failed = [c for c in codes if c not in fetched]
        if failed and config.VERBOSE_NAV:
            print(f"      {len(failed)} 只基金拉取失败，已用交割单净值兜底: {failed}")
    else:
        print("[2/5] 已关闭联网拉净值（config.FETCH_NAV=False），使用交割单确认净值")

    # 3. 计算持仓
    print("[3/5] 计算持仓（摊薄成本法）...")
    positions = position_calculator.compute_positions(trades, nav_map)

    # 4. 导出 CSV
    print("[4/5] 导出 CSV ...")
    pos_csv = os.path.join(config.OUTPUT_DIR, "fund_positions.csv")
    wf_csv = os.path.join(config.OUTPUT_DIR, "wealthfolio_import.csv")
    exporter.export_positions_csv(positions, pos_csv)
    exporter.export_wealthfolio_csv(trades, wf_csv, account=config.ACCOUNT_NAME)

    # 5. 对账校验
    print("[5/5] 对账校验 ...")
    validator.validate(trades, positions)

    # 最终持仓一览
    print("\n===== 当前持仓 =====")
    show = positions.copy()
    show["最新净值"] = show["最新净值"].astype(str)
    print(show.to_string(index=False))
    print(f"\n完成。产物目录: {config.OUTPUT_DIR}")


if __name__ == "__main__":
    main()
