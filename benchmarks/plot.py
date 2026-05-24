"""Generate `docs/bench.svg`, an editorial-engineering benchmark chart.

Visual direction: a printed performance brief. Warm cream paper, single
deep-indigo accent for the library win, monospace numerals throughout,
strong typographic hierarchy with the speedup multiplier as the hero
number. Restrained neutral palette for everything else.

Hand-rolled SVG, zero plotting dependencies. Designed to render
correctly when embedded as `<img>` in a GitHub README: no `<filter>`,
no `<pattern>`, no external resources, no web fonts. System fonts only.

Regenerate after meaningful perf changes::

    uv run python -m benchmarks.plot
"""

import sys
from pathlib import Path

import pydantic

from benchmarks.bench import N_ROWS, RUNS, run

# Palette. Single accent (deep indigo) for library wins, restrained
# neutral scale for stock and reference floor. No red anywhere.
_BG = "#faf8f3"
_INK = "#0f0f17"
_INK_SOFT = "#3d3d4d"
_INK_FAINT = "#8a8a99"
_HAIRLINE = "#e3dfd6"
_ACCENT = "#1e1b4b"
_ACCENT_BAR = "#3730a3"
_STOCK_BAR = "#3d3d4d"
_FLOOR_BAR = "#c5c0b3"
_PILL_TEXT = "#ffffff"

# System font stacks. No web fonts; these must work on any machine that
# renders the SVG via `<img>`.
_FONT_MONO = '"Menlo", "Monaco", "Cascadia Code", "Consolas", "Courier New", monospace'
_FONT_SANS = '"Helvetica Neue", "Helvetica", "Arial", sans-serif'

_LIBRARY_LABELS = {"drf-fastserializers (mixin)", "drf-fastserializers (native)"}
_FLOOR_LABELS = {"Raw dict (reference floor)"}

_DISPLAY_LABEL = {
    "DRF Serializer (stock)": "DRF Serializer  ·  stock",
    "drf-fastserializers (mixin)": "drf-fastserializers  ·  mixin",
    "drf-fastserializers (native)": "drf-fastserializers  ·  native",
    "Raw dict (reference floor)": "raw dict  ·  reference floor",
}

_OUTPUT = Path(__file__).resolve().parent.parent / "docs" / "bench.svg"


def _bar_color(label: str) -> str:
    if label in _LIBRARY_LABELS:
        return _ACCENT_BAR
    if label in _FLOOR_LABELS:
        return _FLOOR_BAR
    return _STOCK_BAR


