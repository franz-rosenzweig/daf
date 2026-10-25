"""Reels: an Instagram reel (or a video post) saved to the Library is kept whole in Daf.

A reel shared to Daf (the phone's share menu, the browser extension, a pasted link) is a video doc
like a YouTube one, but nothing of it stays on Instagram's side: the "reel" job downloads the video
with yt-dlp (STATE/media/<id>.mp4, played from Daf), keeps its picture, its caption and the account
it's from, and transcribes what's said with faster-whisper. The doc's text is the caption, then the
transcript with its timestamps, so it highlights, searches and goes to the review like any other.

Instagram shows almost nothing without a signed-in session, so Daf keeps one: Nathan's Instagram
cookies in STATE/instagram/cookies.txt (mode 600, never logged, never in the repo). They arrive from
his own browser (the extension sends them when he's on instagram.com and they've changed, if
Preferences → Instagram says so) or from the apps' Sign in to Instagram. When Instagram turns the
session away, the job says so, the doc waits, and the next cookies that arrive start it again.
"""
import hashlib
import json
import logging
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

from . import config

log = logging.getLogger("daf.social")

MEDIA = config.STATE / "media"
IG_DIR = config.STATE / "instagram"
IG_COOKIES = IG_DIR / "cookies.txt"
MAX_MB = 400
LOGIN_ERROR = "Instagram needs you to sign in again (Preferences → Instagram)"

_IG = re.compile(r"^https?://(?:www\.|m\.)?instagram\.com/(?:[\w.]+/)?(reels?|p|tv)/([\w-]{5,})", re.I)


def instagram_code(url):
    m = _IG.match((url or "").strip())
    return m.group(2) if m else None


def is_reel(url):
    return instagram_code(url) is not None


def canonical(url):
    """https://www.instagram.com/reel/<code>/ for any of its addresses (/reels/, /p/, a user's path,
    the share link's ?igsh=…), so the same reel is found again however it was shared."""
    m = _IG.match((url or "").strip())
    if not m:
        return url
    kind = "p" if m.group(1).lower() == "p" else "reel"
    return f"https://www.instagram.com/{kind}/{m.group(2)}/"


WAITING = ("SELECT id FROM docs WHERE kind = 'video' AND url LIKE '%instagram.com/%' AND status != 'deleted' "
           "AND id NOT IN (SELECT id FROM doc_content)")


def media_path(doc_id):
    return MEDIA / (re.sub(r"[^\w-]", "_", doc_id) + ".mp4")


# ---- the signed-in session --------------------------------------------------------------------

def _kv(conn, k, v=None):
    if v is None:
        row = conn.execute("SELECT v FROM kv WHERE k = ?", (k,)).fetchone()
        return json.loads(row[0]) if row and row[0] else {}
    conn.execute("INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)", (k, json.dumps(v)))
    return v


def _parse_cookies(b):
    """[{name, value, domain?, path?, expires?, secure?}] from a browser's cookie store, or a Cookie:
    header ("a=1; b=2") from an app's web view. Only instagram.com's."""
    out = []
    if isinstance(b.get("cookies"), list):
        for c in b["cookies"]:
            if not isinstance(c, dict) or not c.get("name"):
                continue
            dom = str(c.get("domain") or ".instagram.com")
            if "instagram.com" not in dom:
                continue
            out.append({"name": str(c["name"]), "value": str(c.get("value") or ""), "domain": dom if dom.startswith(".") else "." + dom.lstrip("."),
                        "path": str(c.get("path") or "/"), "expires": int(float(c.get("expires") or c.get("expirationDate") or 0) or time.time() + 365 * 86400),
                        "secure": bool(c.get("secure", True))})
    elif isinstance(b.get("cookie_header"), str):
        for part in b["cookie_header"].split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                out.append({"name": k.strip(), "value": v.strip(), "domain": ".instagram.com", "path": "/",
                            "expires": int(time.time() + 365 * 86400), "secure": True})
    return [c for c in out if c["name"] and "\t" not in c["value"] and "\n" not in c["value"]]


def session_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()[:16] if value else None


