"""The browser extension's API (extension/): highlight on the live page, and the page goes to the
Library with its highlights, so they show in the reading view, the daily review and the vault
like any other Daf highlight.

Every route takes a device token (`Authorization: Bearer`, the device "browser" made in
Preferences → Account). app.py includes this router near its end, after `conn` and `device`
exist, so import daf.app (not this module) first.

A highlight made on a web page has no block in Daf's text; its pos is the text quote
{q, pre, suf} (the words, and up to 32 characters either side), and the reading view finds it
by its words (reader.js `findPos`), the way it places Karakeep's.
"""
import hashlib
import json
import re

from fastapi import APIRouter, Depends, HTTPException, Request

from . import config, pages, reader, review, vaultnotes
from .app import conn, device
from .pages import find_doc

router = APIRouter(prefix="/api/web", dependencies=[Depends(device)])

COLORS = reader.COLORS


async def _body(request: Request):
    """The JSON object sent, or {}. A dependency, so the routes are plain defs on worker threads:
    saving a page waits on Karakeep and reads the page's article, which mustn't hold up Daf."""
    try:
        b = await request.json()
    except ValueError:
        return {}
    return b if isinstance(b, dict) else {}


def _check_url(b):
    url = str(b.get("url") or "").strip()
    if not re.match(r"^https?://[^\s/]+", url) or len(url) > 4000:
        raise HTTPException(400, "A web page address starting with http:// or https://, please")
    return url


def save_page(c, url, title=None, html=None):
    """pages.save_page, with the page's text when the browser sent it (the page as you see it,
    paywall and all). Returns (doc id, saved, words kept or None)."""
    try:
        doc_id, saved = pages.save_page(c, url, title)
    except Exception as e:  # noqa: BLE001 - Karakeep said no
        raise HTTPException(502, f"The Library didn't take the page: {e}")
    from . import social
    words = pages.keep_text(c, doc_id, html, url) if isinstance(html, str) and html and not social.is_reel(url) else None
    return doc_id, saved, words


def _quote(h):
    try:
        p = json.loads(h["pos"]) if h["pos"] else {}
    except ValueError:
        p = {}
    if isinstance(p, dict) and p.get("q"):
        return {"exact": p["q"], "prefix": p.get("pre") or "", "suffix": p.get("suf") or ""}
    return {"exact": h["text"] or "", "prefix": "", "suffix": ""}   # made in Daf or Karakeep: found by its words


def page_highlights(c, doc_id):
    rows = c.execute("SELECT h.id, h.text, h.pos, h.color, h.source, h.note, s.user_note, s.tags FROM highlights h "
                     "LEFT JOIN review_state s ON s.hl_id = h.id WHERE h.book_id = ? AND h.deleted = 0 ORDER BY h.created",
                     (doc_id,)).fetchall()
    return [{"id": r["id"], "text": r["text"], "note": r["user_note"] or r["note"] or None, "color": r["color"] or "yellow",
             "source": r["source"], "tags": json.loads(r["tags"]) if r["tags"] else [], "quote": _quote(r)}
            for r in rows if (r["text"] or "").strip()]


def _vault(c, s, book_id, source):
    vaultnotes.write_for(c, s, book_id)


@router.post("/page")
def post_page(b=Depends(_body), c=Depends(conn)):
    """{url}: the doc saved from this page and its highlights, or doc_id null. A POST, so the
    address of every page the browser shows stays out of the access log."""
    url = _check_url(b)
    d = find_doc(c, url)
    if not d:
        return {"doc_id": None, "highlights": []}
    return {"doc_id": d["id"], "where": "deleted" if d["status"] == "deleted" else d["where_"], "title": d["title"],
            "words": c.execute("SELECT words FROM docs WHERE id = ?", (d["id"],)).fetchone()[0], "highlights": page_highlights(c, d["id"])}


@router.post("/save")
def post_save(b=Depends(_body), c=Depends(conn)):
    """{url, title, html?}: the page to the Library, without a highlight. html is the page as the
    browser shows it; its text replaces Daf's copy when it has more (a paywall's teaser)."""
    url = _check_url(b)
    doc_id, saved, words = save_page(c, url, b.get("title"), b.get("html"))
    return {"doc_id": doc_id, "saved": saved, "words": words, "highlights": len(page_highlights(c, doc_id))}


