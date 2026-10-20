#!/bin/sh
# Packs the extension into dist/:
#   dist/chromium/          the folder for Chrome or Arc: "Load unpacked"
#   dist/daf-extension.zip  the same, zipped (the Chrome Web Store takes this)
#   dist/firefox/           the folder for Firefox or Zen: about:debugging, "Load Temporary Add-on"
#   dist/daf-extension.xpi  the same, zipped; a permanent install needs Mozilla's signature (README.md)
#   dist/safari/            the folder the Mac app's Safari extension is made from (mac/build.sh),
#                           with safari.js, which gets the token from the Daf app
# Each browser gets a manifest without the other ones' keys. No build step otherwise.
set -eu
cd "$(dirname "$0")"
rm -rf dist
mkdir -p dist/chromium dist/firefox dist/safari
FILES="background.js content.js popup.html popup.js options.html options.js ui.css icons"
for d in chromium firefox safari; do cp -R $FILES "dist/$d/"; done
cp safari.js dist/safari/                        # Safari gets its token from the Daf app (mac/DafSafari)
python3 - <<'EOF'
import json, os, zipfile
m = json.load(open("manifest.json"))
for target in ("chromium", "firefox", "safari"):
    t = json.loads(json.dumps(m))
    if target == "chromium":
        t["background"] = {"service_worker": "background.js"}
        t.pop("browser_specific_settings", None)
    elif target == "safari":
        # Safari 17+: an event page (it unloads when idle, like a service worker), no Firefox keys.
        t["background"] = {"scripts": ["safari.js", "background.js"], "persistent": False}
        t["permissions"] = sorted(set(t.get("permissions", [])) | {"nativeMessaging"})
        t["browser_specific_settings"] = {"safari": {"strict_min_version": "17.0"}}
    else:
        t["background"] = {"scripts": ["background.js"]}
    with open(f"dist/{target}/manifest.json", "w") as f:
        json.dump(t, f, indent=2, ensure_ascii=False)
        f.write("\n")
    if target == "safari":
        continue                                 # Xcode packs it, inside the Mac app
    out = "dist/daf-extension." + ("zip" if target == "chromium" else "xpi")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, names in os.walk(f"dist/{target}"):
            for n in sorted(names):
                p = os.path.join(root, n)
                z.write(p, os.path.relpath(p, f"dist/{target}"))
    print(out, os.path.getsize(out), "bytes")
EOF
