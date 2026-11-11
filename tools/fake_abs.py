#!/usr/bin/env python3
"""A stand-in Audiobookshelf, for trying Daf's Listen pages and for the tests: public-domain books with
made-up narrators, drawn covers, a minute of quiet audio, and the parts of ABS's API Daf uses, reads and
writes alike. Everything is kept in memory and every write is logged (FakeABS.writes), so nothing ever
reaches a real library.

    tools/fake_abs.py [PORT]        then run Daf with DAF_ABS_URL=http://127.0.0.1:PORT DAF_ABS_KEY=fake
"""
import copy
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

H = 3600
# (id, title, author, narrator, series, seconds, colour, chapters' names)
BOOKS = [
    ("moby", "Moby-Dick", "Herman Melville", "Tom Weiss", "", 24 * H + 48 * 60, "#1f3a5a",
     ["Loomings", "The Carpet-Bag", "The Spouter-Inn", "The Counterpane", "Breakfast", "The Street", "The Chapel", "The Pulpit", "The Sermon", "A Bosom Friend"]),
    ("scarlet", "A Study in Scarlet", "Arthur Conan Doyle", "Ruth Avery", "Sherlock Holmes #1", 4 * H + 40 * 60, "#7a1f2b",
     ["Mr. Sherlock Holmes", "The Science of Deduction", "The Lauriston Garden Mystery", "What John Rance Had to Tell", "Our Advertisement Brings a Visitor"]),
    ("four", "The Sign of the Four", "Arthur Conan Doyle", "Ruth Avery", "Sherlock Holmes #2", 4 * H + 30 * 60, "#2f5d46",
     ["The Science of Deduction", "The Statement of the Case", "In Quest of a Solution", "The Story of the Bald-Headed Man"]),
    ("adventures", "The Adventures of Sherlock Holmes", "Arthur Conan Doyle", "Tom Weiss", "Sherlock Holmes #3", 10 * H + 5 * 60, "#4b3a78",
     ["A Scandal in Bohemia", "The Red-Headed League", "A Case of Identity", "The Boscombe Valley Mystery", "The Five Orange Pips"]),
    ("pride", "Pride and Prejudice", "Jane Austen", "Elena Marsh", "", 11 * H + 35 * 60, "#8a5a2b", []),
    ("sense", "Sense and Sensibility", "Jane Austen", "Elena Marsh", "", 12 * H + 2 * 60, "#5a6b2b", []),
    ("meditations", "Meditations", "Marcus Aurelius", "Ruth Avery", "", 5 * H + 2 * 60, "#3b3324",
     ["Book One", "Book Two", "Book Three", "Book Four", "Book Five", "Book Six"]),
    ("timemachine", "The Time Machine", "H. G. Wells", "Tom Weiss", "", 3 * H + 20 * 60, "#1d1d1f", []),
    ("frankenstein", "Frankenstein", "Mary Shelley", "Elena Marsh", "", 8 * H + 30 * 60, "#5a1a12", []),
    ("dracula", "Dracula", "Bram Stoker", "Tom Weiss", "", 15 * H + 30 * 60, "#2a2a3a", []),
]
PROGRESS = {"moby": 0.12, "scarlet": 0.64, "timemachine": 1.0, "pride": 0.03}
COLLECTIONS = [("col-winter", "Long winter", ["moby", "meditations", "pride"]), ("col-car", "Car rides", ["scarlet", "adventures"])]
MARKS = {"moby": [(3 * H + 12 * 60 + 40, "Queequeg at the inn"), (4 * H + 51 * 60 + 5, "Father Mapple’s sermon"), (6 * H + 2 * 60 + 18, "")]}
WEEK = {"moby": [40, 22, 55, 10, 0, 0, 62]}         # minutes, six days ago … today
PODCAST = ("lv-poetry", "Short Poetry Collection", "LibriVox", [("ep1", "Ozymandias"), ("ep2", "The Road Not Taken"), ("ep3", "Sonnet 18")])


