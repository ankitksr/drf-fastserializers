"""ReadOnlyField mapping + Django RelatedManager coercion in from_drf."""

import json

from django.db.models import Manager
from rest_framework import serializers

from drf_fastserializers import FastJSONRenderer, from_drf


def test_read_only_field_maps_to_any():
    class S(serializers.Serializer):
        id = serializers.IntegerField()
        annotated = serializers.ReadOnlyField()

    Fast = from_drf(S)
    payload = Fast.drf(instance={"id": 1, "annotated": {"k": "v"}}).data
    parsed = json.loads(FastJSONRenderer().render(payload))
    assert parsed == {"id": 1, "annotated": {"k": "v"}}


def test_read_only_field_carries_arbitrary_types():
    """ReadOnlyField → Any so any value shape renders as-is."""

    class S(serializers.Serializer):
        id = serializers.IntegerField()
        misc = serializers.ReadOnlyField()

    Fast = from_drf(S)
    for v in (42, "hello", [1, 2], {"nested": True}, None):
        payload = Fast.drf(instance={"id": 1, "misc": v}).data
        parsed = json.loads(FastJSONRenderer().render(payload))
        assert parsed["misc"] == v


class _RecordingManager(Manager):
    """Manager stand-in that tracks `.all()` calls and returns prefetched data.

    Mimics the shape DRF receives from `obj.children_set` on a parent
    where `prefetch_related('children_set')` was applied: pydantic gets
    the manager, our before-validator must call `.all()` to honor the
    prefetch cache, otherwise iterating the manager would query again.
    """

    def __init__(self, items):
        super().__init__()
        self._items = items
        self.all_called = False

    def all(self):
        self.all_called = True
        return self._items


def test_related_manager_coerced_via_all_on_list_fields():
    class Child(serializers.Serializer):
        id = serializers.IntegerField()

    class Parent(serializers.Serializer):
        kids = Child(many=True)

    Fast = from_drf(Parent)
    mgr = _RecordingManager([{"id": 1}, {"id": 2}])
    payload = Fast.drf(instance={"kids": mgr}).data
    parsed = json.loads(FastJSONRenderer().render(payload))
    assert mgr.all_called
    assert parsed == {"kids": [{"id": 1}, {"id": 2}]}


def test_manager_coercer_passes_through_non_managers():
    """A plain list on a list field is untouched (no `.all()` confusion)."""

    class Child(serializers.Serializer):
        id = serializers.IntegerField()

    class Parent(serializers.Serializer):
        kids = Child(many=True)

    Fast = from_drf(Parent)
    payload = Fast.drf(instance={"kids": [{"id": 7}]}).data
    parsed = json.loads(FastJSONRenderer().render(payload))
    assert parsed == {"kids": [{"id": 7}]}


def test_manager_coerced_on_optional_list_field():
    """`list[T] | None` shapes (required=False) still get the coercer."""

    class Child(serializers.Serializer):
        id = serializers.IntegerField()

    class Parent(serializers.Serializer):
        kids = Child(many=True, required=False)

    Fast = from_drf(Parent)
    mgr = _RecordingManager([{"id": 1}])
    payload = Fast.drf(instance={"kids": mgr}).data
    parsed = json.loads(FastJSONRenderer().render(payload))
    assert mgr.all_called
    assert parsed == {"kids": [{"id": 1}]}


def test_manager_coercer_works_with_list_field_of_scalars():
    """ListField(child=IntegerField) also routes through the coercer."""

    class S(serializers.Serializer):
        ids = serializers.ListField(child=serializers.IntegerField())

    Fast = from_drf(S)
    mgr = _RecordingManager([1, 2, 3])
    payload = Fast.drf(instance={"ids": mgr}).data
    parsed = json.loads(FastJSONRenderer().render(payload))
    assert mgr.all_called
    assert parsed == {"ids": [1, 2, 3]}
