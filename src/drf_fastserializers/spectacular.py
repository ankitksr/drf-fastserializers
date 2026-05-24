"""Optional drf-spectacular integration.

Install with the `[spectacular]` extra::

    pip install 'drf-fastserializers[spectacular]'
    # or: uv add 'drf-fastserializers[spectacular]'

Then ensure this module is imported once during app startup so the
extension class auto-registers (drf-spectacular discovers extensions by
class definition). The cleanest spot is your AppConfig.ready()::

    # myapp/apps.py
    from django.apps import AppConfig

    class MyAppConfig(AppConfig):
        name = "myapp"

        def ready(self):
            import drf_fastserializers.spectacular  # noqa: F401

With that wired up, every view whose `serializer_class` is a
`DRFAdapter` shows up in your OpenAPI schema using pydantic's
`model_json_schema()`, including nested models, enum choices,
validators, and computed fields.

Importing this module without `drf-spectacular` installed raises
`ImportError` with a hint pointing at the extra.
"""

try:
    from drf_spectacular.extensions import OpenApiSerializerExtension
except ImportError as exc:
    raise ImportError(
        "drf-spectacular is not installed. "
        "Install with `pip install 'drf-fastserializers[spectacular]'`."
    ) from exc


class FastSerializerSchemaExtension(OpenApiSerializerExtension):
    """Pulls OpenAPI schema from the pydantic model behind a `DRFAdapter`.

    `target_class` is the fully-qualified name of `DRFAdapter`;
    `match_subclasses=True` means every generated adapter (one per
    `FastSerializer`) is covered automatically.
    """

    target_class = "drf_fastserializers.serializer.DRFAdapter"
    match_subclasses = True

    def get_name(self, auto_schema, direction):
        return self.target.serializer_cls.__name__

    def map_serializer(self, auto_schema, direction):
        # Pydantic emits richer JSON-schema than drf-spectacular can
        # introspect from a DRF Field list, so hand it back verbatim and
        # let spectacular inline it. Nested models appear under `$defs`;
        # most OpenAPI tooling (Swagger UI, Redoc) handles that inline.
        mode = "validation" if direction == "request" else "serialization"
        return self.target.serializer_cls.model_json_schema(mode=mode)
