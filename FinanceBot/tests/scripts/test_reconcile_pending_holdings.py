# -*- coding: utf-8 -*-

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from pathlib import Path
import sys

SCRIPTS_ROOT = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_ROOT))

from reconcile_pending_holdings import (
    FINAL_CONFIRMED_HEADERS,
    build_reconciliation,
    load_pending,
    nav_for_trade,
    scheduled_nav_date,
    validate_reference,
    write_csv,
)

CN_TZ = timezone(timedelta(hours=8))


def test_pending_after_snapshot_is_not_subtracted():
    captured_at = datetime(2026, 10, 12, 22, 45, 55, tzinfo=CN_TZ)
    snapshot_rows = {
        "008253": {
            "code": "008253",
            "name": "华宝致远混合(QDII)A",
            "market_value": 939.36,
            "profit": -0.64,
        }
    }
    holdings = {
        "008253": {
            "symbol": "008253",
            "fund_name": "华宝致远混合(QDII)A",
            "quantity": "529.22",
            "unitPrice": "1.7762",
            "amount": "940.00",
        }
    }
    pending = [
        {
            "symbol": "008253",
            "fund_name": "华宝致远混合(QDII)A",
            "trade_time": "2026-10-12 11:01:10",
            "_trade_at": datetime(2026, 10, 12, 11, 1, 10, tzinfo=CN_TZ),
            "_amount": Decimal("10.00"),
        },
        {
            "symbol": "008253",
            "fund_name": "华宝致远混合(QDII)A",
            "trade_time": "2026-10-13 10:51:31",
            "_trade_at": datetime(2026, 10, 13, 10, 51, 31, tzinfo=CN_TZ),
            "_amount": Decimal("10.00"),
        },
    ]
    nav_funds = {
        "008253": {
            "name": "华宝致远混合(QDII)A",
            "latest_date": "2026-10-13",
            "latest_nav": 1.775,
            "history": [
                {"date": "2026-10-09", "nav": 1.775},
                {"date": "2026-10-12", "nav": 1.775},
                {"date": "2026-10-13", "nav": 1.775},
            ],
        }
    }

    confirmed, estimated = build_reconciliation(
        captured_at, snapshot_rows, holdings, pending, nav_funds
    )
    row = confirmed[0]

    assert row["pending_at_snapshot_amount"] == "10.00"
    assert row["current_pending_amount"] == "20.00"
    assert row["confirmed_quantity"] == "523.58"
    assert row["confirmed_cost_basis"] == "930.00"
    assert estimated[0]["estimated_pending_quantity"] == "11.27"
    assert estimated[0]["projected_quantity"] == "534.85"
    assert estimated[0]["share_calculation_status"] == "已按交易时间对应净值全部估算"


def test_validation_matches_asset_detail_within_display_rounding():
    confirmed = [
        {
            "symbol": "008253",
            "confirmed_market_value": "929.36",
            "confirmed_quantity": "523.58",
            "confirmed_unit_cost": "1.7762",
            "pending_at_snapshot_amount": "10.00",
            "latest_nav": "1.775",
            "nav_date": "2026-10-09",
        }
    ]

    result = validate_reference(confirmed)

    assert result["status"] == "pass_with_display_rounding_tolerance"
    assert all(item["passed"] for item in result["checks"].values())





def test_csv_output_uses_chinese_headers():
    path = Path(__file__).with_name("临时对账输出表.csv")
    try:
        write_csv(
            path,
            [{"symbol": "008253", "confirmed_quantity": "523.58"}],
            ["symbol", "confirmed_quantity"],
            {"symbol": "基金代码", "confirmed_quantity": "确认持有份额"},
        )

        lines = path.read_text(encoding="utf-8-sig").splitlines()

        assert lines[0] == "基金代码,确认持有份额"
        assert lines[1] == "008253,523.58"
    finally:
        path.unlink(missing_ok=True)


def test_pending_input_accepts_chinese_headers():
    path = Path(__file__).with_name("临时待确认输入表.csv")
    try:
        path.write_text(
            "交易时间,状态,交易类型,基金代码,基金名称,交易金额,币种,来源截图\n"
            "2026-10-13 10:51:31,交易进行中,buy,008253,华宝致远混合(QDII)A,10.00,CNY,test.jpg\n",
            encoding="utf-8-sig",
        )

        rows = load_pending(path)

        assert rows[0]["symbol"] == "008253"
        assert str(rows[0]["_amount"]) == "10.00"
    finally:
        path.unlink(missing_ok=True)



def test_pending_nav_uses_trade_cutoff_time():
    fund_nav = {
        "history": [
            {"date": "2026-10-12", "nav": 1.77},
            {"date": "2026-10-13", "nav": 1.78},
        ]
    }

    before_cutoff = datetime(2026, 10, 12, 14, 59, tzinfo=CN_TZ)
    after_cutoff = datetime(2026, 10, 12, 15, 0, tzinfo=CN_TZ)

    assert scheduled_nav_date(before_cutoff).isoformat() == "2026-10-12"
    assert scheduled_nav_date(after_cutoff).isoformat() == "2026-10-13"
    assert nav_for_trade(fund_nav, before_cutoff)["nav"] == 1.77
    assert nav_for_trade(fund_nav, after_cutoff)["nav"] == 1.78


def test_pending_shares_are_blank_when_applicable_nav_is_not_published():
    captured_at = datetime(2026, 10, 13, 15, 14, tzinfo=CN_TZ)
    pending = [
        {
            "symbol": "008253",
            "fund_name": "华宝致远混合(QDII)A",
            "trade_time": "2026-10-13 10:51:31",
            "_trade_at": datetime(2026, 10, 13, 10, 51, 31, tzinfo=CN_TZ),
            "_amount": Decimal("10.00"),
        }
    ]
    nav_funds = {
        "008253": {
            "name": "华宝致远混合(QDII)A",
            "latest_date": "2026-10-09",
            "latest_nav": 1.775,
            "history": [{"date": "2026-10-09", "nav": 1.775}],
        }
    }

    confirmed, estimated = build_reconciliation(
        captured_at, {}, {}, pending, nav_funds
    )
    row = estimated[0]

    assert confirmed[0]["current_pending_amount"] == "10.00"
    assert row["estimated_pending_quantity"] == ""
    assert row["projected_quantity"] == ""
    assert row["projected_unit_cost"] == ""
    assert row["pending_nav_missing_amount"] == "10.00"
    assert row["share_calculation_status"] == "全部待净值，交易进行中份额已搁置"



def test_final_confirmed_table_has_only_confirmed_fields():
    assert list(FINAL_CONFIRMED_HEADERS.values()) == [
        "基金代码",
        "基金名称",
        "确定持仓金额",
        "确定持有份额",
        "确定持仓成本",
        "确定每股持仓成本",
    ]
    assert not any("快照" in name for name in FINAL_CONFIRMED_HEADERS.values())
