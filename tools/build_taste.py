#!/usr/bin/env python3
"""Build Daf's taste: a public, static page where anyone can try Daf on sample data.

    python3 tools/build_taste.py OUT_DIR
    python3 tools/build_taste.py OUT_DIR --docs    # only for the docs' screenshots (tools/docs_shots.py)

OUT_DIR gets the page from taste/ (index.html, taste.css, taste.js, shots/) and, in OUT_DIR/app/,
a copy of the real web app (web/) that runs with no server: taste/app/demo.js answers its api/
calls in the browser from the sample library, and keeps what a visitor does in that browser's
localStorage. The copy is the app as it is, with these changes made on the way:

- absolute paths become relative ones ('/api/x' -> 'api/x', '/style.css' -> 'style.css'), so it
  runs from any folder and asks for nothing outside it;
- covers get a .jpg ending (static files in app/api/cover/), and the book reader's pages load
  the fonts from the folder instead of the site's root;
- the service worker, the PDF viewer and the Recovery page are left out, and so is the
  Recovery line in What's new;
- foliate-js's paginator doesn't lay out a section that is still loading (guard_paginator).

The sample library is taste/data: four public-domain books from Project Gutenberg as Gutenberg
made them, three public-domain essays, covers made for the demo, and made-up highlights. Every
highlight is checked against its book or essay here, so the build stops if one can't be found.
Standard library only; it reads the EPUBs as zip files and never runs anything in them.

--docs makes a build for the screenshots in docs/images and nothing else: it adds taste/data/docs.json
(a made-up Feed, Torah shelf and Hardcover status), keeps the whole sidebar but Recovery, and leaves
out the demo's own notes. It is never deployed: the build refuses to write it under stuffs.
"""
import html
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB, TASTE = ROOT / "web", ROOT / "taste"
DATA = TASTE / "data"
MARK = ".daf-taste"
SKIP = {"sw.js", "pdfview.js", "recovery.js", "manifest.webmanifest"}
SKIP_DIRS = {"vendor/pdfjs"}


def fail(msg):
    sys.exit("build_taste: " + msg)


# ---- the EPUBs: which section each made-up Kindle highlight is in --------------------------

def squash(t):
    """book.js's squash(): lower case, whitespace runs to one space, every quote mark to '."""
    t = re.sub(r"[\s­]+", " ", t.lower())
    return re.sub(r"[“”\"‘’']", "'", t).strip()


def sections(epub):
    """The text of each spine section, as the reader's textContent would have it, squashed."""
    with zipfile.ZipFile(epub) as z:
        opf = next(n for n in z.namelist() if n.endswith(".opf"))
        t = z.read(opf).decode("utf-8")
        base = opf.rsplit("/", 1)[0] + "/" if "/" in opf else ""
        items = {}
        for m in re.finditer(r"<item\b[^>]*>", t):
            a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(0)))
            items[a.get("id")] = a.get("href")
        out = []
        for idref in re.findall(r'<itemref\b[^>]*idref="([^"]+)"', t):
            x = z.read(base + items[idref]).decode("utf-8", "replace")
            x = re.sub(r"(?s)<head.*?</head>", "", x)
            out.append(squash(html.unescape(re.sub(r"<[^>]+>", "", x))))
        return out


def place_book_highlight(secs, h, title):
    words = squash(h["text"]).split(" ")
    head, tail = " ".join(words[:8]), " ".join(words[-6:])
    hits = [i for i, s in enumerate(secs) if head in s and tail in s[s.find(head):]]
    if "sec" in h:
        if h["sec"] not in hits:
            fail(f"{title}: “{h['text'][:50]}” isn't in section {h['sec']} (found in {hits})")
        return h["sec"]
    if not hits:
        fail(f"{title}: can't find “{h['text'][:60]}” in the EPUB")
    return hits[0]


# ---- the essays: where each made-up highlight sits in its blocks --------------------------

def block_text(b):
    """A block's text as the page has it (textContent of its HTML)."""
    return html.unescape(re.sub(r"<[^>]+>", "", b["h"]))


