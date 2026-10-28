"""Podcast episodes: the page an episode gets in Daf, with its player, transcript and chapters.

An episode is known by its audio's address (the feed's enclosure), the same address AntennaPod
syncs its listening under (gpodder.py), so an episode met in the Feed, opened from the Podcasts
page or played in AntennaPod is one episode.

- What the feed says about it (gp_episodes): its guid, show notes, picture, length, and the
  Podcasting 2.0 tags for a transcript and chapters, read with the feed (parse_feed).
- Its transcript (episode_text), kept apart from the doc's own text, so a Feed sync, "Load the full
  article" or the Feed forgetting an old item can't take it away. It comes from the show itself when
  the feed links one (JSON, WebVTT, SRT or HTML), and otherwise from faster-whisper on the server
  (media.whisper), on its own worker so an hour of audio doesn't hold up a reel. Chapters come from
  the feed's chapters file, or from the audio file's own (ffprobe).
- Its page is a doc of kind "podcast": the Feed's item when there is one, its Library copy once
  it's highlighted, or a doc of its own (id "ep:…", where_ "podcast") for an episode met only in
  AntennaPod. The reader shows the transcript first and the show notes after it (blocks), so a
  highlight's place in the transcript never moves; the show notes' highlights are moved down once,
  when a transcript arrives in front of them (_store).
- Where you are: a play in Daf goes to AntennaPod as a gpodder play action (device "daf"), and Daf
  starts where the last play anywhere left off (position).

Transcribing is automatic for an episode you play (in AntennaPod or here) or open, unless
Preferences → Podcasts says only when asked (settings "podcasts": {"transcribe": false}).
"""
import hashlib
import html
import json
import logging
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

from . import config, content, db

log = logging.getLogger("daf.episodes")
UA = "Daf/1.0 (personal reading app)"
FEED_MAX_AGE = 6 * 3600
TR_TYPES = {"application/json": 0, "text/vtt": 1, "application/x-subrip": 2, "application/srt": 2, "text/srt": 2, "text/html": 3}
MAX_AUDIO = 1500 * 1024 * 1024


def _local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _ns(tag):
    return tag[1:].split("}", 1)[0].lower() if isinstance(tag, str) and tag.startswith("{") else ""


def _is_podcast_ns(tag):
    n = _ns(tag)
    return "podcastindex" in n or "podcast-namespace" in n


def _seconds(s):
    """itunes:duration: "1:02:03", "62:03" or "3723"."""
    s = str(s or "").strip()
    if not s:
        return None
    try:
        parts = [float(p) for p in s.split(":")]
    except ValueError:
        return None
    sec = 0.0
    for p in parts:
        sec = sec * 60 + p
    return int(sec) or None


def _get(url, timeout=30, limit=8 * 1024 * 1024):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(limit), r.headers.get_content_type()


# ---- feeds -------------------------------------------------------------------------

def parse_feed(data):
    """An RSS feed → (show title, show picture, [episode dicts])."""
    root = ET.fromstring(data)
    ch = root.find("channel")
    if ch is None:
        raise ValueError("not RSS")
    show = (ch.findtext("title") or "").strip()
    pic = None
    for el in ch:
        if _local(el.tag) == "image":
            pic = el.get("href") or (el.findtext("url") or "").strip() or pic
    show_author = next(((el.text or "").strip() for el in ch if _local(el.tag) == "author" and el.text), None)
    out = []
    for it in ch.findall("item")[:300]:
        enc = it.find("enclosure")
        if enc is None or not enc.get("url"):
            continue
        e = {"url": enc.get("url").strip(), "link": (it.findtext("link") or "").strip(), "title": (it.findtext("title") or "").strip(),
             "guid": (it.findtext("guid") or "").strip() or None, "published": None, "duration": None, "image": None,
             "author": show_author, "notes": None, "transcript_url": None, "transcript_type": None, "chapters_url": None}
        try:
            e["published"] = int(parsedate_to_datetime(it.findtext("pubDate")).timestamp())
        except (TypeError, ValueError):
            pass
        best, desc, encoded = None, None, None
        for el in it:
            name = _local(el.tag)
            if name == "duration":
                e["duration"] = _seconds(el.text)
            elif name == "image" and el.get("href"):
                e["image"] = el.get("href")
            elif name == "author" and (el.text or "").strip():
                e["author"] = el.text.strip()
            elif name == "encoded":
                encoded = el.text
            elif name in ("description", "summary") and el.text and not desc:
                desc = el.text
            elif name == "transcript" and _is_podcast_ns(el.tag) and el.get("url"):
                rank = TR_TYPES.get((el.get("type") or "").split(";")[0].strip().lower(), 9)
                if best is None or rank < best[0]:
                    best = (rank, el.get("url"), (el.get("type") or "").split(";")[0].strip().lower())
            elif name == "chapters" and _is_podcast_ns(el.tag) and el.get("url"):
                e["chapters_url"] = el.get("url")
        if best and best[0] < 9:
            e["transcript_url"], e["transcript_type"] = best[1], best[2]
        e["notes"] = encoded or desc
        e["image"] = e["image"] or pic
        out.append(e)
    return show, pic, out


