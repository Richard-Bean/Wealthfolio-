# -*- coding: utf-8 -*-
"""
ocr_to_snapshot.py —— 持仓截图 OCR -> snapshot_input.json

设计目标：双击 BAT 后自动完成：
图片 -> Windows OCR JSON -> 持仓行解析 -> 本地净值 API -> snapshot_input.json

不上传截图。当前解析器面向支付宝/养基宝“我的持有”列表布局：
左列名称、中列金额/昨日收益、右列持有收益/率。
字段布局改变时，应增加新的布局适配规则。
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_IMAGE_DIR = PROJECT_ROOT / "data" / "raw" / "alipay"
DEFAULT_OCR_SCRIPT = PROJECT_ROOT / "scripts" / "ocr_snapshot.ps1"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "alipay" / "snapshot_input.auto.json"
FUND_MAP_CSV = PROJECT_ROOT / "data" / "processed" / "alipay" / "fund_positions.csv"


def find_image(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit).resolve()
        if not path.exists():
            raise FileNotFoundError(path)
        return path
    candidates = [
        path for path in DEFAULT_IMAGE_DIR.iterdir()
        if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"}
    ]
    if not candidates:
        raise FileNotFoundError(f"{DEFAULT_IMAGE_DIR} 下没有图片")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def run_windows_ocr(image_path: Path) -> tuple[Path, dict]:
    output_path = image_path.with_name(f"{image_path.stem}_ocr.txt")
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
    mapping: dict[str, str] = {}
    if FUND_MAP_CSV.exists():
        with FUND_MAP_CSV.open("r", encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                code = (row.get("基金代码") or row.get("symbol") or "").strip()
                name = (row.get("基金名称") or row.get("name") or "").strip()
                if code and name:
                    mapping[name] = code
    return mapping


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
    return None


def parse_signed_number(words: list[dict]) -> float | None:
    """从 OCR words 还原金额/收益/百分比。"""
    words = sorted(words, key=_word_sort_key)
    numeric = [word for word in words if _digits(word.get("text", ""))]
    if not numeric:
        return None

    first_numeric_x = float(numeric[0].get("x", 0))
    sign = 1.0
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
    left_words = [
        word for word in words
        if float(word.get("x", 0)) < image_width * 0.50
    ]
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
    if name in mapping:
        return mapping[name]
    cleaned = re.sub(r"基金|进阶理财|定投|金选|指数基金|灵活取用|CNY|占比|收益", "", name)
    for candidate, code in mapping.items():
        if candidate in name or candidate in cleaned or cleaned.startswith(candidate):
            return code
    best = difflib.get_close_matches(cleaned, mapping.keys(), n=1, cutoff=0.35)
    if not best:
        raise ValueError(f"无法把名称映射为基金代码: {name}")
    return mapping[best[0]]


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


def parse_ocr(ocr: dict, image_width: float) -> list[dict]:
    lines = ocr.get("lines") or []
    parsed_lines = []
    for line in lines:
        words = line.get("words") or []
        value = parse_signed_number(words)
        if value is None:
            continue
        has_sign = any(_is_sign(word.get("text", "")) for word in words)
        parsed_lines.append({
            "words": words,
            "value": value,
            "y": _line_y(words),
            "x": _line_x_center(words),
            "has_sign": has_sign,
        })

    content_lines = [
        item for item in parsed_lines
        if image_width * 0.25 < item["y"] < image_width * 2.0
    ]
    if not content_lines:
        raise ValueError("没有识别到持仓数字")

    # 每个持仓行通常有“金额/日收益/持有收益/率”两层 y 坐标。
    # 以垂直间隔聚类，避免依赖固定像素高度。
    sorted_y = sorted({round(item["y"], 1) for item in content_lines})
    blocks: list[list[float]] = [[sorted_y[0]]]
    for value in sorted_y[1:]:
        if value - blocks[-1][-1] > 100:
            blocks.append([value])
        else:
            blocks[-1].append(value)

    # “全部持有”布局有中间的日收益列；旧布局没有。
    has_middle_signed_column = any(
        item["has_sign"] and image_width * 0.30 <= item["x"] <= image_width * 0.55
        for item in content_lines
    )
    amount_max_x = image_width * (0.45 if has_middle_signed_column else 0.70)
    holding_min_x = image_width * (0.50 if has_middle_signed_column else 0.70)
    holding_max_x = image_width * (0.76 if has_middle_signed_column else 1.01)

    rows = []
    for block in blocks:
        y_min, y_max = min(block), max(block)
        block_lines = [item for item in content_lines if y_min - 1 <= item["y"] <= y_max + 1]

        amount_candidates = [
            item for item in block_lines
            if not item["has_sign"] and item["x"] < amount_max_x and item["value"] > 0
        ]
        if not amount_candidates:
            continue
        amount_line = max(amount_candidates, key=lambda item: abs(item["value"]))

        holding_candidates = [
            item for item in block_lines
            if holding_min_x <= item["x"] <= holding_max_x
        ]
        if not holding_candidates:
            continue

        profit_line = min(holding_candidates, key=lambda item: abs(item["y"] - amount_line["y"]))
        rate_candidates = [item for item in holding_candidates if item is not profit_line]
        rate_line = (
            min(rate_candidates, key=lambda item: abs(item["y"] - (amount_line["y"] + 65)))
            if rate_candidates else None
        )

        row_words = [
            word for word in ocr.get("words") or []
            if float(word.get("x", 0)) < image_width * 0.50
            and y_min - 140 <= float(word.get("y", 0)) <= amount_line["y"] - 10
        ]
        name = _visible_name(row_words, image_width)
        if not name:
            continue

        profit = profit_line["value"]
        rate_ocr = rate_line["value"] if rate_line else None
        amount = _repair_amount(amount_line["value"], profit, rate_ocr or 0.0)
        rate = profit / (amount - profit) * 100.0 if abs(amount - profit) > 1e-9 else (rate_ocr or 0.0)
        rows.append({
            "name": name,
            "market_value": round(amount, 2),
            "profit": round(profit, 2),
            "profit_pct": round(rate, 2),
            "ocr_rate": round(rate_ocr, 2) if rate_ocr is not None else None,
        })

    if not rows:
        raise ValueError("没有识别到完整的“持有金额 + 持有收益 + 持有收益率”行")
    return rows


def build_input(image_path: Path, ocr: dict) -> tuple[dict, list[dict]]:
    from PIL import Image
    with Image.open(image_path) as image:
        image_width = float(image.width)

    parsed = parse_ocr(ocr, image_width)
    mapping = load_fund_names()
    rows = []
    reverse_mapping = {code: name for name, code in mapping.items()}
    for item in parsed:
        code = match_code(item["name"], mapping)
        rows.append({
            "code": code,
            "name": reverse_mapping.get(code, item["name"]),
            "market_value": item["market_value"],
            "profit": item["profit"],
            "profit_pct": item["profit_pct"],
        })
    captured_at = datetime.fromtimestamp(image_path.stat().st_mtime).astimezone()
    return {
        "captured_at": captured_at.isoformat(timespec="seconds"),
        "account": "蚂蚁财富——测试B",
        "source_image": str(image_path),
        "rows": rows,
    }, parsed


def main() -> None:
    parser = argparse.ArgumentParser(description="把持仓截图 OCR 成结构化输入 JSON")
    parser.add_argument("--image", help="截图路径；默认自动选择 raw/alipay 下最新图片")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    image_path = find_image(args.image)
    ocr_path, ocr = run_windows_ocr(image_path)
    payload, parsed = build_input(image_path, ocr)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"截图: {image_path}")
    print(f"OCR文件: {ocr_path}")
    print(f"结构化输入: {output}")
    for item in parsed:
        print(item)


if __name__ == "__main__":
    main()
