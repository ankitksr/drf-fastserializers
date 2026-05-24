"""Marker payloads exchanged between subsystems.

`FastPayload` (output side) carries validated pydantic instances + the
TypeAdapter needed to encode them. The renderer recognizes the type and
routes encoding to `dump_json` (Rust). Anything that treats it as a
dict/list lazy-materializes via `dump_python`.

`RawJSONBytes` (input side) wraps raw request body bytes so that the
matching `DRFAdapter.is_valid` can hand them straight to `validate_json`
(Rust). Anything else reading `request.data` sees a dict-like proxy
that decodes on demand.
"""

import json
from typing import Any

from pydantic import TypeAdapter


class FastPayload:
    """Lazily-materialized JSON payload.

    Renderers detect this type and emit Rust-encoded bytes via
    `adapter.dump_json`. Anything that subscripts or iterates falls back
    to a one-time Python materialization for compatibility.
    """

    __slots__ = ("adapter", "instances", "many", "_materialized")

    def __init__(self, adapter: TypeAdapter, instances: Any, many: bool) -> None:
        self.adapter = adapter
        self.instances = instances
        self.many = many
        self._materialized: Any = None

    def _materialize(self) -> Any:
        if self._materialized is None:
            self._materialized = self.adapter.dump_python(self.instances, mode="json")
        return self._materialized

    def __getitem__(self, key: Any) -> Any:
        return self._materialize()[key]

    def __iter__(self):
        return iter(self._materialize())

    def __len__(self) -> int:
        return len(self._materialize())

    def __contains__(self, item: Any) -> bool:
        return item in self._materialize()

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FastPayload):
            return self._materialize() == other._materialize()
        return self._materialize() == other

    def __repr__(self) -> str:
        return f"FastPayload(many={self.many})"


class RawJSONBytes:
    """Lazy-decoded JSON payload from a `FastJSONParser`.

    Holds the raw request body for the fast input path (validate_json
    runs in Rust over bytes). Falls back to a one-time `json.loads`
    when something else accesses the payload as a Python container.
    """

    __slots__ = ("raw", "_parsed")

    def __init__(self, raw: bytes) -> None:
        self.raw = raw
        self._parsed: Any = None

    def _decode(self) -> Any:
        if self._parsed is None:
            self._parsed = json.loads(self.raw or b"null")
        return self._parsed

    def __getitem__(self, key: Any) -> Any:
        return self._decode()[key]

    def __iter__(self):
        return iter(self._decode())

    def __len__(self) -> int:
        return len(self._decode())

    def __contains__(self, item: Any) -> bool:
        return item in self._decode()

    def get(self, key: Any, default: Any = None) -> Any:
        decoded = self._decode()
        if isinstance(decoded, dict):
            return decoded.get(key, default)
        return default

    def keys(self):
        return self._decode().keys()

    def values(self):
        return self._decode().values()

    def items(self):
        return self._decode().items()

    def __repr__(self) -> str:
        return f"RawJSONBytes({len(self.raw)} bytes)"
