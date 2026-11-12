"""Learn's areas (web/learn.js): a subject, and what's gathered to learn it.

An area holds books, saved articles and videos, and feeds, in the order to go through them, by
reference (the things themselves stay where they are: in Books, the Library and the Feed):
  book:<books.id>  doc:<docs.id>  feed:<feeds.id>
                   (a Feed item is saved to the Library as it's added, and the area keeps the Library's copy)
  url:<address>    a link saved while the Library was away; it becomes the doc with that address
  want:<title>|<by>  a book suggested and wanted, until a book of that title is in Daf

The helper suggests more (suggest_start): the model is asked for books, articles, videos and feeds for
the subject and the goal, given what's there and what was set aside; videos are found on the
Invidious instance when there is one, and a link is only offered once it opens. Its suggestions wait
in area_suggest until they're added or set aside.
"""
import json
import os
import re
import secrets
import threading
import time
import urllib.parse
import urllib.request

from . import ai, db

COLORS = ["#7a1f2b", "#3d5468", "#6b4a2b", "#2f5d46", "#4b3a78", "#8a5a12"]
KINDS = ("book", "article", "video", "feed")
UA = "Daf/1.0 (+self-hosted reader)"


def _now():
    return int(time.time())


def _clean_color(c):
    return c if isinstance(c, str) and re.match(r"^#[0-9a-fA-F]{6}$", c) else COLORS[0]


# ---- the areas ---------------------------------------------------------------------------------

