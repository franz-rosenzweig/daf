"""Render a contact sheet of icon SVGs (large, Dock size, menu size) through the Chrome container.

    python3 sheet.py OUT.png a1.svg a2.svg ...
"""
import base64, json, os, sys, time, urllib.request
sys.path.insert(0, '/srv/dev/daf/tools'); import shot

out, files = sys.argv[1], sys.argv[2:]
cells = []
for f in files:
    svg = open(f).read()
    uri = "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
    name = os.path.splitext(os.path.basename(f))[0].upper()
    cells.append(f'<div class="c"><img src="{uri}" width="260" height="260"><div class="row"><img src="{uri}" width="64" height="64">'
                 f'<img src="{uri}" width="32" height="32"><img src="{uri}" width="18" height="18"></div><b>{name}</b></div>')
cols = min(len(files), 3)
html = f'''<html><body style="margin:0;background:#1d1d1f;font:600 22px -apple-system,Helvetica,sans-serif;color:#aaa">
<style>.g{{display:grid;grid-template-columns:repeat({cols},320px);gap:10px 30px;padding:30px}}.c{{text-align:center}}
.row{{display:flex;gap:18px;align-items:center;justify-content:center;margin:-6px 0 6px;padding:10px;background:#e9e6e1;border-radius:14px}}
.c:nth-child(n) .row{{}}b{{display:block;margin-top:4px}}</style><div class="g">{"".join(cells)}</div></body></html>'''
rows = (len(files) + cols - 1) // cols
W, H = 60 + cols * 350, 60 + rows * 400
ip = shot.container_ip(); shot.ensure_chrome(ip)
page = json.load(urllib.request.urlopen(urllib.request.Request(f"http://{ip}:9222/json/new?about:blank", method="PUT")))
ws = shot.WS(page["webSocketDebuggerUrl"].replace("localhost", ip).replace("127.0.0.1", ip))
ws.send("Page.enable")
ws.send("Emulation.setDeviceMetricsOverride", width=W, height=H, deviceScaleFactor=1, mobile=False)
ws.send("Page.navigate", url="data:text/html;base64," + base64.b64encode(html.encode()).decode()); time.sleep(1.5)
open(out, "wb").write(base64.b64decode(ws.send("Page.captureScreenshot", format="png")["data"]))
urllib.request.urlopen(f"http://{ip}:9222/json/close/{page['id']}")
print(out)
