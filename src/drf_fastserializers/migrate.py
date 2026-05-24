"""Translate `rest_framework.serializers.Serializer` classes into `FastSerializer`.

`from_drf(MyExistingSerializer)` walks `serializer.fields` and builds an
equivalent pydantic-backed schema at runtime. Use the result as you would
any other `FastSerializer`:

    FastTxnOut = from_drf(TxnSerializer)

    class MyView(ListAPIView):
        serializer_class = FastTxnOut.drf
        renderer_classes = [FastJSONRenderer]

`SerializerMethodField`s are auto-translated: the bound `get_*` method is
detected, its return annotation becomes the pydantic field type, and the
getter is invoked once per row at validate time against the source object
(Django model, dict, ...). Annotate `get_*` methods (`-> T`) for the
Rust render fast path; un-annotated getters fall back to `Any` with a
runtime warning. SMFs that hit the ORM remain the caller's
responsibility — prefetch / annotate at the queryset level to avoid N+1.

`ReadOnlyField` maps to `Any` (no type info to extract). Reverse-FK /
M2M `RelatedManager`s on list-typed fields are auto-coerced via `.all()`
so the prefetch cache is honored.

DRF fields with overridden `to_representation` and no scalar mapping
have no mechanical equivalent; the helper raises `MigrationError`
naming the offending field. Add them to `exclude=` and redeclare on
the resulting `FastSerializer`.
"""

import types
import warnings
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Union, get_args, get_origin, get_type_hints
from uuid import UUID

