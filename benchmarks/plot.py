"""Generate `docs/bench.svg`, a polished benchmark chart.

Hand-rolled SVG, zero plotting dependencies. Layout takes cues from
modern data dashboards (Vercel, Linear, Stripe): generous whitespace,
two-tone palette, gradient-filled accent bars, pill-style speedup
annotations, soft outer card with a subtle shadow.

Regenerate after meaningful perf changes::

    uv run python -m benchmarks.plot
"""

import sys
from pathlib import Path

import pydantic

from benchmarks.bench import N_ROWS, RUNS, run

# Palette. Single accent (pydantic pink) for library bars, restrained
# slate scale for everything else.
_ACCENT = "#e92063"
_ACCENT_DARK = "#b3174a"
_ACCENT_SOFT = "#fce4ec"
_STOCK = "#64748b"
_STOCK_DARK = "#475569"
_FLOOR = "#cbd5e1"
_FLOOR_DARK = "#94a3b8"

_TEXT_PRIMARY = "#0f172a"
_TEXT_SECONDARY = "#475569"
_TEXT_MUTED = "#94a3b8"
_CANVAS = "#fafaf9"
_CARD = "#ffffff"
_BORDER = "#e7e5e4"

_LIBRARY_LABELS = {"drf-fastserializers (mixin)", "drf-fastserializers (native)"}
_FLOOR_LABELS = {"Raw dict (reference floor)"}

_OUTPUT = Path(__file__).resolve().parent.parent / "docs" / "bench.svg"


def _bar_palette(label: str) -> tuple[str, str]:
    """Return (fill_gradient_id, text_color) for a strategy label."""
    if label in _LIBRARY_LABELS:
        return "grad-accent", _ACCENT_DARK
    if label in _FLOOR_LABELS:
        return "grad-floor", _FLOOR_DARK
    return "grad-stock", _STOCK_DARK


def _pill(
    x: float,
    y: float,
    text: str,
    *,
    accent: bool,
) -> str:
    """Render a speedup pill. Filled accent for library wins, outline otherwise."""
    width = max(56, 12 + 7 * len(text))
    height = 22
    if accent:
        fill = _ACCENT
        stroke = "none"
        text_color = "#ffffff"
    else:
        fill = "#ffffff"
        stroke = _BORDER
        text_color = _TEXT_SECONDARY
    return (
        f'<g transform="translate({x:.1f},{y:.1f})">'
        f'<rect width="{width}" height="{height}" rx="11" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="1"/>'
        f'<text x="{width / 2}" y="15" text-anchor="middle" '
        f'font-size="11" font-weight="600" fill="{text_color}" '
        f'letter-spacing="0.2">{text}</text>'
        f"</g>"
    )