def remember(conn, feed_url, show, episodes):
    """The feed's episodes into gp_episodes, keeping what an earlier read knew and this one doesn't say."""
    now = int(time.time())
    for e in episodes:
        conn.execute(
            "INSERT INTO gp_episodes (url, link, title, podcast, podcast_title, published, guid, author, image, duration, notes, "
            "transcript_url, transcript_type, chapters_url, checked) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(url) DO UPDATE SET link = COALESCE(NULLIF(excluded.link, ''), link), title = COALESCE(NULLIF(excluded.title, ''), title), "
            "podcast = excluded.podcast, podcast_title = COALESCE(NULLIF(excluded.podcast_title, ''), podcast_title), "
            "published = COALESCE(excluded.published, published), guid = COALESCE(excluded.guid, guid), author = COALESCE(excluded.author, author), "
            "image = COALESCE(excluded.image, image), duration = COALESCE(excluded.duration, duration), notes = COALESCE(excluded.notes, notes), "
            "transcript_url = COALESCE(excluded.transcript_url, transcript_url), transcript_type = COALESCE(excluded.transcript_type, transcript_type), "
            "chapters_url = COALESCE(excluded.chapters_url, chapters_url), checked = excluded.checked",
            (e["url"], e["link"], e["title"], feed_url, show, e["published"], e["guid"], e["author"], e["image"], e["duration"],
             e["notes"], e["transcript_url"], e["transcript_type"], e["chapters_url"], now))


def read_feed(conn, feed_url, max_age=FEED_MAX_AGE):
    """Fetch a feed (at most every max_age) and remember its episodes. Returns the show's title, or None."""
    k = "podfeed:" + feed_url
    was = conn.execute("SELECT v FROM kv WHERE k = ?", (k,)).fetchone()
    if was and time.time() - int(json.loads(was[0]).get("at", 0)) < max_age:
        return json.loads(was[0]).get("title")
    try:
        data, _ = _get(feed_url, timeout=30, limit=30 * 1024 * 1024)
        show, pic, eps = parse_feed(data)
    except Exception as e:  # noqa: BLE001 - a dead feed shouldn't stop anything
        log.info("feed %s: %s", feed_url, e)
        conn.execute("INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)", (k, json.dumps({"at": int(time.time()), "error": str(e)[:200]})))
        return None
    remember(conn, feed_url, show, eps)
    conn.execute("INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)", (k, json.dumps({"at": int(time.time()), "title": show, "image": pic})))
    return show


def show_image(conn, feed_url):
    r = conn.execute("SELECT v FROM kv WHERE k = ?", ("podfeed:" + feed_url,)).fetchone()
    return json.loads(r[0]).get("image") if r else None


def _feed_of_doc(conn, d):
    """A Feed item's feed address, from FreshRSS's list of subscriptions."""
    if not d.get("feed"):
        return None
    subs = json.loads((conn.execute("SELECT v FROM kv WHERE k = 'feed_subs'").fetchone() or ["[]"])[0])
    return next((s.get("url") for s in subs if s.get("id") == d["feed"] and s.get("url")), None)


def meta(conn, audio):
    r = conn.execute("SELECT * FROM gp_episodes WHERE url = ?", (audio,)).fetchone()
    return dict(r) if r else None


