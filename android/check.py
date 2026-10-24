#!/usr/bin/env python3
"""The test build on the phone plugged into this Mac, against a sandbox Daf (check.sh).

    python3 -I check.py BASE COOKIE TOKEN

The phone reaches the sandbox through this Mac: its localhost:8441 is forwarded here
(adb reverse) and on to BASE. The test build (xyz.tiresia.daf.debug, "Daf dev") opens on
it with the token, the page is signed in with the cookie over DevTools, and the checks
run in the page and with keys pressed on the phone. Stdlib only.
"""
import base64
import hashlib
import json
import shlex
import os
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request

PKG = "xyz.tiresia.daf.debug"
PORT = 8441
ADB = os.path.join(os.environ.get("ANDROID_HOME", os.path.expanduser("~/android-sdk")), "platform-tools", "adb")
failures = skipped = 0


def check(ok, what, detail=""):
    global failures
    print(("PASS  " if ok else "FAIL  ") + what + (f"  [{detail}]" if detail else ""), flush=True)
    if not ok:
        failures += 1


def adb(*args, check_=True):
    return subprocess.run([ADB, *args], capture_output=True, text=True, check=check_).stdout


class Net:
    """The way to the sandbox, which the offline checks cut and mend (never the phone's own Wi-Fi)."""
    def __init__(self):
        self.cut, self.conns = threading.Event(), set()

    def sever(self):
        self.cut.set()
        for s in list(self.conns):            # the pipes forget theirs meanwhile
            try:
                s.shutdown(socket.SHUT_RDWR)
                s.close()
            except OSError:
                pass
        self.conns.clear()

    def mend(self):
        self.cut.clear()


NET = Net()
ONLY = os.environ.get("DAF_CHECK", "")       # "offline", "book", "manga", "mangadl", "news", "boot", "docs", "theme", "prune", "listen" or "ink": only those checks


def forward(listen_port, target):
    """localhost:listen_port → target (host:port), one thread per connection."""
    host, port = target.split(":")
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", listen_port))
    srv.listen(32)

    def pipe(a, b):
        """a → b until either end goes; then both are shut, and a (this direction's own) is closed
        and forgotten: a long sync opens hundreds of connections, more than a process may keep."""
        try:
            while True:
                d = a.recv(65536)
                if not d:
                    break
                b.sendall(d)
        except OSError:
            pass
        finally:
            for s in (a, b):
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            NET.conns.discard(a)
            a.close()

    def serve():
        while True:
            c, _ = srv.accept()
            if NET.cut.is_set():
                c.close()
                continue
            try:
                u = socket.create_connection((host, int(port)), timeout=10)
                u.settimeout(None)
            except OSError:
                c.close()
                continue
            NET.conns.update((c, u))
            threading.Thread(target=pipe, args=(c, u), daemon=True).start()
            threading.Thread(target=pipe, args=(u, c), daemon=True).start()

    threading.Thread(target=serve, daemon=True).start()


class WS:
    """Just enough of a WebSocket client for DevTools."""

    def __init__(self, url):
        hp, path = url[len("ws://"):].split("/", 1)
        h, p = hp.split(":")
        self.s = socket.create_connection((h, int(p)), timeout=300)   # a busy phone can be slow to answer DevTools
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET /{path} HTTP/1.1\r\nHost: {hp}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.s.recv(4096)
        self.rest = buf.split(b"\r\n\r\n", 1)[1]
        self.n = 0

    def _recv(self, n):
        while len(self.rest) < n:
            self.rest += self.s.recv(65536)
        out, self.rest = self.rest[:n], self.rest[n:]
        return out

    def read(self):
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

    def send(self, method, **params):
        self.n += 1
        data = json.dumps({"id": self.n, "method": method, "params": params}).encode()
        ln = len(data)
        hdr = bytes([0x81]) + (bytes([0x80 | ln]) if ln < 126 else bytes([0x80 | 126]) + struct.pack(">H", ln) if ln < 65536
                               else bytes([0x80 | 127]) + struct.pack(">Q", ln))
        mask = os.urandom(4)
        self.s.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))
        while True:
            m = self.read()
            if m.get("id") == self.n:
                return m.get("result", m)


