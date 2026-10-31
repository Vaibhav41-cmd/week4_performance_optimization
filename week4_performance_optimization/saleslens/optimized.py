"""Profile-guided optimized SalesLens analytics implementation.

The public contract is identical to :mod:`saleslens.baseline`, but the
algorithm and data structures are different:

* product/customer master data are indexed once in dictionaries;
* transactions are streamed in one pass instead of being retained and
  rescanned for each metric family;
* aggregations use dictionaries, ``defaultdict`` and ``Counter``;
* distinct orders/customers and duplicate detection use sets/counters;
* co-purchase groups use ``defaultdict(set)``;
* top-N selection uses :func:`heapq.nlargest`.

The dominant transaction loop is therefore O(n) expected time after an
O(products + customers) indexing step, instead of repeatedly multiplying the
transaction count by master/bucket list sizes.
"""

from __future__ import annotations

import csv
import heapq
from collections import Counter, defaultdict
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any

TOP_N = 10
HIGH_VALUE_THRESHOLD = 10_000.0


def _load_products(path: str | Path) -> dict[str, tuple[str, str, float | None]]:
    """Load products into an ID index; the first duplicate ID wins."""
    products: dict[str, tuple[str, str, float | None]] = {}
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            product_id = (row.get("product_id") or "").strip()
            if not product_id or product_id in products:
                continue
            try:
                price: float | None = float(row.get("unit_price") or "")
            except ValueError:
                price = None
            products[product_id] = (
                (row.get("product_name") or "").strip(),
                (row.get("category") or "").strip(),
                price,
            )
    return products


def _load_customers(path: str | Path) -> dict[str, tuple[str, str]]:
    """Load customers into an ID index; the first duplicate ID wins."""
    customers: dict[str, tuple[str, str]] = {}
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            customer_id = (row.get("customer_id") or "").strip()
            if not customer_id or customer_id in customers:
                continue
            customers[customer_id] = (
                (row.get("customer_name") or "").strip(),
                (row.get("region") or "").strip(),
            )
    return customers


def analyze_dataset(
    transactions_csv: str | Path,
    products_csv: str | Path,
    customers_csv: str | Path,
) -> dict[str, Any]:
    """Analyze the three SalesLens CSV files in one streaming pass."""
    products = _load_products(products_csv)
    customers = _load_customers(customers_csv)

    rows_read = 0
    valid_rows = 0
    invalid_rows = 0
    total_units = 0
    gross_revenue = 0.0
    discount_amount = 0.0
    net_revenue = 0.0

    order_ids: set[str] = set()
    customer_ids: set[str] = set()
    monthly_revenue: defaultdict[str, float] = defaultdict(float)
    category_revenue: defaultdict[str, float] = defaultdict(float)
    region_revenue: defaultdict[str, float] = defaultdict(float)

    # Mutable two-slot accumulators avoid creating a result object per row.
    product_stats: dict[str, list[float | int]] = {}
    customer_revenue: dict[str, float] = {}
    customer_orders: dict[str, set[str]] = {}
    order_products: defaultdict[str, set[str]] = defaultdict(set)
    transaction_id_counts: Counter[str] = Counter()

    # Bind frequently used methods/functions locally for the hot loop.
    products_get = products.get
    customers_get = customers.get
    fromisoformat = datetime.fromisoformat

    with Path(transactions_csv).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows_read += 1

            # DictReader uses None as the restkey and None for missing values.
            if None in row:
                invalid_rows += 1
                continue

            transaction_id = row.get("transaction_id")
            order_id = row.get("order_id")
            timestamp = row.get("timestamp")
            customer_id = row.get("customer_id")
            product_id = row.get("product_id")
            if not all((transaction_id, order_id, timestamp, customer_id, product_id)):
                invalid_rows += 1
                continue

            try:
                # Validate once with the fast ISO parser, then slice the
                # already-validated YYYY-MM prefix.
                fromisoformat(timestamp)
                quantity = int(row["quantity"])
                discount_percent = float(row["discount_percent"])
            except (TypeError, ValueError):
                invalid_rows += 1
                continue

            if quantity <= 0 or discount_percent < 0 or discount_percent > 90:
                invalid_rows += 1
                continue

            product = products_get(product_id)
            customer = customers_get(customer_id)
            if product is None or customer is None:
                invalid_rows += 1
                continue
            _product_name, category, unit_price = product
            if unit_price is None or unit_price < 0:
                invalid_rows += 1
                continue
            _customer_name, region = customer

            gross = quantity * unit_price
            discount = gross * discount_percent / 100.0
            net = gross - discount

            valid_rows += 1
            total_units += quantity
            gross_revenue += gross
            discount_amount += discount
            net_revenue += net
            order_ids.add(order_id)
            customer_ids.add(customer_id)
            monthly_revenue[timestamp[:7]] += net
            category_revenue[category] += net
            region_revenue[region] += net
            transaction_id_counts[transaction_id] += 1
            order_products[order_id].add(product_id)

            stats = product_stats.get(product_id)
            if stats is None:
                product_stats[product_id] = [net, quantity]
            else:
                stats[0] += net
                stats[1] += quantity

            customer_revenue[customer_id] = customer_revenue.get(customer_id, 0.0) + net
            orders = customer_orders.get(customer_id)
            if orders is None:
                customer_orders[customer_id] = {order_id}
            else:
                orders.add(order_id)

    pair_counts: Counter[tuple[str, str]] = Counter()
    for product_ids in order_products.values():
        if len(product_ids) > 1:
            pair_counts.update(combinations(sorted(product_ids), 2))

    top_product_items = heapq.nlargest(
        TOP_N,
        product_stats.items(),
        key=lambda item: (item[1][0], _DescendingString(item[0])),
    )
    # heapq cannot express "revenue desc, ID asc" with a plain tuple for
    # strings; the custom key object above keeps selection O(k log TOP_N).
    top_products = [
        {
            "product_id": product_id,
            "product_name": products[product_id][0],
            "units": int(stats[1]),
            "revenue": round(float(stats[0]), 2),
        }
        for product_id, stats in top_product_items
    ]

    top_customer_items = heapq.nlargest(
        TOP_N,
        customer_revenue.items(),
        key=lambda item: (item[1], _DescendingString(item[0])),
    )
    top_customers = [
        {
            "customer_id": customer_id,
            "customer_name": customers[customer_id][0],
            "orders": len(customer_orders[customer_id]),
            "revenue": round(revenue, 2),
        }
        for customer_id, revenue in top_customer_items
    ]

    top_pairs = [
        {"product_a": product_a, "product_b": product_b, "count": count}
        for (product_a, product_b), count in heapq.nlargest(
            TOP_N,
            pair_counts.items(),
            key=lambda item: (
                item[1],
                _DescendingString(item[0][0]),
                _DescendingString(item[0][1]),
            ),
        )
    ]

    repeat_customers = sum(1 for orders in customer_orders.values() if len(orders) > 1)
    high_value_customers = sum(
        1 for revenue in customer_revenue.values() if revenue >= HIGH_VALUE_THRESHOLD
    )
    duplicate_ids = sum(1 for count in transaction_id_counts.values() if count > 1)
    duplicate_rows = valid_rows - len(transaction_id_counts)
    best_month = None
    if monthly_revenue:
        # Earliest month wins a revenue tie, matching the baseline.
        best_month = max(sorted(monthly_revenue), key=monthly_revenue.__getitem__)

    return {
        "rows_read": rows_read,
        "valid_rows": valid_rows,
        "invalid_rows": invalid_rows,
        "order_count": len(order_ids),
        "customer_count": len(customer_ids),
        "total_units": total_units,
        "gross_revenue": round(gross_revenue, 2),
        "discount_amount": round(discount_amount, 2),
        "net_revenue": round(net_revenue, 2),
        "average_order_value": round(net_revenue / len(order_ids), 2) if order_ids else 0.0,
        "monthly_revenue": {
            month: round(monthly_revenue[month], 2) for month in sorted(monthly_revenue)
        },
        "revenue_by_category": {
            category: round(category_revenue[category], 2) for category in sorted(category_revenue)
        },
        "category_shares": {
            category: round(category_revenue[category] / net_revenue, 4) if net_revenue else 0.0
            for category in sorted(category_revenue)
        },
        "revenue_by_region": {
            region: round(region_revenue[region], 2) for region in sorted(region_revenue)
        },
        "top_products": top_products,
        "top_customers": top_customers,
        "repeat_customer_count": repeat_customers,
        "repeat_customer_rate": round(repeat_customers / len(customer_ids), 4) if customer_ids else 0.0,
        "high_value_customer_count": high_value_customers,
        "duplicate_transaction_ids": duplicate_ids,
        "duplicate_transaction_rows": duplicate_rows,
        "top_co_purchase_pairs": top_pairs,
        "best_month": best_month,
    }


