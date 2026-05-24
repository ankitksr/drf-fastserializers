# drf-fastserializers

**DRF serializers, pydantic-core inside.**

Drop `FastSerializerMixin` into your existing serializer. The `.data`
path switches to pydantic-core's Rust JSON encoder. 2-3x faster on
large list payloads. No rewrite. Same DRF surface.

```python
from rest_framework import serializers
from drf_fastserializers import FastSerializerMixin, FastJSONRenderer

class TxnSerializer(FastSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Txn
        fields = ["id", "name", "amount", "txn_date"]

class TxnListView(ListAPIView):
    serializer_class = TxnSerializer       # unchanged
    renderer_classes = [FastJSONRenderer]  # add this
    queryset = Txn.objects.all()
```

That's the migration. If `TxnSerializer` translates cleanly the endpoint
gets the speedup on next request. If it doesn't (a `SerializerMethodField`,
say) you get a one-time warning and `.data` keeps working — no breakage,
no Rust speedup until you address the offender.

## Benchmark

21,393 synthetic rows, ~3 MB JSON, 5 runs each.
Python 3.12 · pydantic 2.13 · DRF 3.17.

| Strategy | median_ms | min_ms | speedup |
|---|---:|---:|---:|
| Raw dict → `JSONRenderer` (no validation) | 20 | 20 | 4.80x |
| DRF `Serializer` (stock) | **96** | 96 | **1.00x** |
| **drf-fastserializers (mixin)** | **37** | 35 | **2.64x** |
| **drf-fastserializers (native)** | **36** | 34 | **2.65x** |

Speedup is anchored on stock DRF. Reproduce on your hardware:

```bash
uv run python -m benchmarks.bench
```

`benchmarks/bench.py` ships with the repo and uses synthetic data only.
Real-world gaps widen further on `ModelSerializer` paths (ORM hydration
overhead) and on payloads with nested models. In production workloads
we've seen 3-4x speedups on `ModelSerializer`-based endpoints.

## Install

```bash
uv add drf-fastserializers
# or
pip install drf-fastserializers
```

Requires Python 3.12+, pydantic 2.7+ (v3 supported), DRF 3.14+.

## Migrating an existing serializer

### Drop in the mixin

```python
from drf_fastserializers import FastSerializerMixin

class TxnSerializer(FastSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Txn
        fields = ["id", "name", "amount", "txn_date"]
```

`FastSerializerMixin` must come **first** in the MRO. On first `.data`
access it translates the DRF field list into a pydantic schema (cached
per-class) and switches `.data` to the Rust path. `many=True` is handled
via a `FastListSerializer` wrapper installed automatically.

### Add the renderer

```python
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "drf_fastserializers.FastJSONRenderer",
    ],
}
```

`FastJSONRenderer` subclasses `JSONRenderer` — falls back to stock
encoding for error responses, hand-rolled dicts, browsable API, etc.
Safe as a project-wide default. (Or set `renderer_classes` per view.)

### When auto-translation fails

If a serializer has a `SerializerMethodField` or a custom field with an
overridden `to_representation`, the mixin emits a warning and falls back
to standard DRF `.data`. Three ways to proceed:

**1. Move the computation upstream** — into a queryset annotation or a
model property. Then drop the `SerializerMethodField` entirely.

```python
# before
class TxnSerializer(FastSerializerMixin, serializers.ModelSerializer):
    formatted_amount = serializers.SerializerMethodField()

    def get_formatted_amount(self, obj):
        return f"${obj.amount:,.2f}"

# after
class Txn(models.Model):
    @property
    def formatted_amount(self) -> str:
        return f"${self.amount:,.2f}"

class TxnSerializer(FastSerializerMixin, serializers.ModelSerializer):
    formatted_amount = serializers.CharField(read_only=True)
```

**2. Switch to explicit translation** via `from_drf` + `@computed_field`:

```python
from pydantic import computed_field
from drf_fastserializers import from_drf

_Base = from_drf(TxnSerializer, exclude=("formatted_amount",))

class FastTxnOut(_Base):
    @computed_field
    @property
    def formatted_amount(self) -> str:
        return f"${self.amount:,.2f}"

class TxnListView(ListAPIView):
    serializer_class = FastTxnOut.drf
    renderer_classes = [FastJSONRenderer]
```

**3. Opt out for this serializer** — set `Meta.fast = False`. Mixin
stops trying, warning goes away, endpoint stays on DRF.

### Field mapping

| DRF field | Pydantic type |
|---|---|
| `CharField`, `EmailField`, `URLField`, `SlugField`, `RegexField` | `str` |
| `IntegerField` | `int` |
| `FloatField` | `float` |
| `DecimalField` | `Decimal` |
| `BooleanField` | `bool` |
| `DateField` / `DateTimeField` / `TimeField` / `DurationField` | `date` / `datetime` / `time` / `timedelta` |
| `UUIDField` | `UUID` |
| `IPAddressField`, `FileField`, `ImageField` | `str` |
| `ChoiceField` | `str` |
| `JSONField` | `Any` |
| `DictField`, `HStoreField` | `dict` |
| `ListField(child=X)` | `list[mapped(X)]` |
| `Serializer(...)` (nested) | nested `FastSerializer` (recurse) |
| `ListSerializer(...)` | `list[nested FastSerializer]` |
| `PrimaryKeyRelatedField` | `int` |
| `StringRelatedField`, `HyperlinkedRelatedField`, `SlugRelatedField` | `str` |
| `SerializerMethodField` | **not supported** — see workarounds above |

