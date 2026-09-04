"""Procedural artwork for AI posts when no image generator is configured.

Every AI post gets a unique abstract picture rendered with cairo, seeded by the
post text so the same caption always produces the same picture.
"""

from __future__ import annotations

import colorsys
import hashlib
import math
import random
from pathlib import Path
from typing import Optional

try:
    import cairo
except ImportError:  # pragma: no cover - handled at runtime
    cairo = None

DEFAULT_PALETTES = [
    ["#ff7b54", "#ffb26b", "#ffd56f", "#939b62"],
    ["#5f0f40", "#9a031e", "#fb8b24", "#e36414"],
    ["#0b132b", "#1c2541", "#3a506b", "#5bc0be"],
    ["#f72585", "#7209b7", "#3a0ca3", "#4cc9f0"],
    ["#264653", "#2a9d8f", "#e9c46a", "#f4a261"],
    ["#ffcdb2", "#ffb4a2", "#e5989b", "#b5838d"],
    ["#03045e", "#0077b6", "#00b4d8", "#caf0f8"],
    ["#2b2d42", "#8d99ae", "#edf2f4", "#ef233c"],
    ["#606c38", "#283618", "#fefae0", "#dda15e"],
    ["#10002b", "#5a189a", "#9d4edd", "#e0aaff"],
]


