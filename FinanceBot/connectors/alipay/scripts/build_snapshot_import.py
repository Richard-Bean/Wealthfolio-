# -*- coding: utf-8 -*-
"""
从持仓截图字段 + 本地净值缓存生成 Wealthfolio CSV。

不读取交割单 PDF、交易流水或 基金持仓表.csv。
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

from connectors.alipay.config import ACCOUNT_NAME
from core.market_data.nav_cache import latest_nav_asof, load_cache
from core.normalizer.snapshot_validation import validate_snapshot_values
DEFAULT_CACHE = REPO_ROOT / "data" / "processed" / "market_data" / "净值缓存.json"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "processed" / "alipay" / "资产导入表.csv"
DEFAULT_EXPORT = REPO_ROOT / "data" / "export" / "资产导入表_2026-10-09.csv"
DEFAULT_ACCOUNT = ACCOUNT_NAME
LEGACY_ACCOUNT_NAMES = {"蚂蚁财富——测试B"}

COLUMNS = [
    "date", "account", "activityType", "symbol", "isin", "quantity",
    "unitPrice", "amount", "currency", "fee", "tax", "comment",
]


def normalize_account_name(value: str | None) -> str:
    """将旧测试账户名统一为配置中的支付宝账户名。"""
    account = str(value or "").strip()
    if not account or account in LEGACY_ACCOUNT_NAMES:
        return DEFAULT_ACCOUNT
    return account


def validate_screenshot_row(
    code: str,
    name: str,
    market_value: float,
    profit: float,
    reported_rate_pct: float,
    ocr_rate_pct: float | None = None,
    source_image: str | None = None,
    allow_rate_warning: bool = False,
) -> None:
    """金额、成本和收益率不一致时禁止生成 Wealthfolio CSV。"""
    issues, detail = validate_snapshot_values(
        market_value, profit, reported_rate_pct, ocr_rate_pct
    )
    if allow_rate_warning:
        issues = [
            issue for issue in issues
            if issue["code"] not in {"reported_rate_mismatch", "ocr_rate_mismatch"}
        ]
    if issues:
        location = f"，来源={source_image}" if source_image else ""
        summary = "；".join(
            f"{issue['code']}: {issue['message']}" for issue in issues
        )
        raise ValueError(
            f"快照数据需要人工复核：{code} {name}{location}；{summary}；校验={detail}"
        )


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
    for row in screenshot_rows:
        code, name, market_value, profit, profit_pct = row[:5]
        ocr_rate_pct = row[5] if len(row) > 5 else None
        source_image = row[6] if len(row) > 6 else None
        allow_rate_warning = bool(row[7]) if len(row) > 7 else False
        validate_screenshot_row(
            code,
            name,
            market_value,
            profit,
            profit_pct,
            ocr_rate_pct,
            source_image,
            allow_rate_warning,
        )
        total_cost = round(market_value - profit, 2)
        nav_item = latest_nav_asof(cache, code, captured_at)
        if nav_item:
            nav = float(nav_item["nav"])
            if nav <= 0:
                raise ValueError(f"净值必须大于 0：{code} {name}，净值={nav}")
            raw_shares = market_value / nav
            quantity = round(raw_shares, 2)
            unit_price = round(total_cost / raw_shares, 4)
            nav_note = f"净值日期={nav_item['date']} | 单位净值={nav_item['nav']}"

            market_check = abs(quantity * nav - market_value)
            cost_check = abs(quantity * unit_price - total_cost)
            market_tolerance = max(0.02, abs(market_value) * 0.001)
            cost_tolerance = max(0.02, abs(total_cost) * 0.001)
            if market_check > market_tolerance:
                raise ValueError(
                    f"份额×净值与持有金额不一致：{code} {name}，"
                    f"差额={market_check:.4f}，容差={market_tolerance:.4f}"
                )
            if cost_check > cost_tolerance:
                raise ValueError(
                    f"份额×平均成本与持仓成本不一致：{code} {name}，"
                    f"差额={cost_check:.4f}，容差={cost_tolerance:.4f}"
                )
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
    account = normalize_account_name(payload.get("account") or DEFAULT_ACCOUNT)
    rows = []
    for item in payload["rows"]:
        if item.get("validation_status") == "manual_review":
            errors = item.get("validation_errors") or item.get("validation", {}).get("issues")
            raise ValueError(
                f"快照数据需要人工复核：{item.get('code')} {item.get('name')}；{errors}"
            )
        allow_rate_warning = item.get("validation_status") == "warning"
        row = (
            item["code"],
            item["name"],
            float(item["market_value"]),
            float(item["profit"]),
            float(item["profit_pct"]),
            item.get("ocr_rate"),
            item.get("source_image"),
            allow_rate_warning,
        )
        validate_screenshot_row(*row)
        rows.append(row)
    return captured_at, account, rows


def main() -> None:
    parser = argparse.ArgumentParser(description="由持仓截图和本地净值缓存生成 Wealthfolio CSV")
    parser.add_argument("--input", help="结构化截图输入 JSON；不提供时使用内置测试.jpg数据")
    parser.add_argument("--cache", default=str(DEFAULT_CACHE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--export", default=str(DEFAULT_EXPORT))
    parser.add_argument("--account", default=DEFAULT_ACCOUNT)
    parser.add_argument("--require-nav", action="store_true", help="缺少净值时直接失败")
    args = parser.parse_args()

    if args.input:
        captured_at, input_account, screenshot_rows = load_snapshot_input(args.input)
        account = normalize_account_name(input_account or args.account)
    else:
        captured_at = CAPTURED_AT
        account = normalize_account_name(args.account)
        screenshot_rows = SCREENSHOT_ROWS

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