class _DescendingString:
    """String wrapper that reverses ordering for deterministic top-N ties."""

    __slots__ = ("value",)

    def __init__(self, value: str) -> None:
        self.value = value

    def __lt__(self, other: "_DescendingString") -> bool:
        return self.value > other.value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _DescendingString) and self.value == other.value


def analyze_directory(data_dir: str | Path) -> dict[str, Any]:
    """Analyze ``transactions.csv``, ``products.csv`` and ``customers.csv``."""
    base = Path(data_dir)
    return analyze_dataset(base / "transactions.csv", base / "products.csv", base / "customers.csv")


def format_report(result: dict[str, Any]) -> str:
    """Format the canonical result by joining a list of lines once."""
    lines = [
        "SalesLens transaction analytics",
        "-------------------------------",
        f"Rows read: {result['rows_read']} (valid {result['valid_rows']}, invalid {result['invalid_rows']})",
        f"Orders: {result['order_count']} | Customers: {result['customer_count']} | Units: {result['total_units']}",
        f"Net revenue: INR {result['net_revenue']:,.2f} | Average order value: INR {result['average_order_value']:,.2f}",
        f"Repeat customers: {result['repeat_customer_count']} ({result['repeat_customer_rate']:.2%})",
        f"Duplicate transaction IDs: {result['duplicate_transaction_ids']} ({result['duplicate_transaction_rows']} extra rows)",
        f"Best month: {result['best_month'] or 'n/a'}",
        "",
        "Top products:",
    ]
    lines.extend(
        f"{index:>2}. {product['product_id']} {product['product_name']} - "
        f"INR {product['revenue']:,.2f} ({product['units']} units)"
        for index, product in enumerate(result["top_products"], start=1)
    )
    lines.extend(["", "Top customers:"])
    lines.extend(
        f"{index:>2}. {customer['customer_id']} {customer['customer_name']} - "
        f"INR {customer['revenue']:,.2f} ({customer['orders']} orders)"
        for index, customer in enumerate(result["top_customers"], start=1)
    )
    return "\n".join(lines) + "\n"