def save_cookies(conn, b, by):
    """Keeps Instagram's cookies for yt-dlp (Netscape format) and starts the reels that waited for them."""
    cookies = _parse_cookies(b)
    sid = next((c["value"] for c in cookies if c["name"] == "sessionid" and c["value"]), None)
    if not sid:
        raise ValueError("Those aren't a signed-in Instagram session (no sessionid). Sign in to Instagram first.")
    IG_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(IG_DIR, 0o700)
    lines = ["# Netscape HTTP Cookie File", "# Instagram, for Daf's reels (daf/social.py). Kept private."]
    for c in cookies:
        lines.append("\t".join([c["domain"], "TRUE", c["path"], "TRUE" if c["secure"] else "FALSE", str(c["expires"]), c["name"], c["value"]]))
    tmp = IG_COOKIES.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n")
    os.chmod(tmp, 0o600)
    tmp.replace(IG_COOKIES)
    user = next((c["value"] for c in cookies if c["name"] == "ds_user_id"), None)
    st = _kv(conn, "instagram")
    if st.get("expired") and st.get("hash") == session_hash(sid) and not session_ok():
        return status(conn) | {"restarted": 0, "same": True}       # the lapsed session again: nothing to retry
    st.update({"hash": session_hash(sid), "user": user, "by": by, "updated": int(time.time()), "expired": None})
    _kv(conn, "instagram", st)
    from . import media
    waiting = conn.execute(WAITING).fetchall()               # every reel not kept yet, however long it waited
    for (ref,) in waiting:
        media.queue(conn, "reel", ref)
    return status(conn) | {"restarted": len(waiting)}


def forget(conn):
    IG_COOKIES.unlink(missing_ok=True)
    st = _kv(conn, "instagram")
    st.update({"hash": None, "user": None, "updated": None, "expired": None})
    _kv(conn, "instagram", st)
    return status(conn)


def status(conn):
    st = _kv(conn, "instagram")
    have = IG_COOKIES.exists()
    s = config.load_settings()
    return {"connected": have and not st.get("expired"), "signed_in": have, "expired": st.get("expired"),
            "updated": st.get("updated") if have else None, "by": st.get("by") if have else None,
            "from_browser": bool((s.get("instagram") or {}).get("from_browser")),
            "hash": st.get("hash") if have else None,
            "waiting": len(conn.execute(WAITING).fetchall())}


def _mark_expired():
    from . import db
    with db.session() as conn:
        st = _kv(conn, "instagram")
        if not st.get("expired"):
            st["expired"] = int(time.time())
            _kv(conn, "instagram", st)


def _login_trouble(err):
    # a signed-out session gets the sign-in page where JSON should be ("Failed to parse JSON")
    return bool(re.search(r"log ?in|rate-limit|checkpoint|cookies|not available|parse JSON|HTTP Error (401|403|429)", err or "", re.I))


