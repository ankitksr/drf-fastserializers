"""Tests for FastSerializer schema + DRFAdapter wrapper behavior."""

import pytest

from drf_fastserializers import DRFAdapter, FastSerializer, drf_serializer
from drf_fastserializers._payload import FastPayload

from .conftest import Flags, TxnOut


def test_fastserializer_is_pydantic_model():
    txn = TxnOut(
        id=1,
        name="x",
        txn_date="2026-05-01",
        flags=Flags(),
    )
    assert txn.id == 1
    assert txn.flags.is_nsf is False


def test_drf_descriptor_returns_adapter_class():
    adapter_cls = TxnOut.drf
    assert isinstance(adapter_cls, type)
    assert issubclass(adapter_cls, DRFAdapter)
    assert adapter_cls.serializer_cls is TxnOut


def test_drf_descriptor_cached():
    assert TxnOut.drf is TxnOut.drf


def test_drf_descriptor_distinct_per_subclass():
    assert TxnOut.drf is not Flags.drf
    assert TxnOut.drf.serializer_cls is TxnOut
    assert Flags.drf.serializer_cls is Flags


def test_drf_serializer_helper_matches_descriptor():
    assert drf_serializer(TxnOut) is TxnOut.drf


def test_adapter_single_data_returns_marker(txn_dict: dict):
    serializer = TxnOut.drf(instance=txn_dict)
    payload = serializer.data
    assert isinstance(payload, FastPayload)
    assert payload.many is False


def test_adapter_many_data_returns_marker(txn_dicts: list[dict]):
    serializer = TxnOut.drf(instance=txn_dicts, many=True)
    payload = serializer.data
    assert isinstance(payload, FastPayload)
    assert payload.many is True
    assert len(payload) == len(txn_dicts)


def test_payload_lazy_materialize(txn_dicts: list[dict]):
    payload = TxnOut.drf(instance=txn_dicts, many=True).data
    assert payload[0]["id"] == 1
    assert payload[0]["amount"] == "1200.50"  # Decimal → str via mode="json"
    assert payload[0]["flags"]["is_refund"] is True


def test_adapter_is_valid_accepts_good_input(txn_dict: dict):
    serializer = TxnOut.drf(data=txn_dict)
    assert serializer.is_valid() is True
    assert serializer.errors == {}
    assert isinstance(serializer.validated_data, TxnOut)
    assert serializer.validated_data.id == 1


def test_adapter_is_valid_rejects_bad_input():
    serializer = TxnOut.drf(data={"id": "not-an-int", "name": "x"})
    assert serializer.is_valid() is False
    assert "id" in serializer.errors
    assert "txn_date" in serializer.errors  # missing required field
    assert "flags" in serializer.errors  # missing required field


def test_adapter_is_valid_raises_when_asked():
    from rest_framework.exceptions import ValidationError as DRFValidationError

    serializer = TxnOut.drf(data={"id": "not-an-int"})
    with pytest.raises(DRFValidationError):
        serializer.is_valid(raise_exception=True)


def test_adapter_is_valid_many(txn_dicts: list[dict]):
    serializer = TxnOut.drf(data=txn_dicts, many=True)
    assert serializer.is_valid() is True
    assert len(serializer.validated_data) == len(txn_dicts)
    assert all(isinstance(v, TxnOut) for v in serializer.validated_data)


def test_adapter_is_valid_without_data_raises():
    serializer = TxnOut.drf(instance={"id": 1})
    with pytest.raises(RuntimeError, match="data="):
        serializer.is_valid()


def test_adapter_accepts_django_model_via_from_attributes():
    """from_attributes=True (model_config default) lets validate_python pull
    fields off ORM instances or any attribute-accessible object."""

    class _Obj:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    obj = _Obj(
        id=42,
        name="orm",
        amount=None,
        txn_date="2026-05-01",
        flags=_Obj(is_nsf=False, is_refund=False),
        tags=[],
    )
    payload = TxnOut.drf(instance=obj).data
    assert payload["id"] == 42
    assert payload["name"] == "orm"


class _MoreFields(FastSerializer):
    label: str
    count: int = 0


def test_subclass_gets_independent_adapter_cache():
    """Regression: descriptor must not leak adapters across FastSerializer subclasses."""
    assert _MoreFields.drf.serializer_cls is _MoreFields
    payload = _MoreFields.drf(instance={"label": "z"}).data
    assert payload["label"] == "z"
    assert payload["count"] == 0
