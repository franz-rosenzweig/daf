#!/usr/bin/env python3
"""Take the screenshots in docs/images from the taste's sample library, never from a real one.

    python3 -I tools/docs_shots.py [--only hero-light,books,...] [--chrome PATH]

It makes a --docs build of the taste (tools/build_taste.py) in a temporary folder, serves it on
127.0.0.1, opens each screen in a headless Chrome (Chrome for Testing, or --chrome), and writes the
pictures over the ones in docs/images with the same names, sizes and framing: the window with
rounded corners and a soft shadow on a transparent background, and the three phones in frames.
Today is shot in the evening of whichever time zone is in the evening now, so it has its three
sittings. appearance.png and the two Torah pages aren't taken here. Needs Pillow; otherwise stdlib.
"""
import argparse
import base64
import http.server
import io
import json
import os
import socket
import shutil
import socketserver
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
IMAGES = ROOT / "docs" / "images"
CHROME = os.environ.get("CHROME", str(Path.home() / ".local/opt/google/chrome-linux64/chrome"))
ZONES = ["Pacific/Kiritimati", "Pacific/Auckland", "Australia/Sydney", "Asia/Tokyo", "Asia/Shanghai", "Asia/Bangkok", "Asia/Dhaka",
         "Asia/Kolkata", "Asia/Dubai", "Europe/Istanbul", "Europe/Berlin", "Europe/London", "Atlantic/Azores", "America/Sao_Paulo",
         "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "America/Anchorage", "Pacific/Honolulu"]


def evening_zone():
    for z in ZONES:
        if 19 <= datetime.now(ZoneInfo(z)).hour <= 22:
            return z
    return "Europe/Istanbul"


class Page:
    """Just enough of the DevTools protocol over a WebSocket (as in tools/shot.py)."""

    def __init__(self, url):
        hp, path = url[len("ws://"):].split("/", 1)
        host, port = hp.split(":")
        self.s = socket.create_connection((host, int(port)), timeout=60)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET /{path} HTTP/1.1\r\nHost: {hp}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.s.recv(4096)
        self.rest, self.n = buf.split(b"\r\n\r\n", 1)[1], 0

    def _recv(self, n):
        while len(self.rest) < n:
            self.rest += self.s.recv(65536)
        out, self.rest = self.rest[:n], self.rest[n:]
        return out

    def _read(self):
        payload = b""
        while True:
            b1, b2 = self._recv(2)
            ln = b2 & 0x7F
            if ln == 126:
                ln = struct.unpack(">H", self._recv(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", self._recv(8))[0]
            payload += self._recv(ln)
            if b1 & 0x80:
                return json.loads(payload.decode("utf-8", "replace"))

    def call(self, method, **params):
        self.n += 1
        data = json.dumps({"id": self.n, "method": method, "params": params}).encode()
        ln = len(data)
        hdr = bytes([0x81]) + (bytes([0x80 | ln]) if ln < 126 else bytes([0x80 | 126]) + struct.pack(">H", ln) if ln < 65536 else bytes([0x80 | 127]) + struct.pack(">Q", ln))
        mask = os.urandom(4)
        self.s.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))
        while True:
            m = self._read()
            if m.get("id") == self.n:
                if "error" in m:
                    raise RuntimeError(f"{method}: {m['error']}")
                return m.get("result", {})

    def js(self, expr, wait=0.0):
        r = self.call("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r:
            raise RuntimeError("in the page: " + json.dumps(r["exceptionDetails"])[:400])
        time.sleep(wait)
        return r.get("result", {}).get("value")


# ---- the frames ----------------------------------------------------------------------------

def rounded(size, r, scale=4):
    w, h = size
    m = Image.new("L", (w * scale, h * scale), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w * scale - 1, h * scale - 1), r * scale, fill=255)
    return m.resize(size, Image.LANCZOS)


def shadowed(canvas, mask, at, strength=0.30, blur=18, dy=6):
    sh = Image.new("L", canvas.size, 0)
    sh.paste(mask, (at[0], at[1] + dy))
    sh = sh.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(v * strength))
    canvas.alpha_composite(Image.merge("RGBA", (Image.new("L", canvas.size, 0),) * 3 + (sh,)))


def window(shot, canvas_size, margin, radius):
    """A screenshot as a window: rounded corners and a soft shadow, on transparent."""
    canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    mask = rounded(shot.size, radius)
    shadowed(canvas, mask, (margin, margin))
    win = shot.convert("RGBA")
    win.putalpha(ImageChops.multiply(win.getchannel("A"), mask))
    canvas.alpha_composite(win, (margin, margin))
    return canvas