def ensure_meta(conn, audio, d=None, fetch=True):
    """What the feed says about an episode, reading its feed once if Daf hasn't yet (fetch)."""
    m = meta(conn, audio)
    if m and m.get("checked"):
        return m
    feed = (m or {}).get("podcast") or (_feed_of_doc(conn, d) if d else None)
    if feed and fetch:
        read_feed(conn, feed, max_age=3600)
        m = meta(conn, audio) or m
    if not m and d:                                  # an episode whose feed Daf can't read: what the doc knows
        conn.execute("INSERT OR IGNORE INTO gp_episodes (url, link, title, podcast, podcast_title, published, checked) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (audio, d.get("url"), d.get("title"), feed, d.get("source"), d.get("published"), int(time.time())))
        m = meta(conn, audio)
    return m


# ---- one episode, under all its addresses ----------------------------------------------

def keys(conn, audio):
    """The addresses an episode goes by: its own, and any other feed's copy with the same guid."""
    out = [audio]
    m = meta(conn, audio)
    if m and m.get("guid"):
        out += [r[0] for r in conn.execute("SELECT url FROM gp_episodes WHERE guid = ? AND url != ?", (m["guid"], audio))]
    return out


def docs_of(conn, audio):
    ks = keys(conn, audio)
    return [r[0] for r in conn.execute(f"SELECT id FROM docs WHERE kind = 'podcast' AND enclosure IN ({','.join('?' * len(ks))})", ks)]


def doc_for(conn, audio, create=True):
    """The doc an episode opens as: its Library copy, its Feed item, or one of its own."""
    ks = keys(conn, audio)
    r = conn.execute(f"SELECT id FROM docs WHERE kind = 'podcast' AND enclosure IN ({','.join('?' * len(ks))}) AND status != 'deleted' "
                     "ORDER BY CASE where_ WHEN 'library' THEN 0 WHEN 'feed' THEN 1 ELSE 2 END, added DESC LIMIT 1", ks).fetchone()
    if r or not create:
        return r[0] if r else None
    m = ensure_meta(conn, audio) or {}
    did = "ep:" + hashlib.sha1(audio.encode()).hexdigest()[:16]
    bl = content.blocks(m.get("notes") or "") if m.get("notes") else []
    conn.execute(
        "INSERT OR REPLACE INTO docs (id, kind, where_, status, title, author, source, category, url, published, added, words, summary, "
        "enclosure, thumb, duration) VALUES (?, 'podcast', 'podcast', 'seen', ?, ?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?)",
        (did, m.get("title") or "Podcast episode", m.get("author") or "", m.get("podcast_title") or "", m.get("link") or audio,
         m.get("published"), int(time.time()), content.words(bl), content.summary(bl), audio, m.get("image"), m.get("duration")))
    conn.execute("INSERT OR REPLACE INTO doc_content (id, blocks, fetched) VALUES (?, ?, ?)", (did, json.dumps(bl), int(time.time())))
    return did


def transcript(conn, audio):
    """(blocks, chapters, source, lang) of an episode's transcript, or None."""
    ks = keys(conn, audio)
    r = conn.execute(f"SELECT * FROM episode_text WHERE audio IN ({','.join('?' * len(ks))}) ORDER BY made DESC LIMIT 1", ks).fetchone()
    if not r:
        return None
    return json.loads(r["blocks"]), json.loads(r["chapters"] or "[]"), r["source"], r["lang"]


NOTES_HEAD = {"t": "h3", "x": "Show notes", "h": "Show notes"}


def blocks(conn, d, own):
    """What the reader shows for an episode: the transcript, then its show notes."""
    if d.get("kind") != "podcast" or not d.get("enclosure"):
        return own
    tr = transcript(conn, d["enclosure"])
    if not tr or not tr[0]:
        return own
    return tr[0] + ([NOTES_HEAD] + own if own else [])


def doc_blocks(conn, doc_id):
    """A doc's blocks as the reader has them (an episode's with its transcript)."""
    d = conn.execute("SELECT * FROM docs WHERE id = ?", (doc_id,)).fetchone()
    row = conn.execute("SELECT blocks FROM doc_content WHERE id = ?", (doc_id,)).fetchone()
    try:
        own = json.loads(row[0]) if row and row[0] else []
    except ValueError:
        own = []
    return blocks(conn, dict(d), own) if d else own


def index(conn, doc_id):
    """Search (docs_fts) finds what was said in an episode: its transcript beside its show notes.
    (doc_content's triggers index only the doc's own text.)"""
    d = conn.execute("SELECT title FROM docs WHERE id = ?", (doc_id,)).fetchone()
    if not d:
        return
    text = " ".join(b.get("x", "") for b in doc_blocks(conn, doc_id) if b.get("t") != "img")
    conn.execute("DELETE FROM docs_fts WHERE id = ?", (doc_id,))
    conn.execute("INSERT INTO docs_fts (id, title, body) VALUES (?, ?, ?)", (doc_id, d["title"] or "", text))


# ---- where you are -----------------------------------------------------------------

def position(conn, audio):
    """The last place a play anywhere stopped: (seconds, "AntennaPod" or "Daf", when), or None."""
    ks = keys(conn, audio)
    m = meta(conn, audio)
    q = f"SELECT position, total, device, timestamp FROM gp_actions WHERE action = 'play' AND (episode IN ({','.join('?' * len(ks))})"
    args = list(ks)
    if m and m.get("guid"):
        q += " OR guid = ?"
        args.append(m["guid"])
    r = conn.execute(q + ") ORDER BY timestamp DESC, id DESC LIMIT 1", args).fetchone()
    if not r or r["position"] is None:
        return None
    return {"t": int(r["position"]), "total": r["total"] or None, "from": "Daf" if r["device"] == "daf" else "AntennaPod", "at": r["timestamp"]}


def played(conn, d, started, pos, total):
    """A stretch played in Daf: a gpodder play action AntennaPod picks up on its next sync, and the
    listening time (gpodder.actions_upload makes the session)."""
    from . import gpodder
    audio = d["enclosure"]
    m = ensure_meta(conn, audio, d, fetch=False) or {}
    started, pos = max(0, int(started)), max(0, int(pos))
    gpodder.actions_upload(conn, [{"podcast": m.get("podcast") or "", "episode": audio, "action": "play", "started": started, "position": pos,
                                   "total": int(total) if total else (m.get("duration") or 0), "timestamp": int(time.time()), "device": "daf",
                                   "guid": m.get("guid")}])
    want(conn, audio, "auto")


# ---- transcripts ---------------------------------------------------------------------

def auto_on():
    return (config.load_settings().get("podcasts") or {}).get("transcribe", True) is not False


def want(conn, audio, why="auto"):
    """Transcribe an episode, unless it has its transcript, is on its way, or failed lately.
    why: "auto" (played or opened: only when Preferences says so), "ask" (the button) or "clip"."""
    from . import media
    if why == "auto" and not auto_on():
        return None
    if transcript(conn, audio):
        return "done"
    st = media.job_status(conn, "podtr", audio)
    if st and st["status"] in ("queued", "running"):
        return st["status"]
    if st and st["status"] == "failed" and why == "auto":
        tries = conn.execute("SELECT COUNT(*) FROM jobs WHERE kind = 'podtr' AND ref = ? AND status = 'failed'", (audio,)).fetchone()[0]
        if tries >= 3 or time.time() - (st.get("finished") or 0) < 6 * 3600:
            return "failed"
    media.queue(conn, "podtr", audio)
    return "queued"


def status(conn, audio):
    from . import media
    tr = transcript(conn, audio)
    if tr:
        return {"status": "done", "source": tr[2], "lang": tr[3]}
    st = media.job_status(conn, "podtr", audio)
    return {"status": st["status"] if st else None, "error": st.get("error") if st else None, "auto": auto_on()}


def _cue_items_vtt(text):
    """WebVTT or SRT cues → [(seconds, speaker, text)]. Hours are optional, as WebVTT allows."""
    out = []
    for m in re.finditer(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})\s*-->[^\n]*\n(.*?)(?=\n\s*\n|\Z)", text.replace("\r", ""), re.S):
        sec = int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) + int(m.group(4).ljust(3, "0")) / 1000
        body = m.group(5).strip()
        spk = None
        v = re.match(r"<v(?:\.[^ >]*)?\s+([^>]+)>", body)
        if v:
            spk = v.group(1).strip()
        body = html.unescape(re.sub(r"<[^>]+>", "", body)).replace("\n", " ").strip()
        if body:
            out.append((sec, spk, body))
    return _speakers(out)