def render_svg(results: list[dict]) -> str:
    """Render the editorial benchmark report as a static SVG string."""
    width = 960
    height = 540
    pad_x = 56

    bar_area_x = 296
    bar_area_w = 460
    bars_top = 252
    row_h = 58
    bar_h = 22

    pill_w = 124
    pill_x = width - pad_x - pill_w

    baseline_ms = results[0]["median"]
    max_ms = max(r["median"] for r in results)
    # Round the chart scale up to a clean tick (next multiple of 25).
    scale_max = ((int(max_ms) // 25) + 1) * 25

    # The hero number is the strongest library speedup, not the average.
    # The chart below shows individual rows; the hero shows the headline win.
    library_results = [r for r in results if r["label"] in _LIBRARY_LABELS]
    best = min(library_results, key=lambda r: r["median"]) if library_results else results[0]
    hero_speedup = baseline_ms / best["median"]

    py_ver = ".".join(str(p) for p in sys.version_info[:3])
    pyd_ver = pydantic.VERSION

    parts: list[str] = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">'
        ),
        f'<rect width="{width}" height="{height}" fill="{_BG}"/>',
    ]

    # ---- HEADER ----------------------------------------------------------
    parts.append(
        f'<text x="{pad_x}" y="44" font-family={_FONT_MONO!r} font-size="11" '
        f'font-weight="600" fill="{_INK_FAINT}" letter-spacing="2.4">'
        f"BENCHMARK</text>"
    )
    parts.append(
        f'<text x="{width - pad_x}" y="44" font-family={_FONT_MONO!r} '
        f'font-size="11" font-weight="500" fill="{_INK_FAINT}" '
        f'text-anchor="end" letter-spacing="1.4">DRF-FASTSERIALIZERS</text>'
    )
    parts.append(
        f'<line x1="{pad_x}" y1="72" x2="{width - pad_x}" y2="72" '
        f'stroke="{_HAIRLINE}" stroke-width="1"/>'
    )

    # ---- HERO ------------------------------------------------------------
    # Massive speedup numeral, with "faster" sans-serif inline on the same
    # baseline. Subtitle stacks below.
    parts.append(
        f'<text y="180">'
        f'<tspan x="{pad_x}" font-family={_FONT_MONO!r} font-size="88" '
        f'font-weight="700" fill="{_ACCENT}" letter-spacing="-2">'
        f"{hero_speedup:.1f}×</tspan>"
        f'<tspan font-family={_FONT_SANS!r} font-size="30" font-weight="500" '
        f'fill="{_INK}" dx="22">faster</tspan>'
        f"</text>"
    )
    parts.append(
        f'<text x="{pad_x}" y="214" font-family={_FONT_SANS!r} '
        f'font-size="15" fill="{_INK_SOFT}">'
        f"than stock DRF on a {N_ROWS:,}-row response.  "
        f"one line of code.</text>"
    )
    parts.append(
        f'<line x1="{pad_x}" y1="232" x2="{width - pad_x}" y2="232" '
        f'stroke="{_HAIRLINE}" stroke-width="1"/>'
    )

    # ---- BARS ------------------------------------------------------------
    # Subtle dashed vertical marker at the stock baseline. Library bars
    # visibly end far to the left of it.
    baseline_x = bar_area_x + (baseline_ms / scale_max) * bar_area_w
    parts.append(
        f'<line x1="{baseline_x:.1f}" y1="{bars_top - 6}" '
        f'x2="{baseline_x:.1f}" y2="{bars_top + 4 * row_h + 6}" '
        f'stroke="{_INK_FAINT}" stroke-width="1" stroke-dasharray="2 5" '
        f'opacity="0.4"/>'
    )

    for i, r in enumerate(results):
        y_top = bars_top + i * row_h
        y_mid = y_top + row_h / 2
        bar_y = y_top + (row_h - bar_h) / 2
        bar_w = (r["median"] / scale_max) * bar_area_w

        is_lib = r["label"] in _LIBRARY_LABELS
        is_floor = r["label"] in _FLOOR_LABELS
        color = _bar_color(r["label"])
        speedup = baseline_ms / r["median"]

        # Strategy label, left column.
        if is_lib:
            label_color = _ACCENT
            label_weight = "600"
        elif is_floor:
            label_color = _INK_FAINT
            label_weight = "500"
        else:
            label_color = _INK
            label_weight = "600"
        parts.append(
            f'<text x="{pad_x}" y="{y_mid + 4}" font-family={_FONT_MONO!r} '
            f'font-size="13" font-weight="{label_weight}" '
            f'fill="{label_color}" letter-spacing="0.3">'
            f"{_DISPLAY_LABEL.get(r['label'], r['label'])}</text>"
        )

        # Bar.
        parts.append(
            f'<rect x="{bar_area_x}" y="{bar_y}" width="{bar_w:.1f}" '
            f'height="{bar_h}" fill="{color}" rx="2"/>'
        )

        # ms value, just past the end of the bar.
        val_x = bar_area_x + bar_w + 12
        val_color = _ACCENT if is_lib else (_INK_FAINT if is_floor else _INK)
        parts.append(
            f'<text x="{val_x:.1f}" y="{y_mid + 4}" font-family={_FONT_MONO!r} '
            f'font-size="15" font-weight="700" fill="{val_color}">'
            f"{r['median']:.0f}"
            f'<tspan font-size="11" font-weight="500" dx="2" opacity="0.7">'
            f"ms</tspan></text>"
        )

        # Right-edge annotation: filled pill for library wins; tracked
        # caps for everything else.
        if is_lib:
            parts.append(
                f'<rect x="{pill_x}" y="{y_mid - 12}" width="{pill_w}" '
                f'height="24" rx="12" fill="{_ACCENT}"/>'
            )
            parts.append(
                f'<text x="{pill_x + pill_w / 2}" y="{y_mid + 4}" '
                f'font-family={_FONT_MONO!r} font-size="10" font-weight="700" '
                f'fill="{_PILL_TEXT}" text-anchor="middle" '
                f'letter-spacing="1.6">{speedup:.2f}× SPEEDUP</text>'
            )
        else:
            note = "REFERENCE FLOOR" if is_floor else "BASELINE"
            parts.append(
                f'<text x="{width - pad_x}" y="{y_mid + 4}" '
                f'font-family={_FONT_MONO!r} font-size="10" font-weight="600" '
                f'fill="{_INK_FAINT}" text-anchor="end" letter-spacing="1.6">'
                f"{note}</text>"
            )

    # ---- FOOTER ----------------------------------------------------------
    parts.append(
        f'<line x1="{pad_x}" y1="500" x2="{width - pad_x}" y2="500" '
        f'stroke="{_HAIRLINE}" stroke-width="1"/>'
    )
    parts.append(
        f'<text x="{pad_x}" y="526" font-family={_FONT_MONO!r} '
        f'font-size="11" fill="{_INK_FAINT}" letter-spacing="0.6">'
        f"python {py_ver}  ·  pydantic {pyd_ver}  ·  "
        f"{N_ROWS:,} rows  ·  {RUNS} runs  ·  synthetic data</text>"
    )

    parts.append("</svg>")
    return "".join(parts)


def main() -> None:
    results = run()
    svg = render_svg(results)
    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _OUTPUT.write_text(svg)
    rel = _OUTPUT.relative_to(Path.cwd())
    print(f"wrote {rel}  ({len(svg):,} bytes)")


if __name__ == "__main__":
    main()
