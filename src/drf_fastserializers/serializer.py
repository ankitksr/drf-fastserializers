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

import json
from collections.abc import Callable, Mapping
from typing import Any, ClassVar, Final

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from ._errors import pydantic_errors_to_drf
from ._payload import FastPayload, RawJSONBytes

_UNSET: Final = object()


class _AttrOverlay:
    """Read-through wrapper that returns overridden values for select keys.

    Used to inject pre-resolved `SerializerMethodField` results into a
    source object (Django model, dataclass, ...) without copying it, so
    pydantic's `from_attributes` validation reads the override for SMF
    field names and the underlying object for everything else.
    """

    __slots__ = ("_obj", "_overrides")

    def __init__(self, obj: Any, overrides: dict[str, Any]) -> None:
        object.__setattr__(self, "_obj", obj)
        object.__setattr__(self, "_overrides", overrides)

    def __getattr__(self, name: str) -> Any:
        overrides = object.__getattribute__(self, "_overrides")
        if name in overrides:
            return overrides[name]
        return getattr(object.__getattribute__(self, "_obj"), name)


def _overlay_one(obj: Any, getters: dict[str, Callable[[Any], Any]]) -> Any:
    """Pre-resolve SMF getters against `obj` and inject as an overlay.

    Dict sources merge directly (pydantic accepts dicts via
    `from_attributes`). Object sources get wrapped in `_AttrOverlay`.
    """
    overrides = {name: g(obj) for name, g in getters.items()}
    if isinstance(obj, Mapping):
        merged = dict(obj)
        merged.update(overrides)
        return merged
    return _AttrOverlay(obj, overrides)


def _apply_method_overrides(
    serializer_cls: type["FastSerializer"], source: Any, many: bool
) -> Any:
    """Inject SMF getter results into `source` so pydantic reads them via attrs.

    Returns `source` unchanged when no SMF getters are registered (the
    common case — only `from_drf`-generated classes carry a getter table).
    """
    getters = getattr(serializer_cls, "_fs_method_getters", None)
    if not getters:
        return source
    if many:
        return [_overlay_one(obj, getters) for obj in source]
    return _overlay_one(source, getters)


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


# Cache of partial variants keyed by source class. A partial variant is a
# clone where every declared field is widened to `T | None` with default
# `None`, mirroring DRF's `partial=True` semantics: any subset of fields
# may be omitted on input.
_partial_variant_cache: dict[type, type] = {}


def _partial_variant(cls: type["FastSerializer"]) -> type["FastSerializer"]:
    """Return a clone of `cls` where every field is optional with default None."""
    cached = _partial_variant_cache.get(cls)
    if cached is not None:
        return cached
    from pydantic import create_model

    field_defs: dict[str, tuple[Any, Any]] = {}
    for fname, info in cls.model_fields.items():
        widened = info.annotation | None if info.annotation is not None else Any
        field_defs[fname] = (widened, None)
    variant = create_model(
        f"{cls.__name__}Partial",
        __base__=FastSerializer,
        **field_defs,
    )
    _partial_variant_cache[cls] = variant
    return variant


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
            source = _apply_method_overrides(self.serializer_cls, self.instance, self.many)
            self._validated = adapter.validate_python(source)
        return FastPayload(adapter=adapter, instances=self._validated, many=self.many)

    # --- write path ----------------------------------------------------

    def is_valid(self, raise_exception: bool = False) -> bool:
        if self.initial_data is None:
            raise RuntimeError("is_valid() called without data; pass data=... at construction")
        adapter = self._adapter()
        # SerializerMethodField is read-only: drop any client-supplied values
        # for those names before validation so they cannot pollute
        # `validated_data`. Pure-pydantic schemas (no `_fs_method_getters`)
        # take the unmodified fast path.
        smf_names = getattr(self.serializer_cls, "_fs_method_getters", None)
        try:
            # `FastJSONParser` hands us bytes wrapped in `RawJSONBytes`;
            # validate_json runs in Rust over those bytes, skipping the
            # Python json.loads + validate_python double-walk.
            if isinstance(self.initial_data, RawJSONBytes):
                if smf_names:
                    decoded = json.loads(self.initial_data.raw)
                    for name in smf_names:
                        decoded.pop(name, None)
                    self._validated = adapter.validate_python(decoded)
                else:
                    self._validated = adapter.validate_json(self.initial_data.raw)
            else:
                data = self.initial_data
                if smf_names and isinstance(data, Mapping):
                    data = {k: v for k, v in data.items() if k not in smf_names}
                self._validated = adapter.validate_python(data)
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
        cls = _partial_variant(self.serializer_cls) if self.partial else self.serializer_cls
        return _list_adapter(cls) if self.many else _single_adapter(cls)


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

    @classmethod
    def values_fields(cls, *, exclude: tuple[str, ...] = ()) -> tuple[str, ...]:
        """Return field names for `QuerySet.values(*...)` projection.

        Lets you spell the projection once, on the schema, instead of
        re-typing field names in every view::

            qs = Txn.objects.values(*TxnOut.values_fields())

        Computed fields (declared with `@computed_field`) are excluded;
        only declared model fields are returned, matching what the ORM
        knows how to project.
        """
        return tuple(name for name in cls.model_fields if name not in exclude)


def drf_serializer(serializer_cls: type[FastSerializer]) -> type[DRFAdapter]:
    """Functional alternative to `Schema.drf` when you prefer explicit imports."""
    return _make_adapter(serializer_cls)
