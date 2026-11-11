"""Podcast episodes kept on the server: Download, on a show's page and on each episode's row.

A show says what Daf keeps of it (kv "poddl:<feed>"): "off" (nothing by itself), "new" (every episode
that comes out after you chose it), or "all" (every episode its feed has). One episode can also be kept,
or let go, from its row, whatever the show says.

A kept episode plays from Daf's own copy (episodes.state gives the player /api/podcasts/kept), so it
starts and seeks at once and is still there after the feed drops it; and it's transcribed from that copy
instead of being fetched again (episodes.transcribe).

The files are in STATE/episodes, one an episode, named by a hash of its address. They come one at a time
on their own worker (media.py's "files" lane), and none while the disk has less than MIN_FREE left on it.
After each day's feed reading (sync.py), plan() asks for what the shows' choices want that isn't kept yet.
"""
import hashlib
import json
import logging
import mimetypes
import os
import shutil
import time
import urllib.request
from pathlib import Path

from . import config, db

log = logging.getLogger("daf.downloads")
MODES = ("off", "new", "all")
MIN_FREE = int(config.setting("DAF_KEEP_FREE_GB", "20")) * 1024 ** 3     # the disk keeps this free: no episode comes when there's less
MAX_SIZE = 1500 * 1024 * 1024      # one episode's file at most (as episodes.MAX_AUDIO)
RETRY_AFTER = 7 * 86400            # a download that failed is asked for again by plan() after a week
UA = "Daf/1.0 (personal reading app)"


def folder():
    return config.STATE / "episodes"


def _name(audio, ctype=""):
    ext = mimetypes.guess_extension((ctype or "").split(";")[0].strip()) or Path(audio.split("?")[0]).suffix[:6] or ".mp3"
    if ext in (".mpga", ".mp2"):
        ext = ".mp3"
    return hashlib.sha1(audio.encode()).hexdigest() + ext


# ---- a show's choice ---------------------------------------------------------------------------

def mode(conn, feed):
    """{"mode": "off" | "new" | "all", "since": when it was chosen}."""
    r = conn.execute("SELECT v FROM kv WHERE k = ?", ("poddl:" + feed,)).fetchone()
    try:
        m = json.loads(r[0]) if r else {}
    except ValueError:
        m = {}
    return {"mode": m.get("mode") if m.get("mode") in MODES else "off", "since": m.get("since")}


def set_mode(conn, feed, m):
    """Choose what Daf keeps of a show. Off lets go of what's waiting to come, never what's kept."""
    if m not in MODES:
        raise ValueError("off, new or all")
    conn.execute("INSERT INTO kv (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v",
                 ("poddl:" + feed, json.dumps({"mode": m, "since": int(time.time())})))
    if m == "off":
        for (audio,) in conn.execute("SELECT audio FROM ep_files WHERE feed = ? AND state = 'queued'", (feed,)).fetchall():
            _forget(conn, audio)
        return {"mode": m, "queued": 0}
    return {"mode": m, "queued": plan_show(conn, feed)}


def plan_show(conn, feed):
    """Ask for each of the show's episodes its choice wants and Daf doesn't have yet."""
    m = mode(conn, feed)
    if m["mode"] == "off":
        return 0
    rows = conn.execute("SELECT url, published FROM gp_episodes WHERE podcast = ?", (feed,)).fetchall()
    if m["mode"] == "new":
        rows = [r for r in rows if (r["published"] or 0) >= (m["since"] or 0)]
    have = {r["audio"]: r for r in conn.execute("SELECT audio, state, asked FROM ep_files WHERE feed = ?", (feed,))}
    n = 0
    for r in rows:
        h = have.get(r["url"])
        if h and (h["state"] != "failed" or time.time() - (h["asked"] or 0) < RETRY_AFTER):
            continue
        want(conn, r["url"], feed)
        n += 1
    return n


def plan(conn):
    """Every show that keeps its episodes: what's come since (after the day's feed reading)."""
    n = 0
    for (k,) in conn.execute("SELECT k FROM kv WHERE k LIKE 'poddl:%'").fetchall():
        n += plan_show(conn, k[6:])
    return n


# ---- one episode -------------------------------------------------------------------------------

