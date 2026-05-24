"""FastSerializer schema base + DRF-compatible adapter.

Define schemas as pydantic models:

    class TxnOut(FastSerializer):
        id: int
        name: str

Use the auto-generated DRF adapter in a view:

    class MyView(ListAPIView):
        serializer_class = TxnOut.drf
        renderer_classes = [FastJSONRenderer]

`TxnOut.drf` returns a `DRFAdapter` subclass bound to `TxnOut`. The adapter
quacks like `rest_framework.serializers.Serializer` for the read path
(`.data`) and the write path (`.is_valid()`, `.validated_data`, `.errors`).
"""

from typing import Any, ClassVar, Final

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from ._errors import pydantic_errors_to_drf
from ._payload import FastPayload

_UNSET: Final = object()


def _single_adapter(cls: type["FastSerializer"]) -> TypeAdapter:
    cached = cls.__dict__.get("_fs_single_adapter")
    if cached is None:
        cached = TypeAdapter(cls)
        cls._fs_single_adapter = cached  # type: ignore[attr-defined]
    return cached


def _list_adapter(cls: type["FastSerializer"]) -> TypeAdapter:
    cached = cls.__dict__.get("_fs_list_adapter")
    if cached is None:
        cached = TypeAdapter(list[cls])  # type: ignore[valid-type]
        cls._fs_list_adapter = cached  # type: ignore[attr-defined]
    return cached


class DRFAdapter:
    """DRF-shaped wrapper around a `FastSerializer` subclass.

    One concrete subclass per `FastSerializer`, generated on demand via
    `FastSerializer.drf` and cached process-wide.
    """

    serializer_cls: ClassVar[type["FastSerializer"]]

    def __init__(
        self,
        instance: Any = _UNSET,
        data: Any = _UNSET,
        many: bool = False,
        partial: bool = False,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.instance = None if instance is _UNSET else instance
        self.initial_data = None if data is _UNSET else data
        self.many = many
        self.partial = partial
        self.context = context or {}
        self._validated: Any = None
        self._errors: dict[str, list[str]] = {}

    # --- read path -----------------------------------------------------

    @property
    def data(self) -> FastPayload:
        """Marker payload. `FastJSONRenderer` emits Rust-encoded bytes."""
        adapter = self._adapter()
        if self._validated is None:
            self._validated = adapter.validate_python(self.instance)
        return FastPayload(adapter=adapter, instances=self._validated, many=self.many)

    # --- write path ----------------------------------------------------

    def is_valid(self, raise_exception: bool = False) -> bool:
        if self.initial_data is None:
            raise RuntimeError("is_valid() called without data; pass data=... at construction")
        adapter = self._adapter()
        try:
            self._validated = adapter.validate_python(self.initial_data)
            self._errors = {}
            return True
        except ValidationError as exc:
            self._errors = pydantic_errors_to_drf(exc)
            if raise_exception:
                from rest_framework.exceptions import ValidationError as DRFValidationError

                raise DRFValidationError(self._errors) from exc
            return False

    @property
    def errors(self) -> dict[str, list[str]]:
        return self._errors

    @property
    def validated_data(self) -> Any:
        return self._validated

    # --- internals -----------------------------------------------------

    def _adapter(self) -> TypeAdapter:
        return (
            _list_adapter(self.serializer_cls)
            if self.many
            else _single_adapter(self.serializer_cls)
        )


# Per-FastSerializer cache of generated adapter classes.
_adapter_cache: dict[type, type[DRFAdapter]] = {}


def _make_adapter(serializer_cls: type["FastSerializer"]) -> type[DRFAdapter]:
    cached = _adapter_cache.get(serializer_cls)
    if cached is not None:
        return cached
    name = f"{serializer_cls.__name__}Adapter"
    cls = type(name, (DRFAdapter,), {"serializer_cls": serializer_cls})
    _adapter_cache[serializer_cls] = cls
    return cls


class _DRFAccessor:
    """Class-level descriptor exposing the bound DRF adapter as `.drf`.

    Resolves at attribute access (`TxnOut.drf`), so any pydantic-side class
    construction is unaffected. Returns the descriptor itself when accessed
    on the `FastSerializer` base to keep error messages legible.
    """

    def __get__(self, instance: Any, owner: type | None = None) -> Any:
        if owner is None or owner is FastSerializer:
            return self
        return _make_adapter(owner)

    def __repr__(self) -> str:
        return "<FastSerializer.drf accessor>"


class FastSerializer(BaseModel):
    """Pydantic-backed serializer schema.

    Subclass and define fields as standard pydantic annotations. Use
    `YourSchema.drf` (a `DRFAdapter` subclass) wherever DRF expects a
    `serializer_class`. Wire `FastJSONRenderer` into `renderer_classes`
    to unlock the Rust JSON encode path; the renderer falls back cleanly
    for any non-FastSerializer payload.
    """

    model_config = ConfigDict(extra="ignore", from_attributes=True)

    drf: ClassVar = _DRFAccessor()


def drf_serializer(serializer_cls: type[FastSerializer]) -> type[DRFAdapter]:
    """Functional alternative to `Schema.drf` when you prefer explicit imports."""
    return _make_adapter(serializer_cls)
