"""drf-fastserializers: faster DRF serializers, one line at a time.

Quick start (existing DRF serializers):

    from drf_fastserializers import FastSerializerMixin, FastJSONRenderer
    from rest_framework import serializers

    class TxnSerializer(FastSerializerMixin, serializers.ModelSerializer):
        class Meta:
            model = Txn
            fields = ["id", "name", "amount"]

    class TxnListView(ListAPIView):
        serializer_class = TxnSerializer       # unchanged
        renderer_classes = [FastJSONRenderer]  # add this
        queryset = Txn.objects.all()

The mixin auto-translates the serializer at first .data access (cached
per-class) and switches the read path to pydantic-core's Rust JSON
encoder. `SerializerMethodField`s with a `-> T` return annotation are
auto-translated; un-annotated getters work but fall back to `Any` (no
Rust-side type coercion). The mixin falls back to standard DRF .data
with a warning only when a custom Field with no scalar mapping is
encountered.

New code (define schemas natively in pydantic):

    from drf_fastserializers import FastSerializer

    class TxnOut(FastSerializer):
        id: int
        name: str
        amount: Decimal | None = None

    class TxnListView(ListAPIView):
        serializer_class = TxnOut.drf
        renderer_classes = [FastJSONRenderer]

Public surface:

- `FastSerializerMixin`: mix into an existing DRF Serializer.
- `FastJSONRenderer`: Rust-encoded output path; add to `renderer_classes`.
- `FastJSONParser`: Rust-encoded input path; add to `parser_classes`.
- `FastSerializer`: pydantic-backed schema base for new code.
- `from_drf(SerializerCls)`: explicit DRF to FastSerializer translation.
- `from_model(DjangoModel)`: derive a FastSerializer from a Django model.
- `drf_serializer(SchemaCls)`: functional alternative to `.drf`.
"""

from ._compat import PYD_V3
from ._payload import FastPayload, RawJSONBytes
from .accelerator import FastListSerializer, FastSerializerMixin
from .migrate import MigrationError, from_drf
from .models import ModelMappingError, from_model
from .parser import FastJSONParser
from .renderer import FastJSONRenderer
from .serializer import DRFAdapter, FastSerializer, drf_serializer

# Ordered to match README narrative: migration story first, native second.
__all__ = [
    # Entry path: drop into existing DRF serializers.
    "FastSerializerMixin",
    "FastJSONRenderer",
    "FastJSONParser",
    "FastListSerializer",
    # Migration helpers.
    "from_drf",
    "from_model",
    "MigrationError",
    "ModelMappingError",
    # Native pydantic-first path for new code.
    "FastSerializer",
    "DRFAdapter",
    "drf_serializer",
    # Marker payloads (mostly internal but useful for type hints).
    "FastPayload",
    "RawJSONBytes",
    # Version compatibility flag.
    "PYD_V3",
]

__version__ = "0.3.2"
