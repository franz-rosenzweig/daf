"""The full icon set from the chosen drawing.

    python3 export.py LARGE.svg SMALL.svg OUT_DIR

LARGE is the drawing on Apple's grid (a kit.tile SVG); SMALL is the simpler drawing for 16-48 px.
Every PNG is rendered by Chromium at its own size, never shrunk from a bigger one.

    OUT_DIR/mac/AppIcon.iconset/   the ten macOS sizes, and AppIcon.icns, icon-1024.png
    OUT_DIR/web/                   icon.svg, favicon.svg, favicon.ico (16/32/48), icon-192/512.png,
                                   icon-maskable-512.png, apple-touch-icon.png (180, full square)
    OUT_DIR/android/               adaptive foreground and monochrome per density, legacy launcher
                                   PNGs, and the background colour
    OUT_DIR/preview.png            every file at its size
    OUT_DIR/daf-icons.zip
"""
import base64
import io
import json
import os
import re
import shutil
import sys
import zipfile

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kit  # noqa: E402

BG = "#FFFFFF"           # the adaptive icon's background layer, and the full-square fill


def parts(svg):
    """(defs, art) of a kit.tile SVG: the tile's own pieces are left out of the art."""
    defs = re.search(r"<defs>(.*?)</defs>", svg, re.S).group(1)
    art = svg.split('<g clip-path="url(#tcl)">', 1)[1].rsplit("</g></svg>", 1)[0]
    return defs, art


def placed(svg, scale, fill=None):
    """The art alone on a 1024 canvas, scaled about the centre; on `fill` (a full square) or clear."""
    defs, art = parts(svg)
    bg = (f'<linearGradient id="fullbg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF"/>'
          f'<stop offset="1" stop-color="#F2EFEA"/></linearGradient>') if fill == "gradient" else ""
    under = '<rect width="1024" height="1024" fill="url(#fullbg)"/>' if fill == "gradient" else f'<rect width="1024" height="1024" fill="{fill}"/>' if fill else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024"><defs>{defs}{bg}</defs>{under}'
            f'<g transform="translate(512 512) scale({scale}) translate(-512 -512)">{art}</g></svg>')


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write(text)
    return path


def render(svg_path, out, size):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    return kit.render(svg_path, out, size)


