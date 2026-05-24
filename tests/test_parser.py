"""Tests for FastJSONParser + the Rust input path on DRFAdapter.is_valid."""

import io

import pytest

from drf_fastserializers import FastJSONParser, FastSerializer
from drf_fastserializers._payload import RawJSONBytes


class _PayloadIn(FastSerializer):
    id: int
    name: str


def test_parser_returns_raw_json_bytes():
    parser = FastJSONParser()
    stream = io.BytesIO(b'{"id": 1, "name": "x"}')
    result = parser.parse(stream)
    assert isinstance(result, RawJSONBytes)
    assert result.raw == b'{"id": 1, "name": "x"}'


def test_raw_json_bytes_lazy_decode():
    """Anything that treats RawJSONBytes as a dict triggers a one-time decode."""
    marker = RawJSONBytes(b'{"id": 1, "name": "x"}')
    assert marker["id"] == 1
    assert marker["name"] == "x"
    assert "id" in marker
    assert marker.get("missing", "default") == "default"


def test_adapter_is_valid_uses_validate_json_on_raw_bytes():
    """DRFAdapter must detect RawJSONBytes and route to validate_json."""
    marker = RawJSONBytes(b'{"id": 42, "name": "fast"}')
    serializer = _PayloadIn.drf(data=marker)
    assert serializer.is_valid() is True
    assert serializer.validated_data.id == 42
    assert serializer.validated_data.name == "fast"


def test_adapter_is_valid_invalid_raw_bytes():
    marker = RawJSONBytes(b'{"id": "not-an-int", "name": "x"}')
    serializer = _PayloadIn.drf(data=marker)
    assert serializer.is_valid() is False
    assert "id" in serializer.errors


def test_adapter_is_valid_still_handles_python_dict():
    """Backwards compat: standard JSONParser passing dict still works."""
    serializer = _PayloadIn.drf(data={"id": 7, "name": "py"})
    assert serializer.is_valid() is True
    assert serializer.validated_data.id == 7


def test_parser_handles_str_stream():
    """Some test setups pass a StringIO; parser must encode to bytes."""

    class _StrStream:
        def read(self):
            return '{"id": 9, "name": "str"}'

    parser = FastJSONParser()
    result = parser.parse(_StrStream())
    assert result.raw == b'{"id": 9, "name": "str"}'


def test_parser_raises_parse_error_on_read_failure():
    from rest_framework.exceptions import ParseError

    class _BrokenStream:
        def read(self):
            raise OSError("disk gone")

    with pytest.raises(ParseError, match="Could not read"):
        FastJSONParser().parse(_BrokenStream())
