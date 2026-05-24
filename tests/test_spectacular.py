"""Tests for the optional drf-spectacular extension."""

from datetime import date

from drf_fastserializers import FastSerializer
from drf_fastserializers.spectacular import FastSerializerSchemaExtension


class _Nested(FastSerializer):
    flag: bool = False


class _Txn(FastSerializer):
    id: int
    name: str
    txn_date: date
    nested: _Nested


def test_extension_is_subclass_of_open_api_extension():
    """Smoke test: importing the module wires up the extension class so
    drf-spectacular's metaclass-driven discovery picks it up."""
    from drf_spectacular.extensions import OpenApiSerializerExtension

    assert issubclass(FastSerializerSchemaExtension, OpenApiSerializerExtension)
    assert FastSerializerSchemaExtension.target_class == (
        "drf_fastserializers.serializer.DRFAdapter"
    )
    assert FastSerializerSchemaExtension.match_subclasses is True


def test_extension_emits_pydantic_json_schema():
    """get_name + map_serializer pull from the underlying FastSerializer."""
    adapter_cls = _Txn.drf
    ext = FastSerializerSchemaExtension(adapter_cls)

    name = ext.get_name(auto_schema=None, direction="response")
    assert name == "_Txn"

    schema = ext.map_serializer(auto_schema=None, direction="response")
    assert "properties" in schema
    assert {"id", "name", "txn_date", "nested"} <= set(schema["properties"])


def test_extension_handles_request_vs_response_direction():
    """validation vs serialization mode in pydantic gives slightly different
    schemas (e.g. computed_fields visible only in serialization)."""
    adapter_cls = _Txn.drf
    ext = FastSerializerSchemaExtension(adapter_cls)
    req = ext.map_serializer(auto_schema=None, direction="request")
    res = ext.map_serializer(auto_schema=None, direction="response")
    assert "properties" in req
    assert "properties" in res
