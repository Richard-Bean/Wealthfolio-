# -*- coding: utf-8 -*-

from ocr_to_snapshot import parse_signed_number


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
