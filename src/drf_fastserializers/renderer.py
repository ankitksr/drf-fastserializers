"""DRF renderer that dispatches `FastPayload` to pydantic-core's Rust encoder.

Drop into a view's `renderer_classes`:

    class MyView(ListAPIView):
        renderer_classes = [FastJSONRenderer]
        serializer_class = TxnOut.drf

Three input shapes are handled directly:

- A bare `FastPayload` (most views) → `adapter.dump_json` (Rust).
- A dict with any `FastPayload` values (composed bundles, pagination
  envelopes, etc.) → per-value walk; FastPayloads encode via Rust,
  everything else via DRF's stock `JSONEncoder`.
- Anything else (error responses, hand-rolled dicts, the browsable API,
  ...) → super().render(), unchanged.

The renderer is safe as a project-wide default.
"""

import json
from typing import Any

from rest_framework.renderers import JSONRenderer

from ._payload import FastPayload


class FastJSONRenderer(JSONRenderer):
    """JSON renderer that uses pydantic-core when given a `FastPayload`."""

    def render(
        self,
        data: Any,
        accepted_media_type: str | None = None,
        renderer_context: dict[str, Any] | None = None,
    ) -> bytes:
        if isinstance(data, FastPayload):
            return data.adapter.dump_json(data.instances)

        if isinstance(data, dict) and any(isinstance(v, FastPayload) for v in data.values()):
            return self._render_composed(data, accepted_media_type, renderer_context)

        return super().render(data, accepted_media_type, renderer_context)

    # Compose dict responses whose values are a mix of `FastPayload` markers
    # (Rust-encoded) and arbitrary Python (encoded via DRF's JSONEncoder).
    # Walks `data` in insertion order so output key order matches input.
    # Pagination envelopes (`{"results": FastPayload, "count": int, ...}`)
    # are a subset of this case — no separate pagination path.
    def _render_composed(
        self,
        data: dict[str, Any],
        accepted_media_type: str | None,
        renderer_context: dict[str, Any] | None,
    ) -> bytes:
        ctx = renderer_context or {}
        indent = self.get_indent(accepted_media_type, ctx)
        # Indented or non-compact output can't be assembled cleanly by
        # byte-splicing — pydantic-core's dump_json output is compact,
        # and join bytes would have no indentation. Materialize every
        # `FastPayload` and route through super() for a consistent
        # pretty-printed response. The fast path is the common case
        # (default DRF settings: compact=True, indent=None).
        if indent is not None or not self.compact:
            materialized = {
                k: v._materialize() if isinstance(v, FastPayload) else v
                for k, v in data.items()
            }
            return super().render(materialized, accepted_media_type, renderer_context)

        parts: list[bytes] = [b"{"]
        for i, (k, v) in enumerate(data.items()):
            if i > 0:
                parts.append(b",")
            # json.dumps handles quote/backslash/control-char escaping in keys
            # so a user dict with `{'a"b': ...}` still produces valid JSON.
            parts.append(json.dumps(k, ensure_ascii=self.ensure_ascii).encode("utf-8"))
            parts.append(b":")
            if isinstance(v, FastPayload):
                parts.append(v.adapter.dump_json(v.instances))
            else:
                parts.append(
                    json.dumps(
                        v,
                        cls=self.encoder_class,
                        ensure_ascii=self.ensure_ascii,
                        allow_nan=not self.strict,
                        separators=(",", ":"),
                    ).encode("utf-8")
                )
        parts.append(b"}")
        return b"".join(parts)
