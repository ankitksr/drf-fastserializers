"""Marker payload exchanged between serializer adapter and renderer.

`FastPayload` carries the validated pydantic instances plus the TypeAdapter
needed to encode them. The renderer recognizes the type and routes encoding
to `dump_json` (Rust). Anything else (middleware, tests, paginators) that
treats the payload as a dict/list lazy-materializes via `dump_python`.
"""

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
