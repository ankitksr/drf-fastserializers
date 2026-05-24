# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — Initial

### Added
- `FastSerializer` — pydantic-backed schema base.
- `FastJSONRenderer` — DRF renderer that dispatches `FastPayload` to
  `TypeAdapter.dump_json` (Rust), falls back to stock `JSONRenderer`
  otherwise.
- `DRFAdapter` — DRF-compatible wrapper accessed via `Schema.drf` or
  `drf_serializer(Schema)`. Supports read (`many=True`) and write
  (`is_valid`, `validated_data`, `errors`) paths.
- `FastSerializerMixin` + `FastListSerializer` — in-place acceleration of
  existing DRF serializers; auto-translates via `from_drf`, falls back on
  `MigrationError` with a one-time warning.
- `from_drf(SerializerCls, exclude=())` — explicit DRF → `FastSerializer`
  translation with field-mapping coverage of every common DRF field
  type, plus `source=` → `AliasPath` rewriting.
- Pagination splice: `{"results": <FastPayload>, ...}` wrappers are
  encoded with Rust for the list and stock JSON for the metadata.
- Pydantic 2.7+ supported; pydantic 3.x supported via version gate.
- 44-test suite, ruff-clean, reproducible benchmark in
  `benchmarks/bench.py`.
