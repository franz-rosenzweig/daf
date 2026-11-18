"""Music: your own quiet music under the page, beside Sound's scenes.

Sound's recordings are short loops Daf chooses by the scene. Music is the other shape: whole tracks
from a music library you already keep (a folder, DAF_MUSIC_DIR), played one after another at a low
volume. Daf never changes that library. What it knows about it is one file of its own, the catalogue
(STATE/music/catalogue.json): where each track is in the folder, its names and length, and what
tools/music.py and you have said about it:

- moods: the broad kinds you pick between, in any words you like ("still", "piano", "story"). A
  track can have several, since a lot of music sits between two.
- tags: the finer words under a mood ("sad", "rain", "cello"), for narrowing a mood down and for
  matching a scene.
- energy: 1 (nothing happens) to 3 (it drives).
- off: not for reading.
- gone: its file wasn't there at the last scan (the disk away, or the file moved).

A track with no mood isn't offered, so the catalogue can hold the whole library and only the part
you've sorted plays. What plays is a listening copy, an MP3 Daf makes the first time a track is
asked for (STATE/cache/music), set to one loudness so a quiet piece and a loud one sit at the same
level. A Daf without DAF_MUSIC_DIR or without a catalogue just has no Music.
"""
import contextlib
import fcntl
import hashlib
import json
import logging
import os
import random
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from . import config

log = logging.getLogger("daf.music")

ROOT = config.setting("DAF_MUSIC_DIR")                 # the music folder; empty: no Music
CATALOGUE = config.STATE / "music" / "catalogue.json"
COPIES = config.STATE / "cache" / "music"              # the listening copies (a cache: made again when gone)
KEEP = float(config.setting("DAF_MUSIC_CACHE_GB", "8")) * 1e9
LOUD = -20.0                                           # LUFS every listening copy is set to
AUDIO = (".flac", ".mp3", ".m4a", ".ogg", ".opus", ".wav", ".aiff", ".wma")
ID = re.compile(r"[0-9a-f]{12}")
WORD = re.compile(r"[^\w '&+-]+")

_lock = threading.RLock()
_cat = {"at": None, "data": None}


# ---- the catalogue ------------------------------------------------------------------------------

def track_id(path):
    """A track's id: from its place in the folder, so it stays the same from scan to scan."""
    return hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:12]


def album_id(t):
    return hashlib.sha1(f'{t.get("by") or t.get("artist") or ""}\0{t.get("album") or ""}'.encode("utf-8")).hexdigest()[:12]


def load():
    """The catalogue, {"moods": [the order they show in], "tracks": {id: track}}; read again when the file changes."""
    with _lock:
        try:
            st = CATALOGUE.stat()
        except OSError:
            _cat.update(at=None, data=None)
            return {"moods": [], "tracks": {}}
        at = (st.st_mtime_ns, st.st_size)
        if _cat["at"] != at:
            try:
                d = json.loads(CATALOGUE.read_text(encoding="utf-8"))
            except ValueError as e:
                log.warning("music: the catalogue doesn't read: %s", e)
                d = {}
            _cat.update(at=at, data={"moods": list(d.get("moods") or []), "tracks": dict(d.get("tracks") or {})})
        return _cat["data"]


