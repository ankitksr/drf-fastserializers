"""Derive a `FastSerializer` schema directly from a Django model.

`from_model(Txn, fields=[...])` walks the model's fields, maps each
Django field type to its pydantic equivalent, and returns a ready-to-use
`FastSerializer` subclass, no DRF `ModelSerializer` indirection
required::

    from drf_fastserializers import from_model, FastJSONRenderer
    from myapp.models import Txn

    TxnOut = from_model(Txn, fields=["id", "name", "amount", "txn_date"])

    class TxnListView(ListAPIView):
        serializer_class = TxnOut.drf
        renderer_classes = [FastJSONRenderer]
        queryset = Txn.objects.all()

Field selection mirrors `Meta` conventions: pass `fields="__all__"` to
auto-include every concrete model field, or `exclude=(...)` to drop a
subset. Many-to-many and reverse relations are skipped (those need
explicit `Serializer` work).
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import Field, create_model

from .serializer import FastSerializer

# Django field type name → pydantic type. Lookup by class name keeps the
# helper resilient to Django version drift (no direct imports of Django
# field classes that might move).
_DJANGO_TO_PY: dict[str, Any] = {
    "AutoField": int,
    "BigAutoField": int,
    "SmallAutoField": int,
    "BigIntegerField": int,
    "IntegerField": int,
    "SmallIntegerField": int,
    "PositiveIntegerField": int,
    "PositiveSmallIntegerField": int,
    "PositiveBigIntegerField": int,
    "CharField": str,
    "TextField": str,
    "EmailField": str,
    "URLField": str,
    "SlugField": str,
    "BooleanField": bool,
    "DateField": date,
    "DateTimeField": datetime,
    "TimeField": time,
    "DurationField": timedelta,
    "DecimalField": Decimal,
    "FloatField": float,
    "UUIDField": UUID,
    "JSONField": Any,
    "BinaryField": bytes,
    "FileField": str,
    "ImageField": str,
    "FilePathField": str,
    "GenericIPAddressField": str,
    "IPAddressField": str,
}


class ModelMappingError(NotImplementedError):
    """Raised when a Django field has no clean pydantic mapping."""


def from_model(
    model: type,
    *,
    fields: list[str] | tuple[str, ...] | str = "__all__",
    exclude: tuple[str, ...] = (),
    name: str | None = None,
) -> type[FastSerializer]:
    """Build a `FastSerializer` subclass from a Django model.

    Args:
        model: A Django `models.Model` subclass.
        fields: Either a list of field names or the sentinel `"__all__"`.
        exclude: Field names to drop from the result.
        name: Override the generated class name (default: `"<Model>Fast"`).

    Returns:
        A `FastSerializer` subclass ready for `.drf` + `FastJSONRenderer`.

    Raises:
        ModelMappingError: when a selected field has no mapping (e.g.
            many-to-many, custom field types). Pass it via `exclude=` or
            declare it manually on a subclass.
    """
    meta = model._meta  # type: ignore[attr-defined]
    available = {f.name: f for f in meta.get_fields() if getattr(f, "concrete", False)}
    exclude_set = set(exclude)

    if fields == "__all__":
        names = [n for n in available if n not in exclude_set]
    else:
        names = [n for n in fields if n not in exclude_set]

    field_defs: dict[str, tuple[Any, Any]] = {}
    for fname in names:
        django_field = available.get(fname)
        if django_field is None:
            raise ModelMappingError(
                f"{model.__name__} has no concrete field {fname!r}; "
                f"choose from: {sorted(available)}"
            )
        py_type, default = _map_django_field(model, fname, django_field)
        field_defs[fname] = (py_type, default)

    return create_model(
        name or f"{model.__name__}Fast",
        __base__=FastSerializer,
        **field_defs,
    )


def _map_django_field(model: type, fname: str, django_field: Any) -> tuple[Any, Any]:
    """Return (python_type, pydantic Field info) for one Django field."""
    cls_name = type(django_field).__name__

    py_type = _DJANGO_TO_PY.get(cls_name)
    if py_type is None and getattr(django_field, "related_model", None) is not None:
        # ForeignKey / OneToOne: use the PK type. Default int; refine if
        # the target uses UUID primary keys.
        related = django_field.related_model
        pk = related._meta.pk
        py_type = _DJANGO_TO_PY.get(type(pk).__name__, int)

    if py_type is None:
        raise ModelMappingError(
            f"Field {model.__name__}.{fname} (type {cls_name!r}) has no mapping. "
            f"Exclude it via exclude=(...) and add it manually on the result."
        )

    nullable = bool(getattr(django_field, "null", False))
    has_default = bool(getattr(django_field, "has_default", lambda: False)())

    py_annotation: Any = py_type | None if nullable else py_type

    if has_default:
        default = django_field.default
        if callable(default):
            return py_annotation, Field(default_factory=default)
        return py_annotation, Field(default=default)
    if nullable:
        return py_annotation, Field(default=None)
    return py_annotation, ...