def place_article_highlight(blocks, h, title):
    for i, b in enumerate(blocks):
        s = block_text(b).find(h["text"])
        if s >= 0:
            return {"b": i, "s": s, "e": s + len(h["text"])}
    fail(f"{title}: can't find “{h['text'][:60]}”")


def seed(docs=False):
    books = json.loads((DATA / "books.json").read_text())
    arts = {a["id"]: a for a in json.loads((DATA / "articles.json").read_text())}
    out = {"books": [], "articles": []}
    for b in books["books"]:
        epub = DATA / "books" / b["file"]
        if not epub.exists():
            fail(f"missing {epub}")
        secs = sections(epub)
        hs = []
        for h in b["highlights"]:
            n = place_book_highlight(secs, h, b["title"])
            hs.append({k: v for k, v in h.items() if k != "sec"} | {"xp": f"/body/DocFragment[{n + 1}]/body"})
        out["books"].append({k: v for k, v in b.items() if k != "highlights"} | {"highlights": hs, "size": epub.stat().st_size})
    for aid, st in books["articles"].items():
        a = arts.get(aid) or fail(f"no essay {aid} in articles.json")
        first = next((block_text(x) for x in a["blocks"] if x["t"] == "p"), "")
        summary = first if len(first) <= 220 else first[:220].rsplit(" ", 1)[0] + "…"
        hs = [h | {"pos": place_article_highlight(a["blocks"], h, a["title"])} for h in st.get("highlights", [])]
        out["articles"].append(a | {"summary": summary, "state": st | {"highlights": hs}})
    if docs:
        d = json.loads((DATA / "docs.json").read_text())
        out["docs"] = True
        out["feed"] = []
        for f in d["feed"]:
            blocks = [{"t": "p", "x": t, "h": html.escape(t, quote=False)} for t in f["paragraphs"]]
            out["feed"].append({k: v for k, v in f.items() if k != "paragraphs"} | {"blocks": blocks, "summary": f["paragraphs"][0],
                                "words": sum(len(t.split()) for t in f["paragraphs"])})
        out["torah"], out["hardcover"] = d["torah"], d["hardcover"]
    m = re.search(r"const NEWS = \[\s*\{\s*id:\s*'([^']+)'", (WEB / "tips.js").read_text())
    out["news"] = m.group(1) if m else ""
    return out


# ---- the app, made relative ---------------------------------------------------------------

def rewrite_js(name, s):
    n = 0
    for q in ("'", '"', "`"):
        n += s.count(q + "/api/")
        s = s.replace(q + "/api/", q + "api/")
    # Covers are static files here, so they need a file ending.
    s, k = re.subn(r"""(src="api/cover/' \+ encodeURIComponent\([\w.]+\) \+ ')(")""", r"\1.jpg\2", s)
    if name == "book.js":
        old = '"@import url(\'" + location.origin + "/fonts/fonts.css\');\\n"'
        f = s.count(old)
        s = s.replace(old, '"@import url(\'" + new URL("fonts/fonts.css", location.href).href + "\');\\n"')
        if f != 1:
            fail("book.js: the fonts.css line moved; update rewrite_js")
    if name == "tips.js":
        s, r = re.subn(r"\n[^\n]*go: '#recovery'[^\n]*", "", s)
        if r != 1:
            fail("tips.js: the Recovery line in What's new moved; update rewrite_js")
    left = re.findall(r"""['"`]/(?:api|fonts|vendor|extension)/[^'"`]*""", s) + re.findall(r"location\.origin \+ ['\"]/", s)
    if left:
        fail(f"{name}: absolute paths left: {left[:5]}")
    return s, k


