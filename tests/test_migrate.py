"""Tests for `from_drf` translation of DRF serializers."""

import json
from datetime import date
from decimal import Decimal

import pytest
from rest_framework import serializers

from drf_fastserializers import (
    FastJSONRenderer,
    FastSerializer,
    MigrationError,
    from_drf,
)


class _FlagsDRF(serializers.Serializer):
    is_nsf = serializers.BooleanField(default=False)
    is_refund = serializers.BooleanField(required=False, allow_null=True)


class _TxnDRF(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField(max_length=100)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True)
    txn_date = serializers.DateField()
    flags = _FlagsDRF()
    tags = serializers.ListField(child=serializers.CharField(), required=False)


def test_from_drf_returns_fastserializer_subclass():
    Fast = from_drf(_TxnDRF)
    assert issubclass(Fast, FastSerializer)
    assert Fast.__name__ == "_TxnDRFFast"


def test_from_drf_basic_field_round_trip():
    Fast = from_drf(_TxnDRF)
    payload = Fast.drf(
        instance={
            "id": 1,
            "name": "rent",
            "amount": Decimal("1200.50"),
            "txn_date": date(2026, 5, 1),
            "flags": {"is_nsf": False, "is_refund": True},
            "tags": ["recurring"],
        }
    ).data
    raw = FastJSONRenderer().render(payload)
    parsed = json.loads(raw)
    assert parsed["id"] == 1
    assert parsed["amount"] == "1200.50"
    assert parsed["flags"]["is_refund"] is True
    assert parsed["tags"] == ["recurring"]


def test_from_drf_handles_optional_and_nullable():
    Fast = from_drf(_TxnDRF)
    # tags is required=False → should accept omission
    payload = Fast.drf(
        instance={
            "id": 2,
            "name": "x",
            "amount": None,  # allow_null
            "txn_date": date(2026, 5, 1),
            "flags": {"is_nsf": False, "is_refund": None},
        }
    ).data
    parsed = json.loads(FastJSONRenderer().render(payload))
    assert parsed["amount"] is None
    assert parsed["tags"] == []  # ListField default → translated to None then validated as []
    assert parsed["flags"]["is_refund"] is None


def test_from_drf_exclude_skips_method_field():
    class _MixedDRF(serializers.Serializer):
        id = serializers.IntegerField()
        computed = serializers.SerializerMethodField()

        def get_computed(self, obj) -> int:
            return obj["id"] * 2

    Fast = from_drf(_MixedDRF, exclude=("computed",))
    payload = Fast.drf(instance={"id": 7}).data
    parsed = json.loads(FastJSONRenderer().render(payload))
    assert parsed == {"id": 7}


def test_from_drf_source_path_becomes_alias():
    class _NestedDRF(serializers.Serializer):
        company_name = serializers.CharField(source="company.name")
        id = serializers.IntegerField()

    Fast = from_drf(_NestedDRF)
    payload = Fast.drf(instance={"id": 1, "company": {"name": "Acme"}}).data
    parsed = json.loads(FastJSONRenderer().render(payload))
    assert parsed == {"id": 1, "company_name": "Acme"}


def test_from_drf_unknown_field_raises():
    class _UnknownField(serializers.Field):
        def to_representation(self, value):
            return value

    class _WeirdDRF(serializers.Serializer):
        id = serializers.IntegerField()
        weird = _UnknownField()

    with pytest.raises(MigrationError, match="weird"):
        from_drf(_WeirdDRF)


def test_from_drf_custom_name():
    Fast = from_drf(_TxnDRF, name="TxnFast")
    assert Fast.__name__ == "TxnFast"
