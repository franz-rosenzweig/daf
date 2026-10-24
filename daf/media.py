"""Phase 5: transcripts and clips.

- Videos: captions with yt-dlp (fast), or faster-whisper on the audio when there are none.
  Stored as blocks of kind "cue" ({"t": "cue", "ts": seconds, "x": text}) with chapter
  headings, so the reader's highlighting works on them unchanged.
- Audiobookshelf bookmarks: the minute before the bookmark, transcribed into a highlight.
- Podcast clips: a shared link with a time (from AntennaPod) becomes the transcript of
  the minute before that point.

Everything slow runs as a job in a background thread (the `jobs` table).
"""
import glob
import hashlib
import html
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from . import config, db

log = logging.getLogger("daf.media")
# yt-dlp and faster-whisper are in Daf's own environment (requirements.txt), run with the same Python
# as Daf, so an upgrade of the system's Python can't take them away (October 2026's did).
WHISPER = [sys.executable, str(Path(__file__).resolve().parent.parent / "tools" / "whisper_segments.py")]
# YouTube now wants a JavaScript runtime for some of what yt-dlp asks it; deno, where it's installed.
_DENO = shutil.which("deno") or str(Path.home() / ".deno" / "bin" / "deno")
YTDLP = [sys.executable, "-m", "yt_dlp"] + (["--js-runtimes", f"deno:{_DENO}"] if os.path.exists(_DENO) else [])
ABS_MOUNTS = {"/audiobooks": "/srv/media/audiobooks", "/podcasts": "/srv/media/podcasts"}


# ---- jobs ------------------------------------------------------------------------

def queue(conn, kind, ref, detail=None):
    if conn.execute("SELECT 1 FROM jobs WHERE kind = ? AND ref = ? AND status IN ('queued', 'running')", (kind, ref)).fetchone():
        return
    conn.execute("INSERT INTO jobs (kind, ref, status, detail, created) VALUES (?, ?, 'queued', ?, ?)",
                 (kind, ref, json.dumps(detail) if detail else None, int(time.time())))


def job_status(conn, kind, ref):
    r = conn.execute("SELECT status, error, finished FROM jobs WHERE kind = ? AND ref = ? ORDER BY id DESC LIMIT 1", (kind, ref)).fetchone()
    return dict(r) if r else None


QUICK = ("page",)                 # reading a saved page: its own worker, never behind a long transcript


def _run_one(quick=False):
    with db.session() as conn:
        j = conn.execute(f"SELECT * FROM jobs WHERE status = 'queued' AND kind {'' if quick else 'NOT '}IN ({','.join('?' * len(QUICK))}) "
                         "ORDER BY id LIMIT 1", QUICK).fetchone()
        if not j:
            return False
        conn.execute("UPDATE jobs SET status = 'running', started = ? WHERE id = ?", (int(time.time()), j["id"]))
        j = dict(j)
    try:
        detail = json.loads(j["detail"]) if j["detail"] else {}
        if j["kind"] == "captions":
            video_transcript(j["ref"], use_whisper=False)
        elif j["kind"] == "whisper":
            video_transcript(j["ref"], use_whisper=True)
        elif j["kind"] == "absbookmark":
            abs_bookmark(j["ref"])
        elif j["kind"] == "clip":
            podcast_clip(detail)
        elif j["kind"] == "pdf":
            from . import pdfdoc
            with db.session() as conn:
                pdfdoc.build(conn, j["ref"])
        elif j["kind"] == "summary":
            from . import reader
            with db.session() as conn:
                reader.summarize(conn, j["ref"])
        elif j["kind"] == "page":
            from . import pages
            with db.session() as conn:
                pages.fetch(conn, j["ref"])
        elif j["kind"] == "tagtidy":
            from . import tagging
            with db.session() as conn:
                tagging.propose(conn)
        elif j["kind"] == "tags":
            from . import tagging
            with db.session() as conn:
                tagging.tag_doc(conn, j["ref"])
        elif j["kind"] == "ocr":
            from . import paper_pages
            paper_pages.read_page(j["ref"])
        status, err = "done", None
    except Exception as e:  # noqa: BLE001
        log.exception("job %s", j["id"])
        status, err = "failed", str(e)[:400]
    with db.session() as conn:
        conn.execute("UPDATE jobs SET status = ?, error = ?, finished = ? WHERE id = ?", (status, err, int(time.time()), j["id"]))
    return True


