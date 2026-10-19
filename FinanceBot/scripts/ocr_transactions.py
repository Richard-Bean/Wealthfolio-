# -*- coding: utf-8 -*-
"""交易截图本地解析：Windows OCR 文本 -> 待确认交易 CSV。

只使用本地 OCR 结果、正则规则和本地基金名称/代码映射，不调用 AI、云端模型或外部搜索 API。
"""

from __future__ import annotations

import csv
import difflib
import re
import unicodedata
from decimal import Decimal
from pathlib import Path

CONFIRMED_HEADERS = [
    "记录日期", "交易日期", "账户", "交易类型", "基金代码", "基金名称",
    "交易份额", "成交净值", "交易金额", "手续费", "税费",
    "来源交易编号", "来源文件", "状态", "备注",
]

PENDING_HEADERS = [
    "交易时间",
    "状态",
    "交易类型",
    "基金代码",
    "基金名称",
    "交易金额",
    "币种",
    "来源截图",
]

_DATETIME_RE = re.compile(
    r"(20\d{2})-(\d{1,2})-(\d{1,2})(\d{1,2}):(\d{2}):(\d{2})"
)
_AMOUNT_RE = re.compile(r"(\d+(?:\.\d+)?)元")
_FUND_PREFIX_RE = re.compile(r"^基金[|丨lI1]")
_QDII_RE = re.compile(r"\(QD(?:II|围|lI|1I)?([A-Ca-c]?)\)?")
_ACTIVITY_LABELS = {"定投", "买入", "申购", "卖出", "赎回"}


def _normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = re.sub(r"(?<=\d)\s*[一—–-]\s*(?=\d)", "-", text)
    text = (
        text.replace("：", ":")
        .replace("．", ".")
        .replace("丨", "|")
        .replace("｜", "|")
        .replace("（", "(")
        .replace("）", ")")
    )
    return re.sub(r"\s+", "", text)


def normalize_fund_name(value: object) -> str:
    text = _normalize_text(value)
    text = _FUND_PREFIX_RE.sub("", text)
    text = _QDII_RE.sub(lambda match: f"(QDII){match.group(1).upper()}", text)
    return text.strip(" |·．.")


def _line_geometry(line: dict) -> dict:
    words = line.get("words") or []
    if not words:
        text = str(line.get("text", ""))
        return {"text": text, "normalized": _normalize_text(text), "x": 0.0, "y": 0.0, "right": 0.0}
    left = min(float(word.get("x", 0)) for word in words)
    right = max(float(word.get("x", 0)) + float(word.get("width", 0)) for word in words)
    y = sum(
        float(word.get("y", 0)) + float(word.get("height", 0)) / 2
        for word in words
    ) / len(words)
    text = str(line.get("text", ""))
    return {
        "text": text,
        "normalized": _normalize_text(text),
        "x": (left + right) / 2,
        "right": right,
        "y": y,
    }


def detect_transaction_screenshot(ocr: dict) -> str | None:
    """识别交易记录截图；返回交易文档类型，非交易截图返回 None。"""
    items = [_line_geometry(line) for line in ocr.get("lines") or []]
    if not items:
        return None

    image_width = max((item["right"] for item in items), default=1000.0)
    image_height = max((item["y"] for item in items), default=1000.0)
    has_top_transaction_tab = any(
        "交易记录" in item["normalized"] and item["y"] <= image_height * 0.30
        for item in items
    )
    has_left_activity_label = any(
        item["normalized"] in _ACTIVITY_LABELS and item["x"] <= image_width * 0.20
        for item in items
    )
    if not has_top_transaction_tab or not has_left_activity_label:
        return None

    full_text = "".join(item["normalized"] for item in items)
    if "交易进行中" in full_text:
        return "transaction_in_progress"
    holding_markers = ("名称金额", "昨日收益", "持有收益", "累计收益")
    if any(marker in full_text for marker in holding_markers):
        return None
    return "transaction_activity"

def _match_datetime(text: str) -> str | None:
    match = _DATETIME_RE.search(text)
    if not match:
        return None
    year, month, day, hour, minute, second = match.groups()
    return f"{year}-{int(month):02d}-{int(day):02d} {int(hour):02d}:{minute}:{second}"


def _match_amount(text: str) -> Decimal | None:
    match = _AMOUNT_RE.search(text)
    return Decimal(match.group(1)) if match else None


def _resolve_local_fund(name: str, mapping: dict[str, str]) -> tuple[str, str]:
    normalized_to_name = {
        normalize_fund_name(mapped_name): mapped_name
        for mapped_name in mapping
        if mapped_name
    }
    query = normalize_fund_name(name)
    if query in normalized_to_name:
        matched_name = normalized_to_name[query]
        return mapping[matched_name], matched_name

    candidates = list(normalized_to_name)
    if not candidates:
        return "", name
    best = max(
        candidates,
        key=lambda candidate: difflib.SequenceMatcher(None, query, candidate).ratio(),
    )
    score = difflib.SequenceMatcher(None, query, best).ratio()
    if score < 0.92:
        return "", name
    matched_name = normalized_to_name[best]
    return mapping[matched_name], matched_name


