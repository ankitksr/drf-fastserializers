# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] (0.2.0.dev)

### Added
- `from_model(DjangoModel, fields=...)` derives a `FastSerializer`
  schema straight from a Django model. Maps every concrete field type,
  including nullability, defaults, callable defaults, and FK PK types.
- `FastJSONParser` is a DRF parser that defers JSON decode to
  `validate_json` (Rust). Returns a lazy-decoded `RawJSONBytes` marker
  so middleware and tests reading `request.data` still get a dict.
- `partial=True` semantics on `DRFAdapter.is_valid` build a cached
  partial variant of the schema (every field optional with default
  `None`), so clients can send arbitrary subsets.
- `computed=` argument on `from_drf` replaces `SerializerMethodField`s
  inline with `(callable, return_type)` pairs translated to pydantic
  `@computed_field`s.
- `FastSerializer.values_fields(exclude=(...))` is a projection helper
  for `QuerySet.values(*Schema.values_fields())`.
- Optional `[spectacular]` extra exposing a drf-spectacular
  `OpenApiSerializerExtension` that auto-registers and renders schemas
  via `model_json_schema()`.
- `RawJSONBytes` exposed for type hints around custom parsers.

## [0.1.0] Initial
- `FastSerializer` is the pydantic-backed schema base.
- `FastJSONRenderer` is a DRF renderer that dispatches `FastPayload` to
  `TypeAdapter.dump_json` (Rust), falling back to stock `JSONRenderer`
  otherwise.
- `DRFAdapter` is the DRF-compatible wrapper accessed via `Schema.drf`
  or `drf_serializer(Schema)`. Supports read (`many=True`) and write
  (`is_valid`, `validated_data`, `errors`) paths.
- `FastSerializerMixin` and `FastListSerializer` for in-place
  acceleration of existing DRF serializers.
- `from_drf(SerializerCls, exclude=())` is the explicit DRF to
  `FastSerializer` translator. Field mapping covers every common DRF
  field type, plus `source=` to `AliasPath` rewriting.
- Pagination splice: `{"results": <FastPayload>, ...}` wrappers are
  encoded with Rust for the list and stock JSON for the metadata.
- Pydantic 2.7+ supported; pydantic 3.x supported via version gate.
- 44-test suite, ruff-clean, reproducible benchmark in
  `benchmarks/bench.py`.
