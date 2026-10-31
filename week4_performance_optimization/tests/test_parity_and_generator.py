"""Baseline/optimized parity and deterministic-generator tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from saleslens import baseline, optimized
from saleslens.data_generator import generate_dataset


@pytest.mark.parity
@pytest.mark.parametrize("rows,seed", [(0, 1), (25, 2), (250, 3), (1_000, 4)])
def test_generated_dataset_parity(tmp_path: Path, rows: int, seed: int) -> None:
    data_dir = tmp_path / f"data_{rows}_{seed}"
    metadata = generate_dataset(
        data_dir,
        rows,
        seed=seed,
        product_count=40,
        customer_count=100,
    )

    baseline_result = baseline.analyze_directory(data_dir)
    optimized_result = optimized.analyze_directory(data_dir)

    assert metadata["transaction_rows"] == rows
    assert baseline_result == optimized_result
    assert baseline.format_report(baseline_result) == optimized.format_report(optimized_result)


@pytest.mark.parity
def test_hand_checked_dataset_parity(hand_checked_dataset: Path) -> None:
    assert baseline.analyze_directory(hand_checked_dataset) == optimized.analyze_directory(
        hand_checked_dataset
    )


def test_generator_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    generate_dataset(first, 300, seed=99, product_count=25, customer_count=50)
    generate_dataset(second, 300, seed=99, product_count=25, customer_count=50)

    for filename in ("products.csv", "customers.csv", "transactions.csv"):
        assert (first / filename).read_bytes() == (second / filename).read_bytes()


def test_generator_rejects_invalid_dimensions(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        generate_dataset(tmp_path, -1)
    with pytest.raises(ValueError):
        generate_dataset(tmp_path, 10, product_count=0)
