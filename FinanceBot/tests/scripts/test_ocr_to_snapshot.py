# -*- coding: utf-8 -*-

import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_ROOT))

from ocr_to_snapshot import (
    _clean_row_name,
    DEFAULT_ACCOUNT,
    TEMPLATE_ALL_HOLDINGS,
    TEMPLATE_MY_HOLDINGS,
    detect_template,
    compare_snapshot_rows,
    find_images,
    merge_snapshot_inputs,
    normalize_account_name,
    parse_ocr,
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


def test_same_code_with_amount_conflict_keeps_both_and_reports_conflict():
    first = snapshot_row("017125", "华宝港股互联网ETF联接A", 1079.29, "01.jpg")
    second = snapshot_row("017125", "华宝港股互联网ETF联接A", 1200.00, "02.jpg")

    merged, report = merge_snapshot_inputs([snapshot(first), snapshot(second)])

    assert len(merged["rows"]) == 2
    assert report["duplicates_removed"] == 0
    assert report["similar_but_kept"][0]["comparison"]["amount_match"] is False
    assert report["similar_but_kept"][0]["comparison"]["status"] == "kept_both_amount_conflict"


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


def test_legacy_account_name_is_replaced_with_antfortune():
    assert DEFAULT_ACCOUNT == "蚂蚁财富"
    assert normalize_account_name("蚂蚁财富——测试B") == "蚂蚁财富"
    assert normalize_account_name("其他账户") == "其他账户"


def line(words):
    return {"text": "".join(item["text"] for item in words), "words": words}


def screenshot_ocr(include_cumulative=True):
    name_words = [word("南方纳斯达克100指数A", 60, 900)]
    amount_words = [
        word("611", 70, 1000),
        word("．", 120, 1000),
        word("80", 140, 1000),
    ]
    daily_words = [
        word("+", 400, 1000),
        word("2.50", 420, 1000),
    ]
    holding_words = [
        word("+", 654, 1000),
        word("1", 677, 1000),
        word("t80", 698, 1000),
    ]
    rate_words = [
        word("+", 658, 1060),
        word("2", 676, 1060),
        word("．", 695, 1060),
        word("03", 703, 1060),
        word("％", 740, 1060),
    ]
    cumulative_words = [
        word("+", 899, 1000),
        word("1", 922, 1000),
        word("1", 943, 1000),
        word("·", 960, 1000),
        word("80", 970, 1000),
    ]

    words = name_words + amount_words + daily_words + holding_words + rate_words
    numeric_lines = [amount_words, daily_words, holding_words, rate_words]
    if include_cumulative:
        words += cumulative_words
        numeric_lines.append(cumulative_words)

    return {
        "words": words,
        "lines": [line(items) for items in numeric_lines],
    }


def test_parse_ocr_repairs_profit_from_cumulative_column():
    rows = parse_ocr(screenshot_ocr(include_cumulative=True), image_width=1080)

    assert len(rows) == 1
    assert rows[0]["market_value"] == 611.80
    assert rows[0]["ocr_profit"] == 1.80
    assert rows[0]["cumulative_profit_ocr"] == 11.80
    assert rows[0]["profit"] == 11.80
    assert rows[0]["profit_repair"]["repaired"] is True
    assert rows[0]["validation_status"] == "ok"


def test_parse_ocr_flags_rate_mismatch_without_repair_source():
    rows = parse_ocr(screenshot_ocr(include_cumulative=False), image_width=1080)

    assert rows[0]["profit"] == 1.80
    assert rows[0]["validation_status"] == "manual_review"
    assert any(
        issue["code"] == "ocr_rate_mismatch"
        for issue in rows[0]["validation_errors"]
    )



def template_header(text, y):
    return line([word(part, 0, y) for part in [text]])


def test_detect_template_uses_page_and_column_markers():
    all_holdings = {"lines": [template_header("全部持有 名称/金额 日收益 持有收益 累计收益", 400)]}
    my_holdings = {"lines": [template_header("我的持有 名称 金额/昨日收益 持有收益/率", 700)]}

    assert detect_template(all_holdings, 1080)["id"] == TEMPLATE_ALL_HOLDINGS
    assert detect_template(my_holdings, 1080)["id"] == TEMPLATE_MY_HOLDINGS


def test_all_holdings_template_ignores_status_badges_and_page_edges():
    ocr = {
        "lines": [
            template_header("全部持有 名称/金额 日收益 持有收益 累计收益", 400),
            line([word("13:30", 50, 40)]),
            line([word("2,637.01", 70, 663)]),
            line([word("占比12.67%", 70, 715)]),
            line([word("-93.87", 410, 663)]),
            line([word("-428.10", 650, 663)]),
            line([word("-13.97%", 650, 717)]),
            line([word("-428.10", 900, 663)]),
        ],
        "words": [
            word("13:30", 50, 40),
            word("永赢先锋半导体智选混合A", 60, 531),
            word("基金", 70, 594),
            word("进阶理财", 150, 594),
            word("2,637.01", 70, 663),
            word("占比12.67%", 70, 715),
            word("-93.87", 410, 663),
            word("-428.10", 650, 663),
            word("-13.97%", 650, 717),
            word("-428.10", 900, 663),
        ],
    }

    rows = parse_ocr(ocr, image_width=1080)

    assert len(rows) == 1
    assert rows[0]["template"] == TEMPLATE_ALL_HOLDINGS
    assert rows[0]["name"] == "永赢先锋半导体智选混合A"
    assert rows[0]["market_value"] == 2637.01
    assert rows[0]["cumulative_profit_ocr"] == -428.10


def test_my_holdings_template_uses_combined_columns_and_ignores_page_edges():
    ocr = {
        "lines": [
            template_header("我的持有 名称 金额/昨日收益 持有收益/率", 750),
            line([word("19", 500, 300)]),
            line([word("2,637.01", 520, 900)]),
            line([word("-93.87", 520, 966)]),
            line([word("-428.10", 860, 900)]),
            line([word("-13.97%", 860, 966)]),
            line([word("59", 950, 2300)]),
        ],
        "words": [
            word("19", 500, 300),
            word("永赢先锋半导体智选混合A", 60, 900),
            word("2,637.01", 520, 900),
            word("-93.87", 520, 966),
            word("-428.10", 860, 900),
            word("-13.97%", 860, 966),
            word("59", 950, 2300),
        ],
    }

    rows = parse_ocr(ocr, image_width=1080)

    assert len(rows) == 1
    assert rows[0]["template"] == TEMPLATE_MY_HOLDINGS
    assert rows[0]["name"] == "永赢先锋半导体智选混合A"
    assert rows[0]["market_value"] == 2637.01
    assert rows[0]["daily_profit_ocr"] == -93.87
    assert rows[0]["cumulative_profit_ocr"] is None



def test_same_code_and_amount_duplicate_across_capture_days_is_removed():
    first = snapshot_row("017125", "华宝港股互联网ETF联接A", 1079.29, "20261012.jpg")
    first["captured_at"] = "2026-10-12T22:45:55+08:00"
    second = snapshot_row("017125", "华宝港股互联网ETF联接A", 1079.29, "20261013.jpg")
    second["captured_at"] = "2026-10-13T13:36:24+08:00"

    merged, report = merge_snapshot_inputs([snapshot(first), snapshot(second)])

    assert len(merged["rows"]) == 1
    assert report["duplicates_removed"] == 1
    assert report["removed_duplicates"][0]["comparison"]["same_capture_day"] is False
    assert report["removed_duplicates"][0]["comparison"]["status"] == "duplicate_removed"



def test_clean_row_name_replaces_qdii_ocr_variants():
    assert _clean_row_name("华宝致远混合（QD围A基金进阶理财定投") == "华宝致远混合(QDII)A"
    assert _clean_row_name("银华海外数字经济量化选股混合（QDΧc") == "银华海外数字经济量化选股混合(QDII)C"
    assert _clean_row_name("国泰纳斯达克100指数(QD围") == "国泰纳斯达克100指数(QDII)"


def test_merge_keeps_one_latest_snapshot_per_fund_code():
    left = {
        "account": "蚂蚁财富",
        "code": "008253",
        "name": "华宝致远混合(QDII)A",
        "market_value": 939.36,
        "profit": -0.64,
        "profit_pct": -0.07,
        "captured_at": "2026-10-12T22:45:55+08:00",
    }
    right = {
        **left,
        "market_value": 949.34,
        "profit": -0.66,
        "captured_at": "2026-10-13T13:36:24+08:00",
    }

    merged, comparison = merge_snapshot_inputs([
        {"account": "蚂蚁财富", "rows": [left], "source_images": ["left.jpg"]},
        {"account": "蚂蚁财富", "rows": [right], "source_images": ["right.jpg"]},
    ])

    assert len(merged["rows"]) == 1
    assert merged["rows"][0]["market_value"] == 949.34
    assert comparison["removed_duplicates"][0]["comparison"]["status"] == "superseded_by_newer_snapshot"
