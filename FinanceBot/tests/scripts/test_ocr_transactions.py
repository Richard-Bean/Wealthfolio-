# -*- coding: utf-8 -*-

import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_ROOT))

from ocr_transactions import (
    confirmed_transaction_rows,
    detect_transaction_screenshot,
    merge_pending_rows,
    normalize_fund_name,
    parse_transaction_ocr,
)


def line(text, x, y, width=120):
    return {
        "text": text,
        "words": [{
            "text": text,
            "x": x,
            "y": y,
            "width": width,
            "height": 36,
        }],
    }


def transaction_ocr():
    return {
        "lines": [
            line("收益明细 交易记录", 600, 160, 300),
            line("定投", 70, 500),
            line("基金丨测试基金", 180, 500, 320),
            line("(QDII)A", 180, 550),
            line("2026一10一13 12：09：46", 180, 620, 300),
            line("10．00元", 870, 510),
            line("交易进行中", 840, 560),
            line("定投", 70, 760),
            line("基金丨测试基金B", 180, 760, 320),
            line("2026一10一12 10：18：22", 180, 880, 300),
            line("5．00元", 890, 770),
            line("交易进行中", 840, 820),
        ]
    }


def test_detect_transaction_screenshot():
    assert detect_transaction_screenshot(transaction_ocr()) == "transaction_in_progress"
    holding = {"lines": [line("全部持有 收益明细 交易记录", 500, 160, 360), line("名称金额", 200, 300), line("持有收益", 800, 300)]}
    assert detect_transaction_screenshot(holding) is None


def test_normalize_qdii_ocr_variants():
    assert normalize_fund_name("基金丨测试混合（QD围A") == "测试混合(QDII)A"


def test_parse_transaction_rows_with_local_mapping_only():
    rows = parse_transaction_ocr(
        transaction_ocr(),
        "交易进行中.jpg",
        {"测试基金(QDII)A": "000001", "测试基金B": "000002"},
    )

    assert rows == [
        {
            "交易时间": "2026-10-12 10:18:22",
            "状态": "交易进行中",
            "交易类型": "buy",
            "基金代码": "000002",
            "基金名称": "测试基金B",
            "交易金额": "5.00",
            "币种": "CNY",
            "来源截图": "交易进行中.jpg",
        },
        {
            "交易时间": "2026-10-13 12:09:46",
            "状态": "交易进行中",
            "交易类型": "buy",
            "基金代码": "000001",
            "基金名称": "测试基金(QDII)A",
            "交易金额": "10.00",
            "币种": "CNY",
            "来源截图": "交易进行中.jpg",
        },
    ]


def test_completed_transaction_rows_are_marked_confirmed():
    ocr = transaction_ocr()
    ocr["lines"] = [item for item in ocr["lines"] if item["text"] != "交易进行中"]
    rows = parse_transaction_ocr(ocr, "交易记录.jpg", {"测试基金(QDII)A": "000001", "测试基金B": "000002"})

    assert all(row["状态"] == "已确认" for row in rows)
    confirmed = confirmed_transaction_rows(rows)
    assert len(confirmed) == 2
    assert confirmed[0]["交易类型"] == "买入"


def test_merge_pending_rows_removes_same_order_across_screenshots():
    first = {
        "交易时间": "2026-10-13 12:09:46",
        "状态": "交易进行中",
        "交易类型": "buy",
        "基金代码": "000001",
        "基金名称": "测试基金(QDII)A",
        "交易金额": "10.00",
        "币种": "CNY",
        "来源截图": "第一张.jpg",
    }
    second = {**first, "来源截图": "第二张.jpg"}

    assert merge_pending_rows([first, second]) == [first]