def main(base, cookie, token):
    global skipped
    if "device" not in adb("get-state", check_=False):
        print("no phone: plug it in and allow USB debugging", file=sys.stderr)
        return 2
    forward(PORT, base.split("://", 1)[1].rstrip("/"))
    adb("reverse", f"tcp:{PORT}", f"tcp:{PORT}")
    awake = "mWakefulness=Awake" in adb("shell", "dumpsys", "power")
    locked = "mDreamingLockscreen=true" in adb("shell", "dumpsys", "window") or \
             "isKeyguardShowing=true" in adb("shell", "dumpsys", "window", "policy", check_=False) if awake else True
    adb("shell", "am", "force-stop", PKG)
    adb("shell", "am", "start", "-n", f"{PKG}/xyz.tiresia.daf.MainActivity",
        "--es", "daf.base", f"http://localhost:{PORT}", "--es", "daf.token", token)
    def attach():
        """DevTools on the test build's own WebView (webview_devtools_remote_<its pid>; other apps may have one)."""
        sock = None
        for _ in range(60):
            pid = adb("shell", "pidof", PKG, check_=False).strip()
            found = [l.split("@")[-1] for l in adb("shell", "cat", "/proc/net/unix").split() if "webview_devtools_remote" in l]
            mine = [f for f in found if pid and f.endswith("_" + pid)]
            if mine:
                sock = mine[-1].lstrip("@")
                break
            time.sleep(0.3)
        if not sock:
            return None
        adb("forward", "--remove", "tcp:9224", check_=False)
        adb("forward", "tcp:9224", f"localabstract:{sock}")
        for _ in range(40):
            try:
                pages = [t for t in json.load(urllib.request.urlopen("http://localhost:9224/json", timeout=5)) if t.get("type") == "page"]
                page = next((t for t in pages if f"localhost:{PORT}" in t.get("url", "")), None)
                if page:
                    return WS(page["webSocketDebuggerUrl"])
            except OSError:
                pass
            time.sleep(0.3)
        return None

    conn = {"ws": attach()}
    if not conn["ws"]:
        check(False, "the test build opens Daf, with DevTools")
        return 1

    def js(expr):
        r = conn["ws"].send("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r:
            return "error: " + str(r["exceptionDetails"].get("exception", {}).get("description", ""))[:200]
        return r.get("result", {}).get("value")

    def until(expr, secs=10):
        t0 = time.time()
        while time.time() - t0 < secs:
            if js(f"!!({expr})") is True:
                return True
            time.sleep(0.25)
        return False

    conn["ws"].send("Network.enable")
    conn["ws"].send("Network.setCookie", name="daf", value=cookie, url=f"http://localhost:{PORT}")
    js("location.reload(), 1")
    time.sleep(1)
    check(until("window.dafState && dafState().signedIn && dafState().minutes !== null", 25), "Daf opens on the phone, signed in",
          str(js("document.body && document.body.innerText.slice(0, 80)")))

    ua = js("navigator.userAgent")
    check("(Android shell)" in ua and "Daf/" in ua, "the user agent names the shell", ua[-40:])
    check(js("['shell', 'shell-android'].every(c => document.documentElement.classList.contains(c))") is True, "shell.js marks the page shell-android",
          str(js("document.documentElement.className")))
    check(js("dafShell.platform === 'android' && ['share','download','openExternal','haptic'].every(k => dafShell.can(k))"),
          "window.dafShell is there, on Android")
    r = js("Promise.race([dafShell.openExternal('ftp://nowhere'), new Promise(r => setTimeout(() => r('no answer'), 5000))])")
    check(r is False, "the app answers over the message port (and refuses ftp:)", str(r))
    r = js("Promise.race([dafShell.haptic('confirm'), new Promise(r => setTimeout(() => r('no answer'), 5000))])")
    check(r in (True, False), "dafShell.haptic reaches the app", str(r))
    check(js("navigator.canShare({ files: [new File([new Uint8Array(4)], 'h.png', { type: 'image/png' })] })"),
          "Share as image finds the share sheet behind navigator.share")

    # an article kept on the device by hand: marked in its list, and it opens with Daf out of reach
    def listen_check():
        global skipped
        # listening with the screen off (last: the phone ends up locked)
        if not awake or locked:
            skipped += 1
            print("SKIP  listening with the screen off: unlock the phone and run again", flush=True)
        else:
            adb("shell", "am", "start", "-n", f"{PKG}/xyz.tiresia.daf.MainActivity")
            time.sleep(1)
            doc = js("fetch('/api/docs?where=library&limit=30').then(r => r.json()).then(j => { const d = (j.items || j.docs || []).find(d => d.kind === 'article' && (d.mins || 0) >= 2); return d ? d.id : ''; })")
            js(f"location.hash = 'read/' + encodeURIComponent({json.dumps(doc)}), 1")
            until("document.getElementById('docbody')", 15)
            js("dafCommand('listen'), 1")
            para = "(() => { const m = /¶ (\\d+) of/.exec((document.querySelector('#player .pt .mute') || {}).textContent || ''); return m ? +m[1] : 0; })()"
            playing = until("(document.querySelector('[data-tts=\"play\"]') || {}).getAttribute && document.querySelector('[data-tts=\"play\"]').getAttribute('aria-label') === 'Pause'", 20)
            check(playing, "read-aloud starts in the app", doc)
            time.sleep(2)
            svc = adb("shell", "dumpsys", "activity", "services", PKG, check_=False)
            check("xyz.tiresia.daf.Listen" in svc and "isForeground=true" in svc, "it runs as a media-playback service")
            sess = adb("shell", "dumpsys", "media_session", check_=False)
            mine = sess.split(PKG, 1)[-1][:3000] if PKG in sess else ""
            check("state=PLAYING(3)" in mine or "{state=3," in mine, "with a media session on the lock screen, playing")
            if "state=PLAYING(3)" not in mine and "{state=3," not in mine:
                routed = [l.strip() for l in sess.splitlines() if "media button session" in l.lower()]
                print("INFO  media: " + (" | ".join(routed) or "no media button session") + " || " + " ".join(mine.split())[:600], flush=True)
            # the media buttons go to whichever app last played sound: wait until that's Daf
            for _ in range(30):
                if f"Media button session is {PKG}/" in adb("shell", "dumpsys", "media_session", check_=False):
                    break
                time.sleep(0.5)
            # the media keys, as headphones and the lock screen send them (Android 12's
            # `cmd media_session dispatch` never reaches an app's session; a key event does)
            adb("shell", "input", "keyevent", "KEYCODE_MEDIA_PAUSE", check_=False)
            paused = until("document.querySelector('[data-tts=\"play\"]').getAttribute('aria-label') === 'Play'", 6)
            check(paused, "its pause button pauses the page")
            adb("shell", "input", "keyevent", "KEYCODE_MEDIA_PLAY", check_=False)
            check(until("document.querySelector('[data-tts=\"play\"]').getAttribute('aria-label') === 'Pause'", 6), "and play plays it again")
            start = js(para)
            adb("shell", "input", "keyevent", "KEYCODE_SLEEP")
            time.sleep(45)
            on = js(para)
            check(isinstance(on, int) and on > start, "with the screen off it goes on to the next paragraphs", f"¶ {start} → ¶ {on}")
            js("dafCommand('listen:stop'), 1")
            time.sleep(2)
            check("xyz.tiresia.daf.Listen" not in adb("shell", "dumpsys", "activity", "services", PKG, check_=False), "stopping ends the service")
            adb("shell", "input", "keyevent", "KEYCODE_WAKEUP")


    if ONLY == "listen":
        listen_check()
        adb("reverse", "--remove", f"tcp:{PORT}", check_=False)
        adb("forward", "--remove", "tcp:9224", check_=False)
        note = f" ({skipped} skipped)" if skipped else ""
        print(("CHECK passed" if not failures else f"CHECK {failures} failed") + note, flush=True)
        return 1 if failures else 0

    if ONLY == "ink":
        # Writing with a pen (ink.js), with the stylus as `input stylus` sends it: an S Pen's
        # events, without the S Pen. Leave the tablet alone while it runs.
        doc = js("fetch('/api/docs?where=library&tab=inbox&kind=article&limit=40').then(r => r.json()).then(j => ((j.items || []).find(d => (d.words || 0) > 600) || {}).id || '')")
        check(bool(doc), "an article to write on", str(doc))
        js(f"location.hash = 'read/' + encodeURIComponent({json.dumps(doc)}), 1")
        check(until("document.querySelector('#docbody p[data-i]') && window.DafCore.Ink", 20), "it opens")
        time.sleep(1)
        js("(() => { const e = [...document.querySelectorAll('#docbody p[data-i]')].find(e => e.textContent.length > 250 && !e.querySelector('mark')); const m = document.querySelector('#main'); m.scrollTop += e.getBoundingClientRect().top - 260; return 1; })()")
        time.sleep(0.8)
        # where the page is on the screen: a stylus tap at a known point, as the page saw it
        js("window.__probe = null; addEventListener('pointerdown', e => { window.__probe = [e.clientX, e.clientY, e.pointerType, devicePixelRatio]; }, { capture: true, once: true }), 1")
        size = adb("shell", "wm", "size").split()[-1].split("x")
        w, h = int(size[0]), int(size[1])
        adb("shell", "input", "stylus", "tap", str(w // 2), str(h // 2))
        until("window.__probe", 5)
        probe = js("window.__probe")
        check(isinstance(probe, list) and probe[2] == "pen", "the stylus reaches the page as a pen", str(probe))
        if not isinstance(probe, list):
            return 1
        dpr = probe[3]
        ox, oy = w // 2 - probe[0] * dpr, h // 2 - probe[1] * dpr
        scr = lambda x, y: (str(int(ox + x * dpr)), str(int(oy + y * dpr)))
        box = js("(() => { const e = [...document.querySelectorAll('#docbody p[data-i]')].find(e => e.textContent.length > 250 && !e.querySelector('mark')); const r = e.getBoundingClientRect(); return { i: +e.dataset.i, l: r.left, t: r.top, r: r.right, b: r.bottom, lh: parseFloat(getComputedStyle(e).lineHeight) }; })()")
        st = lambda: js("window.DafCore.Ink.state()") or {}
        top = lambda: js("document.querySelector('#main').scrollTop")
        js("window.DafCore.Ink.state().on || document.querySelector('.inkpal [data-ink=\"on\"]').click(), 1")
        js("document.querySelector('.inkpal [data-ink=\"pen\"]') && document.querySelector('.inkpal [data-ink=\"pen\"]').click(), 1")
        n0, y0 = st().get("strokes", 0), top()
        # down the page, which a finger would scroll
        adb("shell", "input", "stylus", "swipe", *scr(box["l"] + 40, box["t"] + box["lh"] * 1.5), *scr(box["l"] + 90, box["t"] + box["lh"] * 5), "400")
        time.sleep(0.6)
        check(st().get("strokes") == n0 + 1, "the pen writes a stroke", str(st()))
        check(top() == y0, "and the page stays put under it", f"{y0} → {top()}")
        check(js("!!document.querySelector('.inkpal')") is True, "the pen's tools are there")
        adb("shell", "input", "touchscreen", "swipe", *scr(box["l"] + 120, box["t"] + box["lh"] * 6), *scr(box["l"] + 120, box["t"] + box["lh"] * 2), "300")
        time.sleep(0.8)
        check(st().get("strokes") == n0 + 1 and top() != y0, "a finger still scrolls, and writes nothing", f"{st().get('strokes')} strokes, {y0} → {top()}")
        js(f"document.querySelector('#main').scrollTop = {y0}, 1")
        time.sleep(0.5)
        # the highlighter along the paragraph's third line: a highlight of those words
        marks = lambda: js("document.querySelectorAll('#docbody mark[data-h]').length")
        m0 = marks()
        js("document.querySelector('.inkpal [data-ink=\"marker\"]').click(), 1")
        y = box["t"] + box["lh"] * 2.5
        adb("shell", "input", "stylus", "swipe", *scr(box["l"] + 10, y), *scr(box["r"] - 40, y), "500")
        check(until(f"document.querySelectorAll('#docbody mark[data-h]').length > {m0}", 6), "the highlighter over words makes a highlight", f"{m0} → {marks()}")
        # in the margin, then the eraser over it, and Undo
        js("document.querySelector('.inkpal [data-ink=\"pen\"]').click(), 1")
        js("window.DafCore.Ink.state().margin || document.querySelector('.inkpal [data-ink=\"margin\"]').click(), 1")
        time.sleep(0.6)
        r = js(f"(() => {{ const e = document.querySelector('#docbody [data-i=\"{box['i']}\"]').getBoundingClientRect(); return [e.right, e.top, innerWidth]; }})()")
        check(r[2] - r[0] > 180, "Margin leaves room on the right", str(r))
        n1 = st().get("strokes", 0)
        adb("shell", "input", "stylus", "swipe", *scr(r[0] + 40, r[1] + 20), *scr(r[0] + 150, r[1] + 30), "300")
        time.sleep(0.5)
        check(st().get("strokes") == n1 + 1, "the pen writes in the margin", str(st()))
        js("document.querySelector('.inkpal [data-ink=\"eraser\"]').click(), 1")
        adb("shell", "input", "stylus", "swipe", *scr(r[0] + 90, r[1] - 10), *scr(r[0] + 95, r[1] + 60), "300")
        time.sleep(0.5)
        check(st().get("strokes") == n1, "the eraser takes it away", str(st()))
        js("document.querySelector('.inkpal [data-ink=\"undo\"]').click(), 1")
        time.sleep(0.3)
        check(st().get("strokes") == n1 + 1, "Undo brings it back", str(st()))
        js("document.querySelector('.inkpal [data-ink=\"pen\"]').click(), 1")
        os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build"), exist_ok=True)
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build", "ink.png"), "wb") as f:   # to look at
            f.write(subprocess.run([ADB, "exec-out", "screencap", "-p"], capture_output=True).stdout)
        # kept: there again when the article opens again
        until("window.DafCore.Ink.state().queued === 0", 6)
        time.sleep(1)
        js("location.reload(), 1")
        time.sleep(1)
        check(until(f"window.DafCore && window.DafCore.Ink && window.DafCore.Ink.state().strokes === {n1 + 1}", 20), "the strokes are there when it opens again", str(js("window.DafCore && window.DafCore.Ink && window.DafCore.Ink.state()")))
        adb("reverse", "--remove", f"tcp:{PORT}", check_=False)
        adb("forward", "--remove", "tcp:9224", check_=False)
        print(("CHECK passed" if not failures else f"CHECK {failures} failed"), flush=True)
        return 1 if failures else 0

    if ONLY == "docs":
        doc = js("fetch('/api/docs?where=library&tab=inbox&kind=article&limit=40').then(r => r.json()).then(j => ((j.items || []).find(d => (d.words || 0) > 300 && d.thumb) || (j.items || []).find(d => (d.words || 0) > 300) || {}).id || '')")
        check(bool(doc), "an article to keep", str(doc))
        js(f"location.hash = 'read/' + encodeURIComponent({json.dumps(doc)}), 1")
        until("document.getElementById('docbody')", 20)
        js("document.querySelector('[data-ract=more]').click(), 1")
        time.sleep(0.6)
        check(js("!!document.querySelector('#pop [data-more=device]')") is True, "the article's ⋯ menu has Keep on this device")
        js("document.querySelector('#pop [data-more=device]').click(), 1")
        check(until(f"dafShell.offline({{ op: 'list' }}).then(l => (l.docs || []).some(x => x.id === {json.dumps(doc)} && x.pinned))", 30), "and keeps it")
        words = js("document.getElementById('docbody').innerText.split(/\\s+/).length")
        js("location.hash = 'library/article', 1")
        marked = until(f"[...document.querySelectorAll('#rows .row.ondevice')].some(r => r.dataset.doc === {json.dumps(doc)})", 15)
        check(marked, "its row is marked as on this device",
              str(js("[location.hash, document.querySelectorAll('#rows .row[data-doc]').length, document.querySelectorAll('#rows .row.ondevice').length, [...document.querySelectorAll('#rows .row[data-doc]')].slice(0, 2).map(r => r.dataset.doc + ' ' + r.className)]")))
        # opened straight from a link, before any list has asked the app what's on the phone
        js(f"location.hash = 'read/' + encodeURIComponent({json.dumps(doc)}); location.reload(), 1")
        time.sleep(2)
        until("window.DafCore && document.getElementById('docbody')", 30)
        js("document.querySelector('[data-ract=more]').click(), 1")
        label = until("(document.querySelector('#pop [data-more=device] span') || {}).textContent === 'Remove from this device'", 10)
        check(label, "opened from a link, its ⋯ menu knows it's kept", str(js("(document.querySelector('#pop [data-more=device] span') || {}).textContent")))
        js("document.getElementById('pop').hidden = true, 1")
        NET.sever()
        adb("shell", "am", "force-stop", PKG)
        time.sleep(1)
        adb("shell", "am", "start", "-n", f"{PKG}/xyz.tiresia.daf.MainActivity")
        conn["ws"] = attach()
        check(conn["ws"] is not None, "with Daf out of reach, the app starts again")
        if conn["ws"]:
            until("window.DafCore && document.body && document.body.dataset.view", 40)
            js(f"location.hash = 'read/' + encodeURIComponent({json.dumps(doc)}), 1")
            ok = until(f"document.getElementById('docbody') && document.getElementById('docbody').innerText.split(/\\s+/).length >= {int(words or 1) - 5}", 20)
            got = js("document.getElementById('docbody') ? document.getElementById('docbody').innerText.split(/\\s+/).length : 0")
            check(ok, "and the article opens from the device, all of it", f"{got} of {words} words")
            pics = js("[...document.querySelectorAll('#docbody img')].map(i => i.complete && i.naturalWidth > 0)")
            print(f"INFO  its pictures offline: {pics}", flush=True)
            js(f"dafShell.offline({{ op: 'doc', id: {json.dumps(doc)}, on: false }}).then(() => 1)")
        NET.mend()
        adb("reverse", "--remove", f"tcp:{PORT}", check_=False)
        adb("forward", "--remove", "tcp:9224", check_=False)
        print(("CHECK passed" if not failures else f"CHECK {failures} failed"), flush=True)
        return 1 if failures else 0

    # what nothing names any more goes after three weeks; a PDF keeps its file; a kept article deleted in Daf goes
    if ONLY == "prune":
        sha = lambda k: hashlib.sha1(k.encode()).hexdigest()
        enc = lambda i: urllib.parse.quote(i, safe="_-!.~'()*")
        sh = lambda cmd: adb("shell", f"run-as {PKG} sh -c {shlex.quote(cmd)}", check_=False)   # adb shell joins its args: one quoted line
        def sync():
            """A sync, polled: a first one fetches books too, longer than DevTools stays quiet."""
            js("window.__sync = null, dafShell.offline({ op: 'sync' }).then(r => window.__sync = r, e => window.__sync = { error: e.message }), 1")
            until("window.__sync", 900)
            return js("window.__sync") or "no answer"
        r = sync()
        check(isinstance(r, dict) and bool(r.get("data")), "a sync keeps Daf's data", str((r or {}).get("said") if isinstance(r, dict) else r)[:160])
        plan = js("fetch('/api/offline/plan').then(r => r.json())") or {}
        pdfs = js("fetch('/api/docs?where=library&tab=inbox&kind=pdf&limit=40').then(r => r.json()).then(j => (j.items || []).map(d => d.id))") or []
        pid = next((p for p in pdfs if p in plan.get("docs", [])), None)
        if pid:
            check(sh(f"test -s files/data/{sha('/api/docs/' + enc(pid) + '/pdf')} && echo yes").strip() == "yes", "a PDF in the plan keeps its file", pid)
        else:
            print("SKIP  no PDF in the plan", flush=True)
        # one file nothing names, old (goes); one nothing names, new (stays); a cover the plan names, old (stays)
        cover = next((i for i in plan.get("images", []) if i.startswith("/api/cover/")), "")
        named = sha(cover)
        sh(f"cd files/data && echo x > deadbeefdeadbeef && touch -t 202601010000 deadbeefdeadbeef && echo x > cafecafecafecafe && touch -t 202601010000 {named}")
        # a Feed item kept by hand, then deleted in Daf (the sandbox's FreshRSS is a stand-in)
        fid = js("fetch('/api/docs?where=feed&tab=unseen&limit=30').then(r => r.json()).then(j => ((j.items || []).find(d => (d.words || 0) > 40) || {}).id || '')")
        kept = js(f"dafShell.offline({{ op: 'doc', id: {json.dumps(fid)}, on: true }}).then(l => (l.docs || []).filter(x => x.pinned).map(x => x.id), e => 'failed: ' + e.message)")
        check(isinstance(kept, list) and fid in kept, "a Feed item kept by hand", f"{fid} → {str(kept)[:160]}")
        js(f"fetch('/api/docs/' + encodeURIComponent({json.dumps(fid)}) + '/status', {{ method: 'POST', credentials: 'same-origin', headers: {{ 'Content-Type': 'application/json' }}, body: JSON.stringify({{ status: 'deleted' }}) }}).then(r => r.status)")
        r = sync()
        files = sh("ls files/data")
        check("deadbeefdeadbeef" not in files, "a file nothing names, old, goes", str((r or {}).get("said") or r.get("error") if isinstance(r, dict) else r)[:160])
        check("cafecafecafecafe" in files, "one nothing names but new stays")
        check(bool(cover) and named in files, "and an old one the plan names stays", cover)
        check(js(f"dafShell.offline({{ op: 'list' }}).then(l => !l.docs.some(x => x.id === {json.dumps(fid)}))") is True, "a kept item deleted in Daf leaves the device")
        check(sha("/api/docs/" + enc(fid)) not in files, "with its file")
        sh("rm -f files/data/cafecafecafecafe")
        if pid:
            # Daf out of reach with the phone's Wi-Fi still on: the app learns it at its next start, as in "docs"
            NET.sever()
            adb("shell", "am", "force-stop", PKG)
            time.sleep(1)
            adb("shell", "am", "start", "-n", f"{PKG}/xyz.tiresia.daf.MainActivity")
            conn["ws"] = attach()
            until("window.DafCore && document.body && document.body.dataset.view", 40)
            js(f"location.hash = 'pdf/' + encodeURIComponent({json.dumps(pid)}), 1")
            ok = until("document.querySelectorAll('.pdfpages canvas').length > 0", 40)
            check(ok, "with Daf out of reach, a PDF's pages open from the device",
                  str(js("[location.hash, document.body.dataset.view, !!(window.DafCore && DafCore.views && DafCore.views.pdf), (document.getElementById('main') || document.body).innerText.slice(0, 120)]")) + " " +
                  str(js(f"Promise.all([(document.getElementById('pdfpages') || {{}}).innerText, fetch('/api/docs/' + encodeURIComponent({json.dumps(pid)}) + '/pdf').then(r => r.status + ' ' + r.headers.get('content-type') + ' ' + r.headers.get('content-length'), e => 'fetch failed: ' + e.message), "
                         "fetch('/vendor/pdfjs/pdf.worker.min.mjs').then(r => 'worker ' + r.status, e => 'worker failed: ' + e.message)])"))[:300])
            NET.mend()
        adb("reverse", "--remove", f"tcp:{PORT}", check_=False)
        adb("forward", "--remove", "tcp:9224", check_=False)
        print(("CHECK passed" if not failures else f"CHECK {failures} failed"), flush=True)
        return 1 if failures else 0

    # the status and navigation bars take the theme's background, and keep it for the next start
    if ONLY == "theme":
        def bars():
            """The commonest colour along the top and the bottom rows of the screen, as #rrggbb."""
            raw = subprocess.run([ADB, "exec-out", "screencap"], capture_output=True, check=True).stdout
            w, h = struct.unpack("<II", raw[:8])
            off = len(raw) - w * h * 4
            out = []
            for y in (8, h - 8):
                seen = {}
                for x in range(w // 20, w - w // 20, w // 40):
                    i = off + (y * w + x) * 4
                    c = "#%02x%02x%02x" % tuple(raw[i:i + 3])
                    seen[c] = seen.get(c, 0) + 1
                out.append(max(seen, key=seen.get))
            return out
        was = js("JSON.stringify(DafCore.Themes.get())")
        for want in ({"mode": "light", "light": "paper"}, {"mode": "dark", "dark": "nord"}, {"mode": "light", "light": "solarized"}):
            js(f"DafCore.Themes.apply({json.dumps(want)}), 1")
            bg = js("(() => { const x = document.createElement('canvas').getContext('2d'); x.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--bg'); "
                    "x.fillRect(0, 0, 1, 1); return '#' + [...x.getImageData(0, 0, 1, 1).data.slice(0, 3)].map(v => v.toString(16).padStart(2, '0')).join(''); })()")
            time.sleep(1.2)
            got = bars()
            check(got == [bg, bg], f"the bars take {want.get('light') or want.get('dark')} ({want['mode']})", f"page {bg}, bars {got}")
        # the next start paints the last one before the page has loaded
        adb("shell", "am", "force-stop", PKG)
        adb("shell", "am", "start", "-n", f"{PKG}/xyz.tiresia.daf.MainActivity")
        time.sleep(0.6)
        first = bars()
        check(first[0] == bg, "and the next start has it from the first frame", f"{first} for {bg}")
        conn["ws"] = attach()
        if conn["ws"]:
            until("window.DafCore && DafCore.Themes", 40)
            js(f"DafCore.Themes.apply({was}), 1")
        adb("reverse", "--remove", f"tcp:{PORT}", check_=False)
        adb("forward", "--remove", "tcp:9224", check_=False)
        print(("CHECK passed" if not failures else f"CHECK {failures} failed"), flush=True)
        return 1 if failures else 0

    # no network at all: Daf starts from its own copy on the device, with the data it kept
    if ONLY == "boot":
        r = js("Promise.race([dafShell.offline({ op: 'sync' }), new Promise(r => setTimeout(() => r('no answer'), 280000))])")   # a first sync fetches books too
        app = (r or {}).get("app", {}) if isinstance(r, dict) else {}
        check(app.get("ready") is True, "Daf's screens are kept on the device", str(r)[:160])
        check(isinstance(r, dict) and (r.get("data") or 0) > 0, "and its data", str((r or {}).get("said") if isinstance(r, dict) else r)[:120])
        NET.sever()
        adb("shell", "am", "force-stop", PKG)
        time.sleep(1)
        adb("shell", "am", "start", "-n", f"{PKG}/xyz.tiresia.daf.MainActivity")
        conn["ws"] = attach()
        check(conn["ws"] is not None, "with Daf out of reach, the app starts again")
        if conn["ws"]:
            ok = until("window.DafCore && document.body && document.body.dataset.view === 'today' && /Today/.test(document.body.innerText)", 40)
            check(ok, "and opens on Today, from the device", str(js("[location.href, document.body && document.body.innerText.slice(0, 90)]"))[:200])
            js("location.hash = 'books', 1")
            check(until("document.body.dataset.view === 'books' && document.querySelectorAll('#main img, #main .bcard, #main a').length > 3", 15), "Books opens from the device too")
            js("location.hash = 'review', 1")
            check(until("document.body.dataset.view === 'review' && document.getElementById('main').innerText.length > 40", 15), "and the review",
                  str(js("document.getElementById('main').innerText.slice(0, 80)")))
            fonts = js("document.fonts.check('16px Literata') || document.fonts.check('16px Figtree')")
            print(f"INFO  Daf's own fonts offline: {fonts}", flush=True)
        NET.mend()
        adb("reverse", "--remove", f"tcp:{PORT}", check_=False)
        adb("forward", "--remove", "tcp:9224", check_=False)
        print(("CHECK passed" if not failures else f"CHECK {failures} failed"), flush=True)
        return 1 if failures else 0

    # manga for no Wi-Fi: download a volume from its series page, read it cut off, the page waits
    if ONLY == "mangadl":
        pick = js("fetch('/api/manga').then(r => r.json()).then(async d => { let best = null; for (const s of (d.series || []).slice(0, 12)) { "
                  "const x = await fetch('/api/manga/series/' + s.id).then(r => r.json()); for (const b of x.books || []) if (b.ok !== false && (!best || b.pages < best[2])) best = [s.id, b.id, b.pages]; } return best; })")
        check(bool(pick), "a short volume to download", str(pick))
        sid, bid, n = pick
        js(f"dafShell.offline({{ op: 'manga', id: '{bid}', on: false }}).then(() => 1)")
        js(f"location.hash = 'manga/{sid}', 1")
        check(until(f"document.querySelector('[data-mdl=\"{bid}\"]')", 15), "the series page has a download button")
        js(f"document.querySelector('[data-mdl=\"{bid}\"]').click(), 1")
        state = f"dafShell.offline({{ op: 'list' }}).then(l => ((l.manga || []).find(x => x.id === '{bid}') || {{}}))"
        t0 = time.time()
        while time.time() - t0 < 240:
            x = js(state) or {}
            if x.get("state") in ("done", "failed"):
                break
            time.sleep(3)
        check(x.get("state") == "done" and x.get("done") == n, f"the volume downloads ({n} pages)", f"{x.get('state')} {x.get('done')}/{x.get('total')} {round((x.get('bytes') or 0) / 1048576)} MB in {round(time.time() - t0)} s {x.get('error') or ''}")
        check(until(f"document.querySelector('[data-mdl=\"{bid}\"]').dataset.state === 'done'", 6), "and its button says it's on the device")
        js("localStorage.removeItem('daf.outbox'), 1")
        NET.sever()
        js(f"location.hash = 'mread/{bid}', 1")
        check(until("document.body.dataset.view === 'mread' && [...document.querySelectorAll('#mreader img')].some(i => i.complete && i.naturalWidth > 0)", 30),
              "cut off from Daf, it opens from the device")
        time.sleep(2)
        adb("shell", "input", "keyevent", "KEYCODE_VOLUME_DOWN")
        time.sleep(1)
        adb("shell", "input", "keyevent", "KEYCODE_VOLUME_DOWN")
        time.sleep(1)
        check(until("[...document.querySelectorAll('#mreader img')].filter(i => i.complete && i.naturalWidth > 0).length > 0", 6), "and turns its pages")
        js("dafBack(), 1")
        time.sleep(1)
        js("document.body.dataset.view === 'mread' && dafBack(), 1")
        check(until("JSON.parse(localStorage.getItem('daf.outbox') || '[]').some(x => /manga\\/books\\/[^/]+\\/progress$/.test(x.path))", 15),
              "the page read waits in the outbox", str(js("localStorage.getItem('daf.outbox')"))[:160])
        NET.mend()
        js("DafCore.outbox.flush(), 1")
        check(until("JSON.parse(localStorage.getItem('daf.outbox') || '[]').length === 0", 30), "back in reach, it goes to Daf")
        r = js(f"dafShell.offline({{ op: 'manga', id: '{bid}', on: false }}).then(l => (l.manga || []).some(x => x.id === '{bid}'))")
        check(r is False, "and removing the volume lets it go")
        adb("reverse", "--remove", f"tcp:{PORT}", check_=False)
        adb("forward", "--remove", "tcp:9224", check_=False)
        print(("CHECK passed" if not failures else f"CHECK {failures} failed"), flush=True)
        return 1 if failures else 0

    # new posts: the page turns notifications on, a post arrives, the job rings
    if ONLY == "news":
        adb("shell", "pm", "grant", PKG, "android.permission.POST_NOTIFICATIONS", check_=False)   # what the app would ask for
        feed = js("fetch('/api/feed/sources').then(r => r.json()).then(s => (s.folders.flatMap(f => f.feeds).find(x => x.notify) || {}).id || '')")
        check(bool(feed), "a feed set to notify (the sandbox's)", str(feed))
        r = js("Promise.race([dafShell.alerts(), new Promise(r => setTimeout(() => r('no answer'), 8000))])")
        check(r is True, "dafShell.alerts: permission, and the job", str(r))
        time.sleep(3)
        jobs = adb("shell", "cmd", "jobscheduler", "get-job-state", "-u", "0", PKG, "33", check_=False).strip()
        check("unknown" not in jobs.lower(), "the job is scheduled", jobs)
        # a post queued in the sandbox's stand-in FreshRSS beforehand comes in with a refresh
        got = js("fetch('/api/feed/refresh', { method: 'POST' }).then(r => r.json()).then(j => j.new)")
        title = js(f"fetch('/api/docs?where=feed&feed={feed}&limit=1').then(r => r.json()).then(j => (j.items[0] || {{}}).title || '')")
        if not got:
            print("SKIP  a post arriving: queue one in the sandbox's stand-in FreshRSS first", flush=True)
        else:
            check(bool(title), "a post arrives in the sandbox", str(title))
            adb("shell", "cmd", "jobscheduler", "run", "-f", PKG, "33", check_=False)
            ok = False
            for _ in range(20):
                time.sleep(1)
                if title in adb("shell", "dumpsys", "notification", "--noredact", check_=False):
                    ok = True
                    break
            check(ok, "and it rings, with the post's title")
            adb("shell", "cmd", "jobscheduler", "run", "-f", PKG, "33", check_=False)
            time.sleep(4)
            n = adb("shell", "dumpsys", "notification", "--noredact", check_=False).count(title)
            print(f"INFO  the title appears {n} time(s) in the notification list after a second run", flush=True)
        adb("reverse", "--remove", f"tcp:{PORT}", check_=False)
        adb("forward", "--remove", "tcp:9224", check_=False)
        print(("CHECK passed" if not failures else f"CHECK {failures} failed"), flush=True)
        return 1 if failures else 0

    # the manga reader: the whole screen, kept on, the volume keys, Back
    if ONLY == "manga":
        size = adb("shell", "wm", "size")
        print("INFO  " + adb("shell", "getprop", "ro.product.model").strip() + ", " + size.strip().replace("\n", "; ") +
              ", density " + adb("shell", "wm", "density").strip().split(":")[-1].strip(), flush=True)
        js("location.hash = 'today', 1")
        time.sleep(1.5)
        print("INFO  the page's size: " + str(js("[innerWidth, innerHeight, devicePixelRatio, screen.width, screen.height]")), flush=True)
        before = js("innerHeight")
        ids = js("fetch('/api/manga').then(r => r.json()).then(async d => { const s = (d.series || [])[0]; if (!s) return null; "
                 "const x = await fetch('/api/manga/series/' + s.id).then(r => r.json()); return [s.id, (x.books || [])[0].id]; })")
        if not ids:
            check(False, "a manga to open")
        else:
            js(f"location.hash = 'manga/{ids[0]}', 1")
            time.sleep(2)
            js(f"location.hash = 'mread/{ids[1]}', 1")
            check(until("document.body.dataset.view === 'mread' && [...document.querySelectorAll('#mreader img')].some(i => i.complete && i.naturalWidth > 0)", 30),
                  "a manga page draws", str(js("[...document.querySelectorAll('#mreader img')].map(i => i.naturalWidth)")))
            time.sleep(2)
            # (the same call keeps the screen on; with DevTools attached Android keeps it on anyway,
            # so the window's flag can't be checked from here)
            check(js("innerHeight") > before, "the reader takes the whole screen (no status or navigation bar)", f"{before} → {js('innerHeight')}")
            page = "[...document.querySelectorAll('#mreader img')].map(i => (/pages\\/(\\d+)/.exec(i.src) || [])[1]).join(',')"
            a = js(page)
            adb("shell", "input", "keyevent", "KEYCODE_VOLUME_DOWN")
            time.sleep(1.5)
            b = js(page)
            check(a != b, "volume down turns the page", f"{a} → {b}")
            for _ in range(4):
                if js("document.body.dataset.view") != "mread":
                    break
                adb("shell", "input", "keyevent", "KEYCODE_BACK")
                time.sleep(1)
            check(js("document.body.dataset.view") != "mread", "Back closes the reader", str(js("location.hash")))
            time.sleep(1.5)
            check(js("innerHeight") == before, "and the bars come back",
                  f"{js('innerHeight')} / {before}")
        adb("reverse", "--remove", f"tcp:{PORT}", check_=False)
        adb("forward", "--remove", "tcp:9224", check_=False)
        print(("CHECK passed" if not failures else f"CHECK {failures} failed"), flush=True)
        return 1 if failures else 0

    # a book's pages, with real taps and swipes: Scroll (the phone's default) and Pages
    if ONLY == "book":
        size = adb("shell", "wm", "size")
        w, h = map(int, (size.split("Override size:")[-1] if "Override" in size else size.split("Physical size:")[-1]).strip().split("x"))
        frac = "document.querySelector('foliate-view').lastLocation.fraction"
        opened = "((document.querySelector('foliate-view') || {}).lastLocation ? true : false)"
        pop = "!document.getElementById('pop').hidden"

        def layout(flow):
            js("(() => { const t = JSON.parse(localStorage.getItem('daf.type') || '{}'); " + ("t.flow = 'paginated'" if flow else "delete t.flow") +
               "; localStorage.setItem('daf.type', JSON.stringify(t)); Object.keys(localStorage).filter(k => k.startsWith('daf.type.')).forEach(k => localStorage.removeItem(k)); return 1; })()")
            js("location.hash = 'today', 1")
            time.sleep(1)
            js("location.hash = 'ebook/cal%3A160', 1")
            check(until(opened, 30), "the book opens" + (" in Pages" if flow else ""), str(js("document.body.dataset.flow")))
            time.sleep(2.5)

        def moved(action, what, forward=True):
            a = js(frac)
            action()
            time.sleep(1.8)
            b = js(frac)
            check(isinstance(a, (int, float)) and isinstance(b, (int, float)) and (b > a if forward else b < a), what, f"{a} → {b}")

        tap = lambda fx, fy: adb("shell", "input", "tap", str(int(w * fx)), str(int(h * fy)))
        swipe = lambda x0, x1: adb("shell", "input", "swipe", str(int(w * x0)), str(int(h * .5)), str(int(w * x1)), str(int(h * .51)), "160")
        layout(None)
        check(js("document.body.dataset.flow") == "scrolled", "Scroll is the phone's layout")
        moved(lambda: tap(.93, .5), "Scroll: a tap on the right side moves on")
        moved(lambda: tap(.07, .5), "a tap on the left side goes back", forward=False)
        moved(lambda: swipe(.85, .15), "a swipe to the left moves on")
        js("document.querySelector('[data-bk=aa]').click(), 1")
        time.sleep(.6)
        r = js("(() => { const r = document.getElementById('pop').getBoundingClientRect(); return [r.left, r.right, r.top, r.bottom, innerWidth, innerHeight]; })()")
        print("INFO  Aa menu at " + str([round(x) for x in r]), flush=True)
        a = js(frac)
        tap(.5, .5) if r[3] < r[5] * .45 else tap(.96 if r[1] < r[4] * .9 else .04, .55)    # on the page, beside the menu
        time.sleep(1)
        check(js(pop) is False and js(frac) == a, "a tap on the page closes Aa, and only that", f"{a} → {js(frac)}")
        js("document.getElementById('pop').hidden = true, 1")
        js("document.querySelector('[data-bk=aa]').click(), 1")
        time.sleep(.4)
        js("document.querySelector('[data-bk=aa]').click(), 1")
        time.sleep(.4)
        check(js(pop) is False, "and Aa again closes it")
        layout("paginated")
        tap(.07, .5)
        time.sleep(1.2)
        tap(.07, .5)
        time.sleep(1.2)
        moved(lambda: swipe(.85, .15), "Pages: a swipe to the left turns the page")
        sec = "(document.querySelector('foliate-view').lastLocation.tocItem || {}).label"
        last = "(() => { const r = document.querySelector('foliate-view').renderer; return r.page >= r.pages - 2; })()"
        for _ in range(60):                       # to the chapter's last page, by taps
            if js(last):
                break
            tap(.93, .5)
            time.sleep(1)
        c1 = js(sec)
        swipe(.85, .15)
        time.sleep(2.5)
        check(js(last) is not None and js(sec) != c1, "a swipe to the left on a chapter's last page goes on to the next", f"{c1} → {js(sec)}")
        moved(lambda: swipe(.15, .85), "a swipe to the right turns back", forward=False)
        moved(lambda: tap(.93, .5), "a tap on the right side turns the page")
        layout(None)
        js("location.hash = 'today', 1")
        adb("reverse", "--remove", f"tcp:{PORT}", check_=False)
        adb("forward", "--remove", "tcp:9224", check_=False)
        print(("CHECK passed" if not failures else f"CHECK {failures} failed"), flush=True)
        return 1 if failures else 0

    # books on the phone: a book opened in the app opens again with Daf out of reach, and the
    # place turned to there reaches Daf once it's back
    r = js("Promise.race([dafShell.offline({ op: 'list' }), new Promise(r => setTimeout(() => r('no answer'), 5000))])")
    check(isinstance(r, dict) and "books" in r, "dafShell.offline answers", str(r)[:80])
    bk = js("fetch('/api/ebooks').then(r => r.json()).then(j => ((j.books || []).find(b => /^cal:/.test(b.id)) || {}).id || '')")
    if bk:
        js(f"dafShell.offline({{ op: 'keep', id: {json.dumps(bk)}, on: false }}).then(() => 1)")
        js("localStorage.removeItem('daf.outbox'), 1")
        opened = "((document.querySelector('foliate-view') || {}).lastLocation ? true : false)"
        js(f"location.hash = 'ebook/' + encodeURIComponent({json.dumps(bk)}), 1")
        check(until(opened, 30), "a book opens", bk)
        ids = js("dafShell.offline({ op: 'list' }).then(l => l.books.map(b => b.id + ':' + b.size))") or []
        check(any(x.startswith(bk + ":") for x in ids), "and stays on the phone", ", ".join(ids)[:120])
        js("location.hash = 'today', 1")
        time.sleep(1.5)
        NET.sever()
        js(f"location.hash = 'ebook/' + encodeURIComponent({json.dumps(bk)}), 1")
        check(until(opened, 30), "with Daf out of reach it opens from the phone",
              str(js("(document.getElementById('bstage') || {}).innerText")).strip()[:80])
        time.sleep(2)
        js("document.querySelector('foliate-view').next(), 1")
        time.sleep(1)
        js("document.querySelector('foliate-view').next(), 1")
        time.sleep(3)                                  # the page saves its place 1.5 s after the last turn
        cfi = js("document.querySelector('foliate-view').lastLocation.cfi")
        check(until(f"JSON.parse(localStorage.getItem('daf.outbox') || '[]').some(x => /position$/.test(x.path) && x.body.cfi === {json.dumps(cfi)})", 10),
              "turning pages there keeps the place in the outbox")
        NET.mend()
        js("DafCore.outbox.flush(), 1")
        check(until("JSON.parse(localStorage.getItem('daf.outbox') || '[]').length === 0", 30), "back in reach, the outbox empties")
        pos = js(f"fetch('/api/ebooks/' + encodeURIComponent({json.dumps(bk)})).then(r => r.json()).then(d => d.position && d.position.cfi)")
        check(pos == cfi, "and Daf has the place from the phone", f"{str(pos)[:40]} / {str(cfi)[:40]}")
        r = js(f"dafShell.offline({{ op: 'keep', id: {json.dumps(bk)} }}).then(l => l.books.find(b => b.id === {json.dumps(bk)}))")
        check(isinstance(r, dict) and r.get("kept") is True, "Keep on this phone keeps it for good", str(r)[:100])
        adb("shell", "am", "start", "-n", f"{PKG}/xyz.tiresia.daf.SettingsActivity")
        ui = ""
        for _ in range(8):                   # Settings fills its list away from the window; a tablet takes longer
            time.sleep(1.5)
            adb("shell", "uiautomator", "dump", "/sdcard/daf-ui.xml", check_=False)
            ui = adb("shell", "cat", "/sdcard/daf-ui.xml", check_=False)
            if "Books and manga on this device" in ui and "(kept)" in ui:
                break
        adb("shell", "rm", "-f", "/sdcard/daf-ui.xml", check_=False)
        check("Books and manga on this device" in ui and "(kept)" in ui, "Settings lists it under Books and manga on this device")
        adb("shell", "am", "start", "-n", f"{PKG}/xyz.tiresia.daf.MainActivity")
        time.sleep(1.5)
        r = js(f"dafShell.offline({{ op: 'keep', id: {json.dumps(bk)}, on: false }}).then(l => l.books.some(b => b.id === {json.dumps(bk)}))")
        check(r is False, "and letting it go removes it")
        want = js("fetch('/api/books').then(r => r.json()).then(j => [...(j.nightstand || []), ...(j.others || [])].filter(b => b.readable).map(b => b.id))") or []
        r = js("dafShell.offline({ op: 'sync' })")
        got = [b["id"] for b in (r or {}).get("books", [])] if isinstance(r, dict) else []
        check(bool(want) and set(want[:2]) <= set(got), "an update brings the books being read", f"{(r or {}).get('said') if isinstance(r, dict) else r}; {len(got)} of {want[:6]}")
        for b in got:
            js(f"dafShell.offline({{ op: 'keep', id: {json.dumps(b)}, on: false }}).then(() => 1)")
        js("location.hash = 'today', 1")
    else:
        check(False, "a book to keep")
    if ONLY == "offline":
        adb("reverse", "--remove", f"tcp:{PORT}", check_=False)
        adb("forward", "--remove", "tcp:9224", check_=False)
        print(("CHECK passed" if not failures else f"CHECK {failures} failed"), flush=True)
        return 1 if failures else 0

    # Back: the page's first, then nowhere
    js("location.hash = 'review', 1")
    until("document.body.dataset.view === 'review'")
    js("dafCommand('search'), 1")
    until("!document.getElementById('palette').hidden")
    if not awake or locked:
        skipped += 1
        print("SKIP  keys on the phone: unlock it and leave it on, then run again", flush=True)
    else:
        adb("shell", "input", "keyevent", "KEYCODE_BACK")
        check(until("document.getElementById('palette').hidden", 4) and js("document.body.dataset.view") == "review",
              "Back closes search first")
        adb("shell", "input", "keyevent", "KEYCODE_BACK")
        check(until("document.body.dataset.view === 'today'", 4), "then goes back a page", str(js("document.body.dataset.view")))

        # the volume keys turn a book's pages
        bk = js("fetch('/api/ebooks').then(r => r.json()).then(j => { const a = j.items || j.books || j; const b = Array.isArray(a) ? a.find(b => b.readable !== false) : null; return b ? b.id : ''; })")
        if bk:
            js(f"location.hash = 'ebook/' + encodeURIComponent({json.dumps(bk)}), 1")
            text = "(() => { const v = document.querySelector('foliate-view'); try { return v.renderer.getContents()[0].doc.body.innerText.trim().length; } catch (e) { return 0; } })()"
            check(until(f"{text} > 50", 25), "a book opens in the reader", bk)
            time.sleep(1.5)
            place = "(() => { const v = document.querySelector('foliate-view'); return v && v.lastLocation ? v.lastLocation.fraction : -1; })()"
            before, vol = js(place), adb("shell", "cmd", "media_session", "volume", "--stream", "3", "--get", check_=False)
            adb("shell", "input", "keyevent", "KEYCODE_VOLUME_DOWN")
            ok = until(f"{place} > {before}", 5)
            check(ok, "volume down turns the page", f"{before} → {js(place)}")
            after = adb("shell", "cmd", "media_session", "volume", "--stream", "3", "--get", check_=False)
            check(vol == after, "and leaves the volume alone")
            adb("shell", "input", "keyevent", "KEYCODE_VOLUME_UP")
            js("location.hash = 'today', 1")
        else:
            check(False, "a book to open")

    # Share into Daf: a link, with the token
    link = f"https://example.com/daf-android-{int(time.time())}"
    adb("shell", "am", "start", "-n", f"{PKG}/xyz.tiresia.daf.ShareActivity", "-a", "android.intent.action.SEND",
        "-t", "text/plain", "--es", "android.intent.extra.TEXT", f"Worth reading {link}")
    check(until(f"fetch('/api/phone').then(r => r.json()).then(j => j.inbox.some(x => x.url === {json.dumps(link)}))", 10),
          "Share into Daf saves a link to the Library", link)

    # the nudge's switch: on (Android takes the job, and the app doesn't fall over), then off
    import re
    adb("shell", "am", "start", "-n", f"{PKG}/xyz.tiresia.daf.SettingsActivity")
    time.sleep(1.5)
    adb("shell", "uiautomator", "dump", "/sdcard/daf-ui.xml", check_=False)
    ui = adb("shell", "cat", "/sdcard/daf-ui.xml", check_=False)
    m = re.search(r'resource-id="' + re.escape(PKG) + r':id/nudge"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', ui)
    if m and not (not awake or locked):
        x, y = (int(m.group(1)) + int(m.group(3))) // 2, (int(m.group(2)) + int(m.group(4))) // 2
        adb("shell", "input", "tap", str(x), str(y))
        time.sleep(1.5)
        alive = adb("shell", "pidof", PKG, check_=False).strip() != ""
        jobs = adb("shell", "dumpsys", "jobscheduler", check_=False)
        on = adb("shell", "cmd", "jobscheduler", "get-job-state", "-u", "0", PKG, "30", check_=False).strip()
        check(alive and "unknown" not in on.lower(), "switching the nudge on schedules its check, and nothing falls over", on)
        # Android's own permission question may be in front now; answer it, then switch off again
        adb("shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(1)
        adb("shell", "am", "start", "-n", f"{PKG}/xyz.tiresia.daf.SettingsActivity")
        time.sleep(1)
        adb("shell", "input", "tap", str(x), str(y))
        time.sleep(1)
        state = adb("shell", "cmd", "jobscheduler", "get-job-state", "-u", "0", PKG, "30", check_=False).strip()
        prefs = adb("shell", "run-as", PKG, "cat", "shared_prefs/daf.xml", check_=False)
        check("unknown" in state.lower() and 'name="nudge.on" value="false"' in prefs, "and off again cancels it", state)
    else:
        skipped += 1
        print("SKIP  the nudge's switch: no switch on screen, or the phone is locked", flush=True)
    adb("shell", "rm", "-f", "/sdcard/daf-ui.xml", check_=False)

    # another main goal: the widget's answer carries it
    put = lambda g: js("fetch('/api/goals', { method: 'PUT', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ goals: " + g + " }) }).then(r => r.status)")
    adb("shell", "am", "start", "-n", f"{PKG}/xyz.tiresia.daf.MainActivity")
    time.sleep(1.5)
    put_said = put("[{ id: 'pages', period: 'week', target: 200, on: true, main: true }]")
    ok = put_said == 200

    # the widget's numbers and the shortcuts come with the token: leaving the app asks again
    adb("shell", "input", "keyevent", "KEYCODE_HOME")
    time.sleep(3)
    # and Android's own update asks at once, whatever the last answer's age
    adb("shell", "am", "broadcast", "-a", "android.appwidget.action.APPWIDGET_UPDATE", "-n", f"{PKG}/xyz.tiresia.daf.Widget", check_=False)
    time.sleep(3)
    kept = adb("shell", "run-as", PKG, "cat", f"shared_prefs/daf.xml", check_=False)
    check("widget.json" in kept and "&quot;minutes&quot;" in kept, "leaving the app fetches the widget's numbers with the token")
    check(ok and "&quot;kind&quot;:&quot;pages&quot;" in kept.replace(" ", ""), "and the main goal with them (200 pages a week)", f"put {put_said}")
    adb("shell", "am", "start", "-n", f"{PKG}/xyz.tiresia.daf.MainActivity")
    time.sleep(1.5)
    put("[{ id: 'minutes', period: 'day', target: 60, on: true, main: true }]")
    sc = adb("shell", "cmd", "shortcut", "get-shortcuts", "--user", "0", PKG, check_=False)
    print("INFO  shortcuts: " + " ".join(sorted(set(w for w in sc.replace(",", " ").split() if w.startswith("id=")))), flush=True)

    listen_check()

    adb("reverse", "--remove", f"tcp:{PORT}", check_=False)
    adb("forward", "--remove", "tcp:9224", check_=False)
    note = f" ({skipped} skipped)" if skipped else ""
    print(("CHECK passed" if not failures else f"CHECK {failures} failed") + note, flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    sys.exit(main(*sys.argv[1:4]))
