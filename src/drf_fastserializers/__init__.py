"""drf-fastserializers — faster DRF serializers, one line at a time.

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
encoder. Falls back to standard DRF .data with a warning if any field
can't be mechanically translated (typically SerializerMethodField).

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

- `FastSerializerMixin` — mix into an existing DRF Serializer.
- `FastJSONRenderer` — add to `renderer_classes` to unlock Rust encode.
- `FastSerializer` — pydantic-backed schema base for new code.
- `from_drf(SerializerCls)` — explicit DRF → FastSerializer translation.
- `drf_serializer(SchemaCls)` — functional alternative to `.drf`.
"""

from ._compat import PYD_V3
from .accelerator import FastListSerializer, FastSerializerMixin
from .migrate import MigrationError, from_drf
from .renderer import FastJSONRenderer
from .serializer import DRFAdapter, FastSerializer, drf_serializer

# Ordered to match README narrative: migration story first, native second.
__all__ = [
    # Entry path: drop into existing DRF serializers.
    "FastSerializerMixin",
    "FastJSONRenderer",
    "FastListSerializer",
    # Migration helper for explicit translation.
    "from_drf",
    "MigrationError",
    # Native pydantic-first path for new code.
    "FastSerializer",
    "DRFAdapter",
    "drf_serializer",
    # Version compatibility flag.
    "PYD_V3",
]

__version__ = "0.1.0"