def rewrite_index(s):
    s = re.sub(r'\n<link rel="manifest"[^>]*>', "", s)
    s = re.sub(r'\n<script src="/recovery\.js"></script>', "", s)
    s = re.sub(r'\n<script type="module" src="/pdfview\.js"></script>', "", s)
    s = re.sub(r'(href|src)="/(?!/)', r'\1="', s)
    s = s.replace('<link rel="stylesheet" href="style.css">', '<link rel="stylesheet" href="style.css">\n<link rel="stylesheet" href="demo.css">')
    s = s.replace('<script src="shell.js"></script>', '<script src="demo-seed.js"></script>\n<script src="demo.js"></script>\n<script src="shell.js"></script>')
    s = s.replace('<script type="module" src="book.js"></script>', '<script src="demo-ui.js"></script>\n<script type="module" src="book.js"></script>')
    s = s.replace("<title>Daf</title>", '<title>Daf · a demo on sample data</title>\n<meta name="robots" content="noindex">')
    for need in ("demo.css", "demo-seed.js", "demo.js", "demo-ui.js"):
        if need not in s:
            fail("index.html changed shape; update rewrite_index (" + need + ")")
    if re.search(r'(href|src)="/', s):
        fail("index.html: absolute paths left")
    return s


def guard_paginator(s):
    """foliate-js lays a section out again whenever the page resizes, and a resize can land while a new
    section is still loading, before its <body> exists: then it throws (harmless, the load lays it out
    again a moment later). Daf's own copy now carries the same guard, so this is only for an older one."""
    if "!this.#view.document?.body" in s:   # Daf's own copy has the guard since 2026-10-22
        return s
    old = "    render() {\n        if (!this.#view) return\n"
    if s.count(old) != 1:
        fail("foliate-js paginator.js changed; update guard_paginator")
    return s.replace(old, "    render() {\n        if (!this.#view || !this.#view.document?.body) return   // Daf's taste: not while a section loads\n")


def copy_app(app):
    covers = 0
    for p in sorted(WEB.rglob("*")):
        rel = p.relative_to(WEB).as_posix()
        if p.is_dir() or p.name in SKIP or any(rel == d or rel.startswith(d + "/") for d in SKIP_DIRS) or p.name.startswith("."):
            continue
        dst = app / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if p.suffix == ".js" and not rel.startswith("vendor/"):
            s, k = rewrite_js(p.name, p.read_text())
            covers += k
            dst.write_text(s)
        elif rel == "index.html":
            dst.write_text(rewrite_index(p.read_text()))
        elif rel == "vendor/foliate-js/paginator.js":
            dst.write_text(guard_paginator(p.read_text()))
        else:
            shutil.copy2(p, dst)
    if covers != 3:
        fail(f"expected 3 cover addresses in the app, found {covers}; update rewrite_js")


def main():
    args = [a for a in sys.argv[1:] if a != "--docs"]
    docs = "--docs" in sys.argv[1:]
    if len(args) != 1:
        sys.exit(__doc__)
    out = Path(args[0]).resolve()
    if docs and "stuffs" in out.parts:
        fail("a --docs build is only for the screenshots; it never goes on stuffs")
    if out.exists() and any(out.iterdir()):
        if not (out / MARK).exists():
            fail(f"{out} isn't empty and isn't a taste build (no {MARK}); not touching it")
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / MARK).write_text("Built by daf/tools/build_taste.py; the whole folder is replaced on each build.\n")
    s = seed(docs)
    app = out / "app"
    copy_app(app)
    for f in ("demo.js", "demo-ui.js", "demo.css"):
        shutil.copy2(TASTE / "app" / f, app / f)
    (app / "demo-seed.js").write_text("/* The sample library (tools/build_taste.py from taste/data). Public-domain texts; made-up reading. */\n"
                                      "window.DAF_SEED = " + json.dumps(s, ensure_ascii=False, separators=(",", ":")) + ";\n")
    (app / "books").mkdir()
    (app / "api" / "cover").mkdir(parents=True)
    for b in s["books"]:
        shutil.copy2(DATA / "books" / b["file"], app / "books" / b["file"])
        shutil.copy2(DATA / "covers" / b["cover"], app / "api" / "cover" / (b["id"] + ".jpg"))
    for f in ("index.html", "taste.css", "taste.js"):
        if (TASTE / f).exists():
            shutil.copy2(TASTE / f, out / f)
    if (TASTE / "shots").is_dir():
        shutil.copytree(TASTE / "shots", out / "shots")
    n = sum(1 for _ in out.rglob("*") if _.is_file())
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"taste written to {out}: {n} files, {size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
