"""Tests for from_model — Django model → FastSerializer translation."""

import json
from datetime import date
from decimal import Decimal

import pytest

from drf_fastserializers import (
    FastJSONRenderer,
    FastSerializer,
    ModelMappingError,
    from_model,
)

from .models import MockCoop, MockTxn


def test_from_model_returns_fastserializer_subclass():
    fast = from_model(MockTxn, fields=["id", "name"])
    assert issubclass(fast, FastSerializer)
    assert "id" in fast.model_fields
    assert "name" in fast.model_fields


def test_from_model_default_class_name():
    fast = from_model(MockTxn, fields=["id"])
    assert fast.__name__ == "MockTxnFast"


def test_from_model_custom_name():
    fast = from_model(MockTxn, fields=["id"], name="TxnView")
    assert fast.__name__ == "TxnView"


def test_from_model_all_fields():
    fast = from_model(MockTxn, fields="__all__")
    expected = {"id", "name", "amount", "txn_date", "is_active", "notes", "meta", "coop"}
    assert set(fast.model_fields) == expected


def test_from_model_exclude_drops_fields():
    fast = from_model(MockTxn, fields="__all__", exclude=("notes", "meta"))
    assert "notes" not in fast.model_fields
    assert "meta" not in fast.model_fields
    assert "name" in fast.model_fields


def test_from_model_nullable_field_widened_to_optional():
    """Django null=True → pydantic T | None with default None."""
    fast = from_model(MockTxn, fields=["amount"])
    info = fast.model_fields["amount"]
    # validate accepts None
    instance = fast.model_validate({"amount": None})
    assert instance.amount is None
    # validate accepts Decimal
    instance = fast.model_validate({"amount": Decimal("12.34")})
    assert instance.amount == Decimal("12.34")
    # default is None when omitted
    instance = fast.model_validate({})
    assert instance.amount is None
    _ = info  # silence unused


def test_from_model_default_value_preserved():
    """Django default=True on BooleanField is honored."""
    fast = from_model(MockTxn, fields=["is_active"])
    instance = fast.model_validate({})
    assert instance.is_active is True


def test_from_model_default_factory_for_callable_defaults():
    """JSONField default=dict is callable; pydantic gets default_factory."""
    fast = from_model(MockTxn, fields=["meta"])
    a = fast.model_validate({})
    b = fast.model_validate({})
    assert a.meta == {}
    assert a.meta is not b.meta  # factory called per instance


def test_from_model_foreign_key_uses_pk_type():
    """FK is projected as the PK type of the related model (int by default)."""
    fast = from_model(MockTxn, fields=["coop"])
    instance = fast.model_validate({"coop": 42})
    assert instance.coop == 42


def test_from_model_unknown_field_raises():
    with pytest.raises(ModelMappingError, match="no concrete field"):
        from_model(MockTxn, fields=["does_not_exist"])


def test_from_model_round_trip_via_drf_adapter():
    fast = from_model(MockTxn, fields=["id", "name", "amount", "txn_date", "is_active"])
    payload = fast.drf(
        instance={
            "id": 1,
            "name": "mock",
            "amount": Decimal("99.95"),
            "txn_date": date(2026, 5, 1),
            "is_active": True,
        }
    ).data
    parsed = json.loads(FastJSONRenderer().render(payload))
    assert parsed == {
        "id": 1,
        "name": "mock",
        "amount": "99.95",
        "txn_date": "2026-05-01",
        "is_active": True,
    }


def test_from_model_supports_attribute_access():
    """from_attributes=True (inherited from FastSerializer) means ORM instances
    serialize via attribute lookup. Test with an in-memory MockCoop."""
    coop = MockCoop(id=7, name="mock-coop")
    fast = from_model(MockCoop, fields=["id", "name"])
    payload = fast.drf(instance=coop).data
    parsed = json.loads(FastJSONRenderer().render(payload))
    assert parsed == {"id": 7, "name": "mock-coop"}
