# -*- coding: utf-8 -*-
"""Reconcile position snapshots without treating every snapshot as a buy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable


QUANTITY_TOLERANCE = 0.01
MONEY_TOLERANCE = 0.01


@dataclass(frozen=True)
class PositionSnapshot:
    snapshot_date: date
    symbol: str
    quantity: float
    cost_basis: float
    market_value: float
    name: str = ""


@dataclass(frozen=True)
class ReconciliationResult:
    transactions: list[dict]
    reviews: list[dict]
    status: str


def _source_id(prefix: str, account: str, previous: PositionSnapshot | None, current: PositionSnapshot) -> str:
    previous_date = previous.snapshot_date.isoformat() if previous else "initial"
    return (
        f"{prefix}:{account}:{current.symbol}:"
        f"{previous_date}->{current.snapshot_date.isoformat()}"
    )


def initial_buy_from_snapshot(snapshot: PositionSnapshot, account: str) -> dict:
    """Convert only the first observed position into a one-time baseline buy."""
    if snapshot.quantity <= QUANTITY_TOLERANCE:
        raise ValueError("snapshot quantity must be positive")
    if snapshot.cost_basis <= MONEY_TOLERANCE:
        raise ValueError("snapshot cost basis must be positive")

    source_id = _source_id("snapshot-initial", account, None, snapshot)
    return {
        "date": snapshot.snapshot_date.isoformat(),
        "account": account,
        "activityType": "buy",
        "symbol": snapshot.symbol,
        "isin": "",
        "quantity": round(snapshot.quantity, 2),
        "unitPrice": round(snapshot.cost_basis / snapshot.quantity, 4),
        "amount": round(snapshot.cost_basis, 2),
        "currency": "CNY",
        "fee": "",
        "tax": "",
        "comment": (
            f"INITIAL_SNAPSHOT | {snapshot.name} | "
            f"sourceTransactionId={source_id}"
        ),
    }


def reconcile_snapshot(
    previous: PositionSnapshot,
    current: PositionSnapshot,
    account: str,
) -> ReconciliationResult:
    """Compare a later snapshot with the last accepted snapshot.

    A later snapshot is never emitted as another full-position buy. Quantity
    increases can be inferred as one delta buy only when cost basis increases.
    Sales and ambiguous changes require an actual transaction statement because
    snapshots do not contain sale proceeds, fees, or realized gain.
    """
    if previous.symbol != current.symbol:
        raise ValueError("snapshots must refer to the same symbol")
    if current.snapshot_date < previous.snapshot_date:
        return ReconciliationResult(
            transactions=[],
            reviews=[{
                "code": "STALE_SNAPSHOT",
                "symbol": current.symbol,
                "previous_date": previous.snapshot_date.isoformat(),
                "current_date": current.snapshot_date.isoformat(),
            }],
            status="stale_snapshot",
        )

    quantity_delta = current.quantity - previous.quantity
    cost_delta = current.cost_basis - previous.cost_basis
    source_id = _source_id("snapshot-delta", account, previous, current)

    if abs(quantity_delta) <= QUANTITY_TOLERANCE:
        reviews = []
        if abs(cost_delta) > MONEY_TOLERANCE:
            reviews.append({
                "code": "COST_CHANGED_WITHOUT_QUANTITY_CHANGE",
                "symbol": current.symbol,
                "cost_delta": round(cost_delta, 2),
            })
        return ReconciliationResult([], reviews, "unchanged_quantity")

    if quantity_delta > 0 and cost_delta > MONEY_TOLERANCE:
        transaction = {
            "date": current.snapshot_date.isoformat(),
            "account": account,
            "activityType": "buy",
            "symbol": current.symbol,
            "isin": "",
            "quantity": round(quantity_delta, 2),
            "unitPrice": round(cost_delta / quantity_delta, 4),
            "amount": round(cost_delta, 2),
            "currency": "CNY",
            "fee": "",
            "tax": "",
            "comment": (
                f"INFERRED_SNAPSHOT_DELTA | {current.name} | "
                f"sourceTransactionId={source_id}"
            ),
        }
        return ReconciliationResult([transaction], [], "inferred_buy_delta")

    review_code = (
        "SELL_REQUIRES_TRANSACTION_SOURCE"
        if quantity_delta < 0
        else "BUY_COST_INCONSISTENT"
    )
    return ReconciliationResult(
        transactions=[],
        reviews=[{
            "code": review_code,
            "symbol": current.symbol,
            "quantity_delta": round(quantity_delta, 2),
            "cost_delta": round(cost_delta, 2),
            "sourceTransactionId": source_id,
        }],
        status="manual_review",
    )


def reconcile_known_transactions(
    baseline_quantity: float,
    transactions: Iterable[dict],
    observed_quantity: float,
) -> dict:
    """Check a later snapshot against baseline plus actual known transactions."""
    expected_delta = 0.0
    for transaction in transactions:
        activity = str(transaction.get("activityType", "")).lower()
        quantity = float(transaction.get("quantity") or 0.0)
        if activity in {"buy", "deposit", "transfer_in"}:
            expected_delta += quantity
        elif activity in {"sell", "withdrawal", "transfer_out"}:
            expected_delta -= quantity

    expected_quantity = baseline_quantity + expected_delta
    difference = observed_quantity - expected_quantity
    matched = abs(difference) <= QUANTITY_TOLERANCE
    return {
        "status": "matched" if matched else "quantity_mismatch",
        "baseline_quantity": baseline_quantity,
        "expected_quantity": expected_quantity,
        "observed_quantity": observed_quantity,
        "difference": difference,
    }
