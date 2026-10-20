#!/usr/bin/env python3
"""Daf icon, round 4: the macOS 26 appearances of round 3's final (the beech tree rooted in two books).

    python3 make.py

writes
    light.svg, light-small.svg      round 3's final.svg and final-small.svg, copied for the side-by-side
    dark.svg, dark-small.svg        the same drawing on a deep warm charcoal tile, its parchment lifted a little
    tinted.svg, tinted-small.svg    one-tone (greyscale) for the Tinted appearance, which macOS colours itself
    layers/                         background, books and tree as transparent 1024 PNGs and SVGs for Icon Composer
    layers/dark/                    the same three layers for the Dark appearance
    sheet.png                       the three appearances at 256/64/32/16 on light and dark, and a Dock strip by Moshe

The drawing itself is imported from round 3 (r3/tree/make.py), so there is one source for its geometry.
"""
import os
import re
import shutil
import sys

R3 = "/srv/dev/daf/design/icon/r3/tree"
sys.path.insert(0, R3)
import make as T  # noqa: E402  round 3: tree, books, leaves, palette, and kit with its longer paint wait

kit = T.kit
HERE = os.path.dirname(os.path.abspath(__file__))
MOSHE = "/srv/dev/moshe-next/frontend/public/icons/icon-512.png"
FULL_BLEED = 1024 / 824   # Icon Composer masks the whole 1024 canvas; kit's tile is 824 wide, so layers scale up


# ---------------------------------------------------------------- appearances

DARK = dict(T.DEEP,                     # parchment lifted a step so it glows a little on charcoal
            leaf_lit="#EACD95", leaf_shade="#D7AC68", page="#F6EBD2", page_edge="#E6CF9F", page_line="#C9AA75",
            fold="#DEC28B", cover="#AC743F", ink="#86501F",
            ink_deep="#93633A")         # the trunk, lifted so it holds against the dark tile
GREY = dict(                            # Tinted: clear values, no colour of their own
    page="#F0F0F0", page_edge="#D2D2D2", page_line="#9C9C9C", leaf_lit="#D6D6D6", leaf_shade="#BABABA",
    fold="#C6C6C6", ink="#5E5E5E", ink_deep="#8E8E8E", cover="#8A8A8A")

APPEAR = dict(
    light=dict(tones=T.DEEP, spine="#7A4A22", accent="#1A7DA4", tile=("#FFFFFF", "#F2EFEA"),
               ground=("#5E3F1A", 0.16, 1.0), spec="#FFF7E6", halo=0.0, grey=False),
    dark=dict(tones=DARK, spine="#8E5B2E", accent="#57B3D7", tile=("#2A2622", "#1E1B18"),
              ground=("#000000", 0.55, 0.75), spec="#FFF0D2", halo=0.07, grey=False, rim=0.13),
    tinted=dict(tones=GREY, spine="#5A5A5A", accent="#3A3A3A", tile=("#2C2C2C", "#1B1B1B"),
                ground=("#000000", 0.55, 0.75), spec="#FFFFFF", halo=0.0, grey=True, rim=0.13),
)


def set_palette(ap):
    T.C.clear()
    T.C.update(T.BASE_C)
    T.C.update(ap["tones"])
    T.SPINE_DEEP = ap["spine"]
    T.ACCENT["ap"] = ap["accent"]


def placement(svg_path):
    """(tx, ty, k) of the object in a shipped round-3 icon, so every appearance and layer sits exactly there."""
    m = re.search(r"translate\(([-\d.]+) ([-\d.]+)\) scale\(([\d.]+)\)", open(svg_path).read())
    return tuple(float(g) for g in m.groups())


PLACE = placement(os.path.join(R3, "final.svg"))
PLACE_S = placement(os.path.join(R3, "final-small.svg"))


# ---------------------------------------------------------------- round 3's final, split into layers

