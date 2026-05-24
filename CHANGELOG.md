# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.1] - 2026-05-25

### Added
- `ReadOnlyField` now maps to `Any` in `from_drf` instead of raising
  `MigrationError`. Lets serializers that surface `.annotate()` columns
  or model properties translate without `exclude=(...)` boilerplate.
  The field still renders correctly; the output path is slower than for
  fields with a concrete type, since `Any` bypasses Rust-side type
  validation.
- Django `RelatedManager` is auto-coerced via `.all()` on list-typed
  fields. Pydantic's `from_attributes=True` would otherwise see the raw
  manager (the reverse-FK / M2M attribute on a parent) and either fail
  list validation outright or iterate the manager directly, bypassing
  the prefetch cache and triggering an extra query. A
  `field_validator(mode="before")` is attached only to fields whose
  resolved pydantic type is `list[T]` or `list[T] | None`.

## [0.3.0] - 2026-05-25

### Added
- Auto-translate `SerializerMethodField` in `from_drf` and
  `FastSerializerMixin`. The bound `get_*` method is detected on the
  serializer class; its return annotation becomes the pydantic field
  type and the getter runs once per row at validate time against the
  **source object** (Django model, dict, ...), not the pydantic
  instance. Eliminates the previous `RecursionError` when an SMF
  reached into the source object via `computed=` workarounds.
- `_fs_method_getters` table is attached to `from_drf`-generated
  classes when SMFs are present, exposing the mapping for introspection
  and for `DRFAdapter` to inject pre-resolved values via an internal
  attribute overlay (object sources) or merged dict (mapping sources).

### Changed
- `from_drf` no longer raises `MigrationError` on
  `SerializerMethodField`. Callers that previously caught that
  exception to skip the field should either let the auto path run, or
  pass the name in `exclude=` to retain the old skip-it behavior.
- SMF fields are stripped from `is_valid` input before validation —
  they are output-only by DRF contract; client-supplied values for
  those names no longer reach `validated_data`.
- `computed=` continues to take precedence over the auto path when
  both target the same field name. `exclude=` continues to drop the
  field entirely.
- Mixin fallback warning now only fires for genuinely untranslatable
  fields (custom `Field` subclasses with no scalar mapping); SMFs are
  handled silently on the fast path.

### Note
- SMFs that hit the ORM remain the caller's responsibility. The auto
  path matches DRF's per-row Python-side method dispatch cost; it does
  not magically prefetch. Annotate / `select_related` at the queryset
  level for hot endpoints.
- Un-annotated `get_*` methods fall back to `Any` with a one-time
  `UserWarning`. Add `-> T` for full Rust-side type validation.

## [0.2.3] - 2026-05-25

### Changed
- README on PyPI now shows a live PyPI version badge.
- Dependabot enabled for `github-actions` and `pip` (monthly grouped
  PRs).
- Publish workflow pins `astral-sh/setup-uv@v8.1.0` (the action has no
  floating `v8` major tag).

### Note
- Skipped `0.2.2`: the tag was created but its CI run failed before
  upload, so the version was never published. Continuing at `0.2.3` to
  keep PyPI history monotonic.

## [0.2.1] - 2026-05-25

### Fixed
- README benchmark image now uses an absolute `raw.githubusercontent.com`
  URL so it renders on the PyPI project page (relative `docs/bench.svg`
  was broken there).

### Changed
- Releases now publish from GitHub Actions via PyPI trusted publishing
  (OIDC, no long-lived tokens). Tag push to `v*` triggers test → build
  → publish + GitHub Release with auto-generated notes.

## [0.2.0] - 2026-05-25

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

## [0.1.0] - 2026-05-24
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