@contextlib.contextmanager
def changing():
    """Held around read, change and save, so the server and tools/music.py don't write over each other."""
    with _lock:
        CATALOGUE.parent.mkdir(parents=True, exist_ok=True)
        with open(CATALOGUE.with_suffix(".lock"), "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            _cat.update(at=None, data=None)            # whatever the other one wrote, read it
            yield


def save(cat):
    with _lock:
        CATALOGUE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CATALOGUE.with_suffix(".part")
        tmp.write_text(json.dumps(cat, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(CATALOGUE)
        _cat.update(at=None, data=None)


def words(xs, most=12):
    """Mood and tag words as they're kept: lower case, plain, each once, in the order given."""
    out = []
    for x in xs if isinstance(xs, (list, tuple)) else ():
        w = " ".join(WORD.sub(" ", str(x)).lower().split())[:24].strip()
        if w and w not in out:
            out.append(w)
    return out[:most]


def offered(cat=None):
    """The tracks that can play: sorted into a mood, and not turned off."""
    cat = cat or load()
    return {i: t for i, t in cat["tracks"].items() if t.get("moods") and not t.get("off") and not t.get("gone")}


def on():
    return bool(ROOT) and Path(ROOT).is_dir() and bool(offered())


def vocabulary(most=60):
    """The tags the offered tracks carry, the most used first: the words a scene's music is asked for in
    (soundscape.py). Empty when there's no Music."""
    if not ROOT or not Path(ROOT).is_dir():
        return []
    n = {}
    for t in offered().values():
        for g in t.get("tags") or ():
            n[g] = n.get(g, 0) + 1
    return [g for g, _ in sorted(n.items(), key=lambda kv: (-kv[1], kv[0]))][:most]


def _order(cat, found):
    first = [m for m in cat.get("moods") or [] if m in found]
    return first + sorted(m for m in found if m not in first)


def summary():
    """What there is to pick from: every mood with how much it holds and the tags under it (the most
    used first), and the albums."""
    cat = load()
    can = offered(cat) if ROOT and Path(ROOT).is_dir() else {}
    moods, albums = {}, {}
    for t in can.values():
        for m in t["moods"]:
            M = moods.setdefault(m, {"id": m, "n": 0, "secs": 0.0, "tags": {}})
            M["n"] += 1
            M["secs"] += t.get("secs") or 0
            for g in t.get("tags") or ():
                M["tags"][g] = M["tags"].get(g, 0) + 1
        a = albums.setdefault(album_id(t), {"id": album_id(t), "album": t.get("album") or "", "by": t.get("by") or t.get("artist") or "",
                                             "n": 0, "secs": 0.0, "moods": {}})
        a["n"] += 1
        a["secs"] += t.get("secs") or 0
        for m in t["moods"]:
            a["moods"][m] = a["moods"].get(m, 0) + 1
    out = []
    for m in _order(cat, moods):
        M = moods[m]
        out.append({**M, "secs": round(M["secs"]), "tags": [{"id": g, "n": n} for g, n in sorted(M["tags"].items(), key=lambda kv: (-kv[1], kv[0]))]})
    al = [{**a, "secs": round(a["secs"]), "moods": [m for m, _ in sorted(a["moods"].items(), key=lambda kv: -kv[1])]} for a in albums.values()]
    al.sort(key=lambda a: (a["by"].lower(), a["album"].lower()))
    return {"on": bool(can), "moods": out, "albums": al}


def _public(i, t):
    return {"id": i, "title": t.get("title") or "", "artist": t.get("artist") or t.get("by") or "", "album": t.get("album") or "",
            "album_id": album_id(t), "secs": t.get("secs") or 0, "moods": t.get("moods") or [], "tags": t.get("tags") or [],
            "energy": t.get("energy") or None, "src": f"/api/music/tracks/{i}.mp3"}


def fit(t, match):
    """How well a track suits what a scene asks for ({tags, energy}): a point for each tag they
    share, less for every step its energy is away."""
    want = set(match.get("tags") or ())
    s = float(len(want & set(t.get("tags") or ())))
    if match.get("energy") and t.get("energy"):
        s -= 0.75 * abs(int(match["energy"]) - int(t["energy"]))
    return s


def queue(moods=(), tags=(), album=None, recent=(), n=25, match=None, rng=random):
    """The next tracks to play.

    - album: that album, in its order.
    - moods and tags: a shuffle of the tracks in any of those moods (every mood, with none named),
      kept to those with any of those tags when tags are named. What played lately comes last, and
      two from one album don't follow each other when it can be helped.
    - match ({tags, energy}, from the scene): the same pool, the tracks that fit best first.
    """
    can = offered()
    if album:
        rows = [(i, t) for i, t in can.items() if album_id(t) == album]
        rows.sort(key=lambda r: (r[1].get("disc") or 1, r[1].get("n") or 0, r[1].get("path") or ""))
        return [_public(i, t) for i, t in rows]
    moods, tags = set(words(moods)), set(words(tags))
    pool = [(i, t) for i, t in can.items() if (not moods or moods & set(t["moods"])) and (not tags or tags & set(t.get("tags") or ()))]
    recent = list(recent or ())
    late = {i: k for k, i in enumerate(recent)}
    fresh = [r for r in pool if r[0] not in late]
    old = sorted((r for r in pool if r[0] in late), key=lambda r: late[r[0]])      # longest ago first
    if match and (match.get("tags") or match.get("energy")):
        scored = sorted(((fit(t, match), rng.random(), i, t) for i, t in fresh), key=lambda x: (-x[0], x[1]))
        if scored:
            best = scored[0][0]
            # the ones about as good as the best, at least a dozen so it isn't the same three each time
            top = [x for x in scored if x[0] >= best - 1] or scored
            if len(top) < 12:
                top = scored[:12]
            rng.shuffle(top)
            fresh = [(i, t) for _, _, i, t in top]
        out = _spread(fresh, n)
    else:
        rng.shuffle(fresh)
        out = _spread(fresh, n)
    if len(out) < n:
        out += old[: n - len(out)]
    return [_public(i, t) for i, t in out]


def _spread(rows, n):
    """Up to n of rows in their order, moving on past a track from the album just played while another is left."""
    out, rest, last = [], list(rows), None
    while rest and len(out) < n:
        k = next((j for j, (_, t) in enumerate(rest) if album_id(t) != last), 0)
        i, t = rest.pop(k)
        out.append((i, t))
        last = album_id(t)
    return out


def correct(i, b):
    """What you say about a track while it plays: {off}, {moods}, {tags}, {energy}. The track as it's now kept."""
    with changing():
        cat = load()
        t = cat["tracks"].get(i)
        if t is None:
            return None
        t = dict(t)
        if "off" in b:
            if b["off"]:
                t["off"] = True
            else:
                t.pop("off", None)
        if "moods" in b:
            t["moods"] = words(b["moods"], 6)
        if "tags" in b:
            t["tags"] = words(b["tags"])
        if "energy" in b:
            try:
                t["energy"] = min(3, max(1, int(b["energy"])))
            except (TypeError, ValueError):
                t.pop("energy", None)
        t["said"] = int(time.time())                   # yours: a later first-pass tagging leaves it alone
        new = {"moods": list(cat.get("moods") or []), "tracks": {**cat["tracks"], i: t}}
        for m in t.get("moods") or ():                 # a mood nobody had yet goes at the end of the row
            if m not in new["moods"]:
                new["moods"].append(m)
        save(new)
        return {**_public(i, t), "off": bool(t.get("off"))}


# ---- the listening copies -----------------------------------------------------------------------

def source(t):
    """A track's file in the music folder; None when there's no folder, or the path would leave it."""
    if not ROOT or not t.get("path"):
        return None
    root = Path(ROOT).resolve()
    p = (root / t["path"]).resolve()
    return p if p.is_relative_to(root) and p.is_file() else None


def measure(path, timeout=600):
    """A file's loudness as ffmpeg's EBU R 128 meter hears it: {lufs, peak (dBTP), range (LU)}."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0", "-af", "ebur128=peak=true:framelog=quiet", "-f", "null", "-"],
                       capture_output=True, text=True, timeout=timeout, check=False)
    tail = r.stderr[r.stderr.rfind("Summary:"):] if "Summary:" in r.stderr else ""
    def num(label):
        m = re.search(label + r":\s*(-?[\d.]+|-?inf)", tail)
        return float(m.group(1)) if m and "inf" not in m.group(1) else None
    out = {"lufs": num(r"\bI"), "range": num(r"\bLRA"), "peak": num(r"\bPeak")}
    if out["lufs"] is None:
        raise RuntimeError("ffmpeg couldn't measure it: " + (r.stderr.strip().splitlines() or ["no answer"])[-1][:200])
    return out


def gain(lufs, peak):
    """The decibels that bring a track to LOUD without its peaks clipping, at most 12 either way."""
    if lufs is None:
        return 0.0
    g = LOUD - lufs
    if peak is not None:
        g = min(g, -1.0 - peak)
    return round(max(-12.0, min(12.0, g)), 2)


_making = {}
_few = threading.BoundedSemaphore(2)


def copy_of(i):
    """The listening copy of a track, made now if it isn't there. None: no such track, or its file is gone."""
    t = offered().get(i)
    if t is None:
        return None
    out = COPIES / f"{i}.mp3"
    if out.exists():
        os.utime(out)                                  # played lately: pruned last
        return out
    src = source(t)
    if src is None or not shutil.which("ffmpeg"):
        return None
    with _lock:
        mine = _making.setdefault(i, threading.Lock())
    with mine, _few:
        if out.exists():
            return out
        COPIES.mkdir(parents=True, exist_ok=True)
        if t.get("lufs") is None:
            try:
                m = measure(src)
            except Exception as e:                    # noqa: BLE001 - it plays at its own level then
                log.warning("music: measuring %s: %s", i, e)
                m = {}
            if m:
                with changing():
                    cat = load()
                    if i in cat["tracks"]:
                        t = {**cat["tracks"][i], **{k: v for k, v in m.items() if v is not None}}
                        save({"moods": cat["moods"], "tracks": {**cat["tracks"], i: t}})
        tmp = out.with_suffix(".part.mp3")
        cmd = ["ffmpeg", "-hide_banner", "-v", "error", "-y", "-i", str(src), "-map", "0:a:0", "-vn", "-map_metadata", "-1",
               "-af", f"volume={gain(t.get('lufs'), t.get('peak'))}dB", "-ac", "2", "-c:a", "libmp3lame", "-q:a", "4", str(tmp)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900, check=False)
        if r.returncode or not tmp.exists() or tmp.stat().st_size < 2000:
            tmp.unlink(missing_ok=True)
            log.warning("music: copying %s: %s", i, r.stderr.strip()[-300:])
            return None
        tmp.replace(out)
    prune()
    return out


def ahead(ids):
    """Makes the copies of the tracks about to play, in the background, so the next one starts at once."""
    def run():
        for i in ids:
            try:
                copy_of(i)
            except Exception as e:                    # noqa: BLE001
                log.warning("music: ahead %s: %s", i, e)
    if ids:
        threading.Thread(target=run, daemon=True, name="music-ahead").start()


def prune():
    """Keeps the listening copies under KEEP bytes: the ones played longest ago go first."""
    try:
        files = [(f.stat().st_mtime, f.stat().st_size, f) for f in COPIES.glob("*.mp3") if not f.name.endswith(".part.mp3")]
    except OSError:
        return
    total = sum(s for _, s, _ in files)
    for _, s, f in sorted(files):
        if total <= KEEP:
            break
        f.unlink(missing_ok=True)
        total -= s


# ---- the routes ---------------------------------------------------------------------------------

def router():
    from fastapi import APIRouter, Depends, HTTPException
    from fastapi.responses import FileResponse
    from starlette.concurrency import run_in_threadpool

    from .app import json_body, user, user_or_device

    r = APIRouter()

    @r.get("/api/music", dependencies=[Depends(user_or_device)])
    def get_music():
        """{on, moods: [{id, n, secs, tags: [{id, n}]}], albums: [{id, album, by, n, secs, moods}]}."""
        return summary()

    @r.post("/api/music/queue", dependencies=[Depends(user_or_device)])
    async def post_queue(b=Depends(json_body)):
        """{moods, tags, album, recent, n, match: {tags, energy}} → {tracks}: what to play next (queue)."""
        try:
            n = min(60, max(1, int(b.get("n") or 25)))
        except (TypeError, ValueError):
            n = 25
        album = b.get("album") if isinstance(b.get("album"), str) and ID.fullmatch(b.get("album")) else None
        recent = [x for x in b.get("recent") or () if isinstance(x, str) and ID.fullmatch(x)][:400] if isinstance(b.get("recent"), list) else []
        match = b.get("match") if isinstance(b.get("match"), dict) else None
        if match:
            match = {"tags": words(match.get("tags")), "energy": match.get("energy") if match.get("energy") in (1, 2, 3) else None}
        tracks = await run_in_threadpool(queue, b.get("moods") or (), b.get("tags") or (), album, recent, n, match)
        ahead([t["id"] for t in tracks[:2]])
        return {"tracks": tracks}

    @r.get("/api/music/tracks/{name}.mp3", dependencies=[Depends(user_or_device)])
    async def get_track(name: str):
        """A track's listening copy (made the first time it's asked for); takes Range, so it can be moved about in."""
        if not ID.fullmatch(name):
            raise HTTPException(404, "No such track")
        p = await run_in_threadpool(copy_of, name)
        if p is None:
            raise HTTPException(404, "This track isn't here")
        return FileResponse(p, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=86400"})

    @r.post("/api/music/tracks/{name}", dependencies=[Depends(user)])
    async def post_track(name: str, b=Depends(json_body)):
        """{off, moods, tags, energy}: what you say about a track (correct)."""
        if not ID.fullmatch(name):
            raise HTTPException(404, "No such track")
        t = await run_in_threadpool(correct, name, b)
        if t is None:
            raise HTTPException(404, "No such track")
        return t

    return r