def worker(stop, quick=False):
    while not stop.is_set():
        try:
            busy = _run_one(quick)
        except Exception:  # noqa: BLE001
            log.exception("worker")
            busy = False
        stop.wait(1 if busy else 10)


def start_worker():
    # A restart mid-job leaves it "running" forever; put it back in the queue.
    with db.session() as conn:
        conn.execute("UPDATE jobs SET status = 'queued' WHERE status = 'running'")
    stop = threading.Event()
    threading.Thread(target=worker, args=(stop,), name="daf-media", daemon=True).start()
    threading.Thread(target=worker, args=(stop, True), name="daf-pages", daemon=True).start()
    return stop


def whisper(path, start=None, duration=None):
    cmd = WHISPER + [path]
    if start is not None:
        cmd += ["--start", str(start)]
    if duration is not None:
        cmd += ["--duration", str(duration)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
    try:
        out = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise RuntimeError((r.stderr or "whisper failed").strip()[-300:])
    if out.get("error"):
        raise RuntimeError(out["error"])
    return out


# ---- videos ----------------------------------------------------------------------

def youtube_id(url):
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})", url or "")
    return m.group(1) if m else None


def _parse_vtt(text):
    cues = re.findall(r"(\d\d):(\d\d):(\d\d)\.\d{3} --> [^\n]*\n(.*?)(?:\n\n|\Z)", text, re.S)
    lines, cur, last_text = [], None, None
    for h, m, s, t in cues:
        t = re.sub(r"<[^>]+>", "", t).replace("\n", " ").strip()
        t = html.unescape(t)
        if not t or re.fullmatch(r"\[.*\]|\(.*\)", t) or t == last_text:
            continue
        last_text = t
        sec = int(h) * 3600 + int(m) * 60 + int(s)
        spk = None
        mm = re.match(r"^-\s*(\[(.*?)\])?\s*", t)
        if mm:
            spk, t = mm.group(2), t[mm.end():]
            if cur:
                lines.append(cur)
                cur = None
        if cur is None:
            cur = {"ts": sec, "spk": spk, "x": t}
        else:
            if t.startswith(cur["x"][-40:]) and len(cur["x"]) > 40:
                t = t[len(cur["x"][-40:]):]
            cur["x"] += " " + t
        if re.search(r"[.?!][\"”’)]?$", t) and (sec - cur["ts"] >= 6 or len(cur["x"]) > 140):
            lines.append(cur)
            cur = None
    if cur:
        lines.append(cur)
    return lines


def _blocks_from_lines(lines, chapters):
    out, ci = [], 0
    chapters = sorted(chapters or [], key=lambda c: c["start_time"])
    for l in lines:
        while ci < len(chapters) and chapters[ci]["start_time"] <= l["ts"]:
            t = chapters[ci].get("title") or ""
            out.append({"t": "h3", "x": t, "h": html.escape(t), "ts": int(chapters[ci]["start_time"])})
            ci += 1
        x = re.sub(r"\s+", " ", l["x"]).strip()
        out.append({"t": "cue", "ts": l["ts"], "spk": l.get("spk"), "x": x, "h": html.escape(x)})
    return out