def session_ok():
    """Whether Instagram still takes the kept session: its account page, which sends a signed-out
    visitor to the sign-in page. (Its "not available" error is the same for a reel that's gone and a
    session that's lapsed.)"""
    import urllib.request
    try:
        jar = {}
        for line in IG_COOKIES.read_text().splitlines():
            p = line.split("\t")
            if not line.startswith("#") and len(p) == 7:
                jar[p[5]] = p[6]
        req = urllib.request.Request("https://www.instagram.com/accounts/edit/", headers={
            "Cookie": "; ".join(f"{k}={v}" for k, v in jar.items()),
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:140.0) Gecko/20100101 Firefox/140.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return "/accounts/login" not in r.geturl() and r.status == 200
    except Exception:  # noqa: BLE001 - no answer: take it as lapsed
        return False


# ---- the reel job -----------------------------------------------------------------------------

def fetch(doc_id):
    """The "reel" job: the video, its picture, caption and account, then its transcript."""
    from . import db, media, pages
    with db.session() as conn:
        d = conn.execute("SELECT * FROM docs WHERE id = ?", (doc_id,)).fetchone()
    if not d or d["status"] == "deleted" or not is_reel(d["url"]):
        return
    if not IG_COOKIES.exists():
        raise RuntimeError(LOGIN_ERROR)
    MEDIA.mkdir(parents=True, exist_ok=True)
    out = media_path(doc_id)
    with tempfile.TemporaryDirectory() as tmp:
        jar = Path(tmp) / "cookies.txt"                         # yt-dlp writes its jar back: a copy, so a
        jar.write_text(IG_COOKIES.read_text())                  # renewal arriving now isn't overwritten
        os.chmod(jar, 0o600)
        r = subprocess.run(media.YTDLP + ["--cookies", str(jar), "--no-playlist", "--write-info-json",
                                          "-f", "bv*[height<=1280]+ba/b[height<=1280]/bv*+ba/b", "--merge-output-format", "mp4",
                                          "--max-filesize", f"{MAX_MB}M", "-o", f"{tmp}/v.%(ext)s", canonical(d["url"])],
                           capture_output=True, text=True, timeout=900)
        info = {}
        for f in Path(tmp).glob("*.info.json"):
            info = json.loads(f.read_text())
        vids = [f for f in Path(tmp).iterdir() if f.suffix in (".mp4", ".webm", ".mkv", ".mov") and f.stat().st_size > 0]
        if r.returncode != 0 and not vids and not info:
            err = (r.stderr or "").strip().splitlines()
            err = err[-1] if err else "yt-dlp failed"
            if _login_trouble(err) and not session_ok():
                _mark_expired()
                raise RuntimeError(LOGIN_ERROR)
            err = re.sub(r"^ERROR:\s*(\[\w+\]\s*[\w-]+:\s*)?", "", err)
            err = re.split(r";\s*please report|\.\s*Use --cookies", err)[0].strip(" ,.")
            raise RuntimeError("Instagram didn't give the reel (deleted, or a private account?): " + err[:200])
        if vids:
            vids[0].replace(out)
    caption = (info.get("description") or "").strip()
    who = info.get("channel") or info.get("uploader_id") or info.get("uploader") or ""
    who = ("@" + who.lstrip("@")) if who and not who.startswith("@") and " " not in who else who
    first = re.sub(r"\s+", " ", caption.split("\n", 1)[0]).strip()
    title = (first[:117] + "…") if len(first) > 120 else first
    title = title or (f"Reel by {who}" if who else "Instagram reel")
    thumb = pages.keep_thumb(info["thumbnail"]) if info.get("thumbnail") else None
    blocks = []
    if caption:
        for para in [p.strip() for p in re.split(r"\n\s*\n", caption) if p.strip()]:
            blocks.append({"t": "p", "x": para, "h": _esc(para).replace("\n", "<br>")})
    lines = []
    if out.exists():
        try:
            res = media.whisper(str(out))
            lines = [{"ts": int(s["start"]), "spk": None, "x": s["text"]} for s in res.get("segments", []) if s.get("text", "").strip()]
        except Exception as e:  # noqa: BLE001 - the video and caption are still worth keeping
            log.warning("reel %s: no transcript: %s", doc_id, e)
    if lines:
        blocks.append({"t": "h3", "x": "Transcript", "h": "Transcript"})
        blocks += media._blocks_from_lines(lines, [])
    with db.session() as conn:
        conn.execute("INSERT OR REPLACE INTO doc_content (id, blocks, fetched) VALUES (?, ?, ?)", (doc_id, json.dumps(blocks), int(time.time())))
        conn.execute("UPDATE docs SET kind = 'video', url = ?, words = ?, duration = COALESCE(?, duration), "
                     "title = CASE WHEN title IS NULL OR title = '' OR title = url THEN ? ELSE title END, "
                     "author = COALESCE(NULLIF(author, ''), ?), summary = COALESCE(NULLIF(summary, ''), ?), "
                     "thumb = COALESCE(?, thumb), published = COALESCE(published, ?), source = 'instagram.com' WHERE id = ?",
                     (canonical(d["url"]), sum(len(b["x"].split()) for b in blocks), info.get("duration"), title, who,
                      caption[:280], thumb, info.get("timestamp"), doc_id))
        media.queue(conn, "tags", doc_id)
    return len(blocks)


def _esc(s):
    import html
    return html.escape(s)


def prune(conn):
    """Videos whose doc is gone."""
    if not MEDIA.exists():
        return
    have = {re.sub(r"[^\w-]", "_", r[0]) for r in conn.execute("SELECT id FROM docs WHERE kind = 'video'")}
    for f in MEDIA.glob("*.mp4"):
        if f.stem not in have and time.time() - f.stat().st_mtime > 86400:
            f.unlink(missing_ok=True)
