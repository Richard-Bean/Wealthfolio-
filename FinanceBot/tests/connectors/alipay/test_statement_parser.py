# -*- coding: utf-8 -*-

from connectors.alipay.statement_parser import _infer_confirm_date, _to_date


def _row(confirm_date: str, order_no: str = "20260615001080012204270000519"):
    return [
        order_no, "2026/06/15 09:43", "定投买入", "易方达恒生科技ETF联接(QDII)A", "",
        "013308", "50.00", "/", "50.00", "43.96", "0.03", confirm_date,
    ]


def test_to_date_accepts_single_digit_day():
    assert _to_date("2026/06/1 00:00") == "2026-06-01"


def test_infer_confirm_date_recovers_truncated_t_plus_one():
    # PDF 中该单元格被裁切成 2026/06/1；订单号表明交易日为 06-15。
    assert _infer_confirm_date(_row("2026/06/1"), "定投买入", 50.0, 0.0) == "2026-06-16"


def test_infer_confirm_date_keeps_complete_date():
    assert _infer_confirm_date(_row("2026/06/16 00:00"), "定投买入", 50.0, 0.0) == "2026-06-16"