def video_transcript(doc_id, use_whisper=False):
    with db.session() as conn:
        d = conn.execute("SELECT * FROM docs WHERE id = ?", (doc_id,)).fetchone()
    if not d:
        raise KeyError(doc_id)
    vid = youtube_id(d["url"])
    if not vid:
        raise ValueError("Not a YouTube link")
    url = f"https://www.youtube.com/watch?v={vid}"
    with tempfile.TemporaryDirectory() as tmp:
        info = {}
        if not use_whisper:
            subprocess.run(YTDLP + ["--skip-download", "--write-subs", "--write-auto-subs", "--sub-langs", "en.*,en,he.*,he",
                            "--sub-format", "vtt", "--write-info-json", "-o", f"{tmp}/%(id)s.%(ext)s", url],
                           capture_output=True, text=True, timeout=180)
            infos = glob.glob(f"{tmp}/*.info.json")
            if infos:
                info = json.load(open(infos[0]))
            vtts = sorted(glob.glob(f"{tmp}/*.vtt"), key=lambda p: (".en.vtt" not in p, "-orig" in p, p))
            if not vtts:
                raise RuntimeError("no captions on YouTube for this video; try the whisper transcript")
            lines = _parse_vtt(open(vtts[0], encoding="utf-8").read())
        else:
            r = subprocess.run(YTDLP + ["-f", "bestaudio", "-x", "--audio-format", "m4a", "--write-info-json", "-o",
                                f"{tmp}/%(id)s.%(ext)s", url], capture_output=True, text=True, timeout=1800)
            audio = glob.glob(f"{tmp}/*.m4a")
            if not audio:
                raise RuntimeError("couldn't download the audio: " + r.stderr.strip()[-200:])
            infos = glob.glob(f"{tmp}/*.info.json")
            if infos:
                info = json.load(open(infos[0]))
            res = whisper(audio[0])
            lines = [{"ts": int(s["start"]), "spk": None, "x": s["text"]} for s in res["segments"] if s["text"]]
    blocks = _blocks_from_lines(lines, info.get("chapters"))
    with db.session() as conn:
        conn.execute("INSERT OR REPLACE INTO doc_content (id, blocks, fetched) VALUES (?, ?, ?)", (doc_id, json.dumps(blocks), int(time.time())))
        conn.execute("UPDATE docs SET words = ?, duration = COALESCE(?, duration), summary = COALESCE(NULLIF(summary, ''), ?), "
                     "author = COALESCE(NULLIF(author, ''), ?) WHERE id = ?",
                     (sum(len(b["x"].split()) for b in blocks), info.get("duration"), (info.get("description") or "")[:280],
                      info.get("channel"), doc_id))
    return len(blocks)


# ---- audiobookshelf bookmarks ----------------------------------------------------------

def abs_bookmark(bm_id):
    """Transcribe the minute before an Audiobookshelf bookmark into a highlight."""
    from .db import read_only
    item_id, t = bm_id.rsplit(":", 1)
    t = float(t)
    a = read_only(config.ABS_DB)
    try:
        row = a.execute("SELECT b.audioFiles FROM libraryItems li JOIN books b ON b.id = li.mediaId WHERE li.id = ?", (item_id,)).fetchone()
    finally:
        a.close()
    if not row:
        raise KeyError(item_id)
    files = sorted(json.loads(row[0] or "[]"), key=lambda f: f.get("index", 0))
    offset = 0.0
    for f in files:
        dur = float(f.get("duration") or 0)
        if offset + dur >= t or f is files[-1]:
            path = f["metadata"]["path"]
            for k, v in ABS_MOUNTS.items():
                if path.startswith(k + "/"):
                    path = v + path[len(k):]
            local = t - offset
            break
        offset += dur
    res = whisper(path, start=max(0.0, local - 60), duration=min(60, local) or 60)
    text = " ".join(s["text"] for s in res["segments"]).strip()
    if not text:
        raise RuntimeError("nothing intelligible in that minute")
    with db.session() as conn:
        b = conn.execute("SELECT book_id, title FROM audio_bookmarks WHERE id = ?", (bm_id,)).fetchone()
        hid = "abm" + hashlib.sha1(bm_id.encode()).hexdigest()[:16]
        conn.execute("INSERT INTO highlights (id, book_id, source, text, note, chapter, page, created, pos, seen, deleted) "
                     "VALUES (?, ?, 'audiobookshelf', ?, ?, NULL, NULL, ?, ?, ?, 0) "
                     "ON CONFLICT(id) DO UPDATE SET text = excluded.text, note = excluded.note, book_id = excluded.book_id",
                     (hid, b["book_id"] if b else None, text, (b["title"] if b and b["title"] not in ("Pause", "Audiobookmark", "Bookmark") else None),
                      int(time.time()), json.dumps({"t": t}), int(time.time())))
        conn.execute("UPDATE audio_bookmarks SET transcribed = 1 WHERE id = ?", (bm_id,))
    return text


