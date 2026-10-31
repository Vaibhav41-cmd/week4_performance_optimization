"""Shared CSV fixtures for SalesLens correctness and parity tests."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest


def write_csv(path: Path, headers: list[str], rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


@pytest.fixture
def hand_checked_dataset(tmp_path: Path) -> Path:
    """A tiny dataset whose expected result is calculated by hand in tests."""
    write_csv(
        tmp_path / "products.csv",
        ["product_id", "product_name", "category", "unit_price"],
        [
            ["P1", "Alpha", "Category A", "100.00"],
            ["P2", "Beta", "Category B", "50.00"],
            ["P3", "Gamma", "Category A", "200.00"],
        ],
    )
    write_csv(
        tmp_path / "customers.csv",
        ["customer_id", "customer_name", "region"],
        [
            ["C1", "Asha Rao", "West"],
            ["C2", "Ravi Shah", "North"],
        ],
    )
    write_csv(
        tmp_path / "transactions.csv",
        [
            "transaction_id", "order_id", "timestamp", "customer_id",
            "product_id", "quantity", "discount_percent",
        ],
        [
            ["T1", "O1", "2025-01-05T10:00:00", "C1", "P1", 2, 10],
            ["T2", "O1", "2025-01-05T10:00:00", "C1", "P2", 1, 0],
            ["T3", "O2", "2025-02-10T11:00:00", "C1", "P3", 1, 25],
            ["T4", "O3", "2025-02-11T12:00:00", "C2", "P2", 4, 0],
            ["T4", "O4", "2025-03-01T09:00:00", "C2", "P1", 1, 0],
            ["TBAD1", "O5", "2025-03-01T09:00:00", "C2", "PX", 1, 0],
            ["TBAD2", "O6", "2025-03-01T09:00:00", "C2", "P1", 0, 0],
            ["TBAD3", "O7", "not-a-date", "C1", "P1", 1, 0],
        ],
    )
    return tmp_path
