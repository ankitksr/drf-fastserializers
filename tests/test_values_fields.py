"""Tests for FastSerializer.values_fields() projection helper."""

from datetime import date
from decimal import Decimal

from drf_fastserializers import FastSerializer


class _Flags(FastSerializer):
    is_nsf: bool = False
    is_refund: bool = False


class _Txn(FastSerializer):
    id: int
    name: str
    amount: Decimal | None = None
    txn_date: date
    flags: _Flags


def test_values_fields_returns_field_names():
    fields = _Txn.values_fields()
    assert fields == ("id", "name", "amount", "txn_date", "flags")


def test_values_fields_preserves_declaration_order():
    fields = _Txn.values_fields()
    assert list(fields).index("id") < list(fields).index("name")
    assert list(fields).index("name") < list(fields).index("amount")


def test_values_fields_exclude_drops_names():
    fields = _Txn.values_fields(exclude=("flags", "amount"))
    assert "flags" not in fields
    assert "amount" not in fields
    assert set(fields) == {"id", "name", "txn_date"}


def test_values_fields_unknown_exclude_is_noop():
    fields = _Txn.values_fields(exclude=("does_not_exist",))
    assert set(fields) == {"id", "name", "amount", "txn_date", "flags"}
