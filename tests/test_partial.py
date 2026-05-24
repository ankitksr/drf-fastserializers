"""Tests for partial=True semantics on DRFAdapter.is_valid."""

from datetime import date

from drf_fastserializers import FastSerializer


class _Txn(FastSerializer):
    id: int
    name: str
    txn_date: date


def test_partial_accepts_missing_fields():
    """partial=True relaxes every field to optional with default None."""
    serializer = _Txn.drf(data={"name": "only-name"}, partial=True)
    assert serializer.is_valid() is True
    assert serializer.validated_data.name == "only-name"
    assert serializer.validated_data.id is None
    assert serializer.validated_data.txn_date is None


def test_partial_still_validates_types():
    """partial relaxes presence, not type. Bad types still fail."""
    serializer = _Txn.drf(data={"id": "not-an-int"}, partial=True)
    assert serializer.is_valid() is False
    assert "id" in serializer.errors


def test_non_partial_requires_all_fields():
    """Default partial=False keeps the strict required check."""
    serializer = _Txn.drf(data={"name": "only-name"})
    assert serializer.is_valid() is False
    assert "id" in serializer.errors
    assert "txn_date" in serializer.errors


def test_partial_model_dump_exclude_unset():
    """validated_data carries the partial variant; exclude_unset reveals
    exactly which fields the client sent."""
    serializer = _Txn.drf(data={"name": "patched"}, partial=True)
    serializer.is_valid()
    patch = serializer.validated_data.model_dump(exclude_unset=True)
    assert patch == {"name": "patched"}


def test_partial_variant_is_cached():
    """Two consecutive partial=True calls share the same generated class."""
    s1 = _Txn.drf(data={"name": "a"}, partial=True)
    s1.is_valid()
    s2 = _Txn.drf(data={"name": "b"}, partial=True)
    s2.is_valid()
    assert type(s1.validated_data) is type(s2.validated_data)
