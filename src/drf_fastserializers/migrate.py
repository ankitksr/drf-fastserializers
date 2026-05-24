"""Translate `rest_framework.serializers.Serializer` classes into `FastSerializer`.

`from_drf(MyExistingSerializer)` walks `serializer.fields` and builds an
equivalent pydantic-backed schema at runtime. Use the result as you would
any other `FastSerializer`:

    FastTxnOut = from_drf(TxnSerializer)

    class MyView(ListAPIView):
        serializer_class = FastTxnOut.drf
        renderer_classes = [FastJSONRenderer]

Limits: `SerializerMethodField` and DRF fields with overridden
`to_representation` have no mechanical equivalent. The helper raises
`MigrationError` naming the offending field; convert those manually
using pydantic's `@computed_field`, then exclude them from `from_drf`.
"""

from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import AliasPath, Field, computed_field, create_model
from rest_framework import serializers as drf

from .serializer import FastSerializer

# Exact-type DRF field → pydantic type mapping. Subclasses are handled by
# walking MRO below. ListSerializer / Serializer / ListField / SerializerMethodField
# are special-cased before this table is consulted.
_SCALAR_MAP: dict[type[drf.Field], type] = {
    drf.CharField: str,
    drf.EmailField: str,
    drf.URLField: str,
    drf.SlugField: str,
    drf.RegexField: str,
    drf.IntegerField: int,
    drf.FloatField: float,
    drf.DecimalField: Decimal,
    drf.BooleanField: bool,
    drf.DateField: date,
    drf.DateTimeField: datetime,
    drf.TimeField: time,
    drf.DurationField: timedelta,
    drf.UUIDField: UUID,
    drf.IPAddressField: str,
    drf.FileField: str,
    drf.ImageField: str,
    drf.ChoiceField: str,
    drf.JSONField: Any,  # type: ignore[dict-item]
    drf.DictField: dict,
    drf.HStoreField: dict,
    drf.PrimaryKeyRelatedField: int,
    drf.StringRelatedField: str,
    drf.HyperlinkedIdentityField: str,
    drf.HyperlinkedRelatedField: str,
    drf.SlugRelatedField: str,
}


class MigrationError(NotImplementedError):
    """Raised when a DRF field cannot be mechanically translated."""


def from_drf(
    serializer_cls: type[drf.Serializer],
    *,
    name: str | None = None,
    exclude: tuple[str, ...] = (),
    computed: dict[str, tuple[Callable[[Any], Any], type]] | None = None,
) -> type[FastSerializer]:
    """Build a `FastSerializer` subclass equivalent to `serializer_cls`.

    Args:
        serializer_cls: An existing DRF `Serializer` or `ModelSerializer` class.
        name: Override the generated class name; defaults to `"<Cls>Fast"`.
        exclude: Field names to skip (use for fields you intend to drop or
            redeclare manually).
        computed: Replace `SerializerMethodField`s with inline
            `@computed_field`s. Map of ``field_name -> (callable, return_type)``;
            the callable receives the pydantic instance as its sole arg.
            Fields named here are skipped during DRF translation, then
            attached as computed properties on the result.

    Returns:
        A `FastSerializer` subclass ready for `.drf` + `FastJSONRenderer`.

    Raises:
        MigrationError: if any non-excluded, non-computed field has no
            clean mapping. The exception names the field and its DRF type.
    """
    computed = computed or {}
    skip = set(exclude) | set(computed)

    instance = serializer_cls()
    fields: dict[str, tuple[Any, Any]] = {}
    for field_name, field in instance.fields.items():
        if field_name in skip:
            continue
        py_type, py_field = _map_field(field_name, field)
        fields[field_name] = (py_type, py_field)

    cls_name = name or f"{serializer_cls.__name__}Fast"
    base = create_model(cls_name, __base__=FastSerializer, **fields)
    if not computed:
        return base
    return _attach_computed(base, computed, cls_name)


