"""Deterministic synthetic-data generation for SalesLens.

The internship brief requires a self-contained archive, so the project does
not depend on an externally downloaded dataset.  This module generates three
CSV files with the same shape as a small retail export:

``products.csv``
    Product master data (id, name, category and unit price).
``customers.csv``
    Customer master data (id, name and sales region).
``transactions.csv``
    Order line items.  Several rows can belong to one order, which allows
    average-order-value and co-purchase analytics.

The generator intentionally uses only the Python standard library and a
seeded ``random.Random`` instance.  A given seed and row count therefore
produce the same benchmark input on every run.
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any

CATEGORIES: dict[str, tuple[float, float]] = {
    "Electronics": (999.0, 49999.0),
    "Home Appliances": (799.0, 34999.0),
    "Fashion": (299.0, 4999.0),
    "Footwear": (499.0, 6999.0),
    "Grocery": (35.0, 999.0),
    "Personal Care": (99.0, 1499.0),
    "Sports": (399.0, 9999.0),
    "Books": (149.0, 1999.0),
    "Toys": (199.0, 3999.0),
    "Automotive": (499.0, 14999.0),
}

PRODUCT_WORDS = (
    "Aero", "Nova", "Pixel", "Urban", "Eco", "Prime", "Vertex", "Lumina",
    "Turbo", "Classic", "Smart", "Flex", "Orion", "Zen", "Atlas", "Vivid",
)
PRODUCT_TYPES = (
    "Series", "Edition", "Kit", "Pack", "Pro", "Lite", "Max", "Essential",
)
FIRST_NAMES = (
    "Aarav", "Ananya", "Arjun", "Diya", "Ishita", "Kabir", "Meera", "Nikhil",
    "Priya", "Rahul", "Riya", "Rohan", "Sneha", "Vaibhav", "Vihaan", "Zara",
)
LAST_NAMES = (
    "Deshmukh", "Desale", "Iyer", "Jain", "Khan", "Kulkarni", "Mehta", "Nair",
    "Patel", "Patil", "Rao", "Reddy", "Shah", "Sharma", "Singh", "Verma",
)
REGIONS = ("North", "South", "East", "West", "Central", "North-East")
DISCOUNTS = (0, 0, 0, 5, 5, 10, 10, 15, 20)


def _skewed_index(rng: random.Random, upper: int, exponent: float = 2.0) -> int:
    """Return a popularity-skewed index (lower indexes are chosen more)."""
    return min(upper - 1, int(upper * (rng.random() ** exponent)))


def _write_products(path: Path, rng: random.Random, product_count: int) -> list[str]:
    categories = tuple(CATEGORIES)
    product_ids: list[str] = []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["product_id", "product_name", "category", "unit_price"])
        for number in range(1, product_count + 1):
            product_id = f"P{number:05d}"
            category = rng.choice(categories)
            low, high = CATEGORIES[category]
            price = round(rng.uniform(low, high), 2)
            name = f"{rng.choice(PRODUCT_WORDS)} {category.split()[0]} {rng.choice(PRODUCT_TYPES)} {number}"
            writer.writerow([product_id, name, category, f"{price:.2f}"])
            product_ids.append(product_id)
    return product_ids


def _write_customers(path: Path, rng: random.Random, customer_count: int) -> list[str]:
    customer_ids: list[str] = []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["customer_id", "customer_name", "region"])
        for number in range(1, customer_count + 1):
            customer_id = f"C{number:06d}"
            name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
            writer.writerow([customer_id, name, rng.choice(REGIONS)])
            customer_ids.append(customer_id)
    return customer_ids


def _timestamp(rng: random.Random) -> str:
    day = date(2025, 1, 1) + timedelta(days=rng.randrange(365))
    return (
        f"{day.isoformat()}T{rng.randrange(24):02d}:"
        f"{rng.randrange(60):02d}:{rng.randrange(60):02d}"
    )


def generate_dataset(
    output_dir: str | Path,
    transaction_rows: int = 30_000,
    *,
    seed: int = 42,
    product_count: int = 500,
    customer_count: int = 3_000,
) -> dict[str, Any]:
    """Generate a deterministic SalesLens dataset.

    Parameters
    ----------
    output_dir:
        Directory that receives the three CSV files.
    transaction_rows:
        Exact number of data rows in ``transactions.csv``, including a small
        deterministic invalid-row tail (approximately 0.1% for large files).
    seed:
        Seed for reproducible pseudo-random choices.
    product_count, customer_count:
        Sizes of the two master-data files.

    Returns
    -------
    dict
        Metadata describing the generated files and row counts.
    """
    if transaction_rows < 0:
        raise ValueError("transaction_rows cannot be negative")
    if product_count <= 0 or customer_count <= 0:
        raise ValueError("product_count and customer_count must be positive")

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)

    products_path = destination / "products.csv"
    customers_path = destination / "customers.csv"
    transactions_path = destination / "transactions.csv"

    product_ids = _write_products(products_path, rng, product_count)
    customer_ids = _write_customers(customers_path, rng, customer_count)

    invalid_rows = transaction_rows // 1000  # 0.1%, zero for tiny fixtures
    regular_rows = transaction_rows - invalid_rows
    written = 0
    order_number = 0
    transaction_number = 0
    previous_transaction_id = ""

    with transactions_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "transaction_id", "order_id", "timestamp", "customer_id",
                "product_id", "quantity", "discount_percent",
            ]
        )

        while written < regular_rows:
            order_number += 1
            order_id = f"O{order_number:07d}"
            timestamp = _timestamp(rng)
            customer_id = customer_ids[_skewed_index(rng, customer_count, 1.65)]
            line_count = min(regular_rows - written, rng.choices((1, 2, 3, 4), weights=(48, 32, 14, 6))[0])

            used_products: set[str] = set()
            for _ in range(line_count):
                transaction_number += 1
                transaction_id = f"T{transaction_number:08d}"
                # Approximately 0.2% of rows repeat the previous ID.  Duplicate
                # detection is part of the analytics contract.
                if previous_transaction_id and rng.random() < 0.002:
                    transaction_id = previous_transaction_id
                else:
                    previous_transaction_id = transaction_id

                product_id = product_ids[_skewed_index(rng, product_count, 2.15)]
                # Keep most order lines unique while still allowing an
                # occasional repeated product in the same order.
                if product_id in used_products and rng.random() < 0.8:
                    product_id = rng.choice(product_ids)
                used_products.add(product_id)

                writer.writerow(
                    [
                        transaction_id,
                        order_id,
                        timestamp,
                        customer_id,
                        product_id,
                        rng.choices((1, 2, 3, 4, 5), weights=(58, 24, 10, 5, 3))[0],
                        rng.choice(DISCOUNTS),
                    ]
                )
                written += 1

        # A compact invalid tail exercises validation in both engines without
        # making data quality the subject of the benchmark.
        invalid_templates = [
            ["TBAD001", "O9999001", "2025-13-40T25:00:00", customer_ids[0], product_ids[0], 1, 0],
            ["TBAD002", "O9999002", "2025-04-01T09:00:00", "C999999", product_ids[0], 1, 0],
            ["TBAD003", "O9999003", "2025-04-01T09:00:00", customer_ids[0], "P99999", 1, 0],
            ["TBAD004", "O9999004", "2025-04-01T09:00:00", customer_ids[0], product_ids[0], 0, 0],
            ["TBAD005", "O9999005", "2025-04-01T09:00:00", customer_ids[0], product_ids[0], 1, 95],
        ]
        for index in range(invalid_rows):
            writer.writerow(invalid_templates[index % len(invalid_templates)])

    return {
        "output_dir": str(destination),
        "seed": seed,
        "transaction_rows": transaction_rows,
        "regular_rows": regular_rows,
        "invalid_rows_injected": invalid_rows,
        "order_count_generated": order_number,
        "product_count": product_count,
        "customer_count": customer_count,
        "files": {
            "products": str(products_path),
            "customers": str(customers_path),
            "transactions": str(transactions_path),
        },
        "file_sizes_bytes": {
            "products": products_path.stat().st_size,
            "customers": customers_path.stat().st_size,
            "transactions": transactions_path.stat().st_size,
        },
    }
