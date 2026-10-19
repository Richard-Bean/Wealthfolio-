# -*- coding: utf-8 -*-
"""
ocr_to_snapshot.py —— 持仓截图 OCR -> 持仓快照输入.json

设计目标：双击 BAT 后自动完成：
图片 -> Windows OCR JSON -> 持仓行解析 -> 本地净值 API -> 持仓快照输入.json

不上传截图。当前解析器面向支付宝/养基宝“我的持有”列表布局：
左列名称、中列金额/昨日收益、右列持有收益/率。
字段布局改变时，应增加新的布局适配规则。
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from connectors.alipay.config import ACCOUNT_NAME  # noqa: E402
from core.market_data.fund_lookup import (  # noqa: E402
    load_mapping,
    resolve_fund_name,
    save_mapping_entry,
    search_fund_by_name,
)
from ocr_transactions import (  # noqa: E402
    confirmed_transaction_rows,
    detect_transaction_screenshot,
    merge_pending_rows,
    parse_transaction_ocr,
    write_confirmed_transactions,
    write_pending_transactions,
)
from core.normalizer.snapshot_validation import (  # noqa: E402
    RATE_ABS_TOLERANCE,
    RATE_REL_TOLERANCE,
    profit_rate_pct,
    select_profit_candidate,
    validate_snapshot_values,
)

DEFAULT_IMAGE_DIR = PROJECT_ROOT / "data" / "raw" / "alipay"
DEFAULT_OCR_SCRIPT = PROJECT_ROOT / "scripts" / "ocr_snapshot.ps1"
DEFAULT_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed" / "reconciliation" / "alipay"
DEFAULT_OUTPUT = DEFAULT_PROCESSED_DIR / "持仓快照输入.json"
DEFAULT_COMPARISON_OUTPUT = DEFAULT_PROCESSED_DIR / "持仓快照对比报告.json"
DEFAULT_PENDING_OUTPUT = DEFAULT_PROCESSED_DIR / "待确认交易.csv"
DEFAULT_CONFIRMED_OUTPUT = PROJECT_ROOT / "data" / "processed" / "reconciliation" / "后续交易_2026-10-12.csv"
FUND_MAP_CSV = DEFAULT_PROCESSED_DIR / "基金持仓表.csv"
FUND_MAPPING_CSV = DEFAULT_PROCESSED_DIR / "基金名称代码映射.csv"
DEFAULT_ACCOUNT = ACCOUNT_NAME
LEGACY_ACCOUNT_NAMES = {'蚂蚁财富——测试B'}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}
TEMPLATE_ALL_HOLDINGS = "all_holdings_4_columns"
TEMPLATE_MY_HOLDINGS = "my_holdings_3_columns"
TEMPLATE_NAMES = {
    TEMPLATE_ALL_HOLDINGS: "全部持有（名称/金额、日收益、持有收益、累计收益）",
    TEMPLATE_MY_HOLDINGS: "我的持有（名称、金额/昨日收益、持有收益/率）",
}
IGNORED_NAME_SUFFIX_RE = re.compile(
    r"(?:基金|黄金)?(?:进阶理财|稳健理财|灵活取用|今日收益更新)$"
)
QDII_OCR_RE = re.compile(r"QD.{0,4}?(?=[A-Ca-c人民币()（）]|$)", re.S)


def normalize_account_name(value: str | None) -> str:
    """统一旧测试账户名，并保留用户明确指定的其他账户名。"""
    account = str(value or "").strip()
    if not account or account in LEGACY_ACCOUNT_NAMES:
        return DEFAULT_ACCOUNT
    return account

NAME_SIMILARITY_THRESHOLD = 0.88
AMOUNT_ABS_TOLERANCE = 0.05
AMOUNT_REL_TOLERANCE = 0.001


def find_images(explicit: list[str] | None = None) -> list[Path]:
    """返回本次需要处理的全部图片；默认扫描 raw/alipay 下所有支持的图片。"""
    if explicit:
        paths = [Path(item).resolve() for item in explicit]
        missing = [str(path) for path in paths if not path.exists()]
        if missing:
            raise FileNotFoundError("找不到图片: " + ", ".join(missing))
    else:
        paths = [
            path for path in DEFAULT_IMAGE_DIR.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        ]
        if not paths:
            raise FileNotFoundError(f"{DEFAULT_IMAGE_DIR} 下没有图片")

    unique: list[Path] = []
    seen: set[Path] = set()
    for path in sorted(paths, key=lambda item: (item.stat().st_mtime, item.name.lower())):
        if path not in seen:
            unique.append(path)
            seen.add(path)
    return unique


def find_image(explicit: str | None) -> Path:
    """兼容旧调用：只返回一张图片。"""
    if explicit:
        return find_images([explicit])[0]
    return find_images()[-1]


def run_windows_ocr(image_path: Path) -> tuple[Path, dict]:
    timestamp_match = re.search(r"(20\d{6})[_-]?(\d{6})", image_path.stem)
    if timestamp_match:
        output_name = f"识别文本_{timestamp_match.group(1)}_{timestamp_match.group(2)}.txt"
    else:
        modified_at = datetime.fromtimestamp(image_path.stat().st_mtime)
        output_name = f"识别文本_{modified_at.strftime('%Y%m%d_%H%M%S_%f')}.txt"
    output_path = image_path.with_name(output_name)
    subprocess.run(
        [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(DEFAULT_OCR_SCRIPT),
            "-ImagePath", str(image_path),
            "-OutputPath", str(output_path),
        ],
        check=True,
    )
    return output_path, json.loads(output_path.read_text(encoding="utf-8"))


def load_fund_names() -> dict[str, str]:
    return load_mapping(FUND_MAPPING_CSV, FUND_MAP_CSV)


def _word_sort_key(word: dict) -> tuple[float, float]:
    return (float(word.get("x", 0)), float(word.get("y", 0)))


def _digits(text: str) -> str:
    return "".join(ch for ch in str(text) if ch.isdigit())


def _is_sign(text: str) -> str | None:
    value = str(text).strip()
    if value in {"+", "＋"}:
        return "+"
    if value in {"-", "−", "—", "－", "一", "һ"}:
        return "-"
    if len(value) > 1 and _digits(value):
        if value[0] in {"+", "＋"}:
            return "+"
        if value[0] in {"-", "−", "—", "－", "一", "һ"}:
            return "-"
    return None


def parse_signed_number(words: list[dict]) -> float | None:
    """从 OCR words 还原金额/收益/百分比。"""
    words = sorted(words, key=_word_sort_key)
    numeric = [word for word in words if _digits(word.get("text", ""))]
    if not numeric:
        return None

    first_numeric_x = float(numeric[0].get("x", 0))
    sign = 1.0
    embedded_sign = _is_sign(numeric[0].get("text", ""))
    if embedded_sign == "+":
        sign = 1.0
    elif embedded_sign == "-":
        sign = -1.0
    for word in words:
        if float(word.get("x", 0)) < first_numeric_x:
            marker = _is_sign(word.get("text", ""))
            if marker == "+":
                sign = 1.0
            elif marker == "-":
                sign = -1.0

    # 两个数字 token 之间的最后一个小符号视为小数点；
    # OCR 可能把逗号/小数点识别成任意短符号。
    separator_index = None
    numeric_indexes = [index for index, word in enumerate(words) if _digits(word.get("text", ""))]
    for left, right in zip(numeric_indexes, numeric_indexes[1:]):
        between = words[left + 1:right]
        if between:
            separator_index = right - 1

    if separator_index is None:
        digits = "".join(_digits(word.get("text", "")) for word in numeric)
        if not digits:
            return None
        if len(digits) <= 2:
            integer, decimal = "0", digits
        else:
            integer, decimal = digits[:-2], digits[-2:]
    else:
        before = words[:separator_index + 1]
        after = words[separator_index + 1:]
        integer = "".join(_digits(word.get("text", "")) for word in before)
        decimal = "".join(_digits(word.get("text", "")) for word in after)
        if not integer:
            integer = "0"
        if not decimal:
            decimal = "00"

    try:
        return sign * float(f"{integer}.{decimal}")
    except ValueError:
        return None


def _line_y(words: list[dict]) -> float:
    return min(float(word.get("y", 0)) for word in words)


def _line_x_center(words: list[dict]) -> float:
    xs = [float(word.get("x", 0)) + float(word.get("width", 0)) / 2 for word in words]
    return sum(xs) / len(xs)


def _visible_name(words: list[dict], image_width: float) -> str:
    left_words = list(words)
    left_words.sort(key=lambda word: float(word.get("y", 0)))
    ordered = []
    for word in left_words:
        y = float(word.get("y", 0))
        if ordered and abs(y - float(ordered[-1].get("y", 0))) <= 15:
            ordered.append(word)
        else:
            ordered.append(word)
    lines: list[list[dict]] = []
    for word in ordered:
        if not lines or abs(float(word.get("y", 0)) - float(lines[-1][-1].get("y", 0))) > 15:
            lines.append([word])
        else:
            lines[-1].append(word)
    return "".join(
        "".join(str(word.get("text", "")) for word in sorted(line, key=lambda item: float(item.get("x", 0))))
        for line in lines
    ).strip()


def match_code(name: str, mapping: dict[str, str]) -> str:
    result = resolve_fund_name(name, mapping)
    if result.status != "resolved":
        raise ValueError(result.reason or f"无法高可信匹配基金代码: {name}")
    return result.code


def _repair_amount(candidate: float, profit: float, rate_pct: float) -> float:
    """利用收益率修复 OCR 漏掉千位/小数位的金额。"""
    if abs(rate_pct) < 1e-9:
        return candidate
    expected = profit + profit / (rate_pct / 100.0)
    if abs(candidate - expected) <= max(2.0, abs(expected) * 0.03):
        return candidate
    if abs(expected) > 0 and abs(candidate) > abs(expected) * 0.25:
        return candidate

    best = candidate
    best_error = abs(candidate - expected)
    for power in range(-2, 5):
        for adjusted in (candidate * (10 ** power), candidate + (10 ** power), candidate - (10 ** power)):
            error = abs(adjusted - expected)
            if error < best_error:
                best, best_error = adjusted, error
    return best


def _compact_text(value: object) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(char for char in normalized if char.isalnum())


def _numeric_line_items(ocr: dict) -> list[dict]:
    items = []
    for line in ocr.get("lines") or []:
        words = line.get("words") or []
        value = parse_signed_number(words)
        if value is None:
            continue
        items.append({
            "words": words,
            "text": line.get("text", ""),
            "value": value,
            "y": _line_y(words),
            "x": _line_x_center(words),
            "has_sign": any(_is_sign(word.get("text", "")) for word in words),
        })
    return items


def detect_template(ocr: dict, image_width: float) -> dict:
    """根据页面标题、列标题和数字列位置识别两种持仓截图模板。"""
    full_text = _compact_text(
        " ".join(line.get("text", "") for line in ocr.get("lines") or [])
    )
    numeric_items = _numeric_line_items(ocr)
    all_score = 0
    my_score = 0
    evidence = []

    marker_scores = [
        ("全部持有", "all_holdings_4_columns", 5),
        ("名称金额", "all_holdings_4_columns", 2),
        ("累计收益", "all_holdings_4_columns", 3),
        ("我的持有", "my_holdings_3_columns", 5),
        ("金额昨日收益", "my_holdings_3_columns", 3),
        ("持有收益率", "my_holdings_3_columns", 3),
    ]
    for marker, template_id, score in marker_scores:
        if marker in full_text:
            evidence.append(f"文字标记:{marker}")
            if template_id == TEMPLATE_ALL_HOLDINGS:
                all_score += score
            else:
                my_score += score
    if "日收益" in full_text and "金额昨日收益" not in full_text:
        evidence.append("文字标记:日收益")
        all_score += 3

    middle_signed = any(
        item["has_sign"] and image_width * 0.28 <= item["x"] <= image_width * 0.56
        for item in numeric_items
    )
    middle_amount = any(
        not item["has_sign"]
        and item["value"] > 0
        and image_width * 0.45 <= item["x"] <= image_width * 0.73
        for item in numeric_items
    )
    holding_signed = any(
        item["has_sign"] and image_width * 0.55 <= item["x"] <= image_width * 0.80
        for item in numeric_items
    )
    far_right_signed = any(
        item["has_sign"] and image_width * 0.76 <= item["x"] <= image_width * 1.01
        for item in numeric_items
    )
    if middle_signed and far_right_signed:
        all_score += 2
        evidence.append("布局:中间日收益列+右侧累计收益列")
    elif middle_signed and holding_signed:
        all_score += 1
        evidence.append("布局:中间日收益列+右侧持有收益列")
    if middle_amount and far_right_signed and not middle_signed:
        my_score += 2
        evidence.append("布局:中列金额/昨日收益+右列持有收益/率")

    if all_score <= 0 and my_score <= 0:
        raise ValueError("未识别出支持的持仓截图模板")
    if all_score == my_score:
        raise ValueError("截图模板特征冲突，无法确定应使用哪套识别规则")

    template_id = TEMPLATE_ALL_HOLDINGS if all_score > my_score else TEMPLATE_MY_HOLDINGS
    confidence = round(max(all_score, my_score) / max(all_score + my_score, 1), 2)
    return {
        "id": template_id,
        "name": TEMPLATE_NAMES[template_id],
        "confidence": confidence,
        "evidence": evidence,
        "scores": {
            TEMPLATE_ALL_HOLDINGS: all_score,
            TEMPLATE_MY_HOLDINGS: my_score,
        },
    }


def _table_header_y(ocr: dict, template_id: str) -> float | None:
    markers_by_y: dict[float, set[str]] = {}
    markers = (
        ("名称金额", "日收益", "持有收益", "累计收益")
        if template_id == TEMPLATE_ALL_HOLDINGS
        else ("名称", "金额昨日收益", "持有收益率")
    )
    for line in ocr.get("lines") or []:
        words = line.get("words") or []
        if not words:
            continue
        text = _compact_text(line.get("text", ""))
        matched = {marker for marker in markers if marker in text}
        if not matched:
            continue
        y_key = round(_line_y(words) / 10) * 10
        markers_by_y.setdefault(y_key, set()).update(matched)
    if not markers_by_y:
        return None
    best_y, _ = max(
        markers_by_y.items(),
        key=lambda item: (len(item[1]), -item[0]),
    )
    return float(best_y)


def _has_reliable_decimal(words: list[dict]) -> bool:
    text = "".join(str(word.get("text", "")) for word in sorted(words, key=_word_sort_key))
    return bool(re.search(r"\d\s*[．.·。]\s*\d", text))


def _template_rules(template_id: str) -> dict:
    if template_id == TEMPLATE_ALL_HOLDINGS:
        return {
            "amount_x": (0.02, 0.30),
            "daily_x": (0.30, 0.55),
            "holding_x": (0.56, 0.79),
            "cumulative_x": (0.79, 1.01),
            "name_x": 1.01,
            "name_y": (-185.0, -12.0),
            "rate_y_offset": 65.0,
        }
    return {
        "amount_x": (0.45, 0.73),
        "daily_x": (0.45, 0.73),
        "holding_x": (0.76, 1.01),
        "cumulative_x": None,
        "name_x": 0.45,
        "name_y": (-115.0, 115.0),
        "rate_y_offset": 65.0,
    }


def _is_non_fund_asset(name: str) -> bool:
    normalized = _compact_text(name)
    return any(marker in normalized for marker in ("积存金", "黄金理财", "黄金活期", "存金宝"))


def _clean_row_name(name: str) -> str:
    cleaned = re.sub(r"占比.*$", "", str(name or ""))
    cleaned = cleaned.replace("（", "(").replace("）", ")")
    cleaned = QDII_OCR_RE.sub("QDII", cleaned)
    cleaned = re.sub(
        r"\(QDII([A-Ca-c])",
        lambda match: f"(QDII){match.group(1).upper()}",
        cleaned,
    )
    cleaned = IGNORED_NAME_SUFFIX_RE.sub("", cleaned)
    for _ in range(3):
        shortened = re.sub(r"(?:基金)?(?:进阶理财|稳健理财|灵活取用)?(?:定投|指数基金|数基金)$", "", cleaned)
        if shortened == cleaned:
            break
        cleaned = shortened
    if cleaned.endswith("(QDII"):
        cleaned += ")"
    return cleaned.strip(" |·．.")


def parse_ocr(
    ocr: dict,
    image_width: float,
    template: str | dict | None = None,
) -> list[dict]:
    if template is None:
        template_info = detect_template(ocr, image_width)
    elif isinstance(template, dict):
        template_info = template
    else:
        template_info = {
            "id": template,
            "name": TEMPLATE_NAMES.get(template, template),
            "confidence": 1.0,
            "evidence": ["调用方指定模板"],
        }
    template_id = template_info["id"]
    if template_id not in TEMPLATE_NAMES:
        raise ValueError(f"不支持的截图模板: {template_id}")

    rules = _template_rules(template_id)
    parsed_lines = _numeric_line_items(ocr)
    header_y = _table_header_y(ocr, template_id)
    positive_y = [item["y"] for item in parsed_lines if item["y"] > 0]
    fallback_top = min(positive_y) - 200 if positive_y else image_width * 0.25
    content_top = max(image_width * 0.25, (header_y + 45) if header_y is not None else fallback_top)
    content_lines = [item for item in parsed_lines if item["y"] >= content_top]
    if not content_lines:
        raise ValueError("没有识别到持仓数字")

    sorted_y = sorted({round(item["y"], 1) for item in content_lines})
    blocks: list[list[float]] = [[sorted_y[0]]]
    for value in sorted_y[1:]:
        if value - blocks[-1][-1] > 100:
            blocks.append([value])
        else:
            blocks[-1].append(value)

    def in_x(item: dict, bounds: tuple[float, float]) -> bool:
        low, high = bounds
        return low <= item["x"] / image_width <= high

    rows = []
    for block in blocks:
        y_min, y_max = min(block), max(block)
        block_lines = [
            item for item in content_lines
            if y_min - 1 <= item["y"] <= y_max + 1
        ]

        amount_candidates = [
            item for item in block_lines
            if not item["has_sign"] and item["value"] > 0 and in_x(item, rules["amount_x"])
        ]
        if not amount_candidates:
            continue
        amount_line = max(amount_candidates, key=lambda item: abs(item["value"]))

        daily_candidates = [
            item for item in block_lines
            if item["has_sign"] and in_x(item, rules["daily_x"])
        ]
        daily_line = (
            min(daily_candidates, key=lambda item: abs(item["y"] - amount_line["y"]))
            if daily_candidates else None
        )

        holding_candidates = [
            item for item in block_lines
            if item["has_sign"] and in_x(item, rules["holding_x"])
        ]
        if not holding_candidates:
            continue
        profit_line = min(holding_candidates, key=lambda item: abs(item["y"] - amount_line["y"]))
        rate_candidates = [item for item in holding_candidates if item is not profit_line]
        rate_line = (
            min(
                rate_candidates,
                key=lambda item: abs(item["y"] - (amount_line["y"] + rules["rate_y_offset"])),
            )
            if rate_candidates else None
        )

        cumulative_bounds = rules["cumulative_x"]
        cumulative_candidates = (
            [
                item for item in block_lines
                if item["has_sign"] and in_x(item, cumulative_bounds)
            ]
            if cumulative_bounds else []
        )
        cumulative_line = (
            min(cumulative_candidates, key=lambda item: abs(item["y"] - profit_line["y"]))
            if cumulative_candidates else None
        )

        name_y_min = y_min + rules["name_y"][0]
        name_y_max = amount_line["y"] + rules["name_y"][1]
        row_words = [
            word for word in ocr.get("words") or []
            if float(word.get("x", 0)) < image_width * rules["name_x"]
            and name_y_min <= float(word.get("y", 0)) <= name_y_max
        ]
        name = _clean_row_name(_visible_name(row_words, image_width))
        if not name:
            continue

        profit_ocr = profit_line["value"]
        cumulative_profit_ocr = cumulative_line["value"] if cumulative_line else None
        rate_ocr = rate_line["value"] if rate_line else None
        amount = (
            amount_line["value"]
            if _has_reliable_decimal(amount_line["words"])
            else _repair_amount(amount_line["value"], profit_ocr, rate_ocr or 0.0)
        )
        profit, repair_detail = select_profit_candidate(
            amount, profit_ocr, cumulative_profit_ocr, rate_ocr
        )
        calculated_rate = profit_rate_pct(amount, profit)
        rate = calculated_rate if calculated_rate is not None else (rate_ocr or 0.0)
        validation_issues, validation_detail = validate_snapshot_values(
            amount, profit, rate, rate_ocr
        )
        rate_only = bool(validation_issues) and all(
            issue["code"] in {"reported_rate_mismatch", "ocr_rate_mismatch"}
            for issue in validation_issues
        )
        profit_corroborated = (
            cumulative_profit_ocr is not None
            and abs(profit_ocr - cumulative_profit_ocr) <= 0.01
        )
        validation_status = (
            "warning"
            if rate_only and profit_corroborated
            else validation_detail["status"]
        )
        validation_detail["status"] = validation_status
        validation_detail["warnings"] = (
            validation_issues if validation_status == "warning" else []
        )
        rows.append({
            "template": template_id,
            "name": name,
            "market_value": round(amount, 2),
            "profit": round(profit, 2),
            "profit_pct": round(rate, 2),
            "daily_profit_ocr": round(daily_line["value"], 2) if daily_line else None,
            "ocr_profit": round(profit_ocr, 2),
            "cumulative_profit_ocr": (
                round(cumulative_profit_ocr, 2) if cumulative_profit_ocr is not None else None
            ),
            "ocr_rate": round(rate_ocr, 2) if rate_ocr is not None else None,
            "profit_repair": repair_detail,
            "validation_status": validation_detail["status"],
            "validation": validation_detail,
            "validation_errors": [] if validation_status == "warning" else validation_issues,
            "validation_warnings": validation_issues if validation_status == "warning" else [],
        })

    if not rows:
        raise ValueError("没有识别到完整的“持有金额 + 持有收益 + 持有收益率”行")
    return rows


def build_input(image_path: Path, ocr: dict) -> tuple[dict, list[dict]]:
    from PIL import Image
    with Image.open(image_path) as image:
        image_width = float(image.width)

    template_info = detect_template(ocr, image_width)
    parsed = parse_ocr(ocr, image_width, template=template_info)
    mapping = load_fund_names()
    rows = []
    skipped_rows = []
    pending_rows = []
    captured_at = datetime.fromtimestamp(image_path.stat().st_mtime).astimezone()
    for item in parsed:
        if _is_non_fund_asset(item["name"]):
            skipped_rows.append({
                "template": template_info["id"],
                "name": item["name"],
                "market_value": item["market_value"],
                "profit": item["profit"],
                "profit_pct": item["profit_pct"],
                "captured_at": captured_at.isoformat(timespec="seconds"),
                "source_image": str(image_path),
                "reason": "积存金/黄金等非基金资产，暂时忽略",
            })
            continue
        if item["name"] in {"名称/金额日收益", "名称/金额", "余额"}:
            skipped_rows.append({
                "name": item["name"],
                "market_value": item["market_value"],
                "profit": item["profit"],
                "profit_pct": item["profit_pct"],
                "ocr_rate": item.get("ocr_rate"),
                "validation_status": item.get("validation_status"),
                "validation": item.get("validation"),
                "validation_errors": item.get("validation_errors"),
                "captured_at": captured_at.isoformat(timespec="seconds"),
                "source_image": str(image_path),
                "reason": "页面表头或非基金资产",
            })
            continue
        try:
            result = resolve_fund_name(item["name"], mapping, lookup=search_fund_by_name)
        except Exception as exc:
            result = None
            lookup_error = f"{type(exc).__name__}: {exc}"
        else:
            lookup_error = ""

        if not result or result.status != "resolved":
            pending_rows.append({
                **item,
                "captured_at": captured_at.isoformat(timespec="seconds"),
                "source_image": str(image_path),
                "mapping_status": "pending",
                "reason": lookup_error or (result.reason if result else "基金名称解析失败"),
                "candidates": result.candidates if result else [],
            })
            continue

        if result.source == "eastmoney_fund_search":
            save_mapping_entry(
                FUND_MAPPING_CSV,
                code=result.code,
                standard_name=result.matched_name,
                ocr_alias=item["name"],
                method="online_api",
                source=result.source,
            )
            mapping[item["name"]] = result.code
        rows.append({
            "template": template_info["id"],
            "code": result.code,
            "name": result.matched_name or item["name"],
            "ocr_name": item["name"],
            "market_value": item["market_value"],
            "profit": item["profit"],
            "profit_pct": item["profit_pct"],
            "daily_profit_ocr": item.get("daily_profit_ocr"),
            "ocr_profit": item.get("ocr_profit"),
            "cumulative_profit_ocr": item.get("cumulative_profit_ocr"),
            "ocr_rate": item.get("ocr_rate"),
            "profit_repair": item.get("profit_repair"),
            "validation_status": item.get("validation_status"),
            "validation": item.get("validation"),
            "validation_errors": item.get("validation_errors"),
            "validation_warnings": item.get("validation_warnings"),
            "mapping_source": result.source,
            "mapping_score": result.score,
            "captured_at": captured_at.isoformat(timespec="seconds"),
            "source_image": str(image_path),
        })
    return {
        "captured_at": captured_at.isoformat(timespec="seconds"),
        "account": normalize_account_name(DEFAULT_ACCOUNT),
        "source_image": str(image_path),
        "source_images": [str(image_path)],
        "template": template_info["id"],
        "template_detection": template_info,
        "rows": rows,
        "skipped_rows": skipped_rows,
        "pending_mapping_rows": pending_rows,
    }, parsed


def _normalize_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(name)).casefold()
    return "".join(char for char in normalized if char.isalnum())


def _name_similarity(left: str, right: str) -> float:
    left_normalized = _normalize_name(left)
    right_normalized = _normalize_name(right)
    if not left_normalized or not right_normalized:
        return 0.0
    if left_normalized == right_normalized:
        return 1.0
    return difflib.SequenceMatcher(None, left_normalized, right_normalized).ratio()


def _amount_comparison(left: float, right: float) -> tuple[float, bool]:
    delta = abs(float(left) - float(right))
    tolerance = max(AMOUNT_ABS_TOLERANCE, max(abs(float(left)), abs(float(right))) * AMOUNT_REL_TOLERANCE)
    return round(delta, 4), delta <= tolerance


def _same_capture_day(left: dict, right: dict) -> bool:
    left_at = left.get("captured_at")
    right_at = right.get("captured_at")
    if not left_at or not right_at:
        return True
    return str(left_at)[:10] == str(right_at)[:10]


def _is_duplicate_candidate(left: dict, right: dict) -> bool:
    # 同一批次中的截图可能来自不同日期或文件复制时间，但仍是同一初次持仓快照。
    # 名称、代码和金额完全一致时跨日期去重；金额不一致仍保留并记录冲突。
    if left.get("account") != right.get("account"):
        return False
    left_code = str(left.get("code") or "").strip()
    right_code = str(right.get("code") or "").strip()
    code_match = bool(left_code) and left_code == right_code
    high_name_similarity = (
        _name_similarity(left.get("name", ""), right.get("name", ""))
        >= NAME_SIMILARITY_THRESHOLD
    )
    missing_code = not left_code or not right_code
    return code_match or (missing_code and high_name_similarity)


def compare_snapshot_rows(left: dict, right: dict) -> dict:
    name_similarity = round(_name_similarity(left.get("name", ""), right.get("name", "")), 4)
    left_code = str(left.get("code") or "").strip()
    right_code = str(right.get("code") or "").strip()
    if left_code and right_code:
        code_relation = "match" if left_code == right_code else "conflict"
    elif left_code or right_code:
        code_relation = "one_missing"
    else:
        code_relation = "both_missing"
    code_match = code_relation == "match"
    amount_delta, amount_match = _amount_comparison(
        float(left["market_value"]), float(right["market_value"])
    )

    if code_relation == "conflict":
        status = "kept_both_code_mismatch"
    elif code_match and name_similarity >= NAME_SIMILARITY_THRESHOLD and amount_match:
        status = "duplicate_removed"
    elif code_match and amount_match:
        status = "duplicate_removed_name_mismatch"
    elif code_match:
        status = "kept_both_amount_conflict"
    elif name_similarity >= NAME_SIMILARITY_THRESHOLD and amount_match:
        status = "duplicate_removed_missing_code"
    elif name_similarity >= NAME_SIMILARITY_THRESHOLD:
        status = "amount_conflict_removed_missing_code"
    else:
        status = "kept_both"

    return {
        "name_similarity": name_similarity,
        "code_match": code_match,
        "code_relation": code_relation,
        "same_capture_day": _same_capture_day(left, right),
        "amount_delta": amount_delta,
        "amount_match": amount_match,
        "status": status,
    }


def merge_snapshot_inputs(snapshots: list[dict]) -> tuple[dict, dict]:
    if not snapshots:
        captured_at = datetime.now().astimezone().isoformat(timespec="seconds")
        payload = {
            "captured_at": captured_at,
            "account": normalize_account_name(DEFAULT_ACCOUNT),
            "source_image": "",
            "source_images": [],
            "templates": [],
            "template_counts": {},
            "template_sources": [],
            "rows": [],
            "skipped_rows": [],
            "pending_mapping_rows": [],
        }
        report = {
            "template_counts": {},
            "template_sources": [],
            "input_row_count": 0,
            "output_row_count": 0,
            "duplicates_removed": 0,
            "removed_duplicates": [],
            "similar_but_kept": [],
            "skipped_unsupported_rows": [],
            "pending_mapping_rows": [],
            "manual_review_rows": [],
            "validation_warning_rows": [],
        }
        payload["comparison"] = {
            "input_row_count": 0,
            "output_row_count": 0,
            "duplicates_removed": 0,
        }
        return payload, report

    account = normalize_account_name(snapshots[0].get("account", DEFAULT_ACCOUNT))
    source_images = [str(path) for snapshot in snapshots for path in snapshot.get("source_images", [])]
    template_sources = [
        {
            "source_image": snapshot.get("source_image"),
            "template": snapshot.get("template"),
            "template_detection": snapshot.get("template_detection"),
            "captured_at": snapshot.get("captured_at"),
        }
        for snapshot in snapshots
    ]
    template_counts: dict[str, int] = {}
    for source in template_sources:
        template_id = str(source.get("template") or "unknown")
        template_counts[template_id] = template_counts.get(template_id, 0) + 1
    skipped_rows = [
        dict(item)
        for snapshot in snapshots
        for item in snapshot.get("skipped_rows", [])
    ]
    pending_mapping_rows = [
        dict(item)
        for snapshot in snapshots
        for item in snapshot.get("pending_mapping_rows", [])
    ]
    flattened = []
    for snapshot in snapshots:
        for row in snapshot.get("rows", []):
            item = dict(row)
            item.setdefault("account", snapshot.get("account", account))
            item.setdefault("captured_at", snapshot.get("captured_at"))
            item.setdefault("source_image", snapshot.get("source_image"))
            flattened.append(item)

    kept: list[dict] = []
    comparisons: list[dict] = []
    similar_but_kept: list[dict] = []
    for row in flattened:
        duplicate_index = None
        comparison = None
        evaluated = []
        for index, existing in enumerate(kept):
            duplicate_candidate = _is_duplicate_candidate(existing, row)
            high_name_similarity = (
                _name_similarity(existing.get("name", ""), row.get("name", ""))
                >= NAME_SIMILARITY_THRESHOLD
            )
            if not duplicate_candidate and not high_name_similarity:
                continue
            comparison = compare_snapshot_rows(existing, row)
            if comparison["status"] == "kept_both_amount_conflict":
                existing_at = str(existing.get("captured_at") or "")
                row_at = str(row.get("captured_at") or "")
                if row_at > existing_at:
                    comparison["status"] = "superseded_by_newer_snapshot"
            evaluated.append((existing, comparison))
            if duplicate_candidate and (
                comparison["status"].startswith("duplicate_removed")
                or comparison["status"] == "superseded_by_newer_snapshot"
            ):
                duplicate_index = index
                break
        if duplicate_index is None:
            kept.append(row)
            for existing, detail in evaluated:
                if detail["status"] != "duplicate_removed":
                    similar_but_kept.append({
                        "left": {
                            "code": existing.get("code"),
                            "name": existing.get("name"),
                            "market_value": existing.get("market_value"),
                            "source_image": existing.get("source_image"),
                        },
                        "right": {
                            "code": row.get("code"),
                            "name": row.get("name"),
                            "market_value": row.get("market_value"),
                            "source_image": row.get("source_image"),
                        },
                        "comparison": detail,
                    })
            continue

        existing = kept[duplicate_index]
        if comparison and comparison["status"] == "superseded_by_newer_snapshot":
            kept[duplicate_index] = dict(row)
        else:
            for field in ("code", "name", "market_value", "profit", "profit_pct"):
                if existing.get(field) in (None, "") and row.get(field) not in (None, ""):
                    existing[field] = row[field]
        comparisons.append({
            "kept": {
                "code": existing.get("code"),
                "name": existing.get("name"),
                "market_value": existing.get("market_value"),
                "source_image": existing.get("source_image"),
            },
            "removed": {
                "code": row.get("code"),
                "name": row.get("name"),
                "market_value": row.get("market_value"),
                "source_image": row.get("source_image"),
            },
            "comparison": comparison,
        })

    kept.sort(key=lambda item: (str(item.get("code") or ""), str(item.get("name") or "")))
    captured_values = [item.get("captured_at") for item in kept if item.get("captured_at")]
    captured_at = max(captured_values) if captured_values else datetime.now().astimezone().isoformat(timespec="seconds")
    output_rows = [
        {
            "template": item.get("template"),
            "code": item.get("code"),
            "name": item.get("name"),
            "ocr_name": item.get("ocr_name") or item.get("name"),
            "market_value": item.get("market_value"),
            "profit": item.get("profit"),
            "profit_pct": item.get("profit_pct"),
            "daily_profit_ocr": item.get("daily_profit_ocr"),
            "ocr_profit": item.get("ocr_profit"),
            "cumulative_profit_ocr": item.get("cumulative_profit_ocr"),
            "ocr_rate": item.get("ocr_rate"),
            "profit_repair": item.get("profit_repair"),
            "validation_status": item.get("validation_status"),
            "validation": item.get("validation"),
            "validation_errors": item.get("validation_errors"),
            "validation_warnings": item.get("validation_warnings"),
            "mapping_source": item.get("mapping_source"),
            "mapping_score": item.get("mapping_score"),
            "captured_at": item.get("captured_at"),
            "source_image": item.get("source_image"),
        }
        for item in kept
    ]
    payload = {
        "captured_at": captured_at,
        "account": account,
        "source_image": source_images[0] if source_images else "",
        "source_images": source_images,
        "templates": sorted(template_counts),
        "template_counts": template_counts,
        "template_sources": template_sources,
        "rows": output_rows,
        "skipped_rows": skipped_rows,
        "pending_mapping_rows": pending_mapping_rows,
    }
    comparison_report = {
        "template_counts": template_counts,
        "template_sources": template_sources,
        "rules": {
            "name_similarity_threshold": NAME_SIMILARITY_THRESHOLD,
            "amount_absolute_tolerance": AMOUNT_ABS_TOLERANCE,
            "amount_relative_tolerance": AMOUNT_REL_TOLERANCE,
            "rate_absolute_tolerance": RATE_ABS_TOLERANCE,
            "rate_relative_tolerance": RATE_REL_TOLERANCE,
            "different_non_empty_codes_are_kept_separately": True,
            "cross_date_exact_duplicates_are_removed": True,
        },
        "input_row_count": len(flattened),
        "output_row_count": len(output_rows),
        "duplicates_removed": len(flattened) - len(output_rows),
        "removed_duplicates": comparisons,
        "similar_but_kept": similar_but_kept,
        "skipped_unsupported_rows": skipped_rows,
        "pending_mapping_rows": pending_mapping_rows,
        "pending_mapping_count": len(pending_mapping_rows),
        "manual_review_rows": [
            {
                "code": item.get("code"),
                "name": item.get("name"),
                "validation_errors": item.get("validation_errors"),
                "source_image": item.get("source_image"),
            }
            for item in output_rows
            if item.get("validation_status") == "manual_review"
        ],
        "manual_review_count": sum(
            item.get("validation_status") == "manual_review" for item in output_rows
        ),
        "validation_warning_rows": [
            {
                "code": item.get("code"),
                "name": item.get("name"),
                "validation_warnings": item.get("validation_warnings"),
                "source_image": item.get("source_image"),
            }
            for item in output_rows
            if item.get("validation_status") == "warning"
        ],
        "validation_warning_count": sum(
            item.get("validation_status") == "warning" for item in output_rows
        ),
    }
    payload["comparison"] = {
        "input_row_count": comparison_report["input_row_count"],
        "output_row_count": comparison_report["output_row_count"],
        "duplicates_removed": comparison_report["duplicates_removed"],
    }
    return payload, comparison_report


def main() -> None:
    parser = argparse.ArgumentParser(description="本地识别持仓与交易截图并生成结构化数据")
    parser.add_argument("images", nargs="*", help="截图路径；可一次传入多张")
    parser.add_argument("--image", dest="option_images", nargs="+", action="append", default=[], help="截图路径；可重复使用")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--comparison-output", default=str(DEFAULT_COMPARISON_OUTPUT))
    parser.add_argument("--pending-output", default=str(DEFAULT_PENDING_OUTPUT))
    parser.add_argument("--confirmed-output", default=str(DEFAULT_CONFIRMED_OUTPUT))
    args = parser.parse_args()

    explicit = list(args.images)
    for group in args.option_images:
        explicit.extend(group)
    image_paths = find_images(explicit or None)

    snapshots = []
    transaction_rows = []
    document_records = []
    mapping = load_fund_names()
    for image_path in image_paths:
        ocr_path, ocr = run_windows_ocr(image_path)
        document_type = detect_transaction_screenshot(ocr)
        if document_type:
            parsed_transactions = parse_transaction_ocr(ocr, image_path, mapping)
            transaction_rows.extend(parsed_transactions)
            document_records.append({
                "image_path": image_path,
                "ocr_path": ocr_path,
                "document_type": document_type,
                "rows": parsed_transactions,
            })
            continue

        payload, parsed = build_input(image_path, ocr)
        snapshots.append(payload)
        document_records.append({
            "image_path": image_path,
            "ocr_path": ocr_path,
            "document_type": "holding_snapshot",
            "template": payload["template_detection"],
            "rows": parsed,
        })

    transaction_rows = merge_pending_rows(transaction_rows)
    pending_rows = [
        row for row in transaction_rows
        if any(marker in str(row.get("状态", "")) for marker in ("进行中", "处理中", "待确认"))
    ]
    confirmed_rows = confirmed_transaction_rows(transaction_rows)
    pending_output = Path(args.pending_output)
    confirmed_output = Path(args.confirmed_output)
    if pending_rows:
        write_pending_transactions(pending_output, pending_rows)
    else:
        print("未识别到交易进行中截图，保留已有待确认交易文件")
    if confirmed_rows:
        write_confirmed_transactions(confirmed_output, confirmed_rows)
    else:
        print("未识别到已确认后续交易")

    merged, comparison_report = merge_snapshot_inputs(snapshots)
    transaction_sources = [
        {
            "source_image": str(item["image_path"]),
            "document_type": item["document_type"],
            "row_count": len(item["rows"]),
        }
        for item in document_records
        if item["document_type"] != "holding_snapshot"
    ]
    document_counts = {
        "holding_snapshot": len(snapshots),
        "transaction_activity": len(transaction_sources),
        "pending_transaction_rows": len(pending_rows),
        "confirmed_transaction_rows": len(confirmed_rows),
    }
    merged["document_counts"] = document_counts
    merged["transaction_sources"] = transaction_sources
    comparison_report["document_counts"] = document_counts
    comparison_report["transaction_sources"] = transaction_sources

    output = Path(args.output)
    comparison_output = Path(args.comparison_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    comparison_output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    comparison_output.write_text(json.dumps(comparison_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"处理截图: {len(image_paths)} 张")
    for item in document_records:
        print(f"截图: {item['image_path']}")
        if item["document_type"] == "holding_snapshot":
            template_info = item["template"]
            print(f"识别类型: 持仓截图 | {template_info['name']} | 置信度={template_info['confidence']}")
        else:
            print(f"识别类型: 交易截图 | {item['document_type']} | {len(item['rows'])} 笔")
        print(f"OCR文件: {item['ocr_path']}")
        for row in item["rows"]:
            print(row)
    print(f"结构化持仓输入: {output}")
    if pending_rows:
        print(f"待确认交易: {pending_output} | {len(pending_rows)} 笔")
    if confirmed_rows:
        print(f"后续交易: {confirmed_output} | {len(confirmed_rows)} 笔")
    if comparison_report.get("skipped_unsupported_rows"):
        print(f"跳过不支持的资产: {len(comparison_report['skipped_unsupported_rows'])} 项")
        for item in comparison_report["skipped_unsupported_rows"]:
            print(f"跳过: {item['name']} | {item['reason']}")
    if comparison_report.get("pending_mapping_rows"):
        print(f"待确认基金映射: {len(comparison_report['pending_mapping_rows'])} 项")
        for item in comparison_report["pending_mapping_rows"]:
            print(f"待确认: {item['name']} | {item['reason']}")
    print(f"数据对比报告: {comparison_output}")
    print(
        f"对比结果: 输入 {comparison_report['input_row_count']} 项，"
        f"保留 {comparison_report['output_row_count']} 项，"
        f"移除重复 {comparison_report['duplicates_removed']} 项"
    )
    for item in comparison_report["removed_duplicates"]:
        detail = item["comparison"]
        print(
            f"去重: 保留={item['kept']['code']} {item['kept']['name']}，"
            f"移除={item['removed']['code']} {item['removed']['name']}，"
            f"名称相似度={detail['name_similarity']}，"
            f"金额差={detail['amount_delta']}，状态={detail['status']}"
        )
    for item in comparison_report["similar_but_kept"]:
        detail = item["comparison"]
        print(
            f"相似但保留: {item['left']['code']} {item['left']['name']} / "
            f"{item['right']['code']} {item['right']['name']}，"
            f"名称相似度={detail['name_similarity']}，状态={detail['status']}"
        )


if __name__ == "__main__":
    main()
