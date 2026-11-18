#!/usr/bin/env python3
"""Music's catalogue (daf/music.py): what Daf knows about the music folder, kept in STATE/music.

    tools/music.py scan [--only FOLDER] [--forget]   read the folder (DAF_MUSIC_DIR) into the catalogue
    tools/music.py tag FILE                moods, tags and energy from a tagging file
    tools/music.py measure [--all]         the loudness of the tracks that have a mood
    tools/music.py show                    what the catalogue holds, by mood and tag

scan never touches the music: it reads each file's names and length with ffprobe and adds the track,
with no mood yet. A track it already has keeps everything said about it, and one whose file moved
(the same title, album and length somewhere else) keeps it under its new place.

A tagging file is JSON, {"order": [the moods, in the order they show], "places": {place: {moods,
tags, energy, off}}}. A place is a folder ("Some Band/An Album/"), the start of a path, or one
file; the longer place wins, field by field, so an album can set the moods and one track in it its
own tags. What you've said about a track in Daf (its "said") is left alone unless --over is given.

A track whose file is gone keeps its place in the catalogue while it has a mood (the disk may just
be away), marked gone and not offered; scan --forget drops those.

measure is the slow one (it decodes every track): run it under a lid, `heavy tools/music.py measure`.
"""
import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from daf import music  # noqa: E402


def probe(path):
    """A file's names and length from ffprobe: {title, artist, album, by, n, disc, secs}; None if it isn't audio."""
    r = subprocess.run(["ffprobe", "-v", "error", "-of", "json", "-show_entries", "format=duration:format_tags:stream=codec_type:stream_tags", str(path)],
                       capture_output=True, text=True, timeout=60, check=False)
    try:
        d = json.loads(r.stdout or "{}")
    except ValueError:
        return None
    streams = d.get("streams") or []
    if not any(s.get("codec_type") == "audio" for s in streams):
        return None
    tags = {}
    for src in [s.get("tags") or {} for s in streams if s.get("codec_type") == "audio"] + [(d.get("format") or {}).get("tags") or {}]:
        for k, v in src.items():
            tags[k.lower().replace(" ", "_")] = str(v).strip()

    def num(*keys):
        for k in keys:
            try:
                return int(str(tags.get(k) or "").split("/")[0])
            except ValueError:
                pass
        return None

    try:
        secs = round(float((d.get("format") or {}).get("duration") or 0), 1)
    except ValueError:
        secs = 0
    return {"title": tags.get("title") or Path(path).stem, "artist": tags.get("artist") or "", "album": tags.get("album") or "",
            "by": tags.get("album_artist") or tags.get("albumartist") or "", "n": num("track", "tracknumber"), "disc": num("disc", "discnumber"), "secs": secs}


def files(root, only=None):
    base = root / only if only else root
    for p in sorted(base.rglob("*")):
        if p.suffix.lower() in music.AUDIO and p.is_file() and not any(part.startswith(".") for part in p.relative_to(root).parts):
            yield p


def _same(t):
    """What tells a track that moved from another: its title, album and whole seconds."""
    return (t.get("title") or "", t.get("album") or "", round(t.get("secs") or 0))


def scan(root, only=None, workers=6, forget=False, say=print):
    """Reads the folder into the catalogue. → (new, kept, moved, gone)."""
    found = list(files(root, only))
    if not found:                                      # an empty or unmounted folder: nothing is forgotten over that
        raise SystemExit(f"No music found in {root / only if only else root}")
    rel = {p: p.relative_to(root).as_posix() for p in found}
    todo = [p for p in found if music.track_id(rel[p]) not in music.load()["tracks"]]
    with ThreadPoolExecutor(workers) as ex:
        probed = dict(zip(todo, ex.map(probe, todo)))
    with music.changing():
        return _scan(root, only, forget, say, found, rel, probed)


def _scan(root, only, forget, say, found, rel, probed):
    cat = music.load()
    old = dict(cat["tracks"])
    tracks = {}
    new = kept = moved = 0
    scope = (only.rstrip("/") + "/") if only else ""
    for i, t in old.items():                           # what's outside this scan stays as it is
        if scope and not str(t.get("path") or "").startswith(scope):
            tracks[i] = t
    lost = {}                                          # (title, album, whole seconds) → the track whose file is gone
    for i, t in old.items():
        if i not in tracks and not (root / str(t.get("path") or "")).is_file():
            lost[_same(t)] = t
    for p in found:
        i = music.track_id(rel[p])
        if i in old:
            tracks[i] = {k: v for k, v in old[i].items() if k != "gone"}
            kept += 1
            continue
        t = probed.get(p) or probe(p)
        if t is None:
            continue
        was = lost.pop(_same(t), None)
        if was:                                        # the same track somewhere new: what was said about it comes along
            t = {**{k: v for k, v in was.items() if k != "gone"}, **{k: v for k, v in t.items() if v not in (None, "")}}
            moved += 1
        else:
            new += 1
        tracks[i] = {**{k: v for k, v in t.items() if v not in (None, "")}, "path": rel[p]}
    gone = len(lost)
    if not forget:                                     # a sorted track whose file is away stays, marked
        for t in lost.values():
            if t.get("moods") or t.get("said"):
                tracks[music.track_id(t["path"])] = {**t, "gone": True}
    music.save({"moods": cat["moods"], "tracks": tracks})
    say(f"{len(tracks)} tracks: {new} new, {kept} as they were, {moved} moved, {gone} gone")
    return new, kept, moved, gone