def main(large, small, out):
    L, S = open(large).read(), open(small).read()
    tmp = os.path.join(out, ".src")
    os.makedirs(tmp, exist_ok=True)
    src = {
        "tile": write(f"{tmp}/tile.svg", L),
        "tile-small": write(f"{tmp}/tile-small.svg", S),
        # iOS rounds its own corners: the art on a full square, as big on it as on the tile.
        "full": write(f"{tmp}/full.svg", placed(L, round(1024 / 824, 4), "gradient")),
        # Maskable (web) and adaptive (Android): the art inside the safe circle.
        "maskable": write(f"{tmp}/maskable.svg", placed(L, 1.05, BG)),
        "fore": write(f"{tmp}/fore.svg", placed(L, 0.86)),
        "fore-small": write(f"{tmp}/fore-small.svg", placed(S, 0.86)),
    }
    files = []

    # macOS: the iconset, the .icns, and the 1024 the Mac build uses.
    iconset = os.path.join(out, "mac", "AppIcon.iconset")
    for name, px in (("16x16", 16), ("16x16@2x", 32), ("32x32", 32), ("32x32@2x", 64), ("128x128", 128), ("128x128@2x", 256),
                     ("256x256", 256), ("256x256@2x", 512), ("512x512", 512), ("512x512@2x", 1024)):
        files.append(render(src["tile-small" if px <= 48 else "tile"], f"{iconset}/icon_{name}.png", px))
    shutil.copy(f"{iconset}/icon_512x512@2x.png", os.path.join(out, "mac", "icon-1024.png"))
    imgs = {px: Image.open(f"{iconset}/icon_{n}.png").convert("RGBA") for n, px in
            (("16x16", 16), ("32x32", 32), ("32x32@2x", 64), ("128x128", 128), ("256x256", 256), ("512x512", 512), ("512x512@2x", 1024))}
    imgs[1024].save(os.path.join(out, "mac", "AppIcon.icns"), append_images=[imgs[k] for k in (16, 32, 64, 128, 256, 512)])
    files.append(os.path.join(out, "mac", "AppIcon.icns"))

    # Web.
    web = os.path.join(out, "web")
    shutil.copy(src["tile"], f"{web}/icon.svg") if os.path.isdir(web) else (os.makedirs(web), shutil.copy(src["tile"], f"{web}/icon.svg"))
    shutil.copy(src["tile-small"], f"{web}/favicon.svg")
    for px in (16, 32, 48):
        render(src["tile-small"], f"{tmp}/fav-{px}.png", px)
    fav = [Image.open(f"{tmp}/fav-{px}.png").convert("RGBA") for px in (16, 32, 48)]
    fav[2].save(f"{web}/favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)], append_images=fav[:2])
    shutil.copy(f"{tmp}/fav-32.png", f"{web}/favicon-32.png")
    files += [f"{web}/icon.svg", f"{web}/favicon.svg", f"{web}/favicon.ico", f"{web}/favicon-32.png"]
    files.append(render(src["tile"], f"{web}/icon-192.png", 192))
    files.append(render(src["tile"], f"{web}/icon-512.png", 512))
    files.append(render(src["maskable"], f"{web}/icon-maskable-512.png", 512))
    files.append(render(src["full"], f"{web}/apple-touch-icon.png", 180))

    # Android: adaptive foreground (108 dp canvas, art in the 66 dp circle), monochrome from its
    # alpha, legacy launcher icons, and the background colour.
    andr = os.path.join(out, "android")
    for dpi, scale in (("mdpi", 1), ("hdpi", 1.5), ("xhdpi", 2), ("xxhdpi", 3), ("xxxhdpi", 4)):
        px = int(108 * scale)
        f = render(src["fore-small" if px <= 162 else "fore"], f"{andr}/mipmap-{dpi}/ic_launcher_foreground.png", px)
        a = Image.open(f).convert("RGBA").getchannel("A")
        mono = Image.new("RGBA", a.size, (255, 255, 255, 0))
        mono.putalpha(a)
        mono.save(f"{andr}/mipmap-{dpi}/ic_launcher_monochrome.png")
        legacy = int(48 * scale)
        files += [f, f"{andr}/mipmap-{dpi}/ic_launcher_monochrome.png",
                  render(src["tile-small" if legacy <= 48 else "tile"], f"{andr}/mipmap-{dpi}/ic_launcher.png", legacy)]
    write(f"{andr}/values/ic_launcher_background.xml",
          f'<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="ic_launcher_background">{BG}</color>\n</resources>\n')
    write(f"{andr}/mipmap-anydpi-v26/ic_launcher.xml",
          '<?xml version="1.0" encoding="utf-8"?>\n<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
          '    <background android:drawable="@color/ic_launcher_background" />\n    <foreground android:drawable="@mipmap/ic_launcher_foreground" />\n'
          '    <monochrome android:drawable="@mipmap/ic_launcher_monochrome" />\n</adaptive-icon>\n')

    # Checks: each PNG is the size its name says, tile icons have clear corners and a filled middle,
    # full-square ones are opaque to the corner.
    report = []
    for f in files:
        if not f.endswith(".png"):
            continue
        im = Image.open(f).convert("RGBA")
        w, h = im.size
        corner, mid = im.getpixel((0, 0)), im.getpixel((w // 2, int(h * 0.45)))
        report.append({"file": os.path.relpath(f, out), "size": f"{w}x{h}", "corner": corner, "middle": mid})
    json.dump(report, open(os.path.join(out, "checks.json"), "w"), indent=1)

    # The preview: every file at its own size.
    rows = []
    for f in files:
        if not f.endswith(".png"):
            continue
        im = Image.open(f)
        uri = "data:image/png;base64," + base64.b64encode(open(f, "rb").read()).decode()
        dark = "monochrome" in f
        rows.append(f'<figure style="background:{"#333;color:#ddd" if dark else "transparent"}"><img src="{uri}" width="{min(im.width, 256)}" height="{min(im.height, 256)}">'
                    f'<figcaption>{os.path.relpath(f, out)}<br>{im.width}×{im.height}</figcaption></figure>')
    html = ('<html><head><meta charset="utf-8"></head><body style="margin:0;padding:24px;background:#ededed;font:12px -apple-system,Helvetica,sans-serif;color:#444">'
            '<style>figure{display:inline-flex;flex-direction:column;align-items:center;gap:6px;margin:10px;padding:10px;border-radius:10px;vertical-align:bottom}'
            'figcaption{text-align:center;max-width:220px;word-break:break-all}</style>' + "".join(rows) + '</body></html>')
    p = kit._Page(1400, 2400)
    try:
        p.shoot(html, os.path.join(out, "preview.png"))
    finally:
        p.close()

    with zipfile.ZipFile(os.path.join(out, "daf-icons.zip"), "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, names in os.walk(out):
            if ".src" in root:
                continue
            for n in names:
                if n == "daf-icons.zip":
                    continue
                full = os.path.join(root, n)
                z.write(full, os.path.relpath(full, out))
    print(json.dumps({"files": len(files), "out": out}))


if __name__ == "__main__":
    main(*sys.argv[1:4])
