# -*- coding: utf-8 -*-
"""
run.py —— 支付宝连接器一键运行入口

用法:
    python connectors/alipay/scripts/run.py                    # 使用 config.yaml 中的默认交割单
    python connectors/alipay/scripts/run.py /path/to/xxx.pdf   # 指定交割单 PDF

流程:
    解析PDF -> 拉取最新净值(可关) -> 计算持仓 -> 导出CSV -> 对账校验
产物（data/processed/alipay/ 下）:
    fund_positions.csv       持仓汇总（每只基金一行）
    wealthfolio_import.csv   Wealthfolio 可导入的交易流水
"""

import logging
import os
import sys
from pathlib import Path

# 仓库根 = scripts -> alipay -> connectors -> 仓库根（向上 3 级）
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from connectors.alipay import config  # noqa: E402
from connectors.alipay import exporter, nav_provider, statement_parser  # noqa: E402
from connectors.wealthfolio import exporter as wf_exporter  # noqa: E402
from core.normalizer import position_calculator, validator  # noqa: E402

# 运行日志（logs/alipay_fund_csv.log）
_LOG_DIR = REPO_ROOT / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(_LOG_DIR / "alipay_fund_csv.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8",
)


def main():
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else config.PDF_PATH
    if not os.path.exists(pdf_path):
        print(f"[错误] 找不到交割单文件: {pdf_path}")
        print("请把支付宝下载的 PDF 放到 data/raw/alipay/，或传入文件路径。")
        sys.exit(1)

    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    logging.info("开始运行，交割单: %s", pdf_path)

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
        print("[2/5] 已关闭联网拉净值（config.yaml: fetch_nav=false），使用交割单确认净值")

    # 3. 计算持仓
    print("[3/5] 计算持仓（摊薄成本法）...")
    positions = position_calculator.compute_positions(trades, nav_map)

    # 4. 导出 CSV
    print("[4/5] 导出 CSV ...")
    pos_csv = os.path.join(config.OUTPUT_DIR, "fund_positions.csv")
    wf_csv = os.path.join(config.OUTPUT_DIR, "wealthfolio_import.csv")
    exporter.export_positions_csv(positions, pos_csv)
    wf_exporter.export_wealthfolio_csv(trades, wf_csv, account=config.ACCOUNT_NAME)

    # 5. 对账校验
    print("[5/5] 对账校验 ...")
    validator.validate(trades, positions)

    # 最终持仓一览
    print("\n===== 当前持仓 =====")
    show = positions.copy()
    show["最新净值"] = show["最新净值"].astype(str)
    print(show.to_string(index=False))
    print(f"\n完成。产物目录: {config.OUTPUT_DIR}")
    logging.info("运行完成，产物目录: %s", config.OUTPUT_DIR)


if __name__ == "__main__":
    main()
