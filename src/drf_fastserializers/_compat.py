"""Pydantic version compatibility gate.

Supports pydantic v2.7+ and v3.x. Both share the surface this library uses
(BaseModel, TypeAdapter, ConfigDict, ValidationError, model_dump_json).
"""

from typing import Final

import pydantic

_parts = pydantic.VERSION.split(".")
PYD_MAJOR: Final[int] = int(_parts[0])
PYD_MINOR: Final[int] = int(_parts[1])

if PYD_MAJOR < 2 or (PYD_MAJOR == 2 and PYD_MINOR < 7):
    raise RuntimeError(
        f"drf-fastserializers requires pydantic>=2.7, got {pydantic.VERSION}. "
        f"Upgrade with: pip install -U 'pydantic>=2.7'"
    )

PYD_V3: Final[bool] = PYD_MAJOR >= 3