Field options carried through:

| DRF option | Effect on pydantic field |
|---|---|
| `required=False` | non-required with `default=None` (or empty container for `ListField`/`DictField`) |
| `allow_null=True` | type widened to `T \| None` |
| `default=...` | becomes the pydantic default |
| `source="a.b.c"` | becomes `AliasPath("a", "b", "c")` |

### Pagination

Standard DRF pagination works without changes:

```python
class TxnListView(ListAPIView):
    serializer_class = TxnSerializer
    renderer_classes = [FastJSONRenderer]
    pagination_class = LimitOffsetPagination
    queryset = Txn.objects.all()
```

Renderer recognizes `{"results": <FastPayload>, "next": ..., "count": ...}`
and splices the Rust-encoded list bytes into the paginator's wrapper.

## Defining schemas natively (new code)

For new endpoints, skip the DRF serializer and define a pydantic schema
directly. Same renderer; tighter types; cleaner code.

```python
from datetime import date
from decimal import Decimal
from drf_fastserializers import FastSerializer, FastJSONRenderer

class Flags(FastSerializer):
    is_nsf: bool = False
    is_refund: bool = False

class TxnOut(FastSerializer):
    id: int
    name: str
    amount: Decimal | None = None
    txn_date: date
    flags: Flags
    tags: list[str] = []

class TxnListView(ListAPIView):
    serializer_class = TxnOut.drf
    renderer_classes = [FastJSONRenderer]
    queryset = Txn.objects.all()
```

`FastSerializer` is a `pydantic.BaseModel`. Everything pydantic does —
nested models, `@computed_field`, validators, `model_config`, enums —
works.

`TxnOut.drf` is a class-level descriptor returning a `DRFAdapter`
subclass bound to the schema. It quacks like
`rest_framework.serializers.Serializer`:

```python
serializer = TxnOut.drf(instance=qs, many=True)
serializer.data            # FastPayload — encoded on render
serializer.is_valid()      # validates incoming request data
serializer.errors          # DRF-shape: {"field": ["msg", ...]}
serializer.validated_data  # pydantic instances
```

Input validation in a view:

```python
class TxnCreateView(APIView):
    def post(self, request):
        serializer = TxnIn.drf(data=request.data)
        serializer.is_valid(raise_exception=True)
        txn = serializer.validated_data
        Txn.objects.create(**txn.model_dump())
        return Response(status=201)
```

Errors land in DRF's standard shape:

```json
{
  "amount": ["Input should be a valid decimal"],
  "flags.is_nsf": ["Input should be a valid boolean"]
}
```

### Explicit factory

Prefer an explicit import over the `.drf` descriptor? Use `drf_serializer`:

```python
from drf_fastserializers import drf_serializer

class TxnListView(ListAPIView):
    serializer_class = drf_serializer(TxnOut)
```

Both forms return the same cached `DRFAdapter` subclass.

## How it works

Standard DRF serializers iterate field objects in Python on every
response. That overhead dominates response time for endpoints returning
thousands of rows.

`drf-fastserializers` skips DRF's field pipeline. On `.data` access the
serializer hands back a `FastPayload` marker carrying the validated
pydantic instances plus a `TypeAdapter`. `FastJSONRenderer` recognizes
the marker and routes encoding to `TypeAdapter.dump_json` — implemented
in Rust as part of
[pydantic-core](https://github.com/pydantic/pydantic-core). Bytes go
straight to the HTTP response. No Python-side `json.dumps` step.

```
DRF view
  └─ serializer.data        →  FastPayload(adapter, instances)
       └─ FastJSONRenderer  →  adapter.dump_json(instances) [Rust]
            └─ HttpResponse →  bytes
```

For payloads the renderer doesn't recognize (error responses, plain
dicts, browsable API, paginated wrappers), it falls back to stock
`JSONRenderer`. The library never breaks code paths it doesn't
explicitly handle.

## Pydantic v2 + v3

Built against the stable pydantic surface used by both v2.7+ and v3.x
(`BaseModel`, `TypeAdapter`, `ConfigDict`, `ValidationError`,
`model_dump_json`). The pyproject spec is `pydantic>=2.7,<4`. The
`PYD_V3` flag is exposed for downstream code that needs to branch.

## What this library is *not*

- A `ModelSerializer` replacement — it doesn't auto-infer fields from a
  Django model. Use `from_drf(MyModelSerializer)` to lift an existing
  one, or declare fields explicitly in a `FastSerializer`.
- A framework — keep your DRF generics, viewsets, routers, permissions,
  auth backends, throttling, filtering. Only the serializer + renderer
  paths change. Migrate one endpoint at a time.
- A drf-spectacular replacement — schema generation from
  `Model.model_json_schema()` is on the roadmap; for now declare
  response shapes manually with `@extend_schema`.

## License

MIT