def render_svg(results: list[dict]) -> str:
    canvas_w = 920
    pad_outer = 24
    card_w = canvas_w - pad_outer * 2

    title_block_h = 110
    row_h = 78
    footer_h = 64
    rows = len(results)
    card_h = title_block_h + rows * row_h + footer_h
    canvas_h = card_h + pad_outer * 2

    bar_left = 280
    bar_right_padding = 220
    bar_max_w = card_w - bar_left - bar_right_padding
    bar_height = 30

    max_ms = max(r["median"] for r in results)
    baseline_ms = results[0]["median"]

    py_ver = ".".join(str(p) for p in sys.version_info[:3])
    pyd_ver = pydantic.VERSION

    parts: list[str] = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_w}" '
            f'height="{canvas_h}" viewBox="0 0 {canvas_w} {canvas_h}" '
            "font-family=\"-apple-system, BlinkMacSystemFont, 'Segoe UI', "
            'Roboto, Helvetica, Arial, sans-serif">'
        ),
        "<defs>",
        # Bar gradients: subtle vertical tone shift for depth.
        f'<linearGradient id="grad-accent" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{_ACCENT}"/>'
        f'<stop offset="100%" stop-color="{_ACCENT_DARK}"/></linearGradient>',
        f'<linearGradient id="grad-stock" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{_STOCK}"/>'
        f'<stop offset="100%" stop-color="{_STOCK_DARK}"/></linearGradient>',
        f'<linearGradient id="grad-floor" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{_FLOOR}"/>'
        f'<stop offset="100%" stop-color="{_FLOOR_DARK}"/></linearGradient>',
        # Card drop shadow.
        '<filter id="card-shadow" x="-10%" y="-10%" width="120%" height="130%">'
        '<feGaussianBlur in="SourceAlpha" stdDeviation="6"/>'
        '<feOffset dy="4" result="shadowOffset"/>'
        '<feComponentTransfer><feFuncA type="linear" slope="0.12"/></feComponentTransfer>'
        '<feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge>'
        "</filter>",
        "</defs>",
        # Canvas background.
        f'<rect width="{canvas_w}" height="{canvas_h}" fill="{_CANVAS}"/>',
        # Card.
        (
            f'<rect x="{pad_outer}" y="{pad_outer}" width="{card_w}" '
            f'height="{card_h}" rx="14" fill="{_CARD}" stroke="{_BORDER}" '
            f'stroke-width="1" filter="url(#card-shadow)"/>'
        ),
    ]

    # Title block.
    title_x = pad_outer + 36
    title_y = pad_outer + 50
    parts.append(
        f'<text x="{title_x}" y="{title_y}" font-size="22" font-weight="700" '
        f'fill="{_TEXT_PRIMARY}" letter-spacing="-0.4">'
        f"drf-fastserializers vs stock DRF</text>"
    )
    parts.append(
        f'<text x="{title_x}" y="{title_y + 24}" font-size="13" '
        f'fill="{_TEXT_SECONDARY}">'
        f"{N_ROWS:,} synthetic rows · median ms · lower is better</text>"
    )
    # Title divider.
    parts.append(
        f'<line x1="{pad_outer + 36}" y1="{pad_outer + title_block_h - 10}" '
        f'x2="{pad_outer + card_w - 36}" y2="{pad_outer + title_block_h - 10}" '
        f'stroke="{_BORDER}" stroke-width="1"/>'
    )

    # Vertical guide at the baseline position.
    baseline_x = pad_outer + bar_left + (baseline_ms / max_ms) * bar_max_w
    parts.append(
        f'<line x1="{baseline_x:.1f}" y1="{pad_outer + title_block_h + 8}" '
        f'x2="{baseline_x:.1f}" '
        f'y2="{pad_outer + title_block_h + rows * row_h - 8}" '
        f'stroke="{_BORDER}" stroke-width="1" stroke-dasharray="2 4"/>'
    )

    # Rows.
    for i, r in enumerate(results):
        row_top = pad_outer + title_block_h + i * row_h
        label_y = row_top + 22
        bar_y = row_top + 36
        bar_w = (r["median"] / max_ms) * bar_max_w
        gradient_id, _ = _bar_palette(r["label"])
        is_library = r["label"] in _LIBRARY_LABELS
        speedup = baseline_ms / r["median"]

        # Strategy label (above bar).
        label_weight = "600" if is_library else "500"
        label_color = _TEXT_PRIMARY if is_library else _TEXT_SECONDARY
        parts.append(
            f'<text x="{pad_outer + 36}" y="{label_y}" font-size="13" '
            f'font-weight="{label_weight}" fill="{label_color}">'
            f"{r['label']}</text>"
        )

        # Bar.
        parts.append(
            f'<rect x="{pad_outer + bar_left}" y="{bar_y}" '
            f'width="{bar_w:.1f}" height="{bar_height}" rx="6" '
            f'fill="url(#{gradient_id})"/>'
        )

        # ms value next to bar.
        ms_x = pad_outer + bar_left + bar_w + 12
        parts.append(
            f'<text x="{ms_x:.1f}" y="{bar_y + bar_height / 2 + 5}" '
            f'font-size="14" font-weight="700" '
            f'fill="{_TEXT_PRIMARY if is_library else _TEXT_SECONDARY}">'
            f"{r['median']:.0f} ms</text>"
        )

        # Speedup pill.
        pill_x = ms_x + 80
        parts.append(
            _pill(
                pill_x,
                bar_y + bar_height / 2 - 11,
                f"{speedup:.2f}x",
                accent=is_library,
            )
        )

    # Footer.
    footer_y = pad_outer + title_block_h + rows * row_h + 32
    parts.append(
        f'<text x="{pad_outer + 36}" y="{footer_y}" font-size="11" '
        f'fill="{_TEXT_MUTED}">'
        f"{RUNS} runs · Python {py_ver} · pydantic {pyd_ver} · "
        f"synthetic data · benchmarks/bench.py</text>"
    )

    parts.append("</svg>")
    return "\n".join(parts)


def main() -> None:
    results = run()
    svg = render_svg(results)
    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _OUTPUT.write_text(svg)
    print(f"wrote {_OUTPUT.relative_to(Path.cwd())}  ({len(svg):,} bytes)")


if __name__ == "__main__":
    main()
