"""A real browser for pages that only show themselves to one: the headless Chrome in docker-chrome-1
(Karakeep's, which stays when Karakeep goes), driven over its DevTools port. pages.py asks it when a
plain fetch gets a robot check, a script-only page or almost no text. Stdlib only.
"""
import base64
import json
import os
import socket
import struct
import subprocess
import time
import urllib.request

CONTAINER = "docker-chrome-1"


class BrowserError(Exception):
    pass


def _ip():
    try:
        ip = subprocess.run(["docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", CONTAINER],
                            capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception as e:  # noqa: BLE001
        raise BrowserError(f"no browser: {e}") from e
    if not ip:
        raise BrowserError("the browser container isn't running")
    return ip


class _WS:
    def __init__(self, url, timeout=30):
        host_port, path = url[len("ws://"):].split("/", 1)
        host, port = host_port.split(":")
        self.s = socket.create_connection((host, int(port)), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET /{path} HTTP/1.1\r\nHost: {host_port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.s.recv(4096)
            if not chunk:
                raise BrowserError("the browser closed the connection")
            buf += chunk
        self.rest = buf.split(b"\r\n\r\n", 1)[1]
        self.n = 0

    def _recv(self, n):
        while len(self.rest) < n:
            chunk = self.s.recv(65536)
            if not chunk:
                raise BrowserError("the browser closed the connection")
            self.rest += chunk
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
            msg = self.read()
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise BrowserError(str(msg["error"].get("message", msg["error"])))
                return msg.get("result", {})

    def close(self):
        try:
            self.s.close()
        except OSError:
            pass


def page_html(url, settle=4.0, timeout=30):
    """The page's HTML after its scripts have run: (html, the address it ended on)."""
    ip = _ip()
    try:
        tab = json.load(urllib.request.urlopen(urllib.request.Request(f"http://{ip}:9222/json/new?about:blank", method="PUT"), timeout=10))
    except Exception as e:  # noqa: BLE001
        raise BrowserError(f"the browser didn't answer: {e}") from e
    ws = None
    try:
        ws = _WS(tab["webSocketDebuggerUrl"].replace("localhost", ip).replace("127.0.0.1", ip), timeout=timeout)
        ws.send("Page.enable")
        ws.send("Page.navigate", url=url)
        t0, loaded = time.time(), False
        ws.s.settimeout(2)
        while time.time() - t0 < timeout and not loaded:
            try:
                m = ws.read()
            except (socket.timeout, TimeoutError):
                continue
            loaded = m.get("method") == "Page.loadEventFired"
        ws.s.settimeout(timeout)
        time.sleep(settle)                         # pages that draw themselves after load
        r = ws.send("Runtime.evaluate", expression="[document.documentElement.outerHTML, location.href]", returnByValue=True)
        html, where = (r.get("result") or {}).get("value") or ["", url]
        return html, where
    finally:
        if ws:
            ws.close()
        try:
            urllib.request.urlopen(f"http://{ip}:9222/json/close/{tab['id']}", timeout=5)
        except Exception:  # noqa: BLE001
            pass