def _speakers(items):
    """"Name: words" lines: a label before a colon that comes back again and again is a speaker
    (Buzzsprout's are "Jane Doe: …", emoji and all), not a "Note:" in passing."""
    label = re.compile(r"^([^:\n]{2,60}?):\s+(.+)$", re.S)
    counts = {}
    for _, spk, body in items:
        m = None if spk else label.match(body)
        if m:
            counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    names = {k for k, n in counts.items() if n >= 3 and not re.search(r"\d{1,2}:\d{2}", k)}
    out = []
    for sec, spk, body in items:
        m = None if spk else label.match(body)
        if m and m.group(1) in names:
            spk, body = m.group(1).strip(), m.group(2).strip()
        out.append((sec, _speaker(spk), body))
    return out


def _speaker(name):
    """A speaker's label without its brackets and decorations; a machine's "SPEAKER_01" is "Speaker 1"."""
    if not name:
        return None
    n = re.sub(r"^[^\w]+|[^\w]+$", "", str(name).strip())
    m = re.fullmatch(r"(?i)speaker[_ ]?0*(\d+)", n)
    return f"Speaker {int(m.group(1))}" if m else (n or None)


def _cue_items_json(text):
    d = json.loads(text)
    segs = d.get("segments") if isinstance(d, dict) else d
    out = []
    for s in segs or []:
        body = str(s.get("body") or s.get("text") or "").strip()
        if body and s.get("startTime") is not None:
            out.append((float(s["startTime"]), (s.get("speaker") or None), body))
    return out


