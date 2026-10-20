"""Shared kit for drawing Daf's icon: Apple's macOS grid, rendering in headless Chromium, contact sheets.

    import sys; sys.path.insert(0, "/srv/dev/daf/design/icon"); import kit
    svg = kit.tile(inner_svg, defs="")          # 1024 canvas, 824 superellipse tile, soft shadow
    kit.render("v1.svg", "v1-1024.png", 1024)   # each size rendered at its own size
    kit.sheet("sheet.png", ["v1.svg", "v2.svg"], ["V1", "V2"])

Coordinates: the tile spans 100..924 on both axes; its centre is (512, 512). The visual centre
for most objects sits a little above that (about y = 500).
"""
import base64, json, math, os, sys, time, urllib.request
sys.path.insert(0, "/srv/dev/daf/tools")
import shot  # noqa: E402

def squircle(cx=512, cy=512, r=412, n=5.0, steps=360):
    pts = []
    for i in range(steps):
        t = 2 * math.pi * i / steps
        c, s = math.cos(t), math.sin(t)
        pts.append(f"{cx + r * math.copysign(abs(c) ** (2 / n), c):.1f},{cy + r * math.copysign(abs(s) ** (2 / n), s):.1f}")
    return "M" + " L".join(pts) + " Z"

SQ = squircle()

def tile(inner, defs="", top="#FFFFFF", bot="#F2EFEA", shadow=True):
    """The tile: white with the faintest warm fall-off, a crisp contact shadow and a soft ambient one."""
    sh = ('<filter id="tsh" x="-20%" y="-20%" width="140%" height="140%">'
          '<feDropShadow dx="0" dy="3" stdDeviation="3" flood-color="#000" flood-opacity="0.18"/>'
          '<feDropShadow dx="0" dy="14" stdDeviation="16" flood-color="#000" flood-opacity="0.16"/></filter>') if shadow else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024"><defs>{sh}'
            f'<linearGradient id="tbg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{top}"/><stop offset="1" stop-color="{bot}"/></linearGradient>'
            f'<clipPath id="tcl"><path d="{SQ}"/></clipPath>{defs}</defs>'
            f'<g{" filter=\"url(#tsh)\"" if shadow else ""}><path d="{SQ}" fill="url(#tbg)"/></g><g clip-path="url(#tcl)">{inner}</g></svg>')

class _Page:
    def __init__(self, w, h, scale=1):
        self.ip = shot.container_ip(); shot.ensure_chrome(self.ip)
        self.page = json.load(urllib.request.urlopen(urllib.request.Request(f"http://{self.ip}:9222/json/new?about:blank", method="PUT")))
        self.ws = shot.WS(self.page["webSocketDebuggerUrl"].replace("localhost", self.ip).replace("127.0.0.1", self.ip))
        self.ws.send("Page.enable")
        self.ws.send("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=scale, mobile=False)
        self.ws.send("Emulation.setDefaultBackgroundColorOverride", color={"r": 0, "g": 0, "b": 0, "a": 0})

    def shoot(self, html, out, clip=None):
        if len(html) < 1_500_000:
            self.ws.send("Page.navigate", url="data:text/html;base64," + base64.b64encode(html.encode()).decode())
        else:                                   # too big for a data: address: write it into a blank page
            self.ws.send("Page.navigate", url="about:blank")
            time.sleep(0.3)
            frame = self.ws.send("Page.getFrameTree")["frameTree"]["frame"]["id"]
            self.ws.send("Page.setDocumentContent", frameId=frame, html=html)
        time.sleep(1.2 + len(html) / 2_000_000)
        kw = {"format": "png"}
        if clip:
            kw["clip"] = dict(clip, scale=1)
        open(out, "wb").write(base64.b64decode(self.ws.send("Page.captureScreenshot", **kw)["data"]))

    def close(self):
        urllib.request.urlopen(f"http://{self.ip}:9222/json/close/{self.page['id']}")

def _uri(svg_path):
    return "data:image/svg+xml;base64," + base64.b64encode(open(svg_path, "rb").read()).decode()

def render(svg_path, out, size=1024):
    """The SVG rasterised by Chromium at exactly `size` px, transparent around the tile."""
    p = _Page(size, size)
    try:
        p.shoot(f'<html><body style="margin:0;background:transparent"><img src="{_uri(svg_path)}" width="{size}" height="{size}" style="display:block"></body></html>',
                out, {"x": 0, "y": 0, "width": size, "height": size})
    finally:
        p.close()
    return out

def sheet(out, svgs, labels=None, notes=None):
    """One row per icon: 256 px on light, then 64/32/16 on a light strip and on a dark strip."""
    labels = labels or [os.path.splitext(os.path.basename(s))[0] for s in svgs]
    rows = []
    for i, s in enumerate(svgs):
        u = _uri(s)
        small = "".join(f'<img src="{u}" width="{n}" height="{n}">' for n in (64, 32, 16))
        note = f'<div class="n">{notes[i]}</div>' if notes and i < len(notes) else ""
        rows.append(f'<div class="r"><div class="big"><img src="{u}" width="256" height="256"></div>'
                    f'<div class="st lt">{small}</div><div class="st dk">{small}</div><div class="lb"><b>{labels[i]}</b>{note}</div></div>')
    html = ('<html><body style="margin:0;background:#ffffff;font:15px -apple-system,Helvetica,Arial,sans-serif;color:#333">'
            '<style>.r{display:flex;align-items:center;gap:22px;padding:18px 28px;border-bottom:1px solid #eee}'
            '.big{background:#ececec;border-radius:18px;padding:6px}.st{display:flex;gap:18px;align-items:center;padding:16px 20px;border-radius:14px}'
            '.lt{background:#f4f4f4}.dk{background:#1e1e1e}.lb{max-width:300px}.lb b{display:block;font-size:20px;margin-bottom:6px}.n{color:#666;line-height:1.35}</style>'
            + "".join(rows) + '</body></html>')
    h = 300 * len(svgs) + 10
    p = _Page(1100, h)
    try:
        p.shoot(html, out)
    finally:
        p.close()
    return out