def hex_to_rgb(value: str) -> tuple[float, float, float]:
    value = value.lstrip("#")
    if len(value) != 6:
        return (0.5, 0.5, 0.5)
    return tuple(int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def palette_for(seed: str) -> list[str]:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return DEFAULT_PALETTES[digest[0] % len(DEFAULT_PALETTES)]


def _shift(rgb: tuple[float, float, float], dh: float, ds: float = 0.0, dl: float = 0.0):
    h, l, s = colorsys.rgb_to_hls(*rgb)
    h = (h + dh) % 1.0
    l = min(1.0, max(0.0, l + dl))
    s = min(1.0, max(0.0, s + ds))
    return colorsys.hls_to_rgb(h, l, s)


def render_post_art(seed: str, out_path: Path | str, palette: Optional[list[str]] = None,
                    size: int = 768) -> Optional[str]:
    """Render an abstract picture to ``out_path`` (PNG). Returns the path or None."""
    if cairo is None:
        return None
    rng = random.Random(hashlib.sha256(seed.encode("utf-8")).hexdigest())
    colors = [hex_to_rgb(c) for c in (palette or palette_for(seed))]
    if len(colors) < 2:
        colors = [hex_to_rgb(c) for c in palette_for(seed)]

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    ctx = cairo.Context(surface)

    # Background gradient
    angle = rng.random() * math.pi * 2
    gx, gy = math.cos(angle) * size, math.sin(angle) * size
    grad = cairo.LinearGradient(size / 2 - gx / 2, size / 2 - gy / 2, size / 2 + gx / 2, size / 2 + gy / 2)
    c0, c1 = rng.sample(colors, 2)
    grad.add_color_stop_rgb(0, *c0)
    grad.add_color_stop_rgb(1, *c1)
    ctx.set_source(grad)
    ctx.rectangle(0, 0, size, size)
    ctx.fill()

    style = rng.choice(["bokeh", "ribbons", "blocks", "orbits", "dunes"])

    if style == "bokeh":
        for _ in range(rng.randint(18, 40)):
            col = _shift(rng.choice(colors), rng.uniform(-0.05, 0.05), 0.1, rng.uniform(0.0, 0.25))
            radius = rng.uniform(size * 0.03, size * 0.22)
            x, y = rng.uniform(-radius, size + radius), rng.uniform(-radius, size + radius)
            rad = cairo.RadialGradient(x, y, 0, x, y, radius)
            rad.add_color_stop_rgba(0, *col, rng.uniform(0.35, 0.75))
            rad.add_color_stop_rgba(1, *col, 0.0)
            ctx.set_source(rad)
            ctx.arc(x, y, radius, 0, math.tau)
            ctx.fill()
    elif style == "ribbons":
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        for _ in range(rng.randint(6, 14)):
            col = _shift(rng.choice(colors), rng.uniform(-0.08, 0.08), 0.0, rng.uniform(-0.1, 0.2))
            ctx.set_source_rgba(*col, rng.uniform(0.45, 0.9))
            ctx.set_line_width(rng.uniform(size * 0.02, size * 0.12))
            x = rng.uniform(-size * 0.2, size * 0.2)
            y = rng.uniform(0, size)
            ctx.move_to(x, y)
            for _ in range(3):
                ctx.curve_to(
                    rng.uniform(0, size), rng.uniform(0, size),
                    rng.uniform(0, size), rng.uniform(0, size),
                    rng.uniform(size * 0.8, size * 1.2), rng.uniform(0, size),
                )
            ctx.stroke()
    elif style == "blocks":
        cols = rng.randint(3, 7)
        cell = size / cols
        for i in range(cols):
            for j in range(cols):
                if rng.random() < 0.35:
                    continue
                col = _shift(rng.choice(colors), 0, 0, rng.uniform(-0.15, 0.15))
                ctx.set_source_rgba(*col, rng.uniform(0.5, 0.95))
                pad = cell * rng.uniform(0.0, 0.2)
                shape = rng.random()
                x, y = i * cell + pad, j * cell + pad
                w = cell - 2 * pad
                if shape < 0.5:
                    ctx.rectangle(x, y, w, w)
                elif shape < 0.8:
                    ctx.arc(x + w / 2, y + w / 2, w / 2, 0, math.tau)
                else:
                    ctx.move_to(x, y + w)
                    ctx.line_to(x + w / 2, y)
                    ctx.line_to(x + w, y + w)
                    ctx.close_path()
                ctx.fill()
    elif style == "orbits":
        cx, cy = size * rng.uniform(0.3, 0.7), size * rng.uniform(0.3, 0.7)
        for k in range(rng.randint(8, 18)):
            col = _shift(rng.choice(colors), rng.uniform(-0.05, 0.05), 0.1, rng.uniform(0.0, 0.3))
            ctx.set_source_rgba(*col, rng.uniform(0.3, 0.8))
            ctx.set_line_width(rng.uniform(2, size * 0.03))
            r = size * (0.05 + k * 0.05) * rng.uniform(0.8, 1.2)
            start = rng.uniform(0, math.tau)
            ctx.arc(cx, cy, r, start, start + rng.uniform(0.5, math.tau))
            ctx.stroke()
        glow = cairo.RadialGradient(cx, cy, 0, cx, cy, size * 0.25)
        glow.add_color_stop_rgba(0, 1, 1, 1, 0.8)
        glow.add_color_stop_rgba(1, 1, 1, 1, 0.0)
        ctx.set_source(glow)
        ctx.arc(cx, cy, size * 0.25, 0, math.tau)
        ctx.fill()
    else:  # dunes
        layers = rng.randint(4, 8)
        for k in range(layers):
            col = _shift(rng.choice(colors), 0, 0, -0.05 * k)
            ctx.set_source_rgba(*col, 0.9)
            base = size * (0.35 + 0.65 * k / layers)
            ctx.move_to(0, size)
            ctx.line_to(0, base + rng.uniform(-40, 40))
            x = 0.0
            while x < size:
                nx = x + size / rng.uniform(2.5, 5)
                ctx.curve_to(
                    x + (nx - x) / 3, base + rng.uniform(-size * 0.12, size * 0.12),
                    x + 2 * (nx - x) / 3, base + rng.uniform(-size * 0.12, size * 0.12),
                    nx, base + rng.uniform(-size * 0.08, size * 0.08),
                )
                x = nx
            ctx.line_to(size, size)
            ctx.close_path()
            ctx.fill()

    # Subtle vignette + grain
    vignette = cairo.RadialGradient(size / 2, size / 2, size * 0.35, size / 2, size / 2, size * 0.8)
    vignette.add_color_stop_rgba(0, 0, 0, 0, 0)
    vignette.add_color_stop_rgba(1, 0, 0, 0, 0.35)
    ctx.set_source(vignette)
    ctx.rectangle(0, 0, size, size)
    ctx.fill()
    for _ in range(size * 2):
        ctx.set_source_rgba(1, 1, 1, rng.uniform(0.02, 0.08))
        ctx.rectangle(rng.uniform(0, size), rng.uniform(0, size), 1.5, 1.5)
        ctx.fill()

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    surface.write_to_png(str(out_path))
    return str(out_path)
