"""Tests for pydantic→DRF error coercion."""

from pydantic import ValidationError

from drf_fastserializers._errors import pydantic_errors_to_drf

from .conftest import TxnOut


def _try_validate(data: dict) -> ValidationError:
    try:
        TxnOut.model_validate(data)
    except ValidationError as exc:
        return exc
    raise AssertionError("expected ValidationError")


def test_top_level_field_error_keyed_by_field_name():
    exc = _try_validate({"id": "not-an-int", "name": "x"})
    errs = pydantic_errors_to_drf(exc)
    assert "id" in errs
    assert isinstance(errs["id"], list)
    assert len(errs["id"]) >= 1


def test_missing_required_fields_reported():
    exc = _try_validate({"id": 1})
    errs = pydantic_errors_to_drf(exc)
    assert "name" in errs
    assert "txn_date" in errs
    assert "flags" in errs


def test_nested_field_path_dotted():
    exc = _try_validate(
        {
            "id": 1,
            "name": "x",
            "txn_date": "2026-05-01",
            "flags": {"is_nsf": "not-a-bool"},
        }
    )
    errs = pydantic_errors_to_drf(exc)
    assert "flags.is_nsf" in errs


def test_empty_loc_maps_to_non_field_errors():
    """Synthetic case: pydantic ValidationError with empty loc tuple."""

    class _Fake:
        def errors(self):
            return [{"loc": (), "msg": "object-level failure", "type": "value_error"}]

    out = pydantic_errors_to_drf(_Fake())  # type: ignore[arg-type]
    assert "non_field_errors" in out
    assert out["non_field_errors"] == ["object-level failure"]
