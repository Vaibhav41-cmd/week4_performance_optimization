"""Original (baseline) SalesLens analytics implementation.

This module is intentionally kept as the *before* version for Week 4.  It is
correct, readable and representative of a first working implementation:

* master-data records are found with repeated linear searches;
* aggregations are stored in lists of dictionaries and searched linearly;
* distinct values and duplicate checks use list membership/count scans;
* analytics are computed in several passes over an in-memory row list.

Do not "fix" this file when optimizing: the optimized implementation lives in
``saleslens/optimized.py`` so the before/after comparison remains auditable.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

TOP_N = 10
HIGH_VALUE_THRESHOLD = 10_000.0


def _read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    """Read a simple CSV file by manually splitting lines and commas."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    if not lines:
        return []
    headers = [header.strip() for header in lines[0].split(",")]
    rows: list[dict[str, str]] = []
    for line in lines[1:]:
        if not line.strip():
            continue
        values = [value.strip() for value in line.split(",")]
        row = dict(zip(headers, values))
        if len(values) != len(headers):
            row["_malformed"] = "1"
        rows.append(row)
    return rows


def _find_by_id(records: Iterable[dict[str, str]], key: str, wanted: str) -> dict[str, str] | None:
    """Find the first record with ``wanted`` by scanning the whole list."""
    for record in records:
        if record.get(key) == wanted:
            return record
    return None


def _add_to_bucket(
    buckets: list[dict[str, Any]],
    key: str,
    revenue: float,
    units: int = 0,
) -> None:
    """Add revenue/units to a list-backed bucket, searching linearly."""
    for bucket in buckets:
        if bucket["key"] == key:
            bucket["revenue"] += revenue
            bucket["units"] += units
            return
    buckets.append({"key": key, "revenue": revenue, "units": units})


def _distinct_add(values: list[str], value: str) -> None:
    """Append a distinct value using a list membership scan."""
    if value not in values:
        values.append(value)


def _enrich_transaction(
    row: dict[str, str],
    products: list[dict[str, str]],
    customers: list[dict[str, str]],
) -> dict[str, Any] | None:
    """Validate and enrich one transaction using repeated master searches."""
    required = (
        "transaction_id", "order_id", "timestamp", "customer_id",
        "product_id", "quantity", "discount_percent",
    )
    if row.get("_malformed") or any(not row.get(field) for field in required):
        return None

    try:
        parsed_time = datetime.strptime(row["timestamp"], "%Y-%m-%dT%H:%M:%S")
        quantity = int(row["quantity"])
        discount_percent = float(row["discount_percent"])
    except (TypeError, ValueError):
        return None

    if quantity <= 0 or discount_percent < 0 or discount_percent > 90:
        return None

    product = _find_by_id(products, "product_id", row["product_id"])
    customer = _find_by_id(customers, "customer_id", row["customer_id"])
    if product is None or customer is None:
        return None

    try:
        unit_price = float(product["unit_price"])
    except (KeyError, TypeError, ValueError):
        return None
    if unit_price < 0:
        return None

    gross = quantity * unit_price
    discount = gross * discount_percent / 100.0
    net = gross - discount
    return {
        "transaction_id": row["transaction_id"],
        "order_id": row["order_id"],
        "month": parsed_time.strftime("%Y-%m"),
        "customer_id": row["customer_id"],
        "customer_name": customer.get("customer_name", ""),
        "region": customer.get("region", ""),
        "product_id": row["product_id"],
        "product_name": product.get("product_name", ""),
        "category": product.get("category", ""),
        "quantity": quantity,
        "gross": gross,
        "discount": discount,
        "net": net,
    }


def _top_buckets(buckets: list[dict[str, Any]], limit: int = TOP_N) -> list[dict[str, Any]]:
    """Return top buckets by repeatedly finding and removing the maximum."""
    remaining = list(buckets)
    output: list[dict[str, Any]] = []
    while remaining and len(output) < limit:
        best = remaining[0]
        for bucket in remaining[1:]:
            if bucket["revenue"] > best["revenue"] or (
                bucket["revenue"] == best["revenue"] and bucket["key"] < best["key"]
            ):
                best = bucket
        output.append(best)
        remaining.remove(best)
    return output


