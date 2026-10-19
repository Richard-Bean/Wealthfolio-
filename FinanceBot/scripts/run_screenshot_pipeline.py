# -*- coding: utf-8 -*-
"""运行截图转 CSV 的统一本地入口。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parent
PROCESSED = PROJECT_ROOT / "data" / "processed" / "reconciliation" / "alipay"
CACHE = PROJECT_ROOT / "data" / "processed" / "market_data" / "净值缓存.json"
INPUT = PROCESSED / "snapshot_input.auto.json"
COMPARISON = PROCESSED / "snapshot_comparison.json"
PENDING = PROCESSED / "pending_transactions.csv"
CONFIRMED = PROJECT_ROOT / "data" / "processed" / "reconciliation" / "后续交易_2026-10-12.csv"
HOLDINGS = PROCESSED / "wealthfolio_import_auto.csv"
EXPORT = PROJECT_ROOT / "data" / "export" / "wealthfolio_import_auto.csv"


def run(args: list[str]) -> None:
    subprocess.run([sys.executable, *args], cwd=REPO_ROOT, check=True)


def main() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    run([
        str(PROJECT_ROOT / "scripts" / "ocr_to_snapshot.py"),
        "--output", str(INPUT),
        "--comparison-output", str(COMPARISON),
        "--pending-output", str(PENDING),
        "--confirmed-output", str(CONFIRMED),
    ])
    run([
        str(PROJECT_ROOT / "scripts" / "update_nav_cache.py"),
        "--input", str(INPUT),
        "--pending", str(PENDING),
        "--offline",
        "--output", str(CACHE),
    ])
    run([
        str(PROJECT_ROOT / "connectors" / "alipay" / "scripts" / "build_snapshot_import.py"),
        "--input", str(INPUT),
        "--cache", str(CACHE),
        "--require-nav",
        "--output", str(HOLDINGS),
        "--export", str(EXPORT),
    ])
    run([
        str(PROJECT_ROOT / "scripts" / "reconcile_pending_holdings.py"),
        "--snapshot-json", str(INPUT),
        "--holdings-csv", str(HOLDINGS),
        "--pending-csv", str(PENDING),
        "--nav-cache", str(CACHE),
        "--pending-summary", str(PROCESSED / "pending_trades_summary.csv"),
        "--overview-output", str(PROCESSED / "持仓总览.csv"),
        "--confirmed-output", str(PROJECT_ROOT / "data" / "export" / "确定持仓表.csv"),
        "--pending-output", str(PROJECT_ROOT / "data" / "export" / "待处理持仓表.csv"),
        "--validation-output", str(PROCESSED / "pending_reconciliation_validation.json"),
    ])
    print("完成：截图已分类并生成 CSV。")


if __name__ == "__main__":
    main()