"""Reels: an Instagram reel (or a video post) saved to the Library.

Daf's server never talks to Instagram. Instagram takes a sign-in used from a server for a stolen
one and locks the account, so Daf keeps no Instagram sign-in and fetches nothing from it: a reel
shared to Daf (the phone's share menu, the browser extension, a pasted link) is kept as its link,
one doc per reel however it was shared, and opens on Instagram. A reel Daf kept whole before this
(STATE/media/<id>.mp4, its caption and transcript) still plays from Daf.
"""
import re
import time

from . import config

MEDIA = config.STATE / "media"
IG_DIR = config.STATE / "instagram"      # where the sign-in used to be kept: forget() empties it
OFF = "Daf doesn't fetch from Instagram"

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


def media_path(doc_id):
    return MEDIA / (re.sub(r"[^\w-]", "_", doc_id) + ".mp4")


def forget(conn):
    """Whatever Instagram sign-in Daf once kept, gone."""
    if IG_DIR.exists():
        for f in IG_DIR.iterdir():
            f.unlink(missing_ok=True)
    conn.execute("DELETE FROM kv WHERE k = 'instagram'")
    return status(conn)


def status(conn):
    return {"connected": False, "signed_in": False, "expired": None, "updated": None, "by": None,
            "from_browser": False, "hash": None, "waiting": 0, "off": True}


def fetch(doc_id):
    """The old "reel" job: a reel waits as its link."""
    raise RuntimeError(OFF)


def prune(conn):
    """Videos whose doc is gone."""
    if not MEDIA.exists():
        return
    have = {re.sub(r"[^\w-]", "_", r[0]) for r in conn.execute("SELECT id FROM docs WHERE kind = 'video'")}
    for f in MEDIA.glob("*.mp4"):
        if f.stem not in have and time.time() - f.stat().st_mtime > 86400:
            f.unlink(missing_ok=True)
