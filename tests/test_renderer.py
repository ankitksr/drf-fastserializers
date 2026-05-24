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


# Composed envelope tests --------------------------------------------------


def test_renderer_composes_mixed_dict(txn_dict: dict):
    """Bundle-style response: multiple FastPayloads + plain values in one dict."""
    payload = {
        "header": TxnOut.drf(instance=txn_dict).data,
        "items": TxnOut.drf(instance=[txn_dict, {**txn_dict, "id": 2}], many=True).data,
        "meta": {"page": 1, "total": 2},
    }
    raw = FastJSONRenderer().render(payload)
    parsed = json.loads(raw)
    assert parsed["header"]["id"] == 1
    assert [r["id"] for r in parsed["items"]] == [1, 2]
    assert parsed["meta"] == {"page": 1, "total": 2}


def test_renderer_composed_all_fastpayloads(txn_dict: dict):
    """Envelope with no plain values: every key is a FastPayload."""
    payload = {
        "a": TxnOut.drf(instance=txn_dict).data,
        "b": TxnOut.drf(instance={**txn_dict, "id": 99}).data,
    }
    raw = FastJSONRenderer().render(payload)
    parsed = json.loads(raw)
    assert parsed["a"]["id"] == 1
    assert parsed["b"]["id"] == 99


def test_renderer_composed_preserves_key_order(txn_dict: dict):
    """Output key order matches input insertion order."""
    payload = {
        "z": {"plain": 1},
        "a": TxnOut.drf(instance=txn_dict).data,
        "m": {"plain": 2},
        "b": TxnOut.drf(instance={**txn_dict, "id": 9}).data,
    }
    raw = FastJSONRenderer().render(payload)
    # Walk the bytes for ordering; json.loads on a plain dict would
    # preserve order in 3.7+ but checking the raw stream is unambiguous.
    assert raw.index(b'"z"') < raw.index(b'"a"') < raw.index(b'"m"') < raw.index(b'"b"')


def test_renderer_composed_handles_special_chars_in_keys(txn_dict: dict):
    """Keys containing `"` or `\\` must still produce valid JSON."""
    payload = {
        'has"quote': TxnOut.drf(instance=txn_dict).data,
        "back\\slash": {"ok": True},
    }
    raw = FastJSONRenderer().render(payload)
    parsed = json.loads(raw)
    assert parsed['has"quote']["id"] == 1
    assert parsed["back\\slash"] == {"ok": True}


def test_renderer_composed_pagination_envelope(txn_dicts: list[dict]):
    """Pagination shape ({count, next, previous, results: FastPayload}) is
    handled by the composed path — no special-case code needed."""
    payload = {
        "count": 100,
        "next": "http://example.com/?page=2",
        "previous": None,
        "results": TxnOut.drf(instance=txn_dicts, many=True).data,
    }
    raw = FastJSONRenderer().render(payload)
    parsed = json.loads(raw)
    assert parsed["count"] == 100
    assert parsed["next"] == "http://example.com/?page=2"
    assert parsed["previous"] is None
    assert [r["id"] for r in parsed["results"]] == [d["id"] for d in txn_dicts]


def test_renderer_composed_indented_falls_back_to_materialization(txn_dict: dict):
    """indent=2 → Rust dump_json can't pretty-print; materialize all FastPayloads."""
    payload = {
        "header": TxnOut.drf(instance=txn_dict).data,
        "meta": {"page": 1},
    }
    raw = FastJSONRenderer().render(
        payload,
        accepted_media_type="application/json",
        renderer_context={"indent": 2},
    )
    parsed = json.loads(raw)
    assert parsed["header"]["id"] == 1
    assert parsed["meta"] == {"page": 1}
    # Indented output has newlines and spaces; the compact-path splice does not.
    assert b"\n" in raw or b": " in raw


def test_renderer_error_envelope_passes_through():
    """A plain error dict (no FastPayload values) should not trigger composed path."""
    raw = FastJSONRenderer().render({"detail": "not found", "code": 404})
    parsed = json.loads(raw)
    assert parsed == {"detail": "not found", "code": 404}