def phones(shots):
    """Three phone screens side by side, each in a dark frame (docs/images/phones.webp)."""
    canvas = Image.new("RGBA", (1862, 1156), (0, 0, 0, 0))
    W, H, edge, bezel, R = 520, 1082, 3, 15, 67
    for i, s in enumerate(shots):
        x, y = 37 + i * 634, 37
        outer = rounded((W, H), R)
        shadowed(canvas, outer, (x, y), strength=0.35, blur=16)
        body = Image.new("RGBA", (W, H), (70, 69, 76, 255)); body.putalpha(outer)
        canvas.alpha_composite(body, (x, y))
        inner = rounded((W - 2 * edge, H - 2 * edge), R - edge)
        b2 = Image.new("RGBA", inner.size, (24, 24, 26, 255)); b2.putalpha(inner)
        canvas.alpha_composite(b2, (x + edge, y + edge))
        sw, sh = W - 2 * (edge + bezel), H - 2 * (edge + bezel)
        scr = s.convert("RGBA").resize((sw, sh), Image.LANCZOS)
        scr.putalpha(rounded((sw, sh), R - edge - bezel))
        canvas.alpha_composite(scr, (x + edge + bezel, y + edge + bezel))
    return canvas


# ---- the screens ---------------------------------------------------------------------------

DESK = dict(size=(1398, 873), canvas=(1486, 961), margin=44, radius=12)
SHOTS = [
    ("hero-light.png", dict(size=(1598, 998), canvas=(1700, 1100), margin=51, radius=14), {}, ["#today"]),
    ("hero-dark.png", dict(size=(1598, 998), canvas=(1700, 1100), margin=51, radius=14), {"dark": True}, ["#today"]),
    ("add.png", DESK, {}, ["#today", "js:document.querySelector('#side [data-act=\"add\"]').click()"]),
    ("article.png", DESK, {"hl": "green"}, ["#read/pg%3Aschopenhauer-thinking", "select:11:Reading is thinking with some one else's head instead of one's own."]),
    ("book.png", DESK, {}, ["#book/cal%3A1"]),
    ("books.png", DESK, {}, ["#books"]),
    ("feed.png", DESK, {}, ["#feed/Writing"]),
    ("goals.png", dict(DESK, size=(1398, 1009), canvas=(1486, 1097)), {}, ["#prefs/goals", "wait:1.5"]),
    ("highlights.png", DESK, {}, ["#highlights"]),
    ("library-home.png", DESK, {}, ["#library"]),
    ("library.png", DESK, {}, ["#library/article"]),
    ("paper.png", DESK, {}, ["#today", "js:document.querySelector('[data-act=\"paper\"]').click()"]),
    ("reader.png", DESK, {"panel": True}, ["#ebook/cal%3A2/hl:WOODS", "wait:4", "js:document.querySelector('[data-bpt=\"notebook\"]').click()",
                                       "js:(e => { if (e) e.scrollTop = 0; })(document.getElementById('bpanel'))"]),
    ("review.png", dict(DESK, size=(1398, 708), canvas=(1486, 796)), {}, ["#review"]),
    ("search.png", DESK, {}, ["#today", "js:document.querySelector('[data-act=\"palette\"]').click()",
                              "js:(q => { q.value = 'writing'; q.dispatchEvent(new Event('input', { bubbles: true })); })(document.getElementById('palq'))"]),
    ("stats.png", DESK, {}, ["#stats"]),
    ("tablet.webp", dict(DESK, size=(1398, 1047), canvas=(1486, 1135)), {"paper": True}, ["#ebook/cal%3A2/hl:WOODS", "wait:5"]),
    ("torah-shelf.png", DESK, {}, ["#torah"]),
]
PHONES = ("phones.webp", ["#today", "#ebook/cal%3A2/hl:WOODS", "#review"])


def serve(folder):
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(folder), **k)

        def log_message(self, *a):
            pass
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/app/"


