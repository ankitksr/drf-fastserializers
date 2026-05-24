"""Coerce pydantic ValidationError into DRF's `{field: [msg, ...]}` shape."""

from pydantic import ValidationError


def pydantic_errors_to_drf(exc: ValidationError) -> dict[str, list[str]]:
    """Flatten pydantic loc paths to dotted keys. Aggregate messages per key.

    Pydantic loc is a tuple like ('user', 'addresses', 0, 'zip'); DRF expects
    a flat dotted field name. Empty loc maps to 'non_field_errors' to match
    DRF's idiom for object-level validation failures.
    """
    out: dict[str, list[str]] = {}
    for err in exc.errors():
        loc = ".".join(str(part) for part in err["loc"]) or "non_field_errors"
        out.setdefault(loc, []).append(err["msg"])
    return out
