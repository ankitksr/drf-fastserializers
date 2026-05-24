"""Tests for `FastSerializerMixin` — in-place acceleration of DRF serializers."""

import json
import warnings
from datetime import date
from decimal import Decimal

import pytest
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from drf_fastserializers import (
    FastJSONRenderer,
    FastListSerializer,
    FastSerializerMixin,
)
from drf_fastserializers._payload import FastPayload


class _FlagsDRF(serializers.Serializer):
    is_nsf = serializers.BooleanField(default=False)


class _AcceleratedTxn(FastSerializerMixin, serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True)
    txn_date = serializers.DateField()
    flags = _FlagsDRF()


@pytest.fixture
def txn_instance() -> dict:
    return {
        "id": 1,
        "name": "rent",
        "amount": Decimal("1200.50"),
        "txn_date": date(2026, 5, 1),
        "flags": {"is_nsf": False},
    }


def _reset(cls: type) -> None:
    for attr in ("_fast_schema_resolved", "_fast_schema_cache"):
        if attr in cls.__dict__:
            delattr(cls, attr)


@pytest.fixture(autouse=True)
def _reset_translation_cache():
    """Clear per-class translation cache between tests so warnings re-fire."""
    yield
    _reset(_AcceleratedTxn)


def test_mixin_data_returns_fast_payload(txn_instance: dict):
    serializer = _AcceleratedTxn(instance=txn_instance)
    payload = serializer.data
    assert isinstance(payload, FastPayload)


def test_mixin_renders_via_rust(txn_instance: dict):
    serializer = _AcceleratedTxn(instance=txn_instance)
    raw = FastJSONRenderer().render(serializer.data)
    parsed = json.loads(raw)
    assert parsed["id"] == 1
    assert parsed["amount"] == "1200.50"
    assert b": " not in raw, "Should use compact Rust encoder, not json.dumps"


def test_mixin_many_uses_fast_list_serializer(txn_instance: dict):
    serializer = _AcceleratedTxn(instance=[txn_instance, {**txn_instance, "id": 2}], many=True)
    assert isinstance(serializer, FastListSerializer)
    payload = serializer.data
    assert isinstance(payload, FastPayload)
    parsed = json.loads(FastJSONRenderer().render(payload))
    assert len(parsed) == 2
    assert parsed[1]["id"] == 2


def test_mixin_falls_back_when_translation_fails():
    """SerializerMethodField → warning + DRF .data fallback (no Rust speedup)."""

    class _Unaccelerable(FastSerializerMixin, serializers.Serializer):
        id = serializers.IntegerField()
        derived = serializers.SerializerMethodField()

        def get_derived(self, obj):
            return obj["id"] * 10

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        serializer = _Unaccelerable(instance={"id": 3})
        data = serializer.data

    # super().data returns ReturnDict, not FastPayload
    assert not isinstance(data, FastPayload)
    assert data["derived"] == 30
    assert any("auto-translate" in str(w.message) for w in caught)


def test_mixin_meta_fast_false_opts_out_silently(txn_instance: dict):
    class _OptedOut(FastSerializerMixin, serializers.Serializer):
        id = serializers.IntegerField()
        derived = serializers.SerializerMethodField()

        class Meta:
            fast = False

        def get_derived(self, obj):
            return obj["id"] * 10

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        serializer = _OptedOut(instance={"id": 5})
        data = serializer.data
    assert not isinstance(data, FastPayload)
    assert data["derived"] == 50
    assert not any("auto-translate" in str(w.message) for w in caught)


def test_mixin_view_integration(txn_instance: dict):
    """Drop-in: existing DRF view, only the serializer class changes."""

    class _ListView(APIView):
        permission_classes = [AllowAny]
        renderer_classes = [FastJSONRenderer]
        rows: list = []

        def get(self, request, *args, **kwargs):
            return Response(_AcceleratedTxn(instance=self.rows, many=True).data)

    _ListView.rows = [txn_instance, {**txn_instance, "id": 9}]
    response = _ListView.as_view()(APIRequestFactory().get("/list/"))
    response.render()

    assert response.status_code == 200
    body = json.loads(response.content)
    assert len(body) == 2
    assert body[1]["id"] == 9
    assert b": " not in response.content
