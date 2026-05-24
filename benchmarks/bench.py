"""Reproducible benchmark comparing serialization strategies.

Synthetic data only — every row is generated in-memory from `_make_rows`.
No real customer/coop/user names, no real IDs.

Run:

    uv run python -m benchmarks.bench

Or, from any directory with `drf-fastserializers` installed:

    DJANGO_SETTINGS_MODULE=benchmarks.settings python -m benchmarks.bench

Reports median + min + per-run timings over `RUNS` iterations, plus the
JSON payload size each strategy produced and a speedup column anchored
on the DRF baseline.
"""

import gc
import os
import statistics
import sys
import time
from datetime import date
from decimal import Decimal

# Bootstrap Django before importing DRF.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "benchmarks.settings")
import django  # noqa: E402

django.setup()

import pydantic  # noqa: E402
from rest_framework import serializers  # noqa: E402
from rest_framework.renderers import JSONRenderer  # noqa: E402

from drf_fastserializers import (  # noqa: E402
    FastJSONRenderer,
    FastSerializer,
    FastSerializerMixin,
)

N_ROWS = 21_393
RUNS = 5

# ---------------------------------------------------------------------------
# Synthetic row generator. No real data.
# ---------------------------------------------------------------------------

_MOCK_NAMES = ("mock-rent", "mock-payroll", "mock-refund", "mock-payment", "mock-fee")


def _make_rows(n: int) -> list[dict]:
    """Generate `n` synthetic txn-shaped rows."""
    return [
        {
            "id": i,
            "name": _MOCK_NAMES[i % len(_MOCK_NAMES)],
            "amount": Decimal("1200.50") if i % 4 else None,
            "txn_date": date(2026, 5, 1),
            "flags": {
                "is_nsf": i % 9 == 0,
                "is_refund": i % 3 == 0,
            },
            "tags": ["mock-tag-a", "mock-tag-b"],
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Strategy A — DRF Serializer on dicts (stock DRF, no library involved)
# ---------------------------------------------------------------------------


class _Flags(serializers.Serializer):
    is_nsf = serializers.BooleanField()
    is_refund = serializers.BooleanField()


class _TxnDRF(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True)
    txn_date = serializers.DateField()
    flags = _Flags()
    tags = serializers.ListField(child=serializers.CharField())


# ---------------------------------------------------------------------------
# Strategy B — same DRF Serializer, with FastSerializerMixin
# ---------------------------------------------------------------------------


class _TxnMixin(FastSerializerMixin, serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True)
    txn_date = serializers.DateField()
    flags = _Flags()
    tags = serializers.ListField(child=serializers.CharField())


# ---------------------------------------------------------------------------
# Strategy C — pydantic-native FastSerializer
# ---------------------------------------------------------------------------


class _FlagsPyd(FastSerializer):
    is_nsf: bool
    is_refund: bool


class _TxnPyd(FastSerializer):
    id: int
    name: str
    amount: Decimal | None
    txn_date: date
    flags: _FlagsPyd
    tags: list[str]


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------


def _bench(label: str, fn, *, runs: int = RUNS) -> dict:
    """Time `fn` `runs` times; return median, min, full list, payload bytes."""
    timings: list[float] = []
    payload_bytes = 0
    for _ in range(runs):
        gc.collect()
        t0 = time.perf_counter()
        payload_bytes = fn()
        timings.append((time.perf_counter() - t0) * 1000)
    return {
        "label": label,
        "median": statistics.median(timings),
        "min": min(timings),
        "all": [round(x, 1) for x in timings],
        "bytes": payload_bytes,
    }


def _strategy_raw(rows: list[dict], drf_renderer: JSONRenderer) -> int:
    """Baseline: pass dicts straight to JSONRenderer. No validation, no schema."""
    raw = drf_renderer.render(rows)
    return len(raw)


def _strategy_drf(rows: list[dict], drf_renderer: JSONRenderer) -> int:
    """Stock DRF Serializer on dicts."""
    data = _TxnDRF(rows, many=True).data
    raw = drf_renderer.render(data)
    return len(raw)


def _strategy_mixin(rows: list[dict], fast_renderer: FastJSONRenderer) -> int:
    """Stock DRF Serializer + FastSerializerMixin."""
    data = _TxnMixin(rows, many=True).data
    raw = fast_renderer.render(data)
    return len(raw)


def _strategy_native(rows: list[dict], fast_renderer: FastJSONRenderer) -> int:
    """Pydantic-native FastSerializer + FastJSONRenderer."""
    data = _TxnPyd.drf(instance=rows, many=True).data
    raw = fast_renderer.render(data)
    return len(raw)


def run() -> list[dict]:
    """Run every strategy and return the result dicts.

    Exposed so plot.py and other consumers can capture the numbers
    without scraping the printed table. The first entry is always the
    stock DRF baseline; speedups should be anchored on `results[0]["median"]`.
    """
    rows = _make_rows(N_ROWS)
    drf_renderer = JSONRenderer()
    fast_renderer = FastJSONRenderer()

    return [
        _bench("DRF Serializer (stock)", lambda: _strategy_drf(rows, drf_renderer)),
        _bench(
            "drf-fastserializers (mixin)",
            lambda: _strategy_mixin(rows, fast_renderer),
        ),
        _bench(
            "drf-fastserializers (native)",
            lambda: _strategy_native(rows, fast_renderer),
        ),
        _bench(
            "Raw dict (reference floor)",
            lambda: _strategy_raw(rows, drf_renderer),
        ),
    ]


def main() -> None:
    results = run()
    baseline_median = results[0]["median"]

    print(
        f"\nN={N_ROWS:,} synthetic rows, {RUNS} runs each\n"
        f"python={sys.version.split()[0]}  pydantic={pydantic.VERSION}\n"
    )
    print(f"{'Strategy':<32} {'median_ms':>10} {'min_ms':>8} {'speedup':>9} {'kB':>8}")
    print("-" * 72)
    for r in results:
        speedup = baseline_median / r["median"]
        print(
            f"{r['label']:<32} "
            f"{r['median']:>10.1f} "
            f"{r['min']:>8.1f} "
            f"{speedup:>8.2f}x "
            f"{r['bytes'] / 1024:>8.0f}"
        )

    print("\nPer-run timings (ms):")
    for r in results:
        print(f"  {r['label']:<32} {r['all']}")

    # Spot-check: all strategies should produce ~the same payload size.
    sizes = {r["bytes"] for r in results}
    if max(sizes) - min(sizes) > max(sizes) * 0.05:
        print(
            f"\nWARNING: payload sizes diverge by >5% — strategies may not be "
            f"producing equivalent output. Sizes: {sizes}"
        )


if __name__ == "__main__":
    main()
