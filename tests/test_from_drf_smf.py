"""Auto-translation of `SerializerMethodField` via `from_drf`."""

import json

import pytest
from rest_framework import serializers

from drf_fastserializers import FastJSONRenderer, MigrationError, from_drf


class _Src:
    """Lightweight source-object stand-in (Django model role in real apps)."""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def test_smf_reads_source_obj_not_pydantic_instance():
    class W(serializers.Serializer):
        id = serializers.IntegerField()
        n_kids = serializers.SerializerMethodField()
        label = serializers.SerializerMethodField()

        def get_n_kids(self, obj) -> int:
            return obj.kids

        def get_label(self, obj) -> str:
            return f"#{obj.id}"

    Fast = from_drf(W)
    payload = Fast.drf(instance=_Src(id=7, kids=3)).data
    parsed = json.loads(FastJSONRenderer().render(payload))
    assert parsed == {"id": 7, "n_kids": 3, "label": "#7"}


def test_smf_many_true():
    class W(serializers.Serializer):
        id = serializers.IntegerField()
        kid_count = serializers.SerializerMethodField()

        def get_kid_count(self, obj) -> int:
            return obj.kids

    Fast = from_drf(W)
    instances = [_Src(id=i, kids=i * 2) for i in range(3)]
    payload = Fast.drf(instance=instances, many=True).data
    parsed = json.loads(FastJSONRenderer().render(payload))
    assert parsed == [
        {"id": 0, "kid_count": 0},
        {"id": 1, "kid_count": 2},
        {"id": 2, "kid_count": 4},
    ]


def test_smf_dict_source_merges_via_dict():
    class W(serializers.Serializer):
        id = serializers.IntegerField()
        upper = serializers.SerializerMethodField()

        def get_upper(self, obj) -> str:
            # Dict source: getter sees the mapping itself.
            return str(obj["id"]).upper()

    Fast = from_drf(W)
    payload = Fast.drf(instance={"id": 9}).data
    parsed = json.loads(FastJSONRenderer().render(payload))
    assert parsed == {"id": 9, "upper": "9"}


def test_smf_method_name_override():
    class W(serializers.Serializer):
        id = serializers.IntegerField()
        alias = serializers.SerializerMethodField(method_name="custom_getter")

        def custom_getter(self, obj) -> str:
            return f"x{obj.id}"

    Fast = from_drf(W)
    payload = Fast.drf(instance=_Src(id=5)).data
    parsed = json.loads(FastJSONRenderer().render(payload))
    assert parsed == {"id": 5, "alias": "x5"}


def test_smf_unannotated_falls_back_to_any_with_warning():
    class W(serializers.Serializer):
        id = serializers.IntegerField()
        misc = serializers.SerializerMethodField()

        def get_misc(self, obj):
            return {"foo": "bar"}

    with pytest.warns(UserWarning, match="return annotation"):
        Fast = from_drf(W)
    payload = Fast.drf(instance=_Src(id=1)).data
    parsed = json.loads(FastJSONRenderer().render(payload))
    assert parsed == {"id": 1, "misc": {"foo": "bar"}}


def test_smf_computed_takes_precedence_over_auto():
    """computed= entry for the same name wins, and the auto-SMF binding is dropped."""

    class W(serializers.Serializer):
        id = serializers.IntegerField()
        kind = serializers.SerializerMethodField()

        def get_kind(self, obj) -> str:
            return "from-method"

    Fast = from_drf(W, computed={"kind": (lambda self: "from-computed", str)})
    # No auto entry left for this name.
    assert "kind" not in getattr(Fast, "_fs_method_getters", {})
    payload = Fast.drf(instance=_Src(id=1)).data
    parsed = json.loads(FastJSONRenderer().render(payload))
    assert parsed["kind"] == "from-computed"


def test_smf_exclude_silently_drops():
    class W(serializers.Serializer):
        id = serializers.IntegerField()
        dropped = serializers.SerializerMethodField()

        def get_dropped(self, obj) -> str:
            return "x"

    Fast = from_drf(W, exclude=("dropped",))
    payload = Fast.drf(instance=_Src(id=1)).data
    parsed = json.loads(FastJSONRenderer().render(payload))
    assert parsed == {"id": 1}
    assert "dropped" not in getattr(Fast, "_fs_method_getters", {})


def test_smf_write_path_strips_input():
    """Client-supplied values for SMF field names must not survive is_valid."""

    class W(serializers.Serializer):
        id = serializers.IntegerField()
        kind = serializers.SerializerMethodField()

        def get_kind(self, obj) -> str:
            return "computed"

    Fast = from_drf(W)
    adapter = Fast.drf(data={"id": 1, "kind": "hacker-supplied"})
    assert adapter.is_valid(), adapter.errors
    assert adapter.validated_data.kind is None


def test_smf_init_failure_raises_migration_error():
    class W(serializers.Serializer):
        id = serializers.IntegerField()
        foo = serializers.SerializerMethodField()

        def __init__(self, required_arg, **kw):
            super().__init__(**kw)

        def get_foo(self, obj) -> str:
            return "x"

    with pytest.raises(MigrationError, match="instantiate"):
        from_drf(W)


def test_smf_appears_in_pydantic_schema_with_annotated_type():
    class W(serializers.Serializer):
        id = serializers.IntegerField()
        label = serializers.SerializerMethodField()

        def get_label(self, obj) -> str:
            return "x"

    Fast = from_drf(W)
    schema = Fast.model_json_schema()
    assert "label" in schema["properties"]
    # `T | None` from the SMF resolver shows up as anyOf [string, null].
    prop = schema["properties"]["label"]
    types = {entry.get("type") for entry in prop.get("anyOf", [])} or {prop.get("type")}
    assert "string" in types
