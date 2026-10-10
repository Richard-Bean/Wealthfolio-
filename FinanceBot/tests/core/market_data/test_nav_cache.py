# -*- coding: utf-8 -*-

from datetime import date, datetime

from core.market_data.nav_cache import latest_nav_asof


CACHE = {
    "funds": {
        "013308": {
            "history": [
                {"date": "2026-10-08", "nav": 0.9699},
                {"date": "2026-10-09", "nav": 0.9973},
            ]
        }
    }
}


def test_before_settlement_uses_previous_nav():
    item = latest_nav_asof(CACHE, "013308", datetime.fromisoformat("2026-10-09 17:21:00"))
    assert item == {"date": "2026-10-08", "nav": 0.9699}


def test_after_settlement_uses_same_day_nav():
    item = latest_nav_asof(CACHE, "013308", datetime.fromisoformat("2026-10-09 21:00:00"))
    assert item == {"date": "2026-10-09", "nav": 0.9973}


def test_date_input_uses_same_day_nav():
    item = latest_nav_asof(CACHE, "013308", date.fromisoformat("2026-10-09"))
    assert item == {"date": "2026-10-09", "nav": 0.9973}
