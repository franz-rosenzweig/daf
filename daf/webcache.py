"""The web app's files, fingerprinted, so a device can keep them and never ask again.

Through the public address every request costs a few hundred milliseconds, and the page has some
forty files (its scripts, styles, fonts and the book and PDF readers' libraries). So:

- `index_html()` serves the page with each of its scripts and styles as `/name.js?v=<hash of the
  file>`. A fingerprinted file never changes, so it goes out as immutable (app.py's headers), and a
  changed file gets a new address.
- `sw_js()` serves the service worker with VERSION (a hash over everything in web/) and FILES (the
  fingerprinted addresses) filled in. Any change to web/ is a new sw.js, which the browser notices on
  the next load: it fetches the whole new set at once and drops the old one, so a device never mixes
  two versions.

Native shells keep their own copy of web/ (`/api/app-files`) and read index.html as it is on disk.
"""
import hashlib
import json
import os
import re

from . import config

REF = re.compile(r'((?:src|href)=")(/[^"?#]+\.(?:js|css|webmanifest))(")')
_memo = {"sig": None}


def _scan():
    """{relative path: (size, mtime_ns)} for every file under web/."""
    out = {}
    root = config.WEB_DIR
    for dirpath, _, files in os.walk(root):
        for f in files:
            p = os.path.join(dirpath, f)
            st = os.stat(p)
            out[os.path.relpath(p, root)] = (st.st_size, st.st_mtime_ns)
    return out


def _state():
    files = _scan()
    sig = hashlib.sha1(json.dumps(sorted(files.items())).encode()).hexdigest()
    if _memo["sig"] == sig:
        return _memo
    index = (config.WEB_DIR / "index.html").read_text()
    hashes = {}
    for m in REF.finditer(index):
        path = m.group(2)
        f = config.WEB_DIR / path.lstrip("/")
        if f.is_file():
            hashes[path] = hashlib.sha1(f.read_bytes()).hexdigest()[:10]
    page = REF.sub(lambda m: m.group(1) + m.group(2) + ("?v=" + hashes[m.group(2)] if m.group(2) in hashes else "") + m.group(3), index)
    # the page knows which version it is (app.js compares it with /api/health's after time away)
    page = page.replace("<head>", '<head>\n<meta name="daf-version" content="' + sig[:12] + '">', 1)
    _memo.update(sig=sig, version=sig[:12], index=page, files=["/"] + [p + "?v=" + h for p, h in hashes.items()])
    return _memo


def index_html():
    return _state()["index"]


def sw_js():
    st = _state()
    src = (config.WEB_DIR / "sw.js").read_text()
    return src.replace("__VERSION__", st["version"]).replace('["__FILES__"]', json.dumps(st["files"]))


def version():
    return _state()["version"]
