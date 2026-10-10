# -*- coding: utf-8 -*-
"""
从持仓截图字段 + 本地净值缓存生成 Wealthfolio CSV。

不读取交割单 PDF、交易流水或 fund_positions.csv。
截图金额/收益是权威输入；净值只用于反推持有份额。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from core.market_data.nav_cache import latest_nav_asof, load_cache
DEFAULT_CACHE = REPO_ROOT / "data" / "processed" / "market_data" / "nav_cache.json"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "processed" / "alipay" / "wealthfolio_import.csv"
DEFAULT_EXPORT = REPO_ROOT / "data" / "export" / "wealthfolio_import_2026-10-09.csv"

COLUMNS = [
    "date", "account", "activityType", "symbol", "isin", "quantity",
    "unitPrice", "amount", "currency", "fee", "tax", "comment",
]

# 测试.jpg：截图时间 2026-10-09 17:21。
CAPTURED_AT = datetime.fromisoformat("2026-10-09 17:21:00")
SCREENSHOT_ROWS = [
    ("025208", "永赢先锋半导体智选混合A", 2751.83, -313.28, -10.22),
    ("015310", "华泰柏瑞南方东英恒生科技指数ETF联接(QDII)A", 1485.94, -264.06, -15.09),
    ("003376", "广发中债7-10年期国开行债券指数A", 1259.86, 9.83, 0.79),
    ("013308", "易方达恒生科技ETF联接(QDII)A", 1171.60, -228.40, -16.31),
    ("022364", "永赢科技智选混合A", 1154.15, -114.10, -9.00),
]


def build_rows(
    cache: dict,
    account: str,
    captured_at: datetime,
    screenshot_rows: list[tuple],
) -> list[dict]:
    rows = []
    for code, name, market_value, profit, profit_pct in screenshot_rows:
        total_cost = round(market_value - profit, 2)
        nav_item = latest_nav_asof(cache, code, captured_at)
        if nav_item:
            raw_shares = market_value / nav_item["nav"]
            quantity = round(raw_shares, 2)
            unit_price = round(total_cost / raw_shares, 4)
            nav_note = f"净值日期={nav_item['date']} | 单位净值={nav_item['nav']}"
        else:
            quantity = ""
            unit_price = ""
            nav_note = "净值缺失"

        rows.append({
            "date": captured_at.date().isoformat(),
            "account": account,
            "activityType": "buy",
            "symbol": code,
            "isin": "",
            "quantity": quantity,
            "unitPrice": unit_price,
            "amount": total_cost,
            "currency": "CNY",
            "fee": "",
            "tax": "",
            "comment": (
                f"持仓截图+公开净值API | {name} | 持有金额={market_value:.2f} | "
                f"持有收益={profit:.2f} | 持有收益率={profit_pct:.2f}% | {nav_note}"
            ),
        })
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def load_snapshot_input(path: str) -> tuple[datetime, str, list[tuple]]:
    with open(path, "r", encoding="utf-8") as file:
        payload = json.load(file)
    captured_at = datetime.fromisoformat(payload["captured_at"])
    account = payload.get("account", "蚂蚁财富——测试B")
    rows = [
        (
            item["code"],
            item["name"],
            float(item["market_value"]),
            float(item["profit"]),
            float(item["profit_pct"]),
        )
        for item in payload["rows"]
    ]
    return captured_at, account, rows


def main() -> None:
    parser = argparse.ArgumentParser(description="由持仓截图和本地净值缓存生成 Wealthfolio CSV")
    parser.add_argument("--input", help="结构化截图输入 JSON；不提供时使用内置测试.jpg数据")
    parser.add_argument("--cache", default=str(DEFAULT_CACHE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--export", default=str(DEFAULT_EXPORT))
    parser.add_argument("--account", default="蚂蚁财富——测试B")
    parser.add_argument("--require-nav", action="store_true", help="缺少净值时直接失败")
    args = parser.parse_args()

    if args.input:
        captured_at, input_account, screenshot_rows = load_snapshot_input(args.input)
        account = input_account or args.account
    else:
        captured_at, account, screenshot_rows = CAPTURED_AT, args.account, SCREENSHOT_ROWS

    cache = load_cache(args.cache)
    rows = build_rows(cache, account, captured_at, screenshot_rows)
    if args.require_nav and any(not row["quantity"] or not row["unitPrice"] for row in rows):
        raise RuntimeError("有基金缺少净值，未生成完整 CSV；请先运行 update_nav_cache.py")
    write_csv(Path(args.output), rows)
    write_csv(Path(args.export), rows)

    print(f"已生成: {args.output}")
    print(f"已生成: {args.export}")
    for row in rows:
        print(row["symbol"], row["quantity"], row["unitPrice"], row["amount"])


if __name__ == "__main__":
    main()