def parts(sc):
    """r3 tree(crown="calm", books="character", trunk=1.25, accent=...) as two layers: books, and the tree."""
    trunk, ink, kw = 1.25, T.C["ink_deep"], dict(veins="text")
    books = (T.spine_book(262, 704, 500, 80, T.SPINE_DEEP)
             + T.closed_book(318, 628, 432, 76, spine="right", lines=3, spine_col=T.ACCENT["ap"]))
    roots = (T.stem([(500, 631), (466, 627), (430, 632)], 13 * trunk ** 0.5, 3, ink)
             + T.stem([(524, 631), (558, 627), (596, 632)], 13 * trunk ** 0.5, 3, ink))
    stem_ = T.stem([(512, 640), (507, 572), (514, 505), (511, 440), (512, 392)], 38 * trunk, 11 * trunk, ink)
    br = (T.stem([(511, 530), (480, 500), (456, 482)], 15 * trunk, 6, ink)
          + T.stem([(512, 478), (484, 448), (462, 430)], 14 * trunk, 6, ink)
          + T.stem([(513, 505), (546, 478), (568, 462)], 15 * trunk, 6, ink)
          + T.stem([(512, 450), (542, 422), (560, 404)], 14 * trunk, 6, ink))
    top = (T.leaf(sc, (456, 484), 172, -72, petiole=8, **kw)
           + T.leaf(sc, (568, 464), 170, 70, petiole=8, **kw)
           + T.leaf(sc, (462, 432), 186, -42, petiole=8, **kw)
           + T.leaf(sc, (560, 406), 178, 40, petiole=8, **kw)
           + T.leaf(sc, (512, 394), 222, 2, petiole=6, fold=(0.80, 14), **kw))
    return dict(books=books, tree=roots + stem_ + br + top), (512, 786, 230, 10)


def parts_small(sc):
    """r3 tree_small as two layers."""
    ink = T.C["ink_deep"]
    books = (f'<path d="{T.rrect(262, 700, 500, 88, 14)}" fill="{T.SPINE_DEEP}"/>'
             + T.closed_book(318, 616, 432, 92, spine="right", lines=0, cover=17, spine_col=T.ACCENT["ap"]))
    stem_ = T.stem([(512, 630), (508, 570), (513, 500)], 62, 34, ink)
    top = f'<path d="{T.crown_blob(512, 436, 168, 150)}" fill="{T.C["leaf_shade"]}"/>'
    return dict(books=books, tree=stem_ + top), (512, 790, 230, 10)


def check_split():
    """The split must redraw round 3 exactly: same paths, same ids, in the same order."""
    set_palette(APPEAR["light"])
    a, b = T.Scene(), T.Scene()
    p, _ = parts(a)
    whole, _ = T.tree(b, crown="calm", books="character", trunk=1.25, accent="ap")
    assert p["books"] + p["tree"] == whole and a.defs == b.defs, "layer split differs from round 3's drawing"
    a, b = T.Scene(), T.Scene()
    p, _ = parts_small(a)
    whole, _ = T.tree_small(b, accent="ap")
    assert p["books"] + p["tree"] == whole, "small layer split differs from round 3's drawing"


# ---------------------------------------------------------------- finish and assembly