def cover_svg(title, author, colour):
    words, lines, cur = title.split(), [], ""
    for w in words:
        if len(cur + " " + w) > 14 and cur:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    lines.append(cur)
    t = "".join(f'<text x="34" y="{110 + i * 48}" font-family="Georgia,serif" font-size="42" fill="#fff">{html.escape(x)}</text>' for i, x in enumerate(lines))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="500" height="500" viewBox="0 0 500 500"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0" stop-color="{colour}"/><stop offset="1" stop-color="#000" stop-opacity=".85"/></linearGradient></defs>'
            f'<rect width="500" height="500" fill="{colour}"/><rect width="500" height="500" fill="url(#g)" opacity=".55"/>'
            f'<rect x="18" y="18" width="464" height="464" fill="none" stroke="#fff" stroke-opacity=".35" stroke-width="2"/>{t}'
            f'<text x="34" y="452" font-family="Helvetica,Arial,sans-serif" font-size="24" fill="#fff" fill-opacity=".85">{html.escape(author)}</text></svg>').encode()


class FakeABS:
    def __init__(self):
        now = int(time.time() * 1000)
        self.writes, self.lock, self.n = [], threading.Lock(), 0
        self.items = {}
        for i, (bid, title, author, narr, series, dur, colour, chs) in enumerate(BOOKS):
            names = chs or [f"Chapter {k + 1}" for k in range(12)]
            step = dur / len(names)
            files = [{"ino": f"{bid}-a{k}", "index": k + 1, "duration": dur / 2, "mimeType": "audio/mpeg",
                      "metadata": {"filename": f"{title} - Part {k + 1}.mp3", "path": f"/fake/{bid}/{k}.mp3", "size": int(dur / 2 * 8000)}} for k in range(2)]
            sname, _, seq = series.rpartition(" #")
            self.items[bid] = {
                "id": bid, "libraryId": "lib-books", "mediaType": "book", "addedAt": now - i * 86400000, "size": int(dur * 8000) + 412000,
                "media": {"metadata": {"title": title, "subtitle": None, "authors": [{"id": "a-" + author, "name": author}], "narrators": [narr],
                                       "series": [{"id": "s-" + sname, "name": sname, "sequence": seq}] if sname else [], "genres": ["Classics"],
                                       "publishedYear": None, "publisher": "LibriVox", "description": f"A public-domain recording of {title}.",
                                       "isbn": "", "asin": None, "language": "English", "authorName": author, "narratorName": narr, "seriesName": series},
                          "duration": dur, "numAudioFiles": 2, "numChapters": len(names), "numTracks": 2, "audioFiles": files,
                          "chapters": [{"id": k, "start": k * step, "end": (k + 1) * step, "title": n} for k, n in enumerate(names)]},
                "libraryFiles": [{"ino": f["ino"], "metadata": f["metadata"], "fileType": "audio"} for f in files] +
                                [{"ino": f"{bid}-c", "metadata": {"filename": "cover.jpg", "size": 412000}, "fileType": "image"}]}
        pid, ptitle, pauthor, eps = PODCAST
        self.items[pid] = {"id": pid, "libraryId": "lib-pods", "mediaType": "podcast", "addedAt": now,
                           "media": {"metadata": {"title": ptitle, "author": pauthor, "description": "Public-domain poems, read aloud.", "genres": ["Poetry"]},
                                     "numEpisodes": len(eps), "episodes": [{"id": e, "title": t, "publishedAt": now - k * 86400000 * 7, "duration": 120,
                                                                             "audioFile": {"ino": f"{pid}-{e}", "duration": 120, "metadata": {"path": f"/fake/{e}.mp3"}}}
                                                                            for k, (e, t) in enumerate(eps)]}}
        self.progress = {b: {"libraryItemId": b, "episodeId": None, "currentTime": p * self.items[b]["media"]["duration"], "duration": self.items[b]["media"]["duration"],
                             "progress": p, "isFinished": p >= 1, "lastUpdate": now - k * 3600000, "hideFromContinueListening": False}
                         for k, (b, p) in enumerate(PROGRESS.items())}
        self.bookmarks = [{"libraryItemId": b, "time": t, "title": n, "createdAt": now} for b, ms in MARKS.items() for t, n in ms]
        self.collections = {cid: {"id": cid, "libraryId": "lib-books", "name": n, "books": list(bs)} for cid, n, bs in COLLECTIONS}
        self.audio = None

    # -- reads
    def minified(self, it):
        x = copy.deepcopy(it)
        x["media"].pop("audioFiles", None)
        x["media"].pop("chapters", None)
        x.pop("libraryFiles", None)
        return x

    def coll(self, c):
        return {**c, "books": [self.minified(self.items[b]) for b in c["books"] if b in self.items]}

    def route(self, method, path, q, body):
        p = path.rstrip("/")
        if p == "/ping":
            return {"success": True}
        if p == "/status":
            return {"serverVersion": "2.37.2", "isInit": True}
        if p == "/api/libraries":
            return {"libraries": [{"id": "lib-books", "name": "Audiobooks", "mediaType": "book"}, {"id": "lib-pods", "name": "Poems", "mediaType": "podcast"}]}
        m = re.fullmatch(r"/api/libraries/([\w-]+)/(items|collections|search)", p)
        if m and method == "GET":
            lib, what = m.groups()
            if what == "items":
                return {"results": [self.minified(it) for it in self.items.values() if it["libraryId"] == lib]}
            if what == "collections":
                return {"results": [self.coll(c) for c in self.collections.values() if c["libraryId"] == lib], "total": len(self.collections)}
            words = (q.get("q") or [""])[0].lower()
            hits = [it for it in self.items.values() if it["libraryId"] == lib and words in it["media"]["metadata"]["title"].lower()]
            return {"book": [{"libraryItem": self.minified(it)} for it in hits if it["mediaType"] == "book"],
                    "podcast": [{"libraryItem": self.minified(it)} for it in hits if it["mediaType"] == "podcast"], "episodes": []}
        m = re.fullmatch(r"/api/items/([\w-]+)", p)
        if m and method == "GET":
            return copy.deepcopy(self.items[m.group(1)])
        if p == "/api/me":
            return {"id": "u1", "username": "reader", "token": "not-a-token", "mediaProgress": list(self.progress.values()), "bookmarks": self.bookmarks}
        m = re.fullmatch(r"/api/me/item/listening-sessions/([\w-]+)", p)
        if m:
            mins = WEEK.get(m.group(1), [])
            days = [(date.today() - timedelta(days=len(mins) - 1 - k)).isoformat() for k in range(len(mins))]
            return {"total": len(mins), "sessions": [{"date": d, "timeListening": v * 60} for d, v in zip(days, mins) if v]}
        if p == "/api/search/providers":
            return {"providers": {"books": [{"value": "audible", "text": "Audible.com"}, {"value": "google", "text": "Google Books"},
                                            {"value": "openlibrary", "text": "Open Library"}, {"value": "itunes", "text": "iTunes"}]}}
        if p == "/api/search/books":
            t, a, prov = (q.get("title") or [""])[0], (q.get("author") or [""])[0], (q.get("provider") or [""])[0]
            years = {"audible": ["2014", "2019"], "google": ["1851", "2003"], "openlibrary": ["1851", "1992"], "itunes": ["2011"]}.get(prov, ["2000"])
            return list(getattr(self, "search_extra", [])) + [{"title": t + (" (Unabridged)" if k else ""), "author": a, "narrator": "Tom Weiss" if prov == "audible" else "", "publisher": ["Harper", "Penguin", "Dover"][k % 3],
                     "publishedYear": y, "description": f"{t}, by {a}.", "genres": ["Fiction", "Classics"], "language": "English",
                     "cover": "data:image/svg+xml;utf8," + urllib.parse.quote(cover_svg(t, a, ["#334", "#543", "#354"][k % 3]).decode()),
                     "series": [], "isbn": "", "asin": ""} for k, y in enumerate(years)]
        # -- writes
        with self.lock:
            self.writes.append((method, p, body))
        m = re.fullmatch(r"/api/me/item/([\w-]+)/bookmark(?:/(\d+))?", p)
        if m:
            item, t = m.group(1), m.group(2)
            if method == "POST":
                self.bookmarks.append({"libraryItemId": item, "time": int(body["time"]), "title": body.get("title") or "", "createdAt": int(time.time() * 1000)})
            elif method == "PATCH":
                for b in self.bookmarks:
                    if b["libraryItemId"] == item and b["time"] == int(body["time"]):
                        b["title"] = body.get("title") or ""
            elif method == "DELETE":
                self.bookmarks = [b for b in self.bookmarks if not (b["libraryItemId"] == item and b["time"] == int(t))]
            return {}
        if p == "/api/collections" and method == "POST":
            self.n += 1
            c = {"id": f"col-new{self.n}", "libraryId": body["libraryId"], "name": body["name"], "books": list(body.get("books") or [])}
            self.collections[c["id"]] = c
            return self.coll(c)
        m = re.fullmatch(r"/api/collections/([\w-]+)/book(?:/([\w-]+))?", p)
        if m:
            c = self.collections[m.group(1)]
            if method == "POST" and body["id"] not in c["books"]:
                c["books"].append(body["id"])
            elif method == "DELETE":
                c["books"] = [b for b in c["books"] if b != m.group(2)]
            return self.coll(c)
        m = re.fullmatch(r"/api/me/progress/([\w-]+)", p)
        if m and method == "PATCH":
            it = self.items[m.group(1)]
            pr = self.progress.setdefault(it["id"], {"libraryItemId": it["id"], "episodeId": None, "currentTime": 0, "duration": it["media"].get("duration"),
                                                     "progress": 0, "isFinished": False, "lastUpdate": 0, "hideFromContinueListening": False})
            pr.update(isFinished=bool(body.get("isFinished")), lastUpdate=int(time.time() * 1000))
            return {}
        m = re.fullmatch(r"/api/items/([\w-]+)/media", p)
        if m and method == "PATCH":
            md = self.items[m.group(1)]["media"]["metadata"]
            md.update(body.get("metadata") or {})
            if "authors" in (body.get("metadata") or {}):
                md["authorName"] = ", ".join(a["name"] for a in md["authors"])
            if "narrators" in (body.get("metadata") or {}):
                md["narratorName"] = ", ".join(md["narrators"])
            return {"updated": True}
        if re.fullmatch(r"/api/items/([\w-]+)/cover", p):
            return {"success": True}
        if re.fullmatch(r"/api/items/([\w-]+)/play(/[\w-]+)?", p):
            self.n += 1
            return {"id": f"session-{self.n}"}
        if re.fullmatch(r"/api/session/[\w-]+/(sync|close)", p):
            return {}
        raise KeyError(p)


