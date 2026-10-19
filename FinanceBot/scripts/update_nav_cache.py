# -*- coding: utf-8 -*-
"""每日更新基金净值缓存。只请求基金代码，不上传持仓截图或金额。"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.market_data.nav_cache import update_cache
DEFAULT_CACHE = PROJECT_ROOT / "data" / "processed" / "market_data" / "净值缓存.json"
DEFAULT_CODES = ["025208", "015310", "003376", "013308", "022364"]


def main() -> None:
    parser = argparse.ArgumentParser(description="更新基金公开净值本地缓存")
    parser.add_argument("codes", nargs="*", default=DEFAULT_CODES, help="基金代码")
    parser.add_argument("--input", help="从 持仓快照输入.json 自动读取基金代码")
    parser.add_argument("--pending", help="从 待确认交易.csv 补充基金代码")
    parser.add_argument("--output", default=str(DEFAULT_CACHE), help="缓存 JSON 路径")
    parser.add_argument("--offline", action="store_true", help="只使用本地净值缓存，不访问网络")
    args = parser.parse_args()

    codes = list(args.codes or [])
    if args.input:
        with open(args.input, "r", encoding="utf-8") as file:
            snapshot = json.load(file)
        codes.extend(item["code"] for item in snapshot.get("rows", []))
    if args.pending:
        with open(args.pending, "r", encoding="utf-8-sig", newline="") as file:
            codes.extend(
                row.get("基金代码") or row.get("symbol")
                for row in csv.DictReader(file)
            )
    if not codes:
        codes = list(DEFAULT_CODES)
    codes = sorted({str(code).strip() for code in codes if str(code).strip()})

    payload = update_cache(codes, args.output, offline=args.offline)
    print(f"净值缓存已更新: {args.output}")
    for code in codes:
        fund = payload["funds"].get(code)
        if fund:
            print(f"{code}: {fund['name']} | {fund['latest_date']} | {fund['latest_nav']}")
        else:
            print(f"{code}: 失败 | {payload['errors'].get(code, '未知错误')}")


if __name__ == "__main__":
    main()