def _cue_items_html(text):
    """The Podcasting 2.0 HTML form (<cite>, <time>, <p>), or, when there's no <time> in it, SRT cues
    dressed in HTML (Buzzsprout's: <br> for each line break)."""
    out, spk = [], None
    for m in re.finditer(r"(?:<cite>(.*?)</cite>\s*)?<time>([\d:.]+)</time>\s*<p>(.*?)</p>", text, re.S | re.I):
        if m.group(1):
            spk = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip().rstrip(":") or spk
        body = html.unescape(re.sub(r"<[^>]+>", "", m.group(3))).strip()
        if body:
            out.append((_seconds(m.group(2).split(".")[0]) or 0, spk, body))
    if out:
        return out
    plain = re.sub(r"(?i)<br\s*/?>", "\n", text)
    plain = re.sub(r"(?i)</p>", "\n\n", plain)
    return _cue_items_vtt(html.unescape(re.sub(r"<[^>]+>", "", plain)))


def _lines(items):
    """Cues (often a few words each, or single words in JSON) → lines the way the reader shows them:
    a new one for a new speaker, and one ends at a sentence's end after six seconds or 140 characters."""
    lines, cur = [], None
    for sec, spk, x in sorted(items, key=lambda i: i[0]):
        x = re.sub(r"\s+", " ", x).strip()
        if cur is not None and spk and spk != cur["spk"]:
            lines.append(cur)
            cur = None
        if cur is None:
            cur = {"ts": int(sec), "spk": spk, "x": x}
        else:
            cur["x"] += ("" if re.match(r"^[,.;:!?%)\]’']", x) else " ") + x
        if (re.search(r"[.?!][\"”’)]?$", x) and (sec - cur["ts"] >= 6 or len(cur["x"]) > 140)) or len(cur["x"]) > 600:
            lines.append(cur)
            cur = None
    if cur:
        lines.append(cur)
    return lines


def parse_transcript(text, ctype):
    ctype = (ctype or "").lower()
    if "json" in ctype or text.lstrip().startswith(("{", "[")):
        items = _cue_items_json(text)
    elif "html" in ctype or re.search(r"<time>", text, re.I):
        items = _cue_items_html(text)
    else:
        items = _cue_items_vtt(text)
    return _lines(items)