def paper_filter(ap, lit=True, grain=(0.6, 0.26, -0.11, 0.40, -0.18), bump=(9, 6, 0.75)):
    g = grain
    halo = ap["halo"] if lit else 0   # layers get no glow either: Icon Composer lights them itself
    return f"""
<filter id="daf-paper" x="-15%" y="-15%" width="130%" height="130%" color-interpolation-filters="sRGB">
  <feTurbulence type="fractalNoise" baseFrequency="{g[0]}" numOctaves="2" seed="11" result="fine"/>
  <feColorMatrix in="fine" type="matrix" values="0 0 0 0 0.42  0 0 0 0 0.27  0 0 0 0 0.10  {g[1]} 0 0 0 {g[2]}" result="fineA"/>
  <feTurbulence type="fractalNoise" baseFrequency="0.009 0.015" numOctaves="3" seed="4" result="mot"/>
  <feColorMatrix in="mot" type="matrix" values="0 0 0 0 0.55  0 0 0 0 0.36  0 0 0 0 0.14  {g[3]} 0 0 0 {g[4]}" result="motA"/>
  <feMerge result="grain"><feMergeNode in="motA"/><feMergeNode in="fineA"/></feMerge>
  <feComposite in="grain" in2="SourceAlpha" operator="in" result="grainIn"/>
  <feGaussianBlur in="SourceAlpha" stdDeviation="{bump[0]}" result="bump"/>
  <feSpecularLighting in="bump" surfaceScale="{bump[1]}" specularConstant="{bump[2] if lit else 0}" specularExponent="18" lighting-color="{ap['spec']}" result="spec">
    <feDistantLight azimuth="270" elevation="40"/>
  </feSpecularLighting>
  <feComposite in="spec" in2="SourceAlpha" operator="in" result="specIn"/>
  <feGaussianBlur in="SourceAlpha" stdDeviation="22" result="hb"/>
  <feFlood flood-color="#F3DCAA" flood-opacity="{halo}"/>
  <feComposite in2="hb" operator="in" result="halo"/>
  <feMerge><feMergeNode in="halo"/><feMergeNode in="SourceGraphic"/><feMergeNode in="grainIn"/>{'<feMergeNode in="specIn"/>' if lit else ''}</feMerge>
</filter>
<filter id="daf-grey" color-interpolation-filters="sRGB"><feColorMatrix type="saturate" values="0"/></filter>"""


def ground_svg(ap, ground):
    cx, cy, rx, ry = ground
    col, op, spread = ap["ground"]
    return (f'<filter id="daf-ground" x="-50%" y="-200%" width="200%" height="500%"><feGaussianBlur stdDeviation="{ry * 0.8 * spread:.1f}"/></filter>',
            f'<ellipse cx="{cx}" cy="{cy}" rx="{rx * spread:.1f}" ry="{ry * spread:.1f}" fill="{col}" fill-opacity="{op}" filter="url(#daf-ground)"/>')


def icon(name, small=False):
    """A full icon (kit's tile, shadow and all) in one appearance."""
    ap = APPEAR[name]
    set_palette(ap)
    sc = T.Scene()
    p, ground = (parts_small if small else parts)(sc)
    gdef, gsvg = ground_svg(ap, ground)
    tx, ty, k = PLACE_S if small else PLACE
    body = f'<g transform="translate({tx} {ty}) scale({k})">{gsvg}<g filter="url(#daf-paper)">{p["books"]}{p["tree"]}</g></g>'
    if ap["grey"]:
        body = f'<g filter="url(#daf-grey)">{body}</g>'
    if ap.get("rim"):   # a faint light rim inside the tile's edge, brighter at the top, as on Apple's dark icons
        gdef += ('<linearGradient id="daf-rim" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF" stop-opacity="1"/>'
                 '<stop offset="1" stop-color="#FFFFFF" stop-opacity="0.35"/></linearGradient>')
        body += f'<path d="{kit.SQ}" fill="none" stroke="url(#daf-rim)" stroke-opacity="{ap["rim"]}" stroke-width="5"/>'
    return kit.tile(body, "".join(sc.defs) + paper_filter(ap) + gdef, top=ap["tile"][0], bot=ap["tile"][1])


def layer_svgs(name):
    """Background, books and tree on a transparent, full-bleed 1024 canvas, all in the same position.
    No baked shadow or lit edge: Icon Composer adds its own shadow and glass. The grain stays."""
    ap = APPEAR[name]
    set_palette(ap)
    sc = T.Scene()
    p, _ = parts(sc)
    tx, ty, k = PLACE
    place = f"translate(512 512) scale({FULL_BLEED:.5f}) translate(-512 -512) translate({tx} {ty}) scale({k})"
    defs = "".join(sc.defs) + paper_filter(ap, lit=False)
    head = '<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">'
    out = {"background": (f'{head}<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{ap["tile"][0]}"/>'
                          f'<stop offset="1" stop-color="{ap["tile"][1]}"/></linearGradient></defs>'
                          f'<rect width="1024" height="1024" fill="url(#bg)"/></svg>')}
    for key in ("books", "tree"):
        out[key] = f'{head}<defs>{defs}</defs><g transform="{place}"><g filter="url(#daf-paper)">{p[key]}</g></g></svg>'
    return out