def quiet_mp3(folder):
    """A minute of a soft tone, made once (ffmpeg), for the player to play."""
    out = Path(folder) / "quiet.mp3"
    if not out.exists() and shutil.which("ffmpeg"):
        subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=220:duration=60", "-filter:a", "volume=0.05",
                        "-b:a", "48k", str(out)], check=False)
    return out if out.exists() else None


def serve(port=0, folder=None):
    """Start it in a thread: (server, FakeABS, base url)."""
    fake = FakeABS()
    folder = folder or tempfile.mkdtemp(prefix="fakeabs-")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, data, ctype="application/json"):
            raw = data if isinstance(data, bytes) else json.dumps(data).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _any(self, method):
            u = urllib.parse.urlparse(self.path)
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"null") if n else None
            m = re.fullmatch(r"/api/items/([\w-]+)/cover", u.path)
            if m and method == "GET":
                it = fake.items.get(m.group(1))
                if not it:
                    return self._send(404, {})
                md = it["media"]["metadata"]
                colour = next((b[6] for b in BOOKS if b[0] == it["id"]), "#2b4a6b")
                return self._send(200, cover_svg(md["title"], md.get("authorName") or md.get("author") or "", colour), "image/svg+xml")
            if re.fullmatch(r"/api/items/[\w-]+/file/[\w-]+", u.path) and method == "GET":
                f = quiet_mp3(folder)
                return self._send(200, f.read_bytes(), "audio/mpeg") if f else self._send(404, {})
            try:
                return self._send(200, fake.route(method, u.path, urllib.parse.parse_qs(u.query), body))
            except KeyError:
                return self._send(404, {"error": "not found"})

        def do_GET(self):
            self._any("GET")

        def do_POST(self):
            self._any("POST")

        def do_PATCH(self):
            self._any("PATCH")

        def do_DELETE(self):
            self._any("DELETE")

    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, fake, f"http://127.0.0.1:{srv.server_address[1]}"


if __name__ == "__main__":
    srv, fake, base = serve(int(sys.argv[1]) if len(sys.argv) > 1 else 13399)
    print("fake Audiobookshelf at", base, flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
