"""In-place acceleration of existing DRF Serializer subclasses.

Add `FastSerializerMixin` to the inheritance list of an existing
serializer and `.data` switches to the pydantic-core Rust path:

    from drf_fastserializers import FastSerializerMixin, FastJSONRenderer
    from rest_framework import serializers

    class TxnSerializer(FastSerializerMixin, serializers.ModelSerializer):
        class Meta:
            model = Txn
            fields = ["id", "name", "amount"]

    class TxnListView(ListAPIView):
        serializer_class = TxnSerializer
        renderer_classes = [FastJSONRenderer]
        queryset = Txn.objects.all()

The mixin translates the serializer's fields to a `FastSerializer`
schema at first `.data` access (cached per class). If translation fails
(most commonly because of `SerializerMethodField`), it emits a one-time
warning and falls back to DRF's standard `.data`. The mixin is safe to
leave on; it never breaks the response.

Set `Meta.fast = False` to disable the fast path explicitly. Useful for
opt-out per serializer without removing the mixin.
"""

import warnings
from typing import Any, ClassVar

from rest_framework import serializers as drf

from .migrate import MigrationError, from_drf
from .serializer import FastSerializer


class FastListSerializer(drf.ListSerializer):
    """ListSerializer with a Rust-encoded `.data` property.

    Constructed automatically by `FastSerializerMixin.many_init`. Defers
    to the child's translated `FastSerializer` schema; falls back to
    `ListSerializer.data` if translation is unavailable.
    """

    @property
    def data(self) -> Any:
        child_cls = type(self.child)
        schema = _resolve_schema(child_cls)
        if schema is None or self.instance is None:
            return super().data
        return schema.drf(instance=self.instance, many=True).data


class FastSerializerMixin:
    """Mix into an existing DRF Serializer to accelerate `.data`.

    Override order matters: place `FastSerializerMixin` **first** in the
    MRO so its `data` property wins:

        class TxnSerializer(FastSerializerMixin, serializers.ModelSerializer):
            ...
    """

    _fast_schema_cache: ClassVar[type[FastSerializer] | None] = None
    _fast_schema_resolved: ClassVar[bool] = False

    @classmethod
    def many_init(cls, *args: Any, **kwargs: Any) -> drf.ListSerializer:
        # Mirror DRF's many_init logic, swapping ListSerializer → FastListSerializer
        # unless the user explicitly set Meta.list_serializer_class.
        meta = getattr(cls, "Meta", None)
        user_list_cls = getattr(meta, "list_serializer_class", None)
        if user_list_cls is not None and user_list_cls is not drf.ListSerializer:
            return super().many_init(*args, **kwargs)  # type: ignore[misc]

        allow_empty = kwargs.pop("allow_empty", None)
        max_length = kwargs.pop("max_length", None)
        min_length = kwargs.pop("min_length", None)
        child_kwargs = {k: v for k, v in kwargs.items() if k not in drf.LIST_SERIALIZER_KWARGS}
        list_kwargs: dict[str, Any] = {"child": cls(**child_kwargs)}
        if allow_empty is not None:
            list_kwargs["allow_empty"] = allow_empty
        if max_length is not None:
            list_kwargs["max_length"] = max_length
        if min_length is not None:
            list_kwargs["min_length"] = min_length
        list_kwargs.update({k: v for k, v in kwargs.items() if k in drf.LIST_SERIALIZER_KWARGS})
        return FastListSerializer(*args, **list_kwargs)

    @property
    def data(self) -> Any:
        schema = _resolve_schema(type(self))
        if schema is None or self.instance is None:
            return super().data  # type: ignore[misc]
        return schema.drf(instance=self.instance, many=False).data


def _resolve_schema(cls: type) -> type[FastSerializer] | None:
    """Memoized translation of a DRF Serializer class into a FastSerializer.

    Honors `Meta.fast = False` as an explicit opt-out. Caches the result
    (success or failure) on the serializer class itself to keep subsequent
    lookups O(1).
    """
    if not cls.__dict__.get("_fast_schema_resolved"):
        meta = getattr(cls, "Meta", None)
        if meta is not None and getattr(meta, "fast", True) is False:
            cls._fast_schema_cache = None
        else:
            cls._fast_schema_cache = _try_translate(cls)
        cls._fast_schema_resolved = True
    return cls._fast_schema_cache


def _try_translate(cls: type) -> type[FastSerializer] | None:
    try:
        return from_drf(cls)
    except MigrationError as exc:
        warnings.warn(
            f"{cls.__name__}: cannot auto-translate to FastSerializer ({exc}). "
            f"Falling back to standard DRF `.data` (no Rust speedup). "
            f"Pass `exclude=(...)` via from_drf manually, or set `Meta.fast = False` "
            f"to silence this warning.",
            stacklevel=3,
        )
        return None
