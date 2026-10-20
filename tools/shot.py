#!/usr/bin/env python3
"""Screenshot Daf in the headless Chrome container (docker-chrome-1), signed in.

    tools/shot.py OUT.png [--path /#today] [--width 1440 --height 1000] [--dark] [--wait 3]

Starts chromium with remote debugging inside the container if it isn't running,
sets the session cookie, loads the page and saves a PNG. Stdlib only.
"""
import argparse
import base64
import json
import os
import socket
import struct
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from daf import auth  # noqa: E402

CONTAINER = "docker-chrome-1"
BASE = "http://100.91.202.11:8440"


def container_ip():
    return subprocess.run(["docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", CONTAINER],
                          capture_output=True, text=True, check=True).stdout.strip()


def ensure_chrome(ip):
    try:
        urllib.request.urlopen(f"http://{ip}:9222/json/version", timeout=2)
        return
    except OSError:
        pass
    subprocess.run(["docker", "exec", "-d", CONTAINER, "chromium-browser", "--headless=new", "--no-sandbox", "--disable-gpu",
                    "--disable-dev-shm-usage", "--hide-scrollbars", "--remote-debugging-port=9222",
                    "--remote-debugging-address=0.0.0.0", "about:blank"], check=True)
    for _ in range(40):
        try:
            urllib.request.urlopen(f"http://{ip}:9222/json/version", timeout=2)
            return
        except OSError:
            time.sleep(0.25)
    raise SystemExit("chromium did not start")


class WS:
    def __init__(self, url):
        host_port, path = url[len("ws://"):].split("/", 1)
        host, port = host_port.split(":")
        self.s = socket.create_connection((host, int(port)), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET /{path} HTTP/1.1\r\nHost: {host_port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
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

    def send(self, method, **params):
        self.n += 1
        data = json.dumps({"id": self.n, "method": method, "params": params}).encode()
        hdr = bytes([0x81])
        ln = len(data)
        hdr += bytes([0x80 | ln]) if ln < 126 else (bytes([0x80 | 126]) + struct.pack(">H", ln) if ln < 65536 else bytes([0x80 | 127]) + struct.pack(">Q", ln))
        mask = os.urandom(4)
        self.s.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))
        while True:
            msg = self.read()
            if msg.get("id") == self.n:
                return msg.get("result", msg)

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--path", default="/")
    ap.add_argument("--base", default=BASE, help="another address for Daf, e.g. https://daf.tiresia.xyz")
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=1000)
    ap.add_argument("--mobile", action="store_true")
    ap.add_argument("--dark", action="store_true")
    ap.add_argument("--wait", type=float, default=3.0)
    ap.add_argument("--full", action="store_true", help="capture the whole scroll height of <main>")
    a = ap.parse_args()
    ip = container_ip()
    ensure_chrome(ip)
    targets = json.load(urllib.request.urlopen(f"http://{ip}:9222/json"))
    page = next((t for t in targets if t.get("type") == "page"), None)
    if not page:
        page = json.load(urllib.request.urlopen(urllib.request.Request(f"http://{ip}:9222/json/new?about:blank", method="PUT")))
    ws = WS(page["webSocketDebuggerUrl"].replace("localhost", ip).replace("127.0.0.1", ip))
    ws.send("Network.enable")
    ws.send("Network.clearBrowserCache")
    ws.send("Network.setCookie", name=auth.COOKIE, value=auth.make_cookie(), url=a.base)
    ws.send("Emulation.setDeviceMetricsOverride", width=a.width, height=a.height, deviceScaleFactor=1, mobile=a.mobile)
    ws.send("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "dark" if a.dark else "light"}])
    ws.send("Page.enable")
    ws.send("Page.addScriptToEvaluateOnNewDocument", source=(
        "window.__errs=[];addEventListener('error',e=>__errs.push(String(e.message||e)));"
        "addEventListener('unhandledrejection',e=>__errs.push('promise: '+String(e.reason&&e.reason.message||e.reason)));"))
    ws.send("Page.navigate", url="about:blank")
    time.sleep(0.3)
    ws.send("Page.navigate", url=a.base + a.path)
    time.sleep(a.wait)
    if a.full:
        h = ws.send("Runtime.evaluate", expression="document.getElementById('main').scrollHeight", returnByValue=True)
        hh = int(h.get("result", {}).get("value") or a.height)
        ws.send("Emulation.setDeviceMetricsOverride", width=a.width, height=hh, deviceScaleFactor=1, mobile=a.mobile)
        time.sleep(0.8)
    errs = ws.send("Runtime.evaluate", expression="(document.querySelector('#main')||document.body).innerText.slice(0, 160)", returnByValue=True)
    js = ws.send("Runtime.evaluate", expression="JSON.stringify(window.__errs||[])", returnByValue=True)
    js = json.loads(js.get("result", {}).get("value") or "[]")
    if js:
        print("JS ERRORS:", js)
    shot = ws.send("Page.captureScreenshot", format="png")
    with open(a.out, "wb") as f:
        f.write(base64.b64decode(shot["data"]))
    # Leave nothing running: an open reading view would keep counting toward the hour.
    ws.send("Page.navigate", url="about:blank")
    print(a.out, errs.get("result", {}).get("value"))


if __name__ == "__main__":
    main()