def prune(conn, days=14):
    conn.execute("DELETE FROM jobs WHERE status IN ('done', 'failed') AND finished < ?", (int(time.time()) - days * 86400,))


def queue_bookmarks(conn):
    done = {r[0] for r in conn.execute("SELECT id FROM highlights WHERE id LIKE 'abm%'")}
    failed = {r[0] for r in conn.execute("SELECT ref FROM jobs WHERE kind = 'absbookmark' GROUP BY ref HAVING SUM(status = 'failed') >= 3")}
    for r in conn.execute("SELECT id, title FROM audio_bookmarks WHERE book_id IS NOT NULL AND COALESCE(transcribed, 0) = 0").fetchall():
        if "abm" + hashlib.sha1(r["id"].encode()).hexdigest()[:16] in done:
            conn.execute("UPDATE audio_bookmarks SET transcribed = 1 WHERE id = ?", (r["id"],))
            continue
        if r["id"] in failed:
            continue      # three tries is enough; `daf jobs` shows why
        if len(r["title"] or "") >= 25 and " " in (r["title"] or ""):
            continue      # already a typed quote
        queue(conn, "absbookmark", r["id"])


# ---- podcast clips -------------------------------------------------------------------

TIME = re.compile(r"\b(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\b")


def parse_share(text):
    url = (re.search(r"https?://\S+", text or "") or [None])[0]
    url = url.rstrip(").,]") if url else None
    pos = None
    m = re.search(r"[#&?]t=(\d+(?:\.\d+)?)", url or "")
    if m:
        pos = float(m.group(1))
    else:
        tm = TIME.search(re.sub(r"https?://\S+", "", text or ""))
        if tm:
            pos = int(tm.group(1) or 0) * 3600 + int(tm.group(2)) * 60 + int(tm.group(3))
    return url, pos


def podcast_clip(detail):
    url, pos, title = detail.get("url"), detail.get("pos"), detail.get("title")
    with db.session() as conn:
        ep = conn.execute("SELECT * FROM gp_episodes WHERE url = ? OR link = ?", (url.split("#")[0], url.split("#")[0])).fetchone()
        audio = ep["url"] if ep else url.split("#")[0]
        title = (ep["title"] if ep else None) or title or "Podcast episode"
        podcast = ep["podcast_title"] if ep and "podcast_title" in ep.keys() else None
        if pos is None:
            a = conn.execute("SELECT position FROM gp_actions WHERE episode = ? AND action = 'play' ORDER BY timestamp DESC LIMIT 1", (audio,)).fetchone()
            pos = a[0] if a else None
    if pos is None:
        raise ValueError("no time in the shared text, and AntennaPod hasn't reported a position for it")
    res = whisper(audio, start=max(0.0, pos - 60), duration=60)
    text = " ".join(s["text"] for s in res["segments"]).strip()
    if not text:
        raise RuntimeError("nothing intelligible in that minute")
    bid = "pod:" + hashlib.sha1(audio.encode()).hexdigest()[:16]
    with db.session() as conn:
        page = (ep["link"] if ep and ep["link"] else None) or audio
        conn.execute("INSERT INTO books (id, kind, title, author, url, private) VALUES (?, 'podcast', ?, ?, ?, 0) "
                     "ON CONFLICT(id) DO UPDATE SET title = excluded.title, url = excluded.url", (bid, title, podcast, page))
        hid = "pc" + hashlib.sha1(f"{audio}|{int(pos)}".encode()).hexdigest()[:16]
        conn.execute("INSERT OR REPLACE INTO highlights (id, book_id, source, text, note, chapter, page, created, pos, seen, deleted) "
                     "VALUES (?, ?, 'clip', ?, NULL, NULL, NULL, ?, ?, ?, 0)",
                     (hid, bid, text, int(time.time()), json.dumps({"t": pos}), int(time.time())))
        from . import vaultnotes
        vaultnotes.write_article(conn, config.load_settings(), bid)
    return title, pos, text