def tag(rules, over=False, say=print):
    """Moods, tags and energy onto the tracks a tagging file names. → how many tracks it changed."""
    with music.changing():
        return _tag(rules, over, say)


def _tag(rules, over, say):
    cat = music.load()
    said_for = rules.get("places") or {}
    places = sorted(said_for, key=len)                 # the longer (closer) place last, so it wins
    n = 0
    tracks = dict(cat["tracks"])
    for i, t in tracks.items():
        path = str(t.get("path") or "")
        said = {}
        for place in places:
            if path.startswith(place):
                said.update(said_for[place])
        if not said or (t.get("said") and not over):
            continue
        t = dict(t)
        if "moods" in said:
            t["moods"] = music.words(said["moods"], 6)
        if "tags" in said:
            t["tags"] = music.words(said["tags"])
        if "energy" in said:
            t["energy"] = min(3, max(1, int(said["energy"])))
        if "off" in said:
            if said["off"]:
                t["off"] = True
            else:
                t.pop("off", None)
        if t != tracks[i]:
            tracks[i] = t
            n += 1
    order = music.words(rules.get("order"), 40) or list(cat["moods"])
    music.save({"moods": order, "tracks": tracks})
    say(f"{n} tracks tagged")
    return n


def measure(every=False, workers=3, say=print):
    """Loudness for the tracks that have a mood (or every track) and haven't been measured."""
    cat = music.load()
    todo = [(i, t) for i, t in cat["tracks"].items() if t.get("lufs") is None and (every or t.get("moods"))]
    say(f"{len(todo)} to measure")
    done, t0 = {}, time.time()

    def one(row):
        i, t = row
        src = music.source(t)
        if src is None:
            return i, None
        try:
            return i, music.measure(src)
        except Exception as e:                        # noqa: BLE001
            say(f"  {i}: {e}")
            return i, None

    with ThreadPoolExecutor(workers) as ex:
        for k, (i, m) in enumerate(ex.map(one, todo), 1):
            if m:
                done[i] = {a: b for a, b in m.items() if b is not None}
            if k % 200 == 0 or k == len(todo):
                _keep(done)
                say(f"  {k} of {len(todo)} ({time.time() - t0:.0f} s)")
    return len(done)


def _keep(done):
    with music.changing():                             # one writer at a time, with the server
        cat = music.load()
        tracks = dict(cat["tracks"])
        for i, m in done.items():
            if i in tracks:
                tracks[i] = {**tracks[i], **m}
        music.save({"moods": cat["moods"], "tracks": tracks})


def show(say=print):
    cat = music.load()
    can = music.offered(cat)
    say(f'{len(cat["tracks"])} tracks, {len(can)} with a mood, {sum(t.get("secs") or 0 for t in can.values()) / 3600:.1f} hours')
    for m in music.summary()["moods"]:
        say(f'{m["id"]:14} {m["n"]:5}  {m["secs"] / 3600:5.1f} h   ' + ", ".join(f'{g["id"]} {g["n"]}' for g in m["tags"][:14]))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("--only")
    s.add_argument("--forget", action="store_true")
    t = sub.add_parser("tag")
    t.add_argument("file")
    t.add_argument("--over", action="store_true")
    m = sub.add_parser("measure")
    m.add_argument("--all", action="store_true")
    sub.add_parser("show")
    a = ap.parse_args()
    if a.cmd != "show" and a.cmd != "tag" and not music.ROOT:
        sys.exit("DAF_MUSIC_DIR isn't set (the environment, or STATE/daf.env)")
    if a.cmd == "scan":
        scan(Path(music.ROOT), a.only, forget=a.forget)
    elif a.cmd == "tag":
        tag(json.loads(Path(a.file).read_text(encoding="utf-8")), a.over)
    elif a.cmd == "measure":
        measure(a.all)
    else:
        show()


if __name__ == "__main__":
    main()
