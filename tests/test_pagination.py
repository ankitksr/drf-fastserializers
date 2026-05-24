"""Tests for renderer's pagination wrapper splice."""

import json

from drf_fastserializers import FastJSONRenderer

from .conftest import TxnOut


def test_paginated_payload_splice(txn_dicts: list[dict]):
    """Paginators wrap as {'results': <FastPayload>, 'count': ..., 'next': ...}.
    Renderer must encode `results` via Rust + splice into wrapper bytes."""
    payload = TxnOut.drf(instance=txn_dicts, many=True).data
    wrapped = {
        "count": 100,
        "next": "http://x/?page=3",
        "previous": "http://x/?page=1",
        "results": payload,
    }
    raw = FastJSONRenderer().render(wrapped)
    parsed = json.loads(raw)
    assert parsed["count"] == 100
    assert parsed["next"] == "http://x/?page=3"
    assert parsed["previous"] == "http://x/?page=1"
    assert isinstance(parsed["results"], list)
    assert len(parsed["results"]) == len(txn_dicts)
    assert parsed["results"][0]["id"] == 1


def test_paginated_with_only_results_key(txn_dicts: list[dict]):
    """Edge case: paginator emits only `results`."""
    payload = TxnOut.drf(instance=txn_dicts, many=True).data
    raw = FastJSONRenderer().render({"results": payload})
    parsed = json.loads(raw)
    assert "results" in parsed
    assert len(parsed["results"]) == len(txn_dicts)


def test_paginated_nested_metadata(txn_dicts: list[dict]):
    """Renderer should preserve arbitrary wrapper metadata (counts, nested dicts)."""
    payload = TxnOut.drf(instance=txn_dicts, many=True).data
    raw = FastJSONRenderer().render(
        {
            "meta": {"page": 2, "page_size": 5},
            "results": payload,
        }
    )
    parsed = json.loads(raw)
    assert parsed["meta"]["page"] == 2
    assert parsed["meta"]["page_size"] == 5
    assert len(parsed["results"]) == len(txn_dicts)