# ---------------------------------------------------------------- sheet with a Dock strip

def dock_strip(rows, out, size=128):
    """Moshe beside Daf's light, dark and tinted icons (and the tinted one coloured as macOS might), on two desktops."""
    from PIL import Image, ImageDraw, ImageOps
    tmp = os.path.join(HERE, ".d.png")
    ims = []
    for svg in rows:
        kit.render(svg, tmp, size)
        ims.append(Image.open(tmp).convert("RGBA"))
    os.remove(tmp)
    t = ims[-1]
    tint = ImageOps.colorize(t.convert("L"), black="#0B1820", white="#8FD3EE").convert("RGBA")
    tint.putalpha(t.getchannel("A"))
    moshe = Image.open(MOSHE).convert("RGBA").resize((size, size), Image.LANCZOS)
    icons = [moshe] + ims + [tint]
    labels = ["Moshe", "Daf light", "Daf dark", "Daf tinted", "tinted, coloured"]
    gap = 40
    W = len(icons) * (size + gap) + gap
    strip = Image.new("RGBA", (W, 2 * (size + 70)), (255, 255, 255, 255))
    dr = ImageDraw.Draw(strip)
    try:
        from PIL import ImageFont
        font = ImageFont.load_default(size=15)
    except TypeError:
        font = None
    for r, (bg, fg) in enumerate((((214, 220, 228, 255), (40, 40, 40)), ((36, 38, 44, 255), (225, 225, 225)))):
        y0 = r * (size + 70)
        dr.rounded_rectangle([gap // 2, y0 + 14, W - gap // 2, y0 + size + 56], radius=26, fill=bg)
        for i, im in enumerate(icons):
            x = gap + i * (size + gap)
            strip.alpha_composite(im, (x, y0 + 24))
            dr.text((x, y0 + size + 32), labels[i], fill=fg, font=font)
    strip.save(out)


def main():
    check_split()
    os.makedirs(os.path.join(HERE, "layers", "dark"), exist_ok=True)
    shutil.copy(os.path.join(R3, "final.svg"), os.path.join(HERE, "light.svg"))
    shutil.copy(os.path.join(R3, "final-small.svg"), os.path.join(HERE, "light-small.svg"))
    for name in ("dark", "tinted"):
        open(os.path.join(HERE, f"{name}.svg"), "w").write(icon(name))
        open(os.path.join(HERE, f"{name}-small.svg"), "w").write(icon(name, small=True))
    for name, sub in (("light", ""), ("dark", "dark")):
        for key, svg in layer_svgs(name).items():
            p = os.path.join(HERE, "layers", sub, f"{key}.svg")
            open(p, "w").write(svg)
            kit.render(p, p[:-4] + ".png", 1024)
    rows = ["light", "dark", "tinted", "light-small", "dark-small", "tinted-small"]
    notes = ["Default (light): round 3's final, unchanged.",
             "Dark: warm charcoal tile, parchment lifted a step, the trunk lifted, blue from Daf's dark theme.",
             "Tinted: one tone in clear greys on a dark tile; macOS adds the user's tint.",
             "Default, small drawing for 16-48 px.",
             "Dark, small drawing.",
             "Tinted, small drawing."]
    top = os.path.join(HERE, ".sheet-top.png")
    kit.sheet(top, [os.path.join(HERE, f"{r}.svg") for r in rows], ["Light", "Dark", "Tinted", "Light small", "Dark small", "Tinted small"], notes)
    strip = os.path.join(HERE, ".dock.png")
    dock_strip([os.path.join(HERE, f"{r}.svg") for r in ("light", "dark", "tinted")], strip)
    from PIL import Image
    a, b = Image.open(top).convert("RGBA"), Image.open(strip).convert("RGBA")
    sheet = Image.new("RGBA", (max(a.width, b.width), a.height + b.height + 20), (255, 255, 255, 255))
    sheet.alpha_composite(a, (0, 0))
    sheet.alpha_composite(b, (0, a.height + 20))
    sheet.save(os.path.join(HERE, "sheet.png"))
    os.remove(top)
    os.remove(strip)


if __name__ == "__main__":
    main()
