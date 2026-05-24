"""Shared fixtures and pydantic schemas used across tests."""

from datetime import date
from decimal import Decimal

import pytest

from drf_fastserializers import FastSerializer


class Flags(FastSerializer):
    is_nsf: bool = False
    is_refund: bool = False


class TxnOut(FastSerializer):
    id: int
    name: str
    amount: Decimal | None = None
    txn_date: date
    flags: Flags
    tags: list[str] = []


@pytest.fixture
def txn_dict() -> dict:
    return {
        "id": 1,
        "name": "rent",
        "amount": Decimal("1200.50"),
        "txn_date": date(2026, 5, 1),
        "flags": {"is_nsf": False, "is_refund": True},
        "tags": ["recurring", "housing"],
    }


@pytest.fixture
def txn_dicts(txn_dict: dict) -> list[dict]:
    return [{**txn_dict, "id": i, "name": f"row-{i}"} for i in range(1, 6)]
