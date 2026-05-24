"""DRF renderer that dispatches `FastPayload` to pydantic-core's Rust encoder.

Drop into a view's `renderer_classes`:

    class MyView(ListAPIView):
        renderer_classes = [FastJSONRenderer]
        serializer_class = TxnOut.drf

Falls back to the stock `JSONRenderer` for any non-`FastPayload` payload
(error responses, browsable API previews, hand-rolled dicts, etc.), so
it is safe as a global default renderer in `REST_FRAMEWORK` settings.
"""

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

        if isinstance(data, dict) and isinstance(data.get("results"), FastPayload):
            return self._render_paginated(data, accepted_media_type, renderer_context)

        return super().render(data, accepted_media_type, renderer_context)

    # DRF pagination wraps payloads as {"results": <FastPayload>, "next": ...}.
    # Encode the inner payload with Rust, encode the wrapper with stock JSON,
    # then splice the bytes. Cheap and correct: pagination metadata is small,
    # results are the bulk.
    def _render_paginated(
        self,
        data: dict[str, Any],
        accepted_media_type: str | None,
        renderer_context: dict[str, Any] | None,
    ) -> bytes:
        marker: FastPayload = data["results"]
        inner = marker.adapter.dump_json(marker.instances)
        wrapper = {k: v for k, v in data.items() if k != "results"}
        wrapper_bytes = super().render(wrapper, accepted_media_type, renderer_context)
        if not wrapper_bytes.endswith(b"}"):
            # super().render may emit indented form; fall back to full materialize
            return super().render(
                {**wrapper, "results": marker._materialize()},
                accepted_media_type,
                renderer_context,
            )
        head = wrapper_bytes[:-1]
        sep = b"," if wrapper else b""
        return head + sep + b'"results":' + inner + b"}"