def parse_transaction_ocr(
    ocr: dict,
    image_path: Path | str,
    mapping: dict[str, str] | None = None,
) -> list[dict]:
    """把交易记录页 OCR 几何文本解析为待确认交易行。"""
    items = [_line_geometry(line) for line in ocr.get("lines") or []]
    if not items:
        raise ValueError("OCR 没有识别到文本")

    image_width = max((item["right"] for item in items), default=1000.0)
    anchors = [
        item
        for item in items
        if item["normalized"] in _ACTIVITY_LABELS and item["x"] < image_width * 0.20
    ]
    anchors.sort(key=lambda item: item["y"])
    if not anchors:
        raise ValueError("未识别到交易类型标签")

    mapping = mapping or {}
    rows: list[dict] = []
    for index, anchor in enumerate(anchors):
        region_start = anchor["y"] - 45
        region_end = anchors[index + 1]["y"] - 45 if index + 1 < len(anchors) else float("inf")
        region = [
            item
            for item in items
            if region_start <= item["y"] < region_end and item is not anchor
        ]

        trade_time = next(
            (value for item in region if (value := _match_datetime(item["normalized"]))),
            None,
        )
        amount = next(
            (
                value
                for item in region
                if item["x"] >= image_width * 0.68
                and (value := _match_amount(item["normalized"])) is not None
            ),
            None,
        )
        status = next(
            (
                item["normalized"]
                for item in region
                if item["x"] >= image_width * 0.68
                and any(marker in item["normalized"] for marker in ("交易进行中", "处理中", "待确认"))
            ),
            "已确认",
        )

        name_parts = [
            item["normalized"]
            for item in region
            if image_width * 0.12 <= item["x"] < image_width * 0.68
            and _match_datetime(item["normalized"]) is None
            and _match_amount(item["normalized"]) is None
            and item["normalized"] not in {"明细", "基金", "全部"}
        ]
        fund_name = normalize_fund_name("".join(name_parts))

        if not trade_time:
            raise ValueError(f"第 {index + 1} 笔交易缺少交易时间")
        if amount is None:
            raise ValueError(f"第 {index + 1} 笔交易缺少交易金额")
        if not fund_name:
            raise ValueError(f"第 {index + 1} 笔交易缺少基金名称")

        code, standard_name = _resolve_local_fund(fund_name, mapping)
        activity = anchor["normalized"]
        activity_type = "sell" if activity in {"卖出", "赎回"} else "buy"
        rows.append({
            "交易时间": trade_time,
            "状态": status,
            "交易类型": activity_type,
            "基金代码": code,
            "基金名称": standard_name,
            "交易金额": f"{amount:.2f}",
            "币种": "CNY",
            "来源截图": str(image_path),
        })
    return sorted(rows, key=lambda item: (item["交易时间"], item["基金代码"], item["基金名称"]))


def merge_pending_rows(rows: list[dict]) -> list[dict]:
    """跨截图合并完全相同的待确认订单，保留首次出现的来源。"""
    merged: list[dict] = []
    seen: set[tuple] = set()
    for row in rows:
        key = (
            row.get("交易时间"),
            row.get("状态"),
            row.get("交易类型"),
            row.get("基金代码"),
            normalize_fund_name(row.get("基金名称")),
            str(row.get("交易金额")),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(row)
    return sorted(merged, key=lambda item: (item["交易时间"], item["基金代码"], item["基金名称"]))


def write_pending_transactions(path: Path | str, rows: list[dict]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=PENDING_HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def confirmed_transaction_rows(rows: list[dict], account: str = "蚂蚁财富") -> list[dict]:
    """把截图中未标记为进行中的交易转换为后续正式交易行。"""
    confirmed = []
    for row in rows:
        if any(marker in str(row.get("状态", "")) for marker in ("进行中", "处理中", "待确认")):
            continue
        confirmed.append({
            "记录日期": str(row["交易时间"])[:10],
            "交易日期": row["交易时间"],
            "账户": account,
            "交易类型": "买入" if row.get("交易类型") == "buy" else "卖出",
            "基金代码": row.get("基金代码", ""),
            "基金名称": row.get("基金名称", ""),
            "交易份额": "",
            "成交净值": "",
            "交易金额": row.get("交易金额", ""),
            "手续费": "0.00",
            "税费": "0.00",
            "来源交易编号": "",
            "来源文件": row.get("来源截图", ""),
            "状态": row.get("状态", "已确认"),
            "备注": "交易记录截图未显示份额和净值，按交易金额记录",
        })
    return confirmed


def write_confirmed_transactions(path: Path | str, rows: list[dict]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CONFIRMED_HEADERS)
        writer.writeheader()
        writer.writerows(rows)
