# -*- coding: utf-8 -*-

import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_ROOT))

from ocr_to_snapshot import (
    compare_snapshot_rows,
    find_images,
    merge_snapshot_inputs,
    parse_signed_number,
)


def word(text, x, y=0):
    return {"text": text, "x": x, "y": y, "width": 10, "height": 10}


def test_parse_amount_with_thousands_separator():
    words = [word("2", 0), word("，", 10), word("751", 20), word("．", 30), word("83", 40)]
    assert parse_signed_number(words) == 2751.83


def test_parse_negative_profit():
    words = [word("一", 0), word("114", 10), word("．", 20), word("10", 30)]
    assert parse_signed_number(words) == -114.10


def test_parse_positive_rate():
    words = [word("+", 0), word("9", 10), word("．", 20), word("83", 30)]
    assert parse_signed_number(words) == 9.83


def snapshot_row(code, name, market_value, source_image="a.jpg"):
    return {
        "code": code,
        "name": name,
        "market_value": market_value,
        "profit": -10.0,
        "profit_pct": -1.0,
        "captured_at": "2026-10-10T12:00:00+08:00",
        "source_image": source_image,
    }


def snapshot(*rows):
    return {
        "captured_at": "2026-10-10T12:00:00+08:00",
        "account": "测试账户",
        "source_images": [row["source_image"] for row in rows],
        "rows": list(rows),
    }


def test_find_images_accepts_multiple_explicit_paths():
    base = Path(__file__).resolve().parent
    first = base / "_find_images_01.png"
    second = base / "_find_images_02.jpg"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    try:
        assert find_images([str(first), str(second)]) == [first, second]
    finally:
        first.unlink(missing_ok=True)
        second.unlink(missing_ok=True)


def test_merge_removes_same_code_name_and_amount_duplicate():
    first = snapshot_row("017125", "华宝港股互联网ETF联接A", 1079.29, "01.jpg")
    second = snapshot_row("017125", "华宝港股互联网ETF联接A", 1079.30, "02.jpg")

    merged, report = merge_snapshot_inputs([snapshot(first), snapshot(second)])

    assert len(merged["rows"]) == 1
    assert report["duplicates_removed"] == 1
    assert report["removed_duplicates"][0]["comparison"]["status"] == "duplicate_removed"


def test_similar_names_with_different_codes_are_kept():
    first = snapshot_row("017125", "华宝港股互联网ETF联接A", 1079.29, "01.jpg")
    second = snapshot_row("017126", "华宝港股互联网ETF联接C", 1079.29, "02.jpg")

    merged, report = merge_snapshot_inputs([snapshot(first), snapshot(second)])

    assert len(merged["rows"]) == 2
    assert report["duplicates_removed"] == 0
    assert report["similar_but_kept"][0]["comparison"]["code_match"] is False
    assert report["similar_but_kept"][0]["comparison"]["status"] == "kept_both_code_mismatch"


def test_same_code_with_amount_conflict_keeps_only_one_and_reports_conflict():
    first = snapshot_row("017125", "华宝港股互联网ETF联接A", 1079.29, "01.jpg")
    second = snapshot_row("017125", "华宝港股互联网ETF联接A", 1200.00, "02.jpg")

    merged, report = merge_snapshot_inputs([snapshot(first), snapshot(second)])

    assert len(merged["rows"]) == 1
    assert report["removed_duplicates"][0]["comparison"]["amount_match"] is False
    assert report["removed_duplicates"][0]["comparison"]["status"] == "amount_conflict_removed"


def test_full_comparison_covers_name_code_and_amount():
    left = snapshot_row("017125", "华宝港股互联网ETF联接A", 1079.29)
    right = snapshot_row("017125", "华宝港股互联网ETF联接A", 1079.29)

    detail = compare_snapshot_rows(left, right)

    assert detail["name_similarity"] == 1.0
    assert detail["code_match"] is True
    assert detail["amount_match"] is True

def test_missing_code_high_similarity_row_is_merged_and_code_is_backfilled():
    first = snapshot_row("", "华宝港股互联网ETF联接A", 1079.29, "01.jpg")
    second = snapshot_row("017125", "华宝港股互联网ETF联接A", 1079.29, "02.jpg")

    merged, report = merge_snapshot_inputs([snapshot(first), snapshot(second)])

    assert len(merged["rows"]) == 1
    assert merged["rows"][0]["code"] == "017125"
    assert report["removed_duplicates"][0]["comparison"]["status"] == "duplicate_removed_missing_code"