def _attach_computed(
    base: type[FastSerializer],
    computed: dict[str, tuple[Callable[[Any], Any], type]],
    cls_name: str,
) -> type[FastSerializer]:
    """Subclass `base` with `@computed_field` properties attached.

    Each entry's callable becomes a property getter; the second element of
    the tuple is the return annotation pydantic uses to type the field in
    the JSON schema and for output coercion.
    """
    namespace: dict[str, Any] = {}
    for cname, (fn, return_type) in computed.items():
        # Build a typed wrapper so pydantic can read the return annotation.
        def _make_getter(_fn: Callable[[Any], Any], _ret: type) -> Callable[[Any], Any]:
            def getter(self: Any) -> Any:
                return _fn(self)

            getter.__annotations__ = {"self": Any, "return": _ret}
            return getter

        namespace[cname] = computed_field(property(_make_getter(fn, return_type)))
    return type(cls_name, (base,), namespace)


def _map_field(field_name: str, field: drf.Field) -> tuple[Any, Any]:
    """Map one DRF field to (python_type, pydantic Field info)."""
    if isinstance(field, drf.SerializerMethodField):
        raise MigrationError(
            f"Field {field_name!r} is a SerializerMethodField; cannot be "
            f"auto-translated. Pass exclude=({field_name!r},) to from_drf() "
            f"and redeclare it on the result with @computed_field."
        )

    if isinstance(field, drf.ListSerializer):
        child_type = from_drf(type(field.child))
        return _wrap_optional(list[child_type], field), _field_info(field, field_name)

    if isinstance(field, drf.Serializer):
        child_type = from_drf(type(field))
        return _wrap_optional(child_type, field), _field_info(field, field_name)

    if isinstance(field, drf.ListField):
        child_type, _ = _map_field(f"{field_name}[]", field.child)
        return _wrap_optional(list[child_type], field), _field_info(
            field, field_name, empty_default=list
        )

    py_type = _resolve_scalar(field)
    if py_type is None:
        raise MigrationError(
            f"Field {field_name!r} of type {type(field).__name__!r} has no "
            f"mapping in from_drf. Add it to exclude=(...) and declare it "
            f"manually on the resulting FastSerializer."
        )
    return _wrap_optional(py_type, field), _field_info(field, field_name)


def _resolve_scalar(field: drf.Field) -> type | None:
    """Walk MRO to find the closest mapped DRF field type."""
    for cls in type(field).__mro__:
        if cls in _SCALAR_MAP:
            return _SCALAR_MAP[cls]
    return None


def _wrap_optional(py_type: Any, field: drf.Field) -> Any:
    """Wrap as `T | None` when the DRF field is nullable or not required."""
    if field.allow_null or not field.required:
        return py_type | None
    return py_type


def _field_info(
    field: drf.Field,
    field_name: str,
    *,
    empty_default: Any = None,
) -> Any:
    """Build the pydantic Field() carrying default + validation_alias.

    `empty_default` is the factory (e.g. `list`, `dict`) used when the DRF
    field is `required=False` with no explicit default; mirrors DRF's
    behavior of treating those as empty containers rather than null.
    """
    kwargs: dict[str, Any] = {}

    # source="a.b.c" → AliasPath(a, b, c). source=="*" means "the whole object";
    # leave it alone, pydantic's from_attributes handles it.
    source = getattr(field, "source", None)
    if source and source != field_name and source != "*":
        parts = source.split(".")
        kwargs["validation_alias"] = parts[0] if len(parts) == 1 else AliasPath(*parts)

    default = getattr(field, "default", drf.empty)
    if field.required:
        if not kwargs:
            return ...  # plain required field
        return Field(..., **kwargs)
    if default is drf.empty:
        if empty_default is not None:
            kwargs["default_factory"] = empty_default
        else:
            kwargs["default"] = None
    else:
        kwargs["default"] = default
    return Field(**kwargs)
