"""Phase 5: transcripts and clips.

- Videos: captions with yt-dlp (fast), or faster-whisper on the audio when there are none.
  Stored as blocks of kind "cue" ({"t": "cue", "ts": seconds, "x": text}) with chapter
  headings, so the reader's highlighting works on them unchanged.
- Audiobookshelf bookmarks: the minute before the bookmark, transcribed into a highlight.
- Podcast clips: a shared link with a time (from AntennaPod) becomes the transcript of
  the minute before that point, on the episode's page (episodes.py), whose whole transcript is the
  "podtr" job.

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
LONG = ("podtr",)                 # a whole podcast episode through whisper: its own worker too, so a reel doesn't wait an hour
BOOK = ("bookmap",)               # a whole audiobook through whisper (readalong.py), hours of it: its own worker, one book at a time
FILES = ("epdl",)                 # a podcast episode kept on the server (downloads.py): its own worker, one file at a time


TEXT_JOBS = ("reel", "captions", "whisper", "pdf", "page")     # jobs that bring a document's text


def _run_one(lane="main"):
    kinds = {"quick": QUICK, "long": LONG, "book": BOOK, "files": FILES}.get(lane, QUICK + LONG + BOOK + FILES)
    with db.session() as conn:
        j = conn.execute(f"SELECT * FROM jobs WHERE status = 'queued' AND kind {'NOT ' if lane == 'main' else ''}IN ({','.join('?' * len(kinds))}) "
                         "ORDER BY id LIMIT 1", kinds).fetchone()
        if not j:
            return False
        conn.execute("UPDATE jobs SET status = 'running', started = ? WHERE id = ?", (int(time.time()), j["id"]))
        j = dict(j)
    try:
        detail = json.loads(j["detail"]) if j["detail"] else {}
        if j["kind"] == "reel":
            from . import social
            social.fetch(j["ref"])
        elif j["kind"] == "captions":
            video_transcript(j["ref"], use_whisper=False)
        elif j["kind"] == "whisper":
            video_transcript(j["ref"], use_whisper=True)
        elif j["kind"] == "absbookmark":
            abs_bookmark(j["ref"])
        elif j["kind"] == "clip":
            podcast_clip(detail)
        elif j["kind"] == "podtr":
            from . import episodes
            episodes.transcribe(j["ref"])
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
        elif j["kind"] == "bookmap":
            from . import readalong
            readalong.build(j["ref"])
        elif j["kind"] == "epdl":
            from . import downloads
            downloads.fetch(j["ref"])
        status, err = "done", None
    except Exception as e:  # noqa: BLE001
        log.exception("job %s", j["id"])
        status, err = "failed", str(e)[:400]
    with db.session() as conn:
        conn.execute("UPDATE jobs SET status = ?, error = ?, finished = ? WHERE id = ?", (status, err, int(time.time()), j["id"]))
    if status == "done" and j["kind"] in TEXT_JOBS:
        try:                                     # its note in the vault, if it has one, gets the text that just came
            from . import vaultnotes
            with db.session() as conn:
                vaultnotes.refresh(conn, config.load_settings(), j["ref"])
        except Exception:  # noqa: BLE001
            log.exception("vault note after job %s", j["id"])
    return True


def worker(stop, lane="main"):
    while not stop.is_set():
        try:
            busy = _run_one(lane)
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
    threading.Thread(target=worker, args=(stop, "quick"), name="daf-pages", daemon=True).start()
    threading.Thread(target=worker, args=(stop, "long"), name="daf-podcasts", daemon=True).start()
    threading.Thread(target=worker, args=(stop, "book"), name="daf-audiobooks", daemon=True).start()
    threading.Thread(target=worker, args=(stop, "files"), name="daf-downloads", daemon=True).start()
    return stop


def whisper(path, start=None, duration=None, model=None, timeout=7200, low=False):
    """model: another faster-whisper model than the default (audiomap.py asks for the quick base.en).
    low: at the lowest priority and on half the threads (readalong.py's hours of audiobook), so whatever
    else the server is doing goes first."""
    cmd = (["nice", "-n", "19"] if low else []) + WHISPER + [path] + (["--threads", "4"] if low else [])
    if start is not None:
        cmd += ["--start", str(start)]
    if duration is not None:
        cmd += ["--duration", str(duration)]
    if model:
        cmd += ["--model", model]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
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


_WORD_TIME = re.compile(r"<\d\d:\d\d:\d\d\.\d{3}>")
_NOISE = re.compile(r"(>>\s*)?(\[.*\]|\(.*\))")     # [Music], (applause), ">> [clears throat]"


def _vtt_cues(text):
    """(start in whole seconds, [(line, timed)]) for each cue, tags gone. A timed line carries word timings:
    YouTube's auto-captions time each word as it's typed out, so that line is being said right then."""
    for h, m, s, body in re.findall(r"(\d\d):(\d\d):(\d\d)\.\d{3} --> [^\n]*\n(.*?)(?:\n\n|\Z)", text, re.S):
        lines = [(html.unescape(re.sub(r"<[^>]+>", "", raw)).strip(), bool(_WORD_TIME.search(raw))) for raw in body.split("\n")]
        yield int(h) * 3600 + int(m) * 60 + int(s), [l for l in lines if l[0]]


def _fresh(lines, shown):
    """The lines a cue adds to what's on screen. YouTube's auto-captions roll: each cue opens with the line
    the last one ended on, and a 10 ms cue between them shows the line just finished, so every line came
    three times. A cue's first lines go when they're the lines just shown (as many as match), but never a
    timed line: that one is being said now, even when it's the same words again ("No. No.")."""
    for n in range(min(len(lines), len(shown)), 0, -1):
        if not any(timed for _, timed in lines[:n]) and [x for x, _ in lines[:n]] == shown[-n:]:
            return lines[n:]
    return lines


def _parse_vtt(text):
    lines, cur, shown = [], None, []
    for sec, cue in _vtt_cues(text):
        new = _fresh(cue, shown)
        shown = (shown + [x for x, _ in new])[-4:]
        said = " ".join(x for x, _ in new if not _NOISE.fullmatch(x))
        for i, t in enumerate(re.split(r"\s*>>\s*", said)):      # ">>" is YouTube's mark for another voice
            mm = re.match(r"^-\s*(\[(.*?)\])?\s*", t)
            spk = mm.group(2) if mm else None
            if mm:
                t = t[mm.end():]
            if (i or mm) and cur:
                lines.append(cur)
                cur = None
            if not t:
                continue
            if cur is None:
                cur = {"ts": sec, "spk": spk, "x": t}
            else:
                cur["x"] += " " + t
            if sec - cur["ts"] >= 6 or len(cur["x"]) > 140:
                # A paragraph ends at the last sentence end in this line, even mid-line: a rolling caption's
                # lines seldom end with the sentence, and the rest starts the next one.
                ends = [m.end() for m in re.finditer(r"[.?!][\"”’)]?(?=\s|$)", t)]
                if ends:
                    rest = t[ends[-1]:].strip()
                    cur["x"] = cur["x"][:len(cur["x"]) - len(t) + ends[-1]]
                    lines.append(cur)
                    cur = {"ts": sec, "spk": cur["spk"], "x": rest} if rest else None
                elif len(cur["x"]) > 500:            # older auto-captions have no punctuation at all
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


def caption_track(info):
    """The caption track to read, from what yt-dlp says a video has: one a person made ("subtitles") before
    YouTube's automatic ones, English before Hebrew ("iw" is YouTube's old code for it), and among the
    automatic ones plain "en" before "en-orig" and the rest, as before. None when there's none of those."""
    made, auto = info.get("subtitles") or {}, info.get("automatic_captions") or {}
    tracks = [(lang, True) for lang in made] + [(lang, False) for lang in auto if lang not in made]
    tracks = [(lang, m) for lang, m in tracks if lang.split("-")[0] in ("en", "he", "iw")]
    if not tracks:
        return None
    return min(tracks, key=lambda t: (not t[1], not t[0].startswith("en"), t[0] != "en", "-orig" in t[0], t[0]))[0]


def video_transcript(doc_id, use_whisper=False):
    with db.session() as conn:
        d = conn.execute("SELECT * FROM docs WHERE id = ?", (doc_id,)).fetchone()
    if not d:
        raise KeyError(doc_id)
    from . import social
    if social.is_reel(d["url"]):
        return social.fetch(doc_id)              # a reel: kept whole, transcribed from Daf's copy
    vid = youtube_id(d["url"])
    if not vid:
        raise ValueError("Not a YouTube link")
    url = f"https://www.youtube.com/watch?v={vid}"
    with tempfile.TemporaryDirectory() as tmp:
        info = {}
        if not use_whisper:
            # What the video has first, then only the one track chosen from it: asking for every English one at
            # once got a 429 from YouTube on a spare track, and yt-dlp stopped before writing what the video has.
            r = subprocess.run(YTDLP + ["--skip-download", "--write-info-json", "-o", f"{tmp}/%(id)s.%(ext)s", url],
                               capture_output=True, text=True, timeout=180)
            infos = glob.glob(f"{tmp}/*.info.json")
            if not infos:
                raise RuntimeError("couldn't read the video on YouTube: " + r.stderr.strip()[-200:])
            info = json.load(open(infos[0]))
            lang = caption_track(info)
            if not lang:
                raise RuntimeError("no captions on YouTube for this video; try the whisper transcript")
            r = subprocess.run(YTDLP + ["--load-info-json", infos[0], "--skip-download", "--write-subs", "--write-auto-subs",
                                        "--sub-langs", lang, "--sub-format", "vtt", "-o", f"{tmp}/%(id)s.%(ext)s"],
                               capture_output=True, text=True, timeout=180)
            vtts = glob.glob(f"{tmp}/*.vtt")
            if not vtts:
                raise RuntimeError(f"couldn't download YouTube's captions ({lang}): " + r.stderr.strip()[-200:])
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


def doubled_runs(blocks, shortest=5, longest=15):
    """How often a transcript says a run of words (5 to 15) and then the same run again: what YouTube's
    rolling captions left on every line before Daf dropped their overlap. A person does it once or twice
    in a talk."""
    words = " ".join(b["x"] for b in blocks if b.get("t") == "cue").split()
    count = i = 0
    while i < len(words):
        run = next((n for n in range(shortest, longest + 1) if words[i:i + n] == words[i + n:i + 2 * n]
                    and i + 2 * n <= len(words)), 0)
        count, i = count + bool(run), i + (run or 1)
    return count


def stale_captions(conn, ids=None):
    """The YouTube transcripts to make again (`daf captions-rebuild`): the ones asked for, or else every one
    with 3 or more doubled runs. Whisper's transcripts never have them, so they stay as they are.
    `highlights`: how many it has; they're kept by paragraph number, which a new transcript changes."""
    from . import social
    sql = """SELECT d.id, d.title, d.url, c.blocks,
                    (SELECT COUNT(*) FROM highlights h WHERE h.book_id = d.id AND h.deleted = 0) AS highlights
             FROM docs d JOIN doc_content c ON c.id = d.id WHERE c.blocks LIKE '%"t": "cue"%'"""
    if ids:
        sql += f" AND d.id IN ({','.join('?' * len(ids))})"
    out = []
    for r in conn.execute(sql, list(ids or ())).fetchall():
        if not youtube_id(r["url"]) or social.is_reel(r["url"]):
            continue
        n = doubled_runs(json.loads(r["blocks"]))
        if ids or n >= 3:
            out.append({"id": r["id"], "title": r["title"] or r["url"], "doubled": n, "highlights": r["highlights"]})
    return out


def remake_captions(doc_id):
    """The captions job, run right here: YouTube's captions fetched and read again, and the vault note after."""
    n = video_transcript(doc_id, use_whisper=False)
    from . import vaultnotes
    with db.session() as conn:
        vaultnotes.refresh(conn, config.load_settings(), doc_id)
    return n


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
    from . import social
    social.prune(conn)


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
    """The stretch before a point in an episode as a highlight on the episode's page: its transcript's
    lines when it has one, else that stretch through whisper (and the whole episode is transcribed)."""
    from . import episodes, reader, vaultnotes
    url, pos, title, sec = detail.get("url"), detail.get("pos"), detail.get("title"), int(detail.get("sec") or 60)
    base = url.split("#")[0]
    with db.session() as conn:
        ep = conn.execute("SELECT * FROM gp_episodes WHERE url = ? OR link = ?", (base, base)).fetchone()
        audio = ep["url"] if ep else base
        if detail.get("doc") and conn.execute("SELECT 1 FROM docs WHERE id = ?", (detail["doc"],)).fetchone():
            doc_id = detail["doc"]
            audio = conn.execute("SELECT enclosure FROM docs WHERE id = ?", (doc_id,)).fetchone()[0] or audio
        else:
            doc_id = episodes.doc_for(conn, audio)
        if pos is None:
            p = episodes.position(conn, audio)
            pos = p["t"] if p else None
        tr = episodes.transcript(conn, audio)
    if pos is None:
        raise ValueError("no time in the shared text, and AntennaPod hasn't reported a position for it")
    s = config.load_settings()
    if tr:
        with db.session() as conn:
            cues = [(i, b) for i, b in enumerate(tr[0]) if b.get("t") == "cue" and pos - sec <= b["ts"] <= pos]
            if not cues:                         # a long line that started before the stretch
                cues = [max(((i, b) for i, b in enumerate(tr[0]) if b.get("t") == "cue" and b["ts"] <= pos), key=lambda x: x[1]["ts"], default=None)]
                cues = [c for c in cues if c]
            for i, b in cues:
                reader.add_highlight(conn, s, doc_id, i, 0, len(b["x"]), b["x"], t=b["ts"])
            _keep(conn, doc_id)
        return title, pos, " ".join(b["x"] for _, b in cues)
    res = whisper(audio, start=max(0.0, pos - sec), duration=sec)
    text = " ".join(x["text"] for x in res["segments"]).strip()
    if not text:
        raise RuntimeError("nothing intelligible in that stretch")
    with db.session() as conn:
        d = conn.execute("SELECT * FROM docs WHERE id = ?", (doc_id,)).fetchone()
        reader._ensure_book(conn, d)
        hid = "pc" + hashlib.sha1(f"{audio}|{int(pos)}".encode()).hexdigest()[:16]
        conn.execute("INSERT OR REPLACE INTO highlights (id, book_id, source, text, note, chapter, page, created, pos, seen, deleted) "
                     "VALUES (?, ?, 'clip', ?, NULL, NULL, NULL, ?, ?, ?, 0)",
                     (hid, doc_id, text, int(time.time()), json.dumps({"t": pos}), int(time.time())))
        vaultnotes.write_article(conn, s, doc_id)
        episodes.want(conn, audio, "clip")
        _keep(conn, doc_id)
    return d["title"] if d else title, pos, text


def _keep(conn, doc_id):
    """A Feed episode you clip is one you want to keep: to the Library, as a highlight takes any Feed item."""
    from . import reader
    d = conn.execute("SELECT where_ FROM docs WHERE id = ?", (doc_id,)).fetchone()
    if d and d["where_"] == "feed":
        try:
            reader.save_to_library(conn, doc_id)
        except Exception:  # noqa: BLE001 - the clip stands on the Feed item
            log.exception("keeping %s", doc_id)