def _chapters_json(url):
    data, _ = _get(url, timeout=20)
    d = json.loads(data)
    return [{"t": float(c["startTime"]), "title": str(c.get("title") or "").strip()} for c in d.get("chapters", [])
            if c.get("startTime") is not None and c.get("toc") is not False and str(c.get("title") or "").strip()]


def _chapters_probe(src):
    """The audio file's own chapters (ID3 CHAP, MP4 chapters); ffprobe reads a remote file's head only."""
    if not shutil.which("ffprobe"):
        return []
    r = subprocess.run(["ffprobe", "-v", "error", "-user_agent", UA, "-show_chapters", "-of", "json", src],
                       capture_output=True, text=True, timeout=90)
    try:
        chs = json.loads(r.stdout or "{}").get("chapters", [])
    except ValueError:
        return []
    out = [{"t": float(c["start_time"]), "title": ((c.get("tags") or {}).get("title") or "").strip()} for c in chs]
    return [c for c in out if c["title"]]


def _download(url, folder):
    """The episode's audio into folder (on disk: /tmp is memory on this server)."""
    path = Path(folder) / "audio"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    got = 0
    with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            got += len(chunk)
            if got > MAX_AUDIO:
                raise RuntimeError("the audio is over 1.5 GB")
            f.write(chunk)
    return str(path)


def transcribe(audio):
    """The job (media.py's "podtr"): the show's own transcript if the feed links one, else whisper."""
    from . import media
    with db.session() as conn:
        d = conn.execute("SELECT * FROM docs WHERE kind = 'podcast' AND enclosure = ? LIMIT 1", (audio,)).fetchone()
        m = ensure_meta(conn, audio, dict(d) if d else None) or {}
    chapters, lines, source, lang = [], None, None, None
    if m.get("chapters_url"):
        try:
            chapters = _chapters_json(m["chapters_url"])
        except Exception as e:  # noqa: BLE001
            log.info("chapters %s: %s", m["chapters_url"], e)
    if m.get("transcript_url"):
        try:
            data, ctype = _get(m["transcript_url"], timeout=60)
            lines = parse_transcript(data.decode("utf-8", "replace"), m.get("transcript_type") or ctype)
            source = "publisher"
        except Exception as e:  # noqa: BLE001 - the show's file didn't come: whisper it is
            log.info("transcript %s: %s", m["transcript_url"], e)
            lines = None
    if lines:
        if not chapters:
            try:
                chapters = _chapters_probe(audio)
            except Exception:  # noqa: BLE001
                chapters = []
    else:
        tmpdir = config.STATE / "tmp"
        tmpdir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=tmpdir) as tmp:
            path = _download(audio, tmp)
            if not chapters:
                chapters = _chapters_probe(path)
            res = media.whisper(path)
        lines = [{"ts": int(s["start"]), "spk": None, "x": s["text"]} for s in res["segments"] if s["text"].strip()]
        source, lang = "whisper", res.get("language")
        if not lines:
            raise RuntimeError("nothing intelligible in the audio")
    bl = media._blocks_from_lines(lines, [{"start_time": c["t"], "title": c["title"]} for c in chapters])
    with db.session() as conn:
        _store(conn, audio, bl, chapters, source, lang)
    return len(bl)


def _store(conn, audio, bl, chapters, source, lang):
    """Keep a transcript, and move the show notes' highlights down past it in every doc the episode has."""
    first = not transcript(conn, audio)
    docs = docs_of(conn, audio)
    if first:
        for did in docs:
            row = conn.execute("SELECT blocks FROM doc_content WHERE id = ?", (did,)).fetchone()
            if not row or row[0] in ("[]", "", None):
                continue
            shift = len(bl) + 1                   # the transcript and the "Show notes" heading
            for h in conn.execute("SELECT id, pos FROM highlights WHERE book_id = ? AND pos IS NOT NULL", (did,)).fetchall():
                try:
                    p = json.loads(h["pos"])
                except ValueError:
                    continue
                if not isinstance(p, dict) or p.get("b") is None:
                    continue
                p["b"] += shift
                if p.get("be") is not None:
                    p["be"] += shift
                conn.execute("UPDATE highlights SET pos = ? WHERE id = ?", (json.dumps(p), h["id"]))
    conn.execute("INSERT OR REPLACE INTO episode_text (audio, blocks, chapters, source, lang, made) VALUES (?, ?, ?, ?, ?, ?)",
                 (audio, json.dumps(bl, ensure_ascii=False), json.dumps(chapters, ensure_ascii=False), source, lang, int(time.time())))
    for did in docs:
        index(conn, did)
    m = meta(conn, audio) or {}
    if m.get("duration") and docs:
        conn.execute(f"UPDATE docs SET duration = COALESCE(duration, ?) WHERE id IN ({','.join('?' * len(docs))})", [m["duration"], *docs])
    from . import vaultnotes
    s = config.load_settings()
    for did in docs:
        try:
            vaultnotes.refresh(conn, s, did)
        except Exception:  # noqa: BLE001
            log.exception("vault note for %s", did)