@router.post("/highlight")
def post_highlight(b=Depends(_body), c=Depends(conn)):
    """{url, title, text, prefix, suffix, note?, color?, html?}: saves the page if it isn't in Daf
    yet (with its text, as /save), then adds the highlight (source 'daf'), placed by its quote."""
    url = _check_url(b)
    text = re.sub(r"\n{3,}", "\n\n", str(b.get("text") or "").replace("\r", "")).strip()[:10000]
    if not text:
        raise HTTPException(400, "Nothing selected")
    pre, suf = str(b.get("prefix") or "")[-200:], str(b.get("suffix") or "")[:200]
    color = b.get("color") or "yellow"
    if color not in COLORS:
        raise HTTPException(400, "yellow, green, blue, pink or purple")
    note = str(b.get("note") or "").strip() or None
    s = config.load_settings()
    doc_id, saved, _ = save_page(c, url, b.get("title"), b.get("html"))
    # reader.add_highlight names a highlight after its block and start; a web page has neither, so
    # the words just before it stand in for them: the same words twice on a page are two highlights.
    where = "q:" + hashlib.sha1(pre.encode()).hexdigest()[:12]
    hid = reader.add_highlight(c, s, doc_id, None, where, None, text, note=note, color=None if color == "yellow" else color)
    c.execute("UPDATE highlights SET pos = ? WHERE id = ?", (json.dumps({"q": text, "pre": pre, "suf": suf}, ensure_ascii=False), hid))
    if note and review.add_tags(c, hid, review.dot_tags(note)):      # ".tag" in the note tags it, as in Daf
        vaultnotes.write_article(c, s, doc_id)
    return {"id": hid, "doc_id": doc_id, "saved": saved}


def _own(c, hl_id):
    h = c.execute("SELECT h.book_id, h.source FROM highlights h JOIN docs d ON d.id = h.book_id "
                  "WHERE h.id = ? AND h.deleted = 0", (hl_id,)).fetchone()
    if not h:
        raise HTTPException(404, "That highlight isn't in Daf any more")
    return h


@router.get("/instagram")
def get_instagram(c=Depends(conn)):
    """Whether this browser should keep Daf signed in to Instagram (Preferences → Instagram), and
    which session Daf has: a hash of it, never the session itself."""
    from . import social
    st = social.status(c)
    return {"want": st["from_browser"], "hash": st["hash"], "expired": bool(st["expired"])}


@router.post("/instagram")
def post_instagram(b=Depends(_body), c=Depends(conn), name=Depends(device)):
    """{cookies}: instagram.com's cookies from the browser, for the reels (social.py)."""
    from . import social
    if not social.status(c)["from_browser"]:
        raise HTTPException(403, "Daf isn't taking Instagram's sign-in from the browser (Preferences → Instagram)")
    try:
        st = social.save_cookies(c, b, name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "restarted": st.get("restarted", 0), "same": bool(st.get("same"))}


@router.get("/tags")
def get_tags(c=Depends(conn)):
    """Every highlight tag in Daf, the most used first: the note box suggests them."""
    return {"tags": review.all_tags(c)}


@router.put("/highlight/{hl_id}")
def put_highlight(hl_id: str, b=Depends(_body), c=Depends(conn)):
    """{note?, color?, tags?} for a highlight on a saved page. Returns its tags as they now are
    (".tag" in a note adds one)."""
    h = _own(c, hl_id)
    if "color" in b:
        color = b.get("color") or "yellow"
        if color not in COLORS:
            raise HTTPException(400, "yellow, green, blue, pink or purple")
        c.execute("UPDATE highlights SET color = ? WHERE id = ?", (None if color == "yellow" else color, hl_id))
    if "tags" in b:
        if not isinstance(b["tags"], list):
            raise HTTPException(400, "tags: a list")
        review.set_tags(c, hl_id, b["tags"])
    if "note" in b:
        note = str(b.get("note") or "")
        review.set_note(c, hl_id, note)
        review.add_tags(c, hl_id, review.dot_tags(note))
    if "note" in b or "tags" in b:
        _vault(c, config.load_settings(), h["book_id"], h["source"])
    t = c.execute("SELECT tags FROM review_state WHERE hl_id = ?", (hl_id,)).fetchone()
    return {"ok": True, "tags": json.loads(t[0]) if t and t[0] else []}


@router.delete("/highlight/{hl_id}")
def delete_highlight(hl_id: str, c=Depends(conn)):
    h = _own(c, hl_id)
    if h["source"] != "daf":
        raise HTTPException(400, "Only highlights made in Daf or on the web can be removed here")
    reader.remove_highlight(c, config.load_settings(), hl_id)
    return {"ok": True}
