"""
Generates assets/icon/icon.png (1024x1024) for the Cellar Sage app icon.
Dark background (#1a1b26) with the white fox silhouette centred on it.
Uses pycairo (which bundles Cairo DLLs on Windows) + svg.path.
"""

import pathlib
import re
import xml.etree.ElementTree as ET

import cairo
from svg.path import parse_path, Move, Line, CubicBezier, QuadraticBezier, Arc, Close

ROOT    = pathlib.Path(__file__).parent
SVG_IN  = ROOT / "assets" / "images" / "sage_fox_nobg.svg"
PNG_OUT = ROOT / "assets" / "icon" / "icon.png"
SIZE    = 1024

# Fox viewBox: "290 250 440 490"
VB_X, VB_Y, VB_W, VB_H = 290, 250, 440, 490
PADDING = 0.12           # 12% padding each side
SCALE   = SIZE * (1 - 2 * PADDING) / VB_H
OFFSET_X = (SIZE - VB_W * SCALE) / 2 - VB_X * SCALE
OFFSET_Y = (SIZE - VB_H * SCALE) / 2 - VB_Y * SCALE


_NAMED = {"white": "#ffffff", "black": "#000000", "none": None}

def hex_to_rgb(h: str):
    h = _NAMED.get(h.lower(), h)
    if not h:
        return None
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) / 255 for i in (0, 2, 4))


def apply_path(ctx: cairo.Context, d: str):
    """Feed an SVG path data string into a cairo context."""
    path = parse_path(d)
    for seg in path:
        if isinstance(seg, Move):
            ctx.move_to(seg.end.real, seg.end.imag)
        elif isinstance(seg, Line):
            ctx.line_to(seg.end.real, seg.end.imag)
        elif isinstance(seg, CubicBezier):
            ctx.curve_to(
                seg.control1.real, seg.control1.imag,
                seg.control2.real, seg.control2.imag,
                seg.end.real,      seg.end.imag,
            )
        elif isinstance(seg, QuadraticBezier):
            # Promote quadratic to cubic
            s, c, e = seg.start, seg.control, seg.end
            ctx.curve_to(
                s.real + 2/3 * (c.real - s.real),
                s.imag + 2/3 * (c.imag - s.imag),
                e.real + 2/3 * (c.real - e.real),
                e.imag + 2/3 * (c.imag - e.imag),
                e.real, e.imag,
            )
        elif isinstance(seg, Arc):
            # Approximate arc with cubic bezier (svg.path gives us points)
            # For simplicity, line to end — arcs are rare in this fox SVG
            ctx.line_to(seg.end.real, seg.end.imag)
        elif isinstance(seg, Close):
            ctx.close_path()


def draw_element(ctx: cairo.Context, elem, fill_override=None):
    d = elem.get("d", "")
    if not d:
        return

    fill_hex  = fill_override or elem.get("fill", "none")
    fill_rule = elem.get("fill-rule", "nonzero")

    stroke_hex  = elem.get("stroke", "none")
    stroke_w    = float(elem.get("stroke-width", "1"))

    ctx.save()
    ctx.new_path()
    apply_path(ctx, d)

    if fill_rule == "evenodd":
        ctx.set_fill_rule(cairo.FillRule.EVEN_ODD)
    else:
        ctx.set_fill_rule(cairo.FillRule.WINDING)

    fill_rgb   = hex_to_rgb(fill_hex)  if fill_hex   not in ("none", "") else None
    stroke_rgb = hex_to_rgb(stroke_hex) if stroke_hex not in ("none", "") else None

    if fill_rgb:
        ctx.set_source_rgb(*fill_rgb)
        if stroke_rgb:
            ctx.fill_preserve()
        else:
            ctx.fill()

    if stroke_rgb:
        ctx.set_source_rgb(*stroke_rgb)
        ctx.set_line_width(stroke_w)
        ctx.set_line_join(cairo.LineJoin.ROUND)
        ctx.stroke()

    ctx.restore()


def main():
    PNG_OUT.parent.mkdir(parents=True, exist_ok=True)

    tree = ET.parse(SVG_IN)
    ns   = {"svg": "http://www.w3.org/2000/svg"}
    elems = tree.findall(".//svg:path", ns) or tree.findall(".//path")
    if not elems:
        # Strip namespace from tags and retry
        for el in tree.iter():
            el.tag = re.sub(r"\{[^}]+\}", "", el.tag)
        elems = tree.findall(".//path")

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, SIZE, SIZE)
    ctx     = cairo.Context(surface)

    # White background
    ctx.set_source_rgb(1, 1, 1)
    ctx.paint()

    # Apply the viewBox transform: scale + centre
    ctx.translate(OFFSET_X, OFFSET_Y)
    ctx.scale(SCALE, SCALE)

    for elem in elems:
        # Keep original fills — dark fox on white bg, purple accents as-is.
        # White stroke is invisible on white bg; that's intentional.
        draw_element(ctx, elem)

    surface.write_to_png(str(PNG_OUT))
    print(f"Written: {PNG_OUT}  ({PNG_OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
