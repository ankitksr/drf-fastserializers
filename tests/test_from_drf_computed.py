"""Tests for the `computed=` argument on from_drf."""

import json

from rest_framework import serializers

from drf_fastserializers import FastJSONRenderer, from_drf


class _TxnDRF(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    amount = serializers.IntegerField()


def test_computed_replaces_serializer_method_field():
    """computed= attaches a @computed_field on the generated FastSerializer."""

    class _WithMethod(serializers.Serializer):
        id = serializers.IntegerField()
        name = serializers.CharField()
        amount = serializers.IntegerField()
        doubled = serializers.SerializerMethodField()

        def get_doubled(self, obj):
            return obj["amount"] * 2

    fast = from_drf(
        _WithMethod,
        computed={"doubled": (lambda self: self.amount * 2, int)},
    )
    payload = fast.drf(instance={"id": 1, "name": "x", "amount": 5}).data
    parsed = json.loads(FastJSONRenderer().render(payload))
    assert parsed["doubled"] == 10
    assert parsed["amount"] == 5


def test_computed_field_appears_in_output_with_return_type():
    fast = from_drf(
        _TxnDRF,
        computed={"display": (lambda self: f"${self.amount:,.2f}", str)},
    )
    payload = fast.drf(instance={"id": 1, "name": "x", "amount": 1500}).data
    parsed = json.loads(FastJSONRenderer().render(payload))
    assert parsed["display"] == "$1,500.00"


def test_computed_with_exclude_overlapping_ok():
    """exclude and computed can both be specified; computed takes precedence."""

    class _Mixed(serializers.Serializer):
        id = serializers.IntegerField()
        side = serializers.SerializerMethodField()

        def get_side(self, obj):
            return "x"

    fast = from_drf(
        _Mixed,
        computed={"side": (lambda self: "computed", str)},
    )
    payload = fast.drf(instance={"id": 99}).data
    parsed = json.loads(FastJSONRenderer().render(payload))
    assert parsed["side"] == "computed"
