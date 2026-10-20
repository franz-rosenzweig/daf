import sys, json, base64, time, urllib.request
sys.path.insert(0, '/srv/dev/daf/tools'); import shot
SP = ""
svg = open(SP + sys.argv[1]).read()
out = sys.argv[2]
ip = shot.container_ip(); shot.ensure_chrome(ip)
page = json.load(urllib.request.urlopen(urllib.request.Request(f"http://{ip}:9222/json/new?about:blank", method="PUT")))
ws = shot.WS(page["webSocketDebuggerUrl"].replace("localhost", ip).replace("127.0.0.1", ip))
ws.send("Page.enable")
ws.send("Emulation.setDeviceMetricsOverride", width=1024, height=1024, deviceScaleFactor=1, mobile=False)
ws.send("Emulation.setDefaultBackgroundColorOverride", color={"r": 0, "g": 0, "b": 0, "a": 0})
html = '<html><body style="margin:0;background:transparent">' + svg + '</body></html>'
ws.send("Page.navigate", url="data:text/html;base64," + base64.b64encode(html.encode()).decode()); time.sleep(1.5)
open(out, "wb").write(base64.b64decode(ws.send("Page.captureScreenshot", format="png", clip={"x": 0, "y": 0, "width": 1024, "height": 1024, "scale": 1})["data"]))
urllib.request.urlopen(f"http://{ip}:9222/json/close/{page['id']}")
