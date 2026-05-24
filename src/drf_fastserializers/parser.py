"""DRF parser that keeps the input path on the Rust side.

`JSONParser` reads `request.body`, decodes via Python's `json.loads`,
and returns a Python dict. The matching `FastSerializer.is_valid` then
re-walks that dict with `validate_python`. Two passes, both in Python.

`FastJSONParser` skips the first pass. It wraps the raw request body in
a `RawJSONBytes` marker; `DRFAdapter.is_valid` detects the marker and
hands the bytes to `validate_json` (Rust). Anything else that reads
`request.data` sees a dict-like proxy that decodes on demand, so
middleware, tests, and views that bypass our adapter keep working.

Wire it globally::

    REST_FRAMEWORK = {
        "DEFAULT_PARSER_CLASSES": [
            "drf_fastserializers.FastJSONParser",
        ],
    }

Or per view::

    class TxnCreateView(APIView):
        parser_classes = [FastJSONParser]
        renderer_classes = [FastJSONRenderer]
"""

from typing import Any

from rest_framework.exceptions import ParseError
from rest_framework.parsers import JSONParser

from ._payload import RawJSONBytes


class FastJSONParser(JSONParser):
    """JSON parser that defers decode to the validator.

    Returns a `RawJSONBytes` marker carrying the unparsed request body.
    `DRFAdapter.is_valid` routes markers to `validate_json` (Rust);
    everything else triggers a lazy `json.loads` on first access.
    """

    media_type = "application/json"

    def parse(
        self,
        stream: Any,
        media_type: str | None = None,
        parser_context: dict[str, Any] | None = None,
    ) -> RawJSONBytes:
        try:
            raw = stream.read()
        except OSError as exc:
            raise ParseError(f"Could not read request body: {exc}") from exc
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        return RawJSONBytes(raw)