def _count_duplicate_ids(transactions: list[dict[str, Any]]) -> tuple[int, int]:
    """Count duplicate transaction IDs using repeated ``list.count`` scans."""
    ids = [row["transaction_id"] for row in transactions]
    duplicate_ids: list[str] = []
    for transaction_id in ids:
        if ids.count(transaction_id) > 1:
            _distinct_add(duplicate_ids, transaction_id)
    return len(duplicate_ids), len(ids) - len(set(ids))


def _customer_order_counts(transactions: list[dict[str, Any]]) -> dict[str, int]:
    """Count distinct orders per customer using nested list structures."""
    customer_orders: list[dict[str, Any]] = []
    for row in transactions:
        entry = None
        for candidate in customer_orders:
            if candidate["customer_id"] == row["customer_id"]:
                entry = candidate
                break
        if entry is None:
            entry = {"customer_id": row["customer_id"], "order_ids": []}
            customer_orders.append(entry)
        _distinct_add(entry["order_ids"], row["order_id"])
    return {entry["customer_id"]: len(entry["order_ids"]) for entry in customer_orders}


def _co_purchase_pairs(transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Find top product co-purchase pairs with list-backed order groups."""
    order_groups: list[dict[str, Any]] = []
    for row in transactions:
        group = None
        for candidate in order_groups:
            if candidate["order_id"] == row["order_id"]:
                group = candidate
                break
        if group is None:
            group = {"order_id": row["order_id"], "product_ids": []}
            order_groups.append(group)
        _distinct_add(group["product_ids"], row["product_id"])

    pair_counts: list[dict[str, Any]] = []
    for group in order_groups:
        products = sorted(group["product_ids"])
        for left_index, left in enumerate(products):
            for right in products[left_index + 1:]:
                found = None
                for pair in pair_counts:
                    if pair["product_a"] == left and pair["product_b"] == right:
                        found = pair
                        break
                if found is None:
                    pair_counts.append({"product_a": left, "product_b": right, "count": 1})
                else:
                    found["count"] += 1

    pair_counts.sort(key=lambda pair: (-pair["count"], pair["product_a"], pair["product_b"]))
    return pair_counts[:TOP_N]


def analyze_dataset(
    transactions_csv: str | Path,
    products_csv: str | Path,
    customers_csv: str | Path,
) -> dict[str, Any]:
    """Analyze the three SalesLens CSV files with the baseline algorithm."""
    products = _read_csv_rows(products_csv)
    customers = _read_csv_rows(customers_csv)
    raw_transactions = _read_csv_rows(transactions_csv)

    # Pass 1: validate/enrich every row and store the full working set.
    transactions: list[dict[str, Any]] = []
    invalid_rows = 0
    for row in raw_transactions:
        enriched = _enrich_transaction(row, products, customers)
        if enriched is None:
            invalid_rows += 1
        else:
            transactions.append(enriched)

    # Pass 2: headline totals and list-backed distinct values.
    order_ids: list[str] = []
    customer_ids: list[str] = []
    total_units = 0
    gross_revenue = 0.0
    discount_amount = 0.0
    net_revenue = 0.0
    for row in transactions:
        _distinct_add(order_ids, row["order_id"])
        _distinct_add(customer_ids, row["customer_id"])
        total_units += row["quantity"]
        gross_revenue += row["gross"]
        discount_amount += row["discount"]
        net_revenue += row["net"]

    # Pass 3: each aggregation family scans list-backed buckets.
    monthly_buckets: list[dict[str, Any]] = []
    category_buckets: list[dict[str, Any]] = []
    region_buckets: list[dict[str, Any]] = []
    product_buckets: list[dict[str, Any]] = []
    customer_buckets: list[dict[str, Any]] = []
    for row in transactions:
        _add_to_bucket(monthly_buckets, row["month"], row["net"])
        _add_to_bucket(category_buckets, row["category"], row["net"])
        _add_to_bucket(region_buckets, row["region"], row["net"])
        _add_to_bucket(product_buckets, row["product_id"], row["net"], row["quantity"])
        _add_to_bucket(customer_buckets, row["customer_id"], row["net"])

    order_counts = _customer_order_counts(transactions)
    duplicate_ids, duplicate_rows = _count_duplicate_ids(transactions)
    co_purchase_pairs = _co_purchase_pairs(transactions)

    product_names = {row["product_id"]: row["product_name"] for row in transactions}
    customer_names = {row["customer_id"]: row["customer_name"] for row in transactions}

    monthly_revenue = {
        bucket["key"]: round(bucket["revenue"], 2)
        for bucket in sorted(monthly_buckets, key=lambda item: item["key"])
    }
    revenue_by_category = {
        bucket["key"]: round(bucket["revenue"], 2)
        for bucket in sorted(category_buckets, key=lambda item: item["key"])
    }
    category_shares = {
        bucket["key"]: round(bucket["revenue"] / net_revenue, 4) if net_revenue else 0.0
        for bucket in sorted(category_buckets, key=lambda item: item["key"])
    }
    revenue_by_region = {
        bucket["key"]: round(bucket["revenue"], 2)
        for bucket in sorted(region_buckets, key=lambda item: item["key"])
    }

    top_products = [
        {
            "product_id": bucket["key"],
            "product_name": product_names.get(bucket["key"], ""),
            "units": bucket["units"],
            "revenue": round(bucket["revenue"], 2),
        }
        for bucket in _top_buckets(product_buckets)
    ]
    top_customers = [
        {
            "customer_id": bucket["key"],
            "customer_name": customer_names.get(bucket["key"], ""),
            "orders": order_counts.get(bucket["key"], 0),
            "revenue": round(bucket["revenue"], 2),
        }
        for bucket in _top_buckets(customer_buckets)
    ]

    repeat_customers = sum(1 for count in order_counts.values() if count > 1)
    high_value_customers = sum(
        1 for bucket in customer_buckets if bucket["revenue"] >= HIGH_VALUE_THRESHOLD
    )
    best_month = None
    if monthly_buckets:
        best_month = sorted(monthly_buckets, key=lambda item: (-item["revenue"], item["key"]))[0]["key"]

    return {
        "rows_read": len(raw_transactions),
        "valid_rows": len(transactions),
        "invalid_rows": invalid_rows,
        "order_count": len(order_ids),
        "customer_count": len(customer_ids),
        "total_units": total_units,
        "gross_revenue": round(gross_revenue, 2),
        "discount_amount": round(discount_amount, 2),
        "net_revenue": round(net_revenue, 2),
        "average_order_value": round(net_revenue / len(order_ids), 2) if order_ids else 0.0,
        "monthly_revenue": monthly_revenue,
        "revenue_by_category": revenue_by_category,
        "category_shares": category_shares,
        "revenue_by_region": revenue_by_region,
        "top_products": top_products,
        "top_customers": top_customers,
        "repeat_customer_count": repeat_customers,
        "repeat_customer_rate": round(repeat_customers / len(customer_ids), 4) if customer_ids else 0.0,
        "high_value_customer_count": high_value_customers,
        "duplicate_transaction_ids": duplicate_ids,
        "duplicate_transaction_rows": duplicate_rows,
        "top_co_purchase_pairs": co_purchase_pairs,
        "best_month": best_month,
    }


def analyze_directory(data_dir: str | Path) -> dict[str, Any]:
    """Analyze ``transactions.csv``, ``products.csv`` and ``customers.csv``."""
    base = Path(data_dir)
    return analyze_dataset(base / "transactions.csv", base / "products.csv", base / "customers.csv")


def format_report(result: dict[str, Any]) -> str:
    """Format the canonical result using repeated string concatenation."""
    report = "SalesLens transaction analytics\n"
    report += "-------------------------------\n"
    report += f"Rows read: {result['rows_read']} (valid {result['valid_rows']}, invalid {result['invalid_rows']})\n"
    report += f"Orders: {result['order_count']} | Customers: {result['customer_count']} | Units: {result['total_units']}\n"
    report += f"Net revenue: INR {result['net_revenue']:,.2f} | Average order value: INR {result['average_order_value']:,.2f}\n"
    report += f"Repeat customers: {result['repeat_customer_count']} ({result['repeat_customer_rate']:.2%})\n"
    report += f"Duplicate transaction IDs: {result['duplicate_transaction_ids']} ({result['duplicate_transaction_rows']} extra rows)\n"
    report += f"Best month: {result['best_month'] or 'n/a'}\n\nTop products:\n"
    for index, product in enumerate(result["top_products"], start=1):
        report += (
            f"{index:>2}. {product['product_id']} {product['product_name']} - "
            f"INR {product['revenue']:,.2f} ({product['units']} units)\n"
        )
    report += "\nTop customers:\n"
    for index, customer in enumerate(result["top_customers"], start=1):
        report += (
            f"{index:>2}. {customer['customer_id']} {customer['customer_name']} - "
            f"INR {customer['revenue']:,.2f} ({customer['orders']} orders)\n"
        )
    return report.rstrip() + "\n"
