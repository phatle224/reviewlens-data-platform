from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import pytest

from reviewlens.synthetic.generator import FILE_COLUMNS, REQUIRED_FILES, generate_fixture


def _directory_hashes(path: Path) -> dict[str, str]:
    return {
        item.name: hashlib.sha256(item.read_bytes()).hexdigest()
        for item in sorted(path.iterdir())
        if item.is_file()
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_generator_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    generate_fixture(first)
    generate_fixture(second)
    assert _directory_hashes(first) == _directory_hashes(second)


def test_fixture_has_all_nine_olist_sources_and_exact_headers(tmp_path: Path) -> None:
    manifest = generate_fixture(tmp_path)
    assert {item["filename"] for item in manifest["files"]} == set(REQUIRED_FILES)
    assert manifest["data_class"] == "synthetic"
    assert manifest["schema_version"] == "synthetic-olist-v1"
    for filename in REQUIRED_FILES:
        with (tmp_path / filename).open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
        assert tuple(reader.fieldnames or ()) == FILE_COLUMNS[filename]
        assert rows


def test_fixture_relational_foreign_keys_are_valid(tmp_path: Path) -> None:
    generate_fixture(tmp_path)
    customers = {row["customer_id"] for row in _read_csv(tmp_path / REQUIRED_FILES[0])}
    items = _read_csv(tmp_path / "olist_order_items_dataset.csv")
    reviews = _read_csv(tmp_path / "olist_order_reviews_dataset.csv")
    orders = _read_csv(tmp_path / "olist_orders_dataset.csv")
    products = {row["product_id"] for row in _read_csv(tmp_path / "olist_products_dataset.csv")}
    sellers = {row["seller_id"] for row in _read_csv(tmp_path / "olist_sellers_dataset.csv")}
    order_ids = {row["order_id"] for row in orders}

    assert {row["customer_id"] for row in orders} <= customers
    assert {row["order_id"] for row in items} <= order_ids
    assert {row["order_id"] for row in reviews} <= order_ids
    assert {row["product_id"] for row in items} <= products
    assert {row["seller_id"] for row in items} <= sellers


@pytest.mark.parametrize(
    "source_path",
    [
        Path("archive/synthetic-output"),
        Path("olist_dataset/synthetic-output"),
        Path("Yelp-JSON/synthetic-output"),
    ],
)
def test_generator_refuses_real_source_directories(source_path: Path) -> None:
    with pytest.raises(ValueError, match="real source directory"):
        generate_fixture(source_path)


def test_fixture_content_is_explicitly_synthetic(tmp_path: Path) -> None:
    manifest = generate_fixture(tmp_path)
    content = "\n".join(path.read_text(encoding="utf-8") for path in tmp_path.glob("*.csv"))
    assert "synthetic_" in content
    assert manifest["source"] == "reviewlens-olist-fixture-generator"