from pydantic import AliasPath, Field, computed_field, create_model, field_validator
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
    # ReadOnlyField carries no type info (used heavily for `.annotate()`
    # columns and model properties); Any is the honest mapping. Output
    # for these fields routes through pydantic's slower Python path
    # since there's no Rust-side type to validate against.
    drf.ReadOnlyField: Any,  # type: ignore[dict-item]
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
        computed: Replace fields with inline `@computed_field`s. Map of
            ``field_name -> (callable, return_type)``; the callable
            receives the pydantic instance as its sole arg. Takes
            precedence over auto-SMF translation when names overlap.

    Returns:
        A `FastSerializer` subclass ready for `.drf` + `FastJSONRenderer`.

    Raises:
        MigrationError: if a non-excluded, non-computed field has no
            clean mapping, or if the source class cannot be instantiated
            for SMF method binding. The exception names the offending
            field and DRF type.
    """
    computed = computed or {}
    skip = set(exclude) | set(computed)

    instance = _instantiate_for_binding(serializer_cls)

    fields: dict[str, tuple[Any, Any]] = {}
    method_getters: dict[str, Callable[[Any], Any]] = {}
    list_field_names: list[str] = []
    for field_name, field in instance.fields.items():
        if field_name in skip:
            continue
        if isinstance(field, drf.SerializerMethodField):
            py_type, py_field, getter = _resolve_smf(
                field_name, field, serializer_cls, instance
            )
            fields[field_name] = (py_type, py_field)
            method_getters[field_name] = getter
            continue
        py_type, py_field = _map_field(field_name, field)
        fields[field_name] = (py_type, py_field)
        if _is_list_type(py_type):
            list_field_names.append(field_name)

    # Django's reverse FK / M2M `RelatedManager` shows up as the raw
    # attribute on prefetched parents. List-typed fields need it coerced
    # to a queryset (via `.all()`) before pydantic iterates it, otherwise
    # iteration bypasses the prefetch cache and triggers extra queries
    # (or fails validation outright on stricter pydantic builds).
    validators = {
        f"_fs_coerce_manager_{n}": _make_manager_coercer(n)
        for n in list_field_names
    }
    cls_name = name or f"{serializer_cls.__name__}Fast"
    base = create_model(
        cls_name,
        __base__=FastSerializer,
        __validators__=validators or None,
        **fields,
    )
    if method_getters:
        base._fs_method_getters = method_getters  # type: ignore[attr-defined]
    if not computed:
        return base
    return _attach_computed(base, computed, cls_name)


def _instantiate_for_binding(serializer_cls: type[drf.Serializer]) -> drf.Serializer:
    """Build an instance of `serializer_cls` for field walking + SMF method binding.

    DRF's `Serializer.__init__` accepts no required args; subclasses that
    add required positional args break this assumption. We raise a clean
    `MigrationError` so the caller knows to use `exclude=` / `computed=`.
    """
    try:
        return serializer_cls()
    except TypeError as exc:
        raise MigrationError(
            f"Could not instantiate {serializer_cls.__name__}() to bind "
            f"SerializerMethodField getters: {exc}. Pass `exclude=...` for "
            f"every SMF, or use `computed=` to supply replacements."
        ) from exc


def _resolve_smf(
    field_name: str,
    field: drf.SerializerMethodField,
    serializer_cls: type[drf.Serializer],
    instance: drf.Serializer,
) -> tuple[Any, Any, Callable[[Any], Any]]:
    """Translate `SerializerMethodField` → (pydantic_type, FieldInfo, bound_getter).

    The getter receives the **source object** (Django model, dict, ...),
    matching DRF's contract — not the pydantic instance. It runs once
    per row at validate time; pydantic stores the result in a regular
    field, then the Rust `dump_json` path renders it.
    """
    method_name = field.method_name or f"get_{field_name}"
    bound = getattr(instance, method_name, None)
    if not callable(bound):
        raise MigrationError(
            f"SerializerMethodField {field_name!r} expects method "
            f"{method_name!r} on {serializer_cls.__name__}, but none found."
        )
    return_type = _smf_return_type(bound, serializer_cls.__name__, field_name)
    return return_type | None, Field(default=None), bound


def _smf_return_type(
    bound: Callable[..., Any], cls_name: str, field_name: str
) -> Any:
    """Read the return annotation off a bound `get_*` method.

    Missing annotation falls back to `Any`. `Any` defeats pydantic's
    Rust-side type validation, so the output path is slower; warn once
    to nudge callers toward annotating.
    """
    try:
        hints = get_type_hints(bound)
    except Exception:
        hints = {}
    ret = hints.get("return")
    if ret is None:
        warnings.warn(
            f"{cls_name}.{field_name}: SerializerMethodField getter has no "
            f"return annotation; falling back to `Any` (slower output path). "
            f"Add `-> T` to the get_* method for the Rust render fast path.",
            stacklevel=3,
        )
        return Any
    return ret


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
    sub = type(cls_name, (base,), namespace)
    # computed_field declarations override auto-SMF entries of the same name.
    # Drop those from the inherited method-getter table to keep precedence
    # exclude > computed > auto-SMF.
    parent_getters = getattr(base, "_fs_method_getters", None)
    if parent_getters:
        remaining = {k: v for k, v in parent_getters.items() if k not in computed}
        if remaining != parent_getters:
            sub._fs_method_getters = remaining  # type: ignore[attr-defined]
    return sub


def _map_field(field_name: str, field: drf.Field) -> tuple[Any, Any]:
    """Map one DRF field to (python_type, pydantic Field info).

    `SerializerMethodField` is handled by `_resolve_smf` before this is
    called; reaching the SMF branch below indicates an internal error.
    """
    if isinstance(field, drf.SerializerMethodField):
        raise MigrationError(
            f"Internal: SerializerMethodField {field_name!r} reached _map_field. "
            f"This is a bug in from_drf."
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


def _is_list_type(annotation: Any) -> bool:
    """Detect `list[T]`, `list[T] | None`, `Optional[list[T]]` shapes.

    Used during from_drf to decide which fields need the Django Manager
    coercion validator attached.
    """
    origin = get_origin(annotation)
    if origin is list:
        return True
    if origin is Union or origin is types.UnionType:
        return any(_is_list_type(a) for a in get_args(annotation))
    return False


def _make_manager_coercer(field_name: str) -> Any:
    """Build a `field_validator(mode="before")` that calls `.all()` on Django Managers.

    Coerces `RelatedManager` (reverse FK / M2M with prefetch) to a queryset
    before pydantic's list validation walks it. No-op for any other type,
    so non-Django callers pay only one `isinstance` check per validation.
    The Django import is lazy so the lib still imports without Django on
    the path (DRF transitively requires it, but defensively cheap).
    """

    @field_validator(field_name, mode="before")
    @classmethod
    def _coerce(cls: Any, v: Any) -> Any:
        try:
            from django.db.models import Manager
        except ImportError:
            return v
        if isinstance(v, Manager):
            return v.all()
        return v

    return _coerce


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