def chrome(profile, chrome_path):
    proc = subprocess.Popen([chrome_path, "--headless=new", "--no-sandbox", "--hide-scrollbars", "--mute-audio", "--remote-allow-origins=*",
                             "--remote-debugging-port=0", f"--user-data-dir={profile}", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            env=dict(os.environ, TMPDIR="/tmp"))   # its socket's path must stay short
    pf = Path(profile) / "DevToolsActivePort"
    for _ in range(400):
        if pf.exists() and pf.read_text().strip():
            break
        time.sleep(0.1)
    if not pf.exists():
        proc.kill()
        sys.exit("Chrome didn't start: " + chrome_path)
    port = pf.read_text().split()[0]
    pages = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list"))
    return proc, Page(next(p for p in pages if p["type"] == "page")["webSocketDebuggerUrl"])


def open_screen(p, base, size, mobile, opts, zone):
    w, h = size
    p.call("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=2, mobile=mobile)
    p.call("Emulation.setTouchEmulationEnabled", enabled=mobile)
    p.call("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "dark" if opts.get("dark") else "light"}])
    p.call("Emulation.setTimezoneOverride", timezoneId=zone)
    p.call("Page.navigate", url=base + "#today"); time.sleep(2.5)
    # A visitor's first visit, then the settings this picture wants.
    p.js("window.DafTaste.reset(); location.reload()", 2.5)
    p.js("(() => { const d = JSON.parse(localStorage.getItem('daftaste.v1')); d.settings.tips.off = true;"
         + ("d.settings.appearance = { mode: 'light', light: 'paper', dark: 'daf' };" if opts.get("paper") else "")
         + "localStorage.setItem('daftaste.v1', JSON.stringify(d));"
         + ("localStorage.setItem('daf.hlColor', JSON.stringify(" + json.dumps(opts["hl"]) + "));" if opts.get("hl") else "")
         + ("localStorage.setItem('daf.type', JSON.stringify({ flow: 'paginated' })); localStorage.setItem('daf.bookPanel', 'false'); localStorage.setItem('daf.bookToc', 'false');" if opts.get("paper") else "")
         + ("localStorage.setItem('daf.bookPanel', 'true'); localStorage.setItem('daf.bookToc', 'false');" if opts.get("panel") else "")
         + "})()")
    p.js("location.reload()", 3)


def run_steps(p, steps):
    for st in steps:
        if st.startswith("#"):
            if "hl:WOODS" in st:
                hid = p.js("fetch('api/books/cal%3A2').then(r => r.json()).then(d => d.highlights.find(h => h.text.startsWith('I went to the woods')).id)")
                st = st.replace("WOODS", hid)
            p.js("location.hash = " + json.dumps(st), 2.5)
        elif st.startswith("wait:"):
            time.sleep(float(st[5:]))
        elif st.startswith("js:"):
            p.js(st[3:], 1.5)
        elif st.startswith("select:"):
            _, block, text = st.split(":", 2)
            p.js("""(() => {
              const el = document.querySelector('#docbody [data-i="%s"]'), m = document.getElementById('main');
              m.scrollTop += el.getBoundingClientRect().top - m.getBoundingClientRect().top - m.clientHeight * 0.3;
              const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT), t = %s; let n;
              while ((n = w.nextNode())) { const i = n.data.indexOf(t); if (i >= 0) { const r = document.createRange(); r.setStart(n, i); r.setEnd(n, i + t.length);
                const s = getSelection(); s.removeAllRanges(); s.addRange(r); el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true })); return; } }
              throw new Error('not found');
            })()""" % (block, json.dumps(text)), 1.2)
            p.js("(document.querySelector('#selbar:not([hidden]) [data-hb=\"hl\"]') || { click(){} }).click()", 1.5)


def capture(p, size):
    # A scrollIntoView inside a book's frame can scroll the page itself a little; the app never scrolls it.
    p.js("document.scrollingElement.scrollTop = 0; window.scrollTo(0, 0)", 0.4)
    data = p.call("Page.captureScreenshot", format="png")["data"]
    return Image.open(io.BytesIO(base64.b64decode(data))).convert("RGB").resize(size, Image.LANCZOS)


def errors(p):
    # Chrome's "ResizeObserver loop completed with undelivered notifications" is a notice, not an error.
    return p.js("JSON.stringify((window.__errs || []).filter(e => !/^ResizeObserver loop/.test(e)))")


def save(img, name):
    path = IMAGES / name
    if name.endswith(".webp"):
        img.save(path, "WEBP", quality=88, method=6)
    else:
        img.save(path, "PNG", optimize=True)
    print("wrote", path.relative_to(ROOT), img.size)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--chrome", default=CHROME)
    a = ap.parse_args()
    only = {x.strip() for x in a.only.split(",") if x.strip()}
    tmp = Path(tempfile.mkdtemp(prefix="daf-docs-shots-"))
    subprocess.run([sys.executable, "-I", str(ROOT / "tools" / "build_taste.py"), str(tmp / "site"), "--docs"], check=True)
    srv, base = serve(tmp / "site")
    zone = evening_zone()
    proc, p = chrome(str(tmp / "profile"), a.chrome)
    p.call("Page.enable"); p.call("Runtime.enable")
    p.call("Page.addScriptToEvaluateOnNewDocument", source="window.__errs=[];addEventListener('error',e=>__errs.push(String(e.message||e)));"
           "addEventListener('unhandledrejection',e=>__errs.push('promise: '+String(e.reason&&e.reason.message||e.reason)));"
           # Recovery is never in these pictures, not even for a moment while the page draws.
           "new MutationObserver(()=>{if(document.querySelector('[data-go=\\'recovery\\']'))__errs.push('Recovery appeared');})"
           ".observe(document,{subtree:true,childList:true});")
    bad = []
    try:
        for name, frame, opts, steps in SHOTS:
            if only and name.split(".")[0] not in only:
                continue
            open_screen(p, base, frame["size"], False, opts, zone)
            run_steps(p, steps)
            save(window(capture(p, frame["size"]), frame["canvas"], frame["margin"], frame["radius"]), name)
            e = json.loads(errors(p)); bad += [(name, x) for x in e]
        name, screens = PHONES
        if not only or name.split(".")[0] in only:
            shots = []
            for st in screens:
                open_screen(p, base, (390, 844), True, {}, zone)
                run_steps(p, [st])
                shots.append(capture(p, (780, 1688)))
                e = json.loads(errors(p)); bad += [(name, x) for x in e]
            save(phones(shots), name)
    finally:
        try:
            p.call("Browser.close")
        except Exception:
            proc.kill()
        srv.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
    if bad:
        sys.exit("page errors: " + json.dumps(bad)[:2000])


if __name__ == "__main__":
    main()
