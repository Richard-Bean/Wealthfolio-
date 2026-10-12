from datetime import date

from core.normalizer.snapshot_reconciler import (
    PositionSnapshot,
    initial_buy_from_snapshot,
    reconcile_known_transactions,
    reconcile_snapshot,
)


def snapshot(day, quantity, cost_basis, market_value, symbol="025208"):
    return PositionSnapshot(
        snapshot_date=date.fromisoformat(day),
        symbol=symbol,
        quantity=quantity,
        cost_basis=cost_basis,
        market_value=market_value,
        name="模拟基金",
    )


def test_first_snapshot_is_one_initial_buy():
    row = initial_buy_from_snapshot(snapshot("2026-10-01", 100, 900, 1000), "测试账户")

    assert row["activityType"] == "buy"
    assert row["quantity"] == 100
    assert row["amount"] == 900
    assert "INITIAL_SNAPSHOT" in row["comment"]
    assert "sourceTransactionId=" in row["comment"]


def test_market_value_change_without_trade_adds_no_transaction():
    result = reconcile_snapshot(
        snapshot("2026-10-01", 100, 900, 1000),
        snapshot("2026-10-08", 100, 900, 1080),
        "测试账户",
    )

    assert result.status == "unchanged_quantity"
    assert result.transactions == []


def test_same_baseline_import_has_stable_identity():
    first = initial_buy_from_snapshot(snapshot("2026-10-01", 100, 900, 1000), "测试账户")
    second = initial_buy_from_snapshot(snapshot("2026-10-01", 100, 900, 1000), "测试账户")

    assert first["comment"] == second["comment"]


def test_later_buy_is_one_delta_not_full_snapshot_buy():
    result = reconcile_snapshot(
        snapshot("2026-10-01", 100, 900, 1000),
        snapshot("2026-10-08", 150, 1400, 1650),
        "测试账户",
    )

    assert result.status == "inferred_buy_delta"
    assert len(result.transactions) == 1
    assert result.transactions[0]["quantity"] == 50
    assert result.transactions[0]["amount"] == 500
    assert result.transactions[0]["unitPrice"] == 10


def test_sale_is_not_fabricated_from_snapshot():
    result = reconcile_snapshot(
        snapshot("2026-10-01", 150, 1400, 1650),
        snapshot("2026-10-08", 100, 900, 1100),
        "测试账户",
    )

    assert result.transactions == []
    assert result.status == "manual_review"
    assert result.reviews[0]["code"] == "SELL_REQUIRES_TRANSACTION_SOURCE"


def test_actual_sell_statement_reconciles_without_snapshot_buy():
    result = reconcile_known_transactions(
        baseline_quantity=150,
        transactions=[{"activityType": "sell", "quantity": 50}],
        observed_quantity=100,
    )

    assert result["status"] == "matched"
    assert result["difference"] == 0


def test_quantity_gap_is_reported_before_statement_import():
    result = reconcile_known_transactions(
        baseline_quantity=150,
        transactions=[],
        observed_quantity=120,
    )

    assert result["status"] == "quantity_mismatch"
    assert result["difference"] == -30


def test_out_of_order_snapshot_is_stale_and_not_a_trade():
    result = reconcile_snapshot(
        snapshot("2026-10-08", 150, 1400, 1650),
        snapshot("2026-10-01", 100, 900, 1000),
        "测试账户",
    )

    assert result.status == "stale_snapshot"
    assert result.transactions == []
