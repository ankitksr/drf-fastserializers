"""Tests for FastJSONRenderer dispatch + fallback."""

import json

from drf_fastserializers import FastJSONRenderer

from .conftest import TxnOut


def test_renderer_dispatches_to_rust_path(txn_dicts: list[dict]):
    payload = TxnOut.drf(instance=txn_dicts, many=True).data
    raw = FastJSONRenderer().render(payload)
    assert isinstance(raw, bytes)
    parsed = json.loads(raw)
    assert isinstance(parsed, list)
    assert len(parsed) == len(txn_dicts)


def test_rust_path_emits_compact_json(txn_dicts: list[dict]):
    """pydantic-core dump_json emits without spaces; json.dumps inserts ': '.
    The presence of the latter would indicate accidental fallback."""
    payload = TxnOut.drf(instance=txn_dicts, many=True).data
    raw = FastJSONRenderer().render(payload)
    assert b": " not in raw, "Renderer fell back to Python json.dumps"


def test_renderer_falls_back_for_plain_dict():
    """Non-FastPayload payloads — error responses, hand-rolled dicts — must
    still render through the parent JSONRenderer."""
    raw = FastJSONRenderer().render({"detail": "not found"})
    assert raw == b'{"detail":"not found"}'


def test_renderer_falls_back_for_plain_list():
    raw = FastJSONRenderer().render([1, 2, 3])
    assert raw == b"[1,2,3]"


def test_renderer_single_instance(txn_dict: dict):
    payload = TxnOut.drf(instance=txn_dict).data
    raw = FastJSONRenderer().render(payload)
    parsed = json.loads(raw)
    assert parsed["id"] == 1
    assert parsed["flags"]["is_refund"] is True