def want(conn, audio, feed=None):
    """Keep this episode: its file comes on the downloads worker."""
    from . import media
    r = conn.execute("SELECT state FROM ep_files WHERE audio = ?", (audio,)).fetchone()
    if r and r["state"] in ("queued", "going", "done"):
        return r["state"]
    if feed is None:
        e = conn.execute("SELECT podcast FROM gp_episodes WHERE url = ?", (audio,)).fetchone()
        feed = e["podcast"] if e else None
    conn.execute("INSERT INTO ep_files (audio, feed, state, asked) VALUES (?, ?, 'queued', ?) ON CONFLICT(audio) DO UPDATE SET "
                 "state = 'queued', error = NULL, asked = excluded.asked, feed = COALESCE(excluded.feed, ep_files.feed)",
                 (audio, feed, int(time.time())))
    media.queue(conn, "epdl", audio)
    return "queued"


def _forget(conn, audio):
    conn.execute("DELETE FROM ep_files WHERE audio = ?", (audio,))
    conn.execute("DELETE FROM jobs WHERE kind = 'epdl' AND ref = ? AND status = 'queued'", (audio,))


def drop(conn, audio):
    """Let go of an episode: its file, or its place in the line."""
    r = conn.execute("SELECT path FROM ep_files WHERE audio = ?", (audio,)).fetchone()
    if r and r["path"]:
        try:
            (folder() / r["path"]).unlink()
        except FileNotFoundError:
            pass
    _forget(conn, audio)
    return None


def states(conn, urls=None):
    """{audio: "queued" | "going" | "done" | "failed"}."""
    if urls is not None:
        urls = list(urls)
        if not urls:
            return {}
        q = f"SELECT audio, state FROM ep_files WHERE audio IN ({','.join('?' * len(urls))})"
        return {r[0]: r[1] for r in conn.execute(q, urls)}
    return {r[0]: r[1] for r in conn.execute("SELECT audio, state FROM ep_files")}


def kept(conn, audio):
    """(the file, its type) when Daf has this episode, else None."""
    r = conn.execute("SELECT path, type FROM ep_files WHERE audio = ? AND state = 'done'", (audio,)).fetchone()
    if not r or not r["path"]:
        return None
    p = folder() / r["path"]
    return (p, r["type"] or "audio/mpeg") if p.is_file() else None


def free():
    folder().mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(folder()).free


def fetch(audio):
    """The job (media.py's "epdl"): the episode's file into the folder, whole or not at all."""
    with db.session() as conn:
        r = conn.execute("SELECT state FROM ep_files WHERE audio = ?", (audio,)).fetchone()
        if not r or r["state"] == "done":
            return                                  # let go of, or kept, since it was asked for
        conn.execute("UPDATE ep_files SET state = 'going' WHERE audio = ?", (audio,))
    part = None
    try:
        if free() < MIN_FREE:
            raise RuntimeError("the disk is nearly full")
        req = urllib.request.Request(audio, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as resp:
            ctype = resp.headers.get_content_type() or "audio/mpeg"
            name = _name(audio, ctype)
            part = folder() / (name + ".part")
            got = 0
            with open(part, "wb") as f:
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    got += len(chunk)
                    if got > MAX_SIZE:
                        raise RuntimeError("the audio is over 1.5 GB")
                    f.write(chunk)
        if not got:
            raise RuntimeError("the file was empty")
        os.replace(part, folder() / name)
    except Exception as e:
        if part:
            part.unlink(missing_ok=True)
        with db.session() as conn:
            if conn.execute("SELECT 1 FROM ep_files WHERE audio = ?", (audio,)).fetchone():
                conn.execute("UPDATE ep_files SET state = 'failed', error = ? WHERE audio = ?", (str(e)[:300], audio))
        raise
    with db.session() as conn:
        if not conn.execute("SELECT 1 FROM ep_files WHERE audio = ?", (audio,)).fetchone():
            (folder() / name).unlink(missing_ok=True)  # let go of while it came
            return
        conn.execute("UPDATE ep_files SET state = 'done', path = ?, size = ?, type = ?, error = NULL, done = ? WHERE audio = ?",
                     (name, got, ctype if ctype.startswith("audio/") else "audio/mpeg", int(time.time()), audio))
