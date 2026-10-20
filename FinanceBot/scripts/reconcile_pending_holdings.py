# -*- coding: utf-8 -*-
"""把持仓快照与“交易进行中”买入单拆分、估算并生成两份持仓文件。

计算口径：
1. 只扣减在原始持仓快照采集时点之前或当时已经存在的交易进行中买入金额；
2. 快照之后的新买入不从原始快照中扣减，只进入“交易进行中”估算；
3. 确认持仓份额 = (快照持有金额 - 快照时点待确认金额) / 最新净值；
4. 确认持仓成本 = 快照持仓成本 - 快照时点待确认金额；
5. 交易进行中估算份额 = 当前待确认金额 / 最新净值，按两位小数记录；
6. 组合持仓成本价 = (确认成本 + 待确认金额) / (确认份额 + 估算份额)。
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, Iterable, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed" / "reconciliation" / "alipay"
DEFAULT_EXPORT_DIR = PROJECT_ROOT / "data" / "export"
DEFAULT_SNAPSHOT_JSON = DEFAULT_PROCESSED_DIR / "持仓快照输入.json"
DEFAULT_HOLDINGS_CSV = DEFAULT_PROCESSED_DIR / "资产导入表_自动.csv"
DEFAULT_PENDING_CSV = DEFAULT_PROCESSED_DIR / "待确认交易.csv"
DEFAULT_NAV_CACHE = PROJECT_ROOT / "data" / "processed" / "market_data" / "净值缓存.json"
DEFAULT_PENDING_SUMMARY = DEFAULT_PROCESSED_DIR / "待确认交易汇总.csv"
DEFAULT_HOLDINGS_OVERVIEW_OUTPUT = DEFAULT_PROCESSED_DIR / "持仓总览.csv"
DEFAULT_CONFIRMED_OUTPUT = DEFAULT_EXPORT_DIR / "确定持仓表.csv"
DEFAULT_PENDING_OUTPUT = DEFAULT_EXPORT_DIR / "待处理持仓表.csv"
DEFAULT_VALIDATION_OUTPUT = DEFAULT_PROCESSED_DIR / "待确认持仓对账校验.json"

PENDING_HEADERS = {
    "trade_time": "交易时间",
    "status": "状态",
    "activity_type": "交易类型",
    "symbol": "基金代码",
    "fund_name": "基金名称",
    "amount": "交易金额",
    "currency": "币种",
    "source_image": "来源截图",
}
PENDING_SUMMARY_HEADERS = {
    "symbol": "基金代码",
    "fund_name": "基金名称",
    "pending_count": "交易进行中笔数",
    "pending_amount": "交易进行中金额",
    "first_trade_time": "最早交易时间",
    "last_trade_time": "最晚交易时间",
    "source_images": "来源截图",
}
CONFIRMED_HEADERS = {
    "symbol": "基金代码",
    "fund_name": "基金名称",
    "nav_date": "净值日期",
    "latest_nav": "最新净值",
    "snapshot_captured_at": "快照采集时间",
    "snapshot_market_value": "快照持有金额",
    "snapshot_profit": "快照持有收益",
    "snapshot_quantity": "快照持有份额",
    "snapshot_cost_basis": "快照持仓成本",
    "snapshot_unit_cost": "快照每股持仓成本",
    "pending_at_snapshot_count": "快照时点待确认笔数",
    "pending_at_snapshot_amount": "快照时点待确认金额",
    "current_pending_count": "当前交易进行中笔数",
    "current_pending_amount": "当前交易进行中金额",
    "current_pending_trade_times": "当前交易进行中时间",
    "confirmed_market_value": "确认持仓金额",
    "confirmed_quantity": "确认持有份额",
    "confirmed_cost_basis": "确认持仓成本",
    "confirmed_unit_cost": "确认每股持仓成本",
    "calculation_rule": "计算规则",
}
ESTIMATED_HEADERS = {
    **{key: value for key, value in CONFIRMED_HEADERS.items() if key != "calculation_rule"},
    "determinable_pending_amount": "可估算交易进行中金额",
    "pending_nav_missing_amount": "待净值交易进行中金额",
    "pending_nav_missing_count": "待净值交易笔数",
    "estimated_pending_quantity": "估算交易进行中份额",
    "estimated_nav_details": "估算净值适用明细",
    "share_calculation_status": "份额计算状态",
    "projected_quantity": "预计持有份额",
    "projected_cost_basis": "预计持仓成本",
    "projected_unit_cost": "预计每股持仓成本",
    "projected_market_value": "预计持仓金额",
    "transaction_rule": "交易规则",
}

HOLDINGS_OVERVIEW_HEADERS = {
    "symbol": "基金代码",
    "fund_name": "基金名称",
    "nav_date": "净值日期",
    "latest_nav": "最新净值",
    "snapshot_captured_at": "快照采集时间",
    "snapshot_market_value": "快照持有金额",
    "snapshot_profit": "快照持有收益",
    "snapshot_quantity": "快照持有份额",
    "snapshot_cost_basis": "快照持仓成本",
    "snapshot_unit_cost": "快照每股持仓成本",
    "pending_at_snapshot_count": "已扣除交易进行中笔数",
    "pending_at_snapshot_amount": "已扣除交易进行中金额",
    "confirmed_market_value": "确定持仓金额",
    "confirmed_quantity": "确定持有份额",
    "confirmed_cost_basis": "确定持仓成本",
    "confirmed_unit_cost": "确定每股持仓成本",
    "calculation_rule": "计算规则",
}
FINAL_CONFIRMED_HEADERS = {
    "symbol": "基金代码",
    "fund_name": "基金名称",
    "confirmed_market_value": "确定持仓金额",
    "confirmed_quantity": "确定持有份额",
    "confirmed_cost_basis": "确定持仓成本",
    "confirmed_unit_cost": "确定每股持仓成本",
}
PENDING_HOLDINGS_HEADERS = {
    "symbol": "基金代码",
    "fund_name": "基金名称",
    "current_pending_count": "交易进行中笔数",
    "current_pending_amount": "待处理金额",
    "pending_cost_basis": "待处理持仓成本",
    "current_pending_trade_times": "交易时间",
    "share_confirmation_date": "份额确定日期",
    "estimated_nav_details": "适用净值明细",
    "determinable_pending_amount": "可估算金额",
    "pending_nav_missing_amount": "待净值金额",
    "share_calculation_status": "份额状态",
    "source_images": "来源截图",
    "transaction_rule": "份额计算规则",
}

ZERO = Decimal("0")
QTY_2 = Decimal("0.01")
MONEY_2 = Decimal("0.01")
COST_4 = Decimal("0.0001")
CN_TZ = timezone(timedelta(hours=8))


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_2, rounding=ROUND_HALF_UP)


def quantity(value: Decimal) -> Decimal:
    return value.quantize(QTY_2, rounding=ROUND_HALF_UP)


def unit_cost(value: Decimal) -> Decimal:
    return value.quantize(COST_4, rounding=ROUND_HALF_UP)


def decimal_text(value: Decimal | None, quantum: Decimal | None = None) -> str:
    if value is None:
        return ""
    if quantum is not None:
        value = value.quantize(quantum, rounding=ROUND_HALF_UP)
    return format(value, "f")


def parse_decimal(value: object, *, default: Decimal | None = None) -> Decimal | None:
    if value is None or value == "":
        return default
    return Decimal(str(value).replace(",", "").strip())


def read_csv(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def write_csv(
    path: Path,
    rows: Iterable[dict],
    fieldnames: List[str],
    headers: Dict[str, str] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    aliases = headers or {name: name for name in fieldnames}
    output_fieldnames = [aliases[name] for name in fieldnames]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=output_fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({aliases[key]: value for key, value in row.items() if key in aliases})


def load_snapshot_rows(path: Path) -> tuple[datetime, Dict[str, dict]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    captured_at = datetime.fromisoformat(payload["captured_at"])
    rows = {row["code"]: row for row in payload.get("rows", []) if row.get("code")}
    return captured_at, rows


def load_holdings(path: Path) -> Dict[str, dict]:
    return {row["symbol"]: row for row in read_csv(path) if row.get("symbol")}


def load_nav(path: Path) -> Dict[str, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("funds", {})


def load_pending(path: Path) -> List[dict]:
    if not path.exists():
        return []
    rows = read_csv(path)
    for row in rows:
        row["trade_time"] = row.get("交易时间") or row.get("trade_time")
        row["symbol"] = row.get("基金代码") or row.get("symbol")
        row["fund_name"] = row.get("基金名称") or row.get("fund_name")
        row["amount"] = row.get("交易金额") or row.get("amount")
        row["source_image"] = row.get("来源截图") or row.get("source_image")
        row["_trade_at"] = datetime.strptime(row["trade_time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=CN_TZ)
        row["_amount"] = parse_decimal(row["amount"], default=ZERO)
    return sorted(rows, key=lambda item: (item["_trade_at"], item["symbol"]))


def pending_summary_rows(pending: List[dict]) -> List[dict]:
    grouped: Dict[str, dict] = {}
    for row in pending:
        item = grouped.setdefault(
            row["symbol"],
            {
                "symbol": row["symbol"],
                "fund_name": row["fund_name"],
                "pending_count": 0,
                "pending_amount": ZERO,
                "first_trade_time": row["trade_time"],
                "last_trade_time": row["trade_time"],
                "source_images": set(),
            },
        )
        item["pending_count"] += 1
        item["pending_amount"] += row["_amount"]
        item["first_trade_time"] = min(item["first_trade_time"], row["trade_time"])
        item["last_trade_time"] = max(item["last_trade_time"], row["trade_time"])
        item["source_images"].add(row["source_image"])

    output = []
    for symbol in sorted(grouped):
        item = grouped[symbol]
        output.append(
            {
                "symbol": symbol,
                "fund_name": item["fund_name"],
                "pending_count": item["pending_count"],
                "pending_amount": decimal_text(money(item["pending_amount"])),
                "first_trade_time": item["first_trade_time"],
                "last_trade_time": item["last_trade_time"],
                "source_images": "; ".join(sorted(item["source_images"])),
            }
        )
    return output


def scheduled_nav_date(trade_at: datetime) -> date:
    """15:00 前使用当日净值；15:00 及以后使用下一交易日净值。"""
    trade_date = trade_at.date()
    return trade_date if trade_at.hour < 15 else trade_date + timedelta(days=1)


def nav_for_trade(fund_nav: dict, trade_at: datetime) -> dict | None:
    target_date = scheduled_nav_date(trade_at)
    history = fund_nav.get("history") or []
    exact = [item for item in history if item.get("date") == target_date.isoformat()]
    if exact:
        return exact[-1]

    # 周末没有净值，使用下一个实际净值日；工作日缺记录时不向前或向后替代。
    if target_date.weekday() >= 5:
        for item in history:
            if date.fromisoformat(item["date"]) > target_date:
                return item
    return None


def share_confirmation_date(trade_at: datetime) -> str:
    """返回交易日后的第2个交易日（周一至周五，不含节假日）。"""
    confirmation = trade_at.date()
    remaining = 2
    while remaining:
        confirmation += timedelta(days=1)
        if confirmation.weekday() < 5:
            remaining -= 1
    return confirmation.isoformat()


def build_reconciliation(
    snapshot_captured_at: datetime,
    snapshot_rows: Dict[str, dict],
    holdings: Dict[str, dict],
    pending: List[dict],
    nav_funds: Dict[str, dict],
) -> tuple[List[dict], List[dict]]:
    pending_by_symbol: Dict[str, List[dict]] = defaultdict(list)
    for row in pending:
        pending_by_symbol[row["symbol"]].append(row)

    symbols = sorted(set(snapshot_rows) | set(holdings) | set(pending_by_symbol))
    confirmed_rows: List[dict] = []
    estimated_rows: List[dict] = []

    for symbol in symbols:
        snapshot = snapshot_rows.get(symbol, {})
        holding = holdings.get(symbol, {})
        orders = pending_by_symbol.get(symbol, [])
        fund_nav = nav_funds.get(symbol)
        if not fund_nav:
            raise ValueError(f"{symbol}: 净值缓存缺少基金数据")

        nav = parse_decimal(fund_nav.get("latest_nav"))
        if nav is None or nav <= ZERO:
            raise ValueError(f"{symbol}: 最新净值无效")

        fund_name = (
            snapshot.get("name")
            or holding.get("fund_name")
            or fund_nav.get("name")
            or (orders[0]["fund_name"] if orders else symbol)
        )
        snapshot_value = parse_decimal(snapshot.get("market_value"))
        snapshot_profit = parse_decimal(snapshot.get("profit"), default=ZERO)
        original_quantity = parse_decimal(holding.get("quantity"), default=ZERO)
        original_cost_basis = parse_decimal(holding.get("amount"), default=ZERO)
        original_unit_cost = parse_decimal(holding.get("unitPrice"))

        row_captured_at = (
            datetime.fromisoformat(str(snapshot["captured_at"]))
            if snapshot.get("captured_at")
            else snapshot_captured_at
        )
        eligible_orders = [row for row in orders if row["_trade_at"] <= row_captured_at]
        eligible_amount = sum((row["_amount"] for row in eligible_orders), ZERO)
        current_pending_amount = sum((row["_amount"] for row in orders), ZERO)

        if snapshot_value is not None:
            confirmed_value_exact = snapshot_value - eligible_amount
            confirmed_quantity_exact = confirmed_value_exact / nav
            confirmed_cost_exact = original_cost_basis - eligible_amount
            confirmed_unit_cost_exact = confirmed_cost_exact / confirmed_quantity_exact
        else:
            confirmed_value_exact = ZERO
            confirmed_quantity_exact = ZERO
            confirmed_cost_exact = ZERO
            confirmed_unit_cost_exact = ZERO

        determinable_orders: list[tuple[dict, dict]] = []
        missing_orders: list[dict] = []
        nav_details: list[str] = []
        order_details: list[dict] = []
        for order in orders:
            target_date = scheduled_nav_date(order["_trade_at"])
            nav_item = nav_for_trade(fund_nav, order["_trade_at"])
            nav_detail = (
                f"{order['trade_time']} → 净值日{target_date.isoformat()}(待净值)"
                if nav_item is None
                else f"{order['trade_time']} → 净值日{nav_item['date']}({nav_item['nav']})"
            )
            nav_details.append(nav_detail)
            order_details.append(
                {
                    "order": order,
                    "nav_item": nav_item,
                    "nav_detail": nav_detail,
                    "share_confirmation_date": share_confirmation_date(order["_trade_at"]),
                }
            )
            if nav_item is None:
                missing_orders.append(order)
                continue
            determinable_orders.append((order, nav_item))

        determinable_amount = sum((order["_amount"] for order, _ in determinable_orders), ZERO)
        missing_amount = sum((order["_amount"] for order in missing_orders), ZERO)
        estimated_pending_quantity_exact = sum(
            (order["_amount"] / parse_decimal(nav_item["nav"], default=ZERO)
             for order, nav_item in determinable_orders),
            ZERO,
        )
        all_pending_determinable = not missing_orders and bool(orders)
        projected_cost_exact = confirmed_cost_exact + current_pending_amount
        projected_quantity_exact = (
            confirmed_quantity_exact + estimated_pending_quantity_exact
            if not missing_orders
            else None
        )
        projected_unit_cost_exact = (
            projected_cost_exact / projected_quantity_exact
            if projected_quantity_exact
            else None
        )
        if not orders:
            share_status = "无交易进行中"
        elif not determinable_orders:
            share_status = "全部待净值，交易进行中份额已搁置"
        elif missing_orders:
            share_status = "部分待净值，仅估算已有适用净值的交易"
        else:
            share_status = "已按交易时间对应净值全部估算"

        common = {
            "symbol": symbol,
            "fund_name": fund_name,
            "nav_date": fund_nav.get("latest_date", ""),
            "latest_nav": decimal_text(nav),
            "snapshot_captured_at": row_captured_at.isoformat(timespec="seconds"),
            "snapshot_market_value": decimal_text(money(snapshot_value)) if snapshot_value is not None else "",
            "snapshot_profit": decimal_text(money(snapshot_profit)) if snapshot else "",
            "snapshot_quantity": decimal_text(quantity(original_quantity)) if holding else "",
            "snapshot_cost_basis": decimal_text(money(original_cost_basis)) if holding else "",
            "snapshot_unit_cost": decimal_text(unit_cost(original_unit_cost)) if original_unit_cost is not None else "",
            "pending_at_snapshot_count": len(eligible_orders),
            "pending_at_snapshot_amount": decimal_text(money(eligible_amount)),
            "current_pending_count": len(orders),
            "current_pending_amount": decimal_text(money(current_pending_amount)),
            "current_pending_trade_times": "; ".join(row["trade_time"] for row in orders),
            "confirmed_market_value": decimal_text(money(confirmed_value_exact)),
            "confirmed_quantity": decimal_text(quantity(confirmed_quantity_exact)),
            "confirmed_cost_basis": decimal_text(money(confirmed_cost_exact)),
            "confirmed_unit_cost": decimal_text(unit_cost(confirmed_unit_cost_exact)),
            "calculation_rule": "确定持仓与交易进行中分开；交易进行中份额不进入确认持仓",
        }
        confirmed_rows.append(common)
        estimated_rows.append(
            {
                **common,
                "determinable_pending_amount": decimal_text(money(determinable_amount)),
                "pending_nav_missing_amount": decimal_text(money(missing_amount)),
                "pending_nav_missing_count": len(missing_orders),
                "estimated_pending_quantity": (
                    decimal_text(quantity(estimated_pending_quantity_exact))
                    if determinable_orders
                    else ""
                ),
                "estimated_nav_details": "; ".join(nav_details),
                "pending_cost_basis": decimal_text(money(current_pending_amount)),
                "source_images": "; ".join(sorted({row["source_image"] for row in orders if row.get("source_image")})),
                "share_calculation_status": share_status,
                "projected_quantity": (
                    decimal_text(quantity(projected_quantity_exact))
                    if projected_quantity_exact is not None
                    else ""
                ),
                "projected_cost_basis": decimal_text(money(projected_cost_exact)),
                "projected_unit_cost": (
                    decimal_text(unit_cost(projected_unit_cost_exact))
                    if projected_unit_cost_exact is not None
                    else ""
                ),
                "projected_market_value": (
                    decimal_text(money(projected_quantity_exact * nav))
                    if projected_quantity_exact is not None
                    else ""
                ),
                "transaction_rule": (
                    "15:00前下单使用当日净值，15:00及以后使用下一交易日净值；"
                    "份额确定日期=交易日+2个交易日；适用净值未发布时份额留空，不使用最新净值替代"
                ),
                "pending_order_details": order_details,
            }
        )

    return confirmed_rows, estimated_rows


def confirmed_holdings_rows(rows: List[dict]) -> List[dict]:
    return [row for row in rows if row.get("snapshot_market_value") not in (None, "")]


def pending_holdings_rows(rows: List[dict]) -> List[dict]:
    """将基金汇总拆成按交易时间逐笔输出的待处理交易。"""
    output: List[dict] = []
    for row in rows:
        for detail in row.get("pending_order_details", []):
            order = detail["order"]
            nav_item = detail["nav_item"]
            amount = decimal_text(money(order["_amount"]))
            output.append(
                {
                    "symbol": row["symbol"],
                    "fund_name": row["fund_name"],
                    "current_pending_count": 1,
                    "current_pending_amount": amount,
                    "pending_cost_basis": amount,
                    "current_pending_trade_times": order["trade_time"],
                    "share_confirmation_date": detail["share_confirmation_date"],
                    "estimated_nav_details": detail["nav_detail"],
                    "determinable_pending_amount": amount if nav_item is not None else "0.00",
                    "pending_nav_missing_amount": "0.00" if nav_item is not None else amount,
                    "share_calculation_status": (
                        "已按交易时间对应净值估算"
                        if nav_item is not None
                        else "全部待净值，交易进行中份额已搁置"
                    ),
                    "source_images": order.get("source_image", ""),
                    "transaction_rule": row["transaction_rule"],
                }
            )
    return output


def validate_reference(confirmed_rows: List[dict]) -> dict:
    row = next(item for item in confirmed_rows if item["symbol"] == "008253")
    expected = {
        "symbol": "008253",
        "fund_name": "华宝致远混合(QDII)A",
        "confirmed_market_value": Decimal("929.34"),
        "confirmed_quantity": Decimal("523.57"),
        "confirmed_unit_cost": Decimal("1.7763"),
        "pending_at_snapshot_amount": Decimal("10.00"),
        "latest_nav": Decimal("1.7750"),
        "nav_date": "2026-10-09",
        "source_image": str(DEFAULT_PROCESSED_DIR / "资产详情校验_20261013_151649.jpg"),
    }
    calculated = {
        "confirmed_market_value": Decimal(row["confirmed_market_value"]),
        "confirmed_quantity": Decimal(row["confirmed_quantity"]),
        "confirmed_unit_cost": Decimal(row["confirmed_unit_cost"]),
        "pending_at_snapshot_amount": Decimal(row["pending_at_snapshot_amount"]),
        "latest_nav": Decimal(row["latest_nav"]),
        "nav_date": row["nav_date"],
    }
    tolerances = {
        "confirmed_market_value": Decimal("0.05"),
        "confirmed_quantity": Decimal("0.05"),
        "confirmed_unit_cost": Decimal("0.0005"),
        "pending_at_snapshot_amount": Decimal("0.00"),
        "latest_nav": Decimal("0.0001"),
    }
    checks = {}
    for field, tolerance in tolerances.items():
        difference = abs(calculated[field] - expected[field])
        checks[field] = {
            "expected": decimal_text(expected[field]),
            "calculated": decimal_text(calculated[field]),
            "difference": decimal_text(difference),
            "tolerance": decimal_text(tolerance),
            "passed": difference <= tolerance,
        }
    checks["nav_date"] = {
        "expected": expected["nav_date"],
        "calculated": calculated["nav_date"],
        "passed": calculated["nav_date"] == expected["nav_date"],
    }

    exact_fields = ("pending_at_snapshot_amount", "latest_nav", "nav_date")
    exact_match = all(checks[field]["passed"] and checks[field].get("difference", "0") == "0" for field in exact_fields)
    exact_match = exact_match and all(
        checks[field]["difference"] == "0"
        for field in ("confirmed_market_value", "confirmed_quantity", "confirmed_unit_cost")
    )
    passed = all(item["passed"] for item in checks.values())
    return {
        "status": "pass_exact" if exact_match else ("pass_with_display_rounding_tolerance" if passed else "fail"),
        "reference": {key: decimal_text(value) if isinstance(value, Decimal) else value for key, value in expected.items()},
        "checks": checks,
        "note": "校验持仓快照时点待确认金额；快照之后新增交易只进入当前交易进行中统计。支付宝展示值经过四舍五入，份额允许0.05份、成本价允许0.0005元差异。",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="拆分确认持仓与交易进行中估算持仓")
    parser.add_argument("--snapshot-json", default=str(DEFAULT_SNAPSHOT_JSON))
    parser.add_argument("--holdings-csv", default=str(DEFAULT_HOLDINGS_CSV))
    parser.add_argument("--pending-csv", default=str(DEFAULT_PENDING_CSV))
    parser.add_argument("--nav-cache", default=str(DEFAULT_NAV_CACHE))
    parser.add_argument("--pending-summary", default=str(DEFAULT_PENDING_SUMMARY))
    parser.add_argument("--overview-output", default=str(DEFAULT_HOLDINGS_OVERVIEW_OUTPUT))
    parser.add_argument("--confirmed-output", default=str(DEFAULT_CONFIRMED_OUTPUT))
    parser.add_argument("--pending-output", default=str(DEFAULT_PENDING_OUTPUT))
    parser.add_argument("--validation-output", default=str(DEFAULT_VALIDATION_OUTPUT))
    args = parser.parse_args()

    snapshot_captured_at, snapshot_rows = load_snapshot_rows(Path(args.snapshot_json))
    holdings = load_holdings(Path(args.holdings_csv))
    pending = load_pending(Path(args.pending_csv))
    nav_funds = load_nav(Path(args.nav_cache))

    confirmed_rows, estimated_rows = build_reconciliation(
        snapshot_captured_at, snapshot_rows, holdings, pending, nav_funds
    )
    summary_rows = pending_summary_rows(pending)
    validation = validate_reference(confirmed_rows)

    confirmed_output_rows = confirmed_holdings_rows(confirmed_rows)
    pending_output_rows = pending_holdings_rows(estimated_rows)
    overview_fields = list(HOLDINGS_OVERVIEW_HEADERS)
    confirmed_fields = list(FINAL_CONFIRMED_HEADERS)
    pending_fields = list(PENDING_HOLDINGS_HEADERS)

    write_csv(
        Path(args.pending_summary),
        summary_rows,
        list(PENDING_SUMMARY_HEADERS),
        PENDING_SUMMARY_HEADERS,
    )
    write_csv(
        Path(args.overview_output),
        confirmed_output_rows,
        overview_fields,
        HOLDINGS_OVERVIEW_HEADERS,
    )
    write_csv(
        Path(args.confirmed_output),
        confirmed_output_rows,
        confirmed_fields,
        FINAL_CONFIRMED_HEADERS,
    )
    write_csv(
        Path(args.pending_output),
        pending_output_rows,
        pending_fields,
        PENDING_HOLDINGS_HEADERS,
    )
    Path(args.validation_output).write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"交易进行中统计: {len(pending)} 笔, {len(summary_rows)} 只基金")
    print(f"持仓总览: {args.overview_output} | {len(confirmed_output_rows)} 行")
    print(f"确定持仓表: {args.confirmed_output} | {len(confirmed_output_rows)} 行")
    print(f"待处理持仓表: {args.pending_output} | {len(pending_output_rows)} 行")
    print(f"第三张截图校验: {validation['status']}")


if __name__ == "__main__":
    main()