def create(c, name, goal="", color=None, suggest=True):
    name = (name or "").strip()[:80]
    if not name:
        raise ValueError("A name, please")
    aid = "a" + secrets.token_hex(5)
    last = c.execute("SELECT COALESCE(MAX(ord), 0) FROM areas").fetchone()[0]
    c.execute("INSERT INTO areas (id, name, goal, color, ord, suggest, created) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (aid, name, (goal or "").strip()[:200], _clean_color(color), last + 1, 1 if suggest else 0, _now()))
    c.commit()
    return aid


def update(c, aid, b):
    a = c.execute("SELECT * FROM areas WHERE id = ?", (aid,)).fetchone()
    if not a:
        raise KeyError(aid)
    name = (b["name"] if "name" in b else a["name"]) or ""
    if not str(name).strip():
        raise ValueError("A name, please")
    c.execute("UPDATE areas SET name = ?, goal = ?, color = ?, suggest = ? WHERE id = ?",
              (str(name).strip()[:80], str(b["goal"] if "goal" in b else a["goal"] or "").strip()[:200],
               _clean_color(b["color"]) if "color" in b else a["color"],
               (1 if b["suggest"] else 0) if "suggest" in b else a["suggest"], aid))
    c.commit()


def delete(c, aid):
    """The area goes; what was in it stays where it is."""
    for t in ("area_items", "area_suggest", "area_chat"):
        c.execute(f"DELETE FROM {t} WHERE area_id = ?", (aid,))
    c.execute("DELETE FROM areas WHERE id = ?", (aid,))
    c.commit()


def reorder(c, ids):
    for i, aid in enumerate(ids):
        c.execute("UPDATE areas SET ord = ? WHERE id = ?", (i + 1, aid))
    c.commit()


# ---- what's in one -----------------------------------------------------------------------------

def _valid_ref(c, ref):
    kind, _, key = (ref or "").partition(":")
    if not key:
        return False
    if kind == "book":
        return bool(c.execute("SELECT 1 FROM books WHERE id = ?", (key,)).fetchone())
    if kind == "doc":
        return bool(c.execute("SELECT 1 FROM docs WHERE id = ?", (key,)).fetchone())
    if kind == "feed":
        return bool(c.execute("SELECT 1 FROM feeds WHERE id = ?", (key,)).fetchone())
    if kind == "url":
        return bool(re.match(r"^https?://\S+$", key))
    return kind == "want" and bool(key.strip(" |"))


SAVED_FIRST = ("feed", "pool")         # the Feed (and the Edition's pool) lets go of what's been seen: kept in the Library instead


def _library_copy(c, url):
    from . import pages
    n = pages.norm_url(url)
    for r in c.execute("SELECT id, url FROM docs WHERE where_ = 'library' AND COALESCE(status, '') != 'deleted' AND url IS NOT NULL "
                       "AND instr(lower(url), ?) > 0 ORDER BY added DESC", (n.split("://", 1)[-1].lower(),)):
        if pages.norm_url(r["url"]) == n:
            return r["id"]
    return None


def _save_doc(c, did):
    from . import reader
    return reader.save_to_library(c, did)


def kept(c, ref, save=None):
    """The ref an area keeps for a thing: a Feed item is its Library copy, saved now when `save` is given
    (reader.save_to_library: its highlights and place go along), or the ref as it is."""
    kind, _, key = (ref or "").partition(":")
    if kind != "doc":
        return ref
    d = c.execute("SELECT where_, url FROM docs WHERE id = ?", (key,)).fetchone()
    if not d or d["where_"] not in SAVED_FIRST or not d["url"]:
        return ref
    have = _library_copy(c, d["url"])
    if have:
        return "doc:" + have
    return "doc:" + save(c, key) if save else ref


def add(c, aid, ref, save=_save_doc):
    """Into an area; gives the ref it's kept as (a Feed item is saved to the Library first)."""
    if not c.execute("SELECT 1 FROM areas WHERE id = ?", (aid,)).fetchone():
        raise KeyError(aid)
    if not _valid_ref(c, ref):
        raise ValueError("Nothing to add")
    ref = kept(c, ref, save)
    last = c.execute("SELECT COALESCE(MAX(ord), 0) FROM area_items WHERE area_id = ?", (aid,)).fetchone()[0]
    c.execute("INSERT INTO area_items (area_id, ref, ord, added) VALUES (?, ?, ?, ?) ON CONFLICT(area_id, ref) DO NOTHING",
              (aid, ref, last + 1, _now()))
    c.commit()
    return ref


def remove(c, aid, ref, bad=False):
    """Out of the area. Not a good source (bad): the helper keeps it as set aside, so it isn't suggested
    again; gives that row's id, so Undo can take it back (unskip)."""
    k = kept(c, ref)
    sid = None
    if bad:
        x = _resolve(c, k)
        if x:
            kind, _, key = k.partition(":")
            row = (c.execute("SELECT url FROM docs WHERE id = ?", (key,)).fetchone() if kind == "doc" else
                   c.execute("SELECT url FROM feeds WHERE id = ?", (key,)).fetchone() if kind == "feed" else None)
            url = key if kind == "url" else (row[0] if row else "") or ""
            sid = "s" + secrets.token_hex(5)
            c.execute("INSERT INTO area_suggest (id, area_id, kind, title, by, url, state, made) VALUES (?, ?, ?, ?, ?, ?, 'skipped', ?)",
                      (sid, aid, x["kind"] if x["kind"] in KINDS else "article", x["title"], x["by"], url, _now()))
    c.execute("DELETE FROM area_items WHERE area_id = ? AND ref IN (?, ?)", (aid, ref, k))
    c.commit()
    return sid


def unskip(c, sid):
    """Undo a "not a good source": the helper may suggest it again."""
    c.execute("DELETE FROM area_suggest WHERE id = ? AND state = 'skipped'", (sid,))
    c.commit()


def order_items(c, aid, refs):
    for i, ref in enumerate(refs):
        c.execute("UPDATE area_items SET ord = ? WHERE area_id = ? AND ref = ?", (i + 1, aid, ref))
    c.commit()


def _hm(sec):
    m = int(round((sec or 0) / 60))
    return (f"{m // 60} h {m % 60} min" if m % 60 else f"{m // 60} h") if m >= 60 else f"{m} min"


def _resolve(c, ref):
    """One thing in an area, as the page shows it, or None when it's gone from Daf."""
    kind, _, key = ref.partition(":")
    if kind == "url":                                     # saved while the Library was away: the doc, once it's there
        d = c.execute("SELECT id FROM docs WHERE url = ? AND COALESCE(status, '') != 'deleted' ORDER BY added DESC LIMIT 1", (key,)).fetchone()
        if d:
            kind, key = "doc", d["id"]
        else:
            return {"ref": ref, "kind": "article", "title": urllib.parse.urlparse(key).netloc or key, "by": "", "len": "",
                    "st": "Saving", "pct": 0, "pic": "", "go": ""}
    if kind == "want":
        title, _, by = key.partition("|")
        b = c.execute("SELECT id FROM books WHERE kind = 'book' AND lower(title) LIKE ? LIMIT 1", (title.strip().lower() + "%",)).fetchone()
        if not b:
            return {"ref": ref, "kind": "book", "title": title.strip(), "by": by.strip(), "len": "", "st": "Wanted", "pct": 0, "pic": "", "go": ""}
        kind, key = "book", b["id"]
    if kind == "book":
        b = c.execute("SELECT * FROM books WHERE id = ?", (key,)).fetchone()
        if not b or b["private"]:
            return None
        pct = max(float(b["progress"] or 0), float(b["audio_pct"] or 0))
        done = (b["status"] or "").lower() in ("read", "finished", "done") or pct >= 99.5
        return {"ref": ref, "kind": "book", "title": b["title"], "by": b["author"] or "", "len": "",
                "st": "Done" if done else (f"{round(pct)}%" if pct >= 1 else "New"), "pct": 100 if done else pct,
                "pic": "/api/cover/" + urllib.parse.quote(b["id"], safe=""), "go": "book/" + urllib.parse.quote(b["id"], safe=""), "id": b["id"]}
    if kind == "doc":
        d = c.execute("SELECT * FROM docs WHERE id = ?", (key,)).fetchone()
        if not d or d["status"] == "deleted":
            return None
        pct = float(d["progress"] or 0)                    # (docs keep it out of 100)
        done = d["status"] == "archive" or pct >= 95
        k = d["kind"] if d["kind"] in ("video", "podcast", "pdf") else "article"
        ln = _hm(d["duration"]) if d["duration"] else (f"{max(1, round((d['words'] or 0) / 230))} min" if d["words"] else "")
        return {"ref": ref, "kind": "video" if k == "video" else "article", "title": d["title"] or d["url"] or "", "by": d["source"] or d["author"] or "",
                "len": ln, "st": "Done" if done else (f"{round(pct)}%" if pct >= 1 else "New"), "pct": 100 if done else pct,
                "pic": d["thumb"] or "", "go": "read/" + urllib.parse.quote(d["id"], safe=""), "id": d["id"]}
    if kind == "feed":
        f = c.execute("SELECT * FROM feeds WHERE id = ?", (key,)).fetchone()
        if not f:
            return None
        n = c.execute("SELECT COUNT(*) FROM docs WHERE where_ = 'feed' AND status = 'unseen' AND feed = ?", (key,)).fetchone()[0]
        return {"ref": ref, "kind": "feed", "title": f["title"] or f["url"], "by": urllib.parse.urlparse(f["site"] or f["url"]).netloc,
                "len": "", "st": f"{n} new" if n else "", "pct": 0, "new": n, "pic": "", "go": "feed/" + urllib.parse.quote(key, safe=""), "id": key}
    return None


def _items(c, aid):
    rows = c.execute("SELECT ref FROM area_items WHERE area_id = ? ORDER BY ord, added", (aid,)).fetchall()
    return [x for x in (_resolve(c, r["ref"]) for r in rows) if x]


def _month_seconds(c, ids):
    if not ids:
        return 0
    t = time.localtime()
    start = int(time.mktime((t.tm_year, t.tm_mon, 1, 0, 0, 0, 0, 0, -1)))
    q = ",".join("?" * len(ids))
    return c.execute(f"SELECT COALESCE(SUM(seconds), 0) FROM sessions WHERE item IN ({q}) AND start >= ? AND private = 0",
                     (*ids, start)).fetchone()[0]


def _summary(c, a):
    items = _items(c, a["id"])
    count = {k: sum(1 for x in items if x["kind"] == k) for k in KINDS}
    words = {"book": ("book", "books"), "article": ("article", "articles"), "video": ("video", "videos"), "feed": ("feed", "feeds")}
    counts = " · ".join(f"{n} {words[k][n != 1]}" for k, n in count.items() if n)
    secs = _month_seconds(c, [x["id"] for x in items if x.get("id")])
    things = [x for x in items if x["kind"] != "feed"]          # (a feed is followed, never finished)
    return {"id": a["id"], "name": a["name"], "goal": a["goal"] or "", "color": a["color"] or COLORS[0], "suggest": bool(a["suggest"]),
            "counts": counts, "n": len(things), "done": sum(1 for x in things if x["st"] == "Done"),
            "month": _hm(secs) + " this month" if secs >= 60 else "",
            "pics": [x["pic"] for x in items if x["pic"]][:4], "tiles": [x["title"] for x in items if not x["pic"]][:4]}


def list_areas(c):
    return [_summary(c, a) for a in c.execute("SELECT * FROM areas ORDER BY ord, created")]


def page(c, aid):
    a = c.execute("SELECT * FROM areas WHERE id = ?", (aid,)).fetchone()
    if not a:
        raise KeyError(aid)
    items = _items(c, aid)
    things = [x for x in items if x["kind"] != "feed"]
    ids = [x["id"] for x in things if x.get("id")]
    hls = []
    if ids:
        q = ",".join("?" * len(ids))
        for h in c.execute(f"SELECT h.id, h.text, h.note, h.color, h.book_id, COALESCE(b.title, d.title) AS title FROM highlights h "
                           f"LEFT JOIN books b ON b.id = h.book_id LEFT JOIN docs d ON d.id = h.book_id "
                           f"WHERE h.deleted = 0 AND h.book_id IN ({q}) AND COALESCE(b.private, 0) = 0 ORDER BY h.created DESC LIMIT 40", ids):
            hls.append(dict(h))
    return {"area": _summary(c, a), "items": things, "feeds": [x for x in items if x["kind"] == "feed"],
            "next": [x for x in things if x["st"] not in ("Done",)][:5], "highlights": hls,
            "suggestions": suggestions(c, aid), "looking": aid in _looking}


def areas_of(c, refs):
    """The areas a thing is in (for its Add to an area); for several, the areas they're all in."""
    refs = [kept(c, r) for r in ([refs] if isinstance(refs, str) else refs) if r]
    if not refs:
        return []
    ins = [{r[0] for r in c.execute("SELECT area_id FROM area_items WHERE ref = ?", (ref,))} for ref in refs]
    return sorted(set.intersection(*ins))


# ---- the helper ----------------------------------------------------------------------------------

_looking = {}           # area id -> when its look began, while the model is being asked
_errors = {}            # area id -> what went wrong last time


PROMPT = """Someone is learning a subject with a reading app that keeps books, saved articles and videos, and feeds.
Subject: {name}
{goal}They already have:
{have}
{skip}Suggest {n} more things to add, a mix of books, articles, videos and feeds (blogs, newsletters or sites with an RSS feed), the
best-known and most trusted for a learner at their stage, and none they already have or set aside.

Reply with JSON only, no prose: a list of objects with "kind" ("book", "article", "video" or "feed"), "title", "by" (the author,
site or channel) and "url" (for an article, video or feed: its address; your best guess is fine, each one is checked
before it's shown, so give "" only when you have no idea)."""


def _ask_model(name, goal, have, skipped, n=6):
    text = PROMPT.format(name=name, goal=f"Their goal: {goal}\n" if goal else "",
                         have="\n".join(f"- {t}" for t in have) or "- nothing yet",
                         skip=("Set aside already:\n" + "\n".join(f"- {t}" for t in skipped) + "\n") if skipped else "", n=n)
    out = ai.run(text, timeout=240)
    m = re.search(r"\[.*\]", out, re.S)
    if not m:
        raise RuntimeError("The model's answer had no list in it")
    got = json.loads(m.group(0))
    keep = []
    for g in got if isinstance(got, list) else []:
        if not isinstance(g, dict) or g.get("kind") not in KINDS or not str(g.get("title") or "").strip():
            continue
        keep.append({"kind": g["kind"], "title": str(g["title"]).strip()[:200], "by": str(g.get("by") or "").strip()[:120],
                     "url": str(g.get("url") or "").strip()})
    return keep


def _opens(url):
    """True when the address answers (the model's links are only offered once they do)."""
    if not re.match(r"^https?://\S+$", url or ""):
        return False
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status < 400
    except Exception:  # noqa: BLE001
        return False


def _video(title, by):
    """A real video for a suggested one: the Invidious instance's search (the Edition's), when there is one."""
    base = os.environ.get("DAF_INVIDIOUS_URL", "")
    if not base:
        return ""
    try:
        q = urllib.parse.urlencode({"q": f"{title} {by}".strip(), "type": "video"})
        with urllib.request.urlopen(urllib.request.Request(f"{base.rstrip('/')}/api/v1/search?{q}", headers={"User-Agent": UA}), timeout=12) as r:
            res = json.loads(r.read().decode("utf-8"))
        v = next((x for x in res if x.get("type") == "video" and x.get("videoId")), None)
        return f"https://www.youtube.com/watch?v={v['videoId']}" if v else ""
    except Exception:  # noqa: BLE001
        return ""


def _checked(s):
    """The suggestion with a link that opens, or None (a book needs none: it's looked up when added)."""
    if s["kind"] == "book":
        s["url"] = ""
        return s
    if s["kind"] == "video":
        s["url"] = _video(s["title"], s["by"]) or s["url"]
        if re.search(r"youtube\.com/watch|youtu\.be/", s["url"]):      # YouTube answers for any watch address: ask its oEmbed
            return s if _opens("https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(s["url"], safe="")) else None
    return s if _opens(s["url"]) else None


def suggest_now(c, aid, ask=None, check=None):
    """Ask, check and keep the helper's suggestions for an area (runs in the background: suggest_start)."""
    a = c.execute("SELECT * FROM areas WHERE id = ?", (aid,)).fetchone()
    if not a:
        return []
    have = [x["title"] for x in _items(c, aid)]
    old = c.execute("SELECT title, state FROM area_suggest WHERE area_id = ?", (aid,)).fetchall()
    skipped = [r["title"] for r in old if r["state"] == "skipped"]
    seen = {r["title"].lower() for r in old} | {t.lower() for t in have}
    got = (ask or _ask_model)(a["name"], a["goal"] or "", have + [r["title"] for r in old if r["state"] == "new"], skipped)
    kept = []
    for s in got:
        if s["title"].lower() in seen:
            continue
        s = (check or _checked)(s)
        if not s:
            continue
        seen.add(s["title"].lower())
        c.execute("INSERT INTO area_suggest (id, area_id, kind, title, by, url, state, made) VALUES (?, ?, ?, ?, ?, ?, 'new', ?)",
                  ("s" + secrets.token_hex(5), aid, s["kind"], s["title"], s["by"], s["url"], _now()))
        kept.append(s)
    c.commit()
    return kept


def suggest_start(aid):
    """Look for suggestions in the background, once at a time per area."""
    if aid in _looking:
        return False
    _looking[aid] = _now()
    _errors.pop(aid, None)

    def go():
        c = db.connect()
        try:
            suggest_now(c, aid)
        except Exception as e:  # noqa: BLE001
            _errors[aid] = str(e)[:300]
        finally:
            c.close()
            _looking.pop(aid, None)
    threading.Thread(target=go, daemon=True).start()
    return True


def suggestions(c, aid):
    return [dict(r) for r in c.execute("SELECT id, kind, title, by, url FROM area_suggest WHERE area_id = ? AND state = 'new' ORDER BY made, rowid", (aid,))]


def error(aid):
    return _errors.get(aid, "")


def skip(c, sid):
    c.execute("UPDATE area_suggest SET state = 'skipped' WHERE id = ?", (sid,))
    c.commit()


def take(c, sid, save_link=None, follow=None):
    """Add a suggestion to its area: an article or a video is saved to the Library, a feed followed, a book wanted."""
    s = c.execute("SELECT * FROM area_suggest WHERE id = ?", (sid,)).fetchone()
    if not s:
        raise KeyError(sid)
    if s["kind"] == "book":
        ref = "want:" + s["title"] + ("|" + s["by"] if s["by"] else "")
    elif s["kind"] == "feed":
        ref = "feed:" + (follow or _follow)(c, s["url"])
    else:
        did = (save_link or _save_link)(c, s["url"], s["title"])
        ref = ("doc:" + did) if did else ("url:" + s["url"])
    add(c, s["area_id"], ref)
    c.execute("UPDATE area_suggest SET state = 'added' WHERE id = ?", (sid,))
    c.commit()
    return ref


def _save_link(c, url, title=None):
    """The Library's doc for a link (saved now), or None when the Library is away (it waits in the inbox)."""
    from . import pages, phone
    try:
        return pages.save_page(c, url, title or None)[0]
    except Exception:  # noqa: BLE001
        phone.save_shared(c, url, title or "", "")
        return None


def _follow(c, url):
    """Follow a feed and give its id."""
    from .sources import feedsrc, rss
    src = feedsrc.get()
    if src is rss or getattr(src, "__name__", "") == rss.__name__:
        return rss.follow(url, None, c)[0]
    name = src.subscribe(url, None, conn=c)
    r = c.execute("SELECT id FROM feeds WHERE title = ? ORDER BY added DESC LIMIT 1", (name,)).fetchone()
    if not r:
        raise ValueError("Followed, but Daf doesn't read that feed itself yet")
    return r["id"]
