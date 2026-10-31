"""Hand-checked functional tests shared by both SalesLens engines."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from saleslens import baseline, optimized
from tests.conftest import write_csv

ENGINES = [baseline, optimized]


@pytest.mark.correctness
@pytest.mark.parametrize("engine", ENGINES, ids=["baseline", "optimized"])
def test_hand_checked_metrics(engine, hand_checked_dataset: Path) -> None:
    result = engine.analyze_directory(hand_checked_dataset)

    assert result == {
        "rows_read": 8,
        "valid_rows": 5,
        "invalid_rows": 3,
        "order_count": 4,
        "customer_count": 2,
        "total_units": 9,
        "gross_revenue": 750.0,
        "discount_amount": 70.0,
        "net_revenue": 680.0,
        "average_order_value": 170.0,
        "monthly_revenue": {"2025-01": 230.0, "2025-02": 350.0, "2025-03": 100.0},
        "revenue_by_category": {"Category A": 430.0, "Category B": 250.0},
        "category_shares": {"Category A": 0.6324, "Category B": 0.3676},
        "revenue_by_region": {"North": 300.0, "West": 380.0},
        "top_products": [
            {"product_id": "P1", "product_name": "Alpha", "units": 3, "revenue": 280.0},
            {"product_id": "P2", "product_name": "Beta", "units": 5, "revenue": 250.0},
            {"product_id": "P3", "product_name": "Gamma", "units": 1, "revenue": 150.0},
        ],
        "top_customers": [
            {"customer_id": "C1", "customer_name": "Asha Rao", "orders": 2, "revenue": 380.0},
            {"customer_id": "C2", "customer_name": "Ravi Shah", "orders": 2, "revenue": 300.0},
        ],
        "repeat_customer_count": 2,
        "repeat_customer_rate": 1.0,
        "high_value_customer_count": 0,
        "duplicate_transaction_ids": 1,
        "duplicate_transaction_rows": 1,
        "top_co_purchase_pairs": [
            {"product_a": "P1", "product_b": "P2", "count": 1}
        ],
        "best_month": "2025-02",
    }


@pytest.mark.correctness
@pytest.mark.parametrize("engine", ENGINES, ids=["baseline", "optimized"])
def test_empty_transactions(engine, tmp_path: Path) -> None:
    write_csv(tmp_path / "products.csv", ["product_id", "product_name", "category", "unit_price"], [])
    write_csv(tmp_path / "customers.csv", ["customer_id", "customer_name", "region"], [])
    write_csv(
        tmp_path / "transactions.csv",
        ["transaction_id", "order_id", "timestamp", "customer_id", "product_id", "quantity", "discount_percent"],
        [],
    )

    result = engine.analyze_directory(tmp_path)
    assert result["rows_read"] == 0
    assert result["valid_rows"] == 0
    assert result["net_revenue"] == 0.0
    assert result["average_order_value"] == 0.0
    assert result["best_month"] is None
    assert result["top_products"] == []


@pytest.mark.correctness
@pytest.mark.parametrize("engine", ENGINES, ids=["baseline", "optimized"])
def test_repeated_product_in_one_order_counts_pair_once(engine, tmp_path: Path) -> None:
    write_csv(
        tmp_path / "products.csv",
        ["product_id", "product_name", "category", "unit_price"],
        [["P1", "Alpha", "A", "10"], ["P2", "Beta", "B", "20"]],
    )
    write_csv(
        tmp_path / "customers.csv",
        ["customer_id", "customer_name", "region"],
        [["C1", "Asha Rao", "West"]],
    )
    write_csv(
        tmp_path / "transactions.csv",
        ["transaction_id", "order_id", "timestamp", "customer_id", "product_id", "quantity", "discount_percent"],
        [
            ["T1", "O1", "2025-01-01T10:00:00", "C1", "P1", 1, 0],
            ["T2", "O1", "2025-01-01T10:00:00", "C1", "P1", 2, 0],
            ["T3", "O1", "2025-01-01T10:00:00", "C1", "P2", 1, 0],
        ],
    )

    result = engine.analyze_directory(tmp_path)
    assert result["top_co_purchase_pairs"] == [
        {"product_a": "P1", "product_b": "P2", "count": 1}
    ]


@pytest.mark.correctness
@pytest.mark.parametrize("engine", ENGINES, ids=["baseline", "optimized"])
def test_top_ranking_ties_use_id_order(engine, tmp_path: Path) -> None:
    write_csv(
        tmp_path / "products.csv",
        ["product_id", "product_name", "category", "unit_price"],
        [["P2", "Beta", "B", "100"], ["P1", "Alpha", "A", "100"]],
    )
    write_csv(
        tmp_path / "customers.csv",
        ["customer_id", "customer_name", "region"],
        [["C2", "Ravi Shah", "North"], ["C1", "Asha Rao", "West"]],
    )
    write_csv(
        tmp_path / "transactions.csv",
        ["transaction_id", "order_id", "timestamp", "customer_id", "product_id", "quantity", "discount_percent"],
        [
            ["T1", "O1", "2025-01-01T10:00:00", "C2", "P2", 1, 0],
            ["T2", "O2", "2025-01-02T10:00:00", "C1", "P1", 1, 0],
        ],
    )

    result = engine.analyze_directory(tmp_path)
    assert [row["product_id"] for row in result["top_products"]] == ["P1", "P2"]
    assert [row["customer_id"] for row in result["top_customers"]] == ["C1", "C2"]


@pytest.mark.correctness
@pytest.mark.parametrize("engine", ENGINES, ids=["baseline", "optimized"])
def test_first_duplicate_master_record_wins(engine, tmp_path: Path) -> None:
    write_csv(
        tmp_path / "products.csv",
        ["product_id", "product_name", "category", "unit_price"],
        [["P1", "First", "A", "100"], ["P1", "Second", "B", "999"]],
    )
    write_csv(
        tmp_path / "customers.csv",
        ["customer_id", "customer_name", "region"],
        [["C1", "First Customer", "West"], ["C1", "Second Customer", "North"]],
    )
    write_csv(
        tmp_path / "transactions.csv",
        ["transaction_id", "order_id", "timestamp", "customer_id", "product_id", "quantity", "discount_percent"],
        [["T1", "O1", "2025-01-01T10:00:00", "C1", "P1", 1, 0]],
    )

    result = engine.analyze_directory(tmp_path)
    assert result["net_revenue"] == 100.0
    assert result["top_products"][0]["product_name"] == "First"
    assert result["top_customers"][0]["customer_name"] == "First Customer"
    assert result["revenue_by_region"] == {"West": 100.0}