# ---- the episode page's own details ----------------------------------------------------

def state(conn, d, opening=True):
    """What the episode page needs besides the doc: the audio, where you were, chapters, and the
    transcript's state. Nothing here waits on the network; opening it asks for a transcript (want),
    whose job reads the feed."""
    audio = d["enclosure"]
    m = meta(conn, audio) or {}
    if opening:
        want(conn, audio, "auto")
    tr = transcript(conn, audio)
    pos = position(conn, audio)
    src = audio if audio.startswith("https://") else "/api/podcasts/audio?u=" + urllib.parse.quote(audio, safe="")
    return {"audio": src, "orig": audio, "position": pos, "duration": d.get("duration") or m.get("duration"),
            "chapters": tr[1] if tr else [], "image": m.get("image") or d.get("thumb"), "podcast": m.get("podcast_title") or d.get("source"),
            "feed": m.get("podcast"), "transcript": status(conn, audio)}



def show(conn, feed_url, limit=80):
    """A show's page: its episodes, newest first, with how far each was played."""
    read_feed(conn, feed_url)
    sub = conn.execute("SELECT title FROM gp_subs WHERE url = ?", (feed_url,)).fetchone()
    rows = [dict(r) for r in conn.execute("SELECT url, title, published, duration, guid, podcast_title FROM gp_episodes WHERE podcast = ? "
                                          "ORDER BY published DESC LIMIT ?", (feed_url, limit))]
    title = (sub["title"] if sub and sub["title"] else None) or (rows[0]["podcast_title"] if rows else feed_url)
    have = {r[0] for r in conn.execute("SELECT audio FROM episode_text")}
    out = []
    for r in rows:
        p = conn.execute("SELECT MAX(position), MAX(total) FROM gp_actions WHERE action = 'play' AND episode = ?", (r["url"],)).fetchone()
        dur = r["duration"] or p[1]
        out.append({"audio": r["url"], "title": r["title"], "published": r["published"], "duration": dur,
                    "played": p[0], "done": bool(p[0] and dur and p[0] >= dur - 60), "transcript": r["url"] in have})
    return {"feed": feed_url, "title": title, "image": show_image(conn, feed_url), "episodes": out}


def on_actions(conn, actions):
    """AntennaPod reported plays: the episodes played in the last two days get their transcripts."""
    if not auto_on():
        return
    now = time.time()
    seen = set()
    for a in actions or []:
        if not isinstance(a, dict) or str(a.get("action", "")).lower() != "play" or not a.get("episode") or a.get("device") == "daf":
            continue
        ts = a.get("timestamp")
        try:
            from .gpodder import _ts
            if now - _ts(ts) > 2 * 86400:
                continue
        except Exception:  # noqa: BLE001
            continue
        if a["episode"] in seen:
            continue
        seen.add(a["episode"])
        want(conn, a["episode"], "auto")


def clip(conn, d, t, sec=30):
    """Clip 30s on an episode with no transcript yet: the job transcribes that stretch into a
    highlight, and the whole episode gets its transcript too."""
    from . import media
    audio = d["enclosure"]
    media.queue(conn, "clip", f"{audio}#{int(t)}", {"url": audio, "pos": float(t), "sec": int(sec), "doc": d["id"], "title": d["title"]})
    want(conn, audio, "clip")
