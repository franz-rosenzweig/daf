"""Sound: a quiet bed of recorded sound under the book, that follows the scene you're in.

The model reads a part of the book once (a chapter, or a long one's half) and says where its scenes
change and what each would sound like, in Daf's own sounds (SOUNDS): rain on the moor, a fire in a
hall, the sea from a ship's deck, a crowd in an inn, or for a book of essays or prayer, some quiet
music. Daf keeps what it said (table soundscapes) and, wherever you are, gives the scene you're in,
so the reader (web/sound.js) can fade from one bed into the next.

Where you are comes as the reader's place (its CFI, fraction and the words on the page) or the
Kindle's (the plugin's page, POST /api/kindle/where): audiomap.py finds it in the book's text, the
same way it finds the audiobook's place. A part is read when you first get to it, and the next one
while you read on, so most of the time it's there already.

The sounds are recordings, all Creative Commons 0 (public domain): seamless loops with half a
second of their own end before them and of their start after them (PAD in sound.js), each kind at
one loudness. Thirty are the ones Chataltul plays (BORROWED): Daf keeps a copy in STATE/sounds,
fetched from DAF_SOUNDS_URL the first time one is needed. The rest are Daf's own (OWN), which
tools/sounds.py makes into STATE/sounds from recordings on Freesound, with sounds.json beside them
naming each one's recording and who made it. A Daf without those files just doesn't offer them.
"""
import bisect
import functools
import json
import logging
import os
import re
import threading
import time
import urllib.request
import zipfile

from lxml import etree

from . import ai, audiomap, config, db, ebooks

log = logging.getLogger("daf.soundscape")

# id: (file, what it sounds like and where it fits: the model chooses by this). Chataltul's, fetched
# from SOURCE the first time one is needed.
BORROWED = {
    "rain": ("rain-1", "steady rain"),
    "drizzle": ("lightrain-1", "soft rain over open country"),
    "downpour": ("heavyrain-1", "a heavy downpour"),
    "thunderstorm": ("thunder-1", "rain with rolling thunder"),
    "far-storm": ("farstorm-1", "a summer night with thunder far off, crickets close"),
    "gale": ("wind-1", "wind howling round a house: a winter storm, a blizzard, a gale"),
    "empty-wind": ("hollowwind-1", "a thin, distant wind: open moor, tundra, a ruin, desolation"),
    "hearth": ("hearth-1", "a fire in a fireplace, indoors"),
    "campfire": ("crackle-1", "a crackling fire with snaps and pops: a camp, a forge, a burning"),
    "stove": ("sauna-1", "a wood stove burning steady: a small warm room, a cabin, a kitchen"),
    "great-hall": ("bigroom-1", "a big fire in a large room that rings: a hall, a castle, a church"),
    "surf": ("waves-1", "slow surf on a beach"),
    "rough-sea": ("bigwaves-1", "big waves hitting the shore: a storm at sea, cliffs"),
    "ocean": ("ocean-1", "breakers coming in: by the sea, a harbour, a ship's deck"),
    "stream": ("stream-1", "a brook or a river"),
    "forest": ("birds-1", "dawn chorus in a pine forest: woods, morning"),
    "garden": ("springbirds-1", "birds in spring: a garden, a village, the countryside by day"),
    "meadow": ("birdsong-1", "birdsong on a warm day: fields, a road, a park"),
    "jungle": ("rainforest-1", "drops on leaves in a rainforest, a shower now and then"),
    "night": ("night-1", "crickets and cicadas on a warm night outdoors"),
    "crickets": ("crickets-1", "just crickets: a still night, a porch, a field"),
    "crowd": ("cafeteria-1", "a busy crowd indoors: a tavern, a feast, a market hall, a school"),
    "murmur": ("cafe-1", "quiet talk and the odd cup: a café, an inn, a restaurant"),
    "chatter": ("copenhagen-1", "people chatting outdoors: a street, a square, a terrace"),
    "city-night": ("city-1", "a quiet city street at night, the odd car"),
    "calm": ("wandering-1", "music: slow, calm synths (reflection, peace, an essay)"),
    "vast": ("dunes-1", "music: wide and spacey (deserts, the sky, space, awe)"),
    "sacred": ("angelic-1", "music: soft drifting chords (prayer, the holy, wonder)"),
    "meditative": ("bowls-1", "music: singing bowls, waves and a bird (meditation, healing)"),
    "gong": ("tibetan-1", "music: a singing bowl and a gong (stillness, ritual)"),
}
# Daf's own: tools/sounds.py makes them into DIR (its PICKS say from which recordings).
OWN = {
    # Rain and storms
    "rain-tent": ("rain-tent-1", "rain pattering on a tent, from inside: camping, a soldier's bivouac, a night in the open"),
    "rain-window": ("rain-window-1", "rain on a window and its sill, heard from inside: a rainy day in a room, a study"),
    "tin-roof": ("tin-roof-1", "rain drumming on a metal roof, from inside: a hut, a shed, a shack, the tropics"),
    "rain-roof": ("rain-roof-1", "rain on the roof, heard from the attic: a house in the rain, a bedroom under the eaves"),
    "rain-car": ("rain-car-1", "rain on the roof of a parked car, from inside: waiting in a car, a stakeout"),
    "rain-city": ("rain-city-1", "rain falling on a quiet city street: wet pavements, a town in the rain"),
    "rain-leaves": ("rain-leaves-1", "a shower falling on the leaves of a forest: rain in the woods, a jungle path"),
    "gutter": ("gutter-1", "rain running down a gutter and dripping: a porch, a doorway, a yard in the rain"),
    "drips": ("drips-1", "water dripping softly after the rain: the shower is over, a wet garden, a leaking roof"),
    "storm-trees": ("storm-trees-1", "a storm in the trees: wind roaring through branches and rain, a wild night outdoors"),
    "storm-tent": ("storm-tent-1", "wind and rain shaking a tent: a storm at camp, an expedition, the mountains"),
    "umbrella": ("umbrella-1", "rain pattering on an umbrella: walking in the rain, waiting at a stop"),
    # Wind, snow and sand
    "wind-trees": ("wind-trees-1", "wind rustling through big trees at night: a windy evening, a wood, a garden"),
    "wind-grass": ("wind-grass-1", "wind blowing through dry grass: a prairie, a field, the steppe, open plains"),
    "reeds": ("reeds-1", "wind in the reeds, birds here and there: a marsh, a riverbank, the fens"),
    "mountain": ("mountain-1", "wind on a mountainside, in gusts: a summit, a pass, the hills, a climb"),
    "desert-wind": ("desert-wind-1", "a dry wind moaning across empty ground: a desert, a wasteland, a ruin in the sun"),
    "sandstorm": ("sandstorm-1", "a sandstorm: hot wind roaring, sand hissing, a caravan caught in the desert"),
    "polar-wind": ("polar-wind-1", "a cold wind over ice and snow: the Arctic, a frozen shore, a winter expedition"),
    "snowfall": ("snowfall-1", "snow falling softly at night, everything muffled: a winter town, a snowy evening"),
    "autumn": ("autumn-1", "a cold, quiet wood in late autumn: bare trees, a few birds, a breeze in dry leaves"),
    "barn-wind": ("barn-wind-1", "inside a barn in a strong wind: creaking boards and rattles, a farm in a storm"),
    # Water
    "river": ("river-1", "a wide river flowing past in the evening: a riverbank, a bridge, a ford"),
    "waterfall": ("waterfall-1", "a mountain waterfall, steady and close: a gorge, a cascade, a hike"),
    "lake": ("lake-1", "small waves lapping on a lake shore, a bird now and then: a quiet lake, a pond"),
    "pebbles": ("pebbles-1", "waves rolling the pebbles on a shingle beach: a cold coast, a cove"),
    "canal": ("canal-1", "a canal in the early morning: water lapping at the stones, a boat, a gull"),
    "fountain": ("fountain-1", "a fountain splashing in a courtyard garden, birds: a cloister, a palace garden"),
    "watermill": ("watermill-1", "a watermill's wheel turning and splashing: a mill, a millstream, an old village"),
    "underwater": ("underwater-1", "under the water: a deep muffled hush with bubbles, diving, a submarine, drowning"),
    "cave": ("cave-1", "water dripping in a cave, ringing off the rock: a cavern, a mine, a cellar, a grotto"),
    "sea-cave": ("sea-cave-1", "drips in a sea cave with the waves booming outside: a smugglers' cave, a cliff"),
    # Ships and the sea
    "ship": ("ship-1", "a big wooden ship creaking and groaning on the swell: below decks on a sailing ship"),
    "engine-room": ("engine-room-1", "a ship's engines humming below decks: a steamer, a ferry, a cabin at sea"),
    "sailing": ("sailing-1", "inside a sailboat's cabin, water rushing past the hull: a voyage, a yacht at sea"),
    "rowing": ("rowing-1", "paddles dipping as a small boat moves over calm water: a rowing boat, a canoe"),
    "harbour": ("harbour-1", "a harbour: boats, water against the quay, gulls, the sea beyond"),
    "gulls": ("gulls-1", "gulls and small birds over waves on a rocky shore: a coast, an island"),
    "river-boat": ("river-boat-1", "a motor boat chugging along a river: a river journey, a launch, a ferry"),
    "rigging": ("rigging-1", "wind in the rigging of moored boats, lines clinking on masts: a marina, a quay"),
    # Getting around
    "train": ("train-1", "inside a train carriage, the wheels clacking on the rails: a journey by rail"),
    "steam-train": ("steam-train-1", "inside an old steam train's carriage, rumbling along: a journey long ago"),
    "station": ("station-1", "a big railway station: a train idling, people waiting, the hall's echo"),
    "subway": ("subway-1", "riding the underground through a tunnel: the subway, the metro, the Tube"),
    "bus": ("bus-1", "riding a bus: the engine, the road, a stop now and then"),
    "car": ("car-1", "inside a car on an open road, windows up: a drive, a road trip, a getaway"),
    "airplane": ("airplane-1", "the steady roar inside an airliner's cabin: a flight, a long-haul trip"),
    "carriage": ("carriage-1", "riding in a horse-drawn carriage: hooves and wheels on a country road"),
    "spaceship": ("spaceship-1", "the low hum inside a spaceship: a starship's corridor, a cabin in orbit"),
    "tram": ("tram-1", "riding a streetcar through town: a tram, a trolley, the city going by"),
    # Towns and crowds
    "city-day": ("city-day-1", "a busy city by day, heard from a balcony: traffic, buses, a modern town"),
    "road": ("road-1", "a road with light traffic and birds: a suburb, a small town, a street by day"),
    "market": ("market-1", "a busy market: stalls, shoppers, chatter in the open air, a market square"),
    "bazaar": ("bazaar-1", "a bazaar in an old Middle Eastern city at evening: a souk, the Old City, alleys"),
    "fair": ("fair-1", "a fairground: rides, a crowd, music in the distance, a carnival, a funfair"),
    "pub": ("pub-1", "a busy pub or bar, all talk and clatter: a tavern at night, a saloon"),
    "big-crowd": ("big-crowd-1", "a big crowd outdoors, talking: a festival, a rally, a fair, a busy square"),
    "party": ("party-1", "a party in the next room, voices muffled through the wall"),
    "museum": ("museum-1", "a museum or gallery: footsteps on hard floors, hushed voices in big rooms"),
    "fireworks": ("fireworks-1", "fireworks bursting far away over a town: a celebration, New Year's night"),
    # Rooms and buildings
    "church-bells": ("church-bells-1", "church bells ringing out over a town: a Sunday, a wedding, a holiday"),
    "cathedral": ("cathedral-1", "the hush of a cathedral: a vast stone room, a door far off, the city outside"),
    "prayer-hall": ("prayer-hall-1", "people murmuring in a big echoing hall: a church or synagogue before the service"),
    "library": ("library-1", "a library: pages, footsteps and the odd hushed voice far off, a reading room"),
    "clock": ("clock-1", "a clock ticking in a quiet room: waiting, a study, a sickroom, a long night"),
    "quiet-flat": ("quiet-flat-1", "a small flat late at night: a clock in the kitchen, the city far off, stillness"),
    "hall": ("hall-1", "a large hall full of quiet people: a courtroom before the judge comes, a lecture"),
    "hospital": ("hospital-1", "a hospital corridor: a quiet hum, doors, a ward at night, a waiting room"),
    "hotel": ("hotel-1", "a hotel lobby in the morning: soft voices, the street outside, a grand hotel"),
    "prison": ("prison-1", "a prison: voices echoing down hard corridors, a cell block, a jail"),
    "kitchen": ("kitchen-1", "something frying in a pan: a kitchen, breakfast cooking, a cook at the stove"),
    "fan": ("fan-1", "an electric fan humming: a hot room, a summer afternoon indoors, a sickbed"),
    "pencil": ("pencil-1", "a pencil writing on paper: a letter, a diary, homework, someone at a desk"),
    "tunnel": ("tunnel-1", "a tunnel: dripping water and wind at its mouth, rain outside, an underpass, a cellar"),
    # Work
    "machine-hall": ("machine-hall-1", "a big room humming with machines: an engine room, a power station, a laboratory"),
    "factory": ("factory-1", "a factory floor: machines running, a steady industrial din, a mill town"),
    "forge": ("forge-1", "a forge's fire roaring under the bellows: a blacksmith's, a foundry"),
    "printing-press": ("printing-press-1", "a printing works: presses running, a newspaper being printed, a big machine hall"),
    "workshop": ("workshop-1", "a quiet workshop: a clock, a low hum, birds outside, a craftsman's bench"),
    "typewriter": ("typewriter-1", "someone typing on an old typewriter: an office, a newsroom, a writer at work"),
    # Woods, fields and animals
    "frogs": ("frogs-1", "a chorus of frogs and toads: a pond or marsh on a spring night"),
    "pond-night": ("pond-night-1", "a pond at night: frogs, crickets and insects, a swamp, a bayou"),
    "owl": ("owl-1", "an owl calling in the dark: a night in the woods, an old house at night"),
    "cicadas": ("cicadas-1", "cicadas at midday in the heat: southern countryside, olive groves, siesta"),
    "heat": ("heat-1", "a drowsy hot summer afternoon in a field: insects humming, heat haze"),
    "bees": ("bees-1", "bees humming at a hive: an orchard, a garden in summer, a beekeeper"),
    "jungle-day": ("jungle-day-1", "a tropical jungle by day: insects, exotic birds, a river through the forest"),
    "evening": ("evening-1", "evening in the countryside: birds settling, a field at dusk, a farm far off"),
    "night-farm": ("night-farm-1", "a summer night near a farm: crickets, insects, a bird now and then"),
    "crows": ("crows-1", "crows calling in fog, small birds: a bare wood, a churchyard, a grey morning"),
    "loons": ("loons-1", "loons calling across a lake: a northern lake at dusk, wilderness"),
    "sheep": ("sheep-1", "a flock of sheep with bells: a hillside pasture, a shepherd, the hills"),
    "farmyard": ("farmyard-1", "a farm by day: birds, animals here and there, a breeze, the countryside"),
    "wolves": ("wolves-1", "a pack of wolves howling in the dark: a winter forest, the wild, a lonely night"),
    "cowbells": ("cowbells-1", "cows grazing with their bells: an alpine meadow, a high pasture, a mountain farm"),
    # Music
    "piano": ("piano-1", "music: soft piano and guitar, slow and open (thought, memory, a letter)"),
    "melancholy": ("melancholy-1", "music: a slow, sad cello with muted piano (sorrow, loss, a farewell)"),
    "guitar": ("guitar-1", "music: slow ambient guitar, bright and warm (hope, morning, a journey)"),
    "harp": ("harp-1", "music: a dreamy harp drifting (wonder, a fairy tale, childhood)"),
    "choir": ("choir-1", "music: wordless voices, an ethereal choir (prayer, heaven, grief)"),
    "drone": ("drone-1", "music: a deep, sacred drone (a sanctuary, awe, the holy)"),
    "warm-drone": ("warm-drone-1", "music: a warm, low pad that barely moves (rest, night, a quiet mind)"),
    "dread": ("dread-1", "music: dark, uneasy drones (dread, suspense, something wrong)"),
    "organ": ("organ-1", "music: a church organ playing slowly (a service, a funeral, a wedding, a cathedral)"),
}
SOUNDS = {**BORROWED, **OWN}
SOURCE = os.environ.get("DAF_SOUNDS_URL") or "https://stuffs.tiresia.xyz/kavana/audio/"
DIR = config.STATE / "sounds"
PART_MIN, PART_MAX = 3000, 45000         # characters: a part shorter joins the next; a longer one is cut at a paragraph
RETRY = 600                              # seconds before a part the model failed on is tried again
LEAF = ("p", "li", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "dd", "dt", "figcaption", "pre", "div", "td")

# ---- the sounds -------------------------------------------------------------------------------

_fetch = threading.Lock()


def offered():
    """The sounds this Daf can play, as SOUNDS: every borrowed one (fetched when it's first needed),
    and those of its own whose file is here."""
    return {k: v for k, v in SOUNDS.items() if k in BORROWED or (DIR / f"{v[0]}.mp3").exists()}


def sound_file(name):
    """The path of a sound's recording, a borrowed one fetched from SOURCE the first time; None for no
    such sound, or one of Daf's own that isn't here."""
    s = SOUNDS.get(name)
    if not s:
        return None
    p = DIR / f"{s[0]}.mp3"
    if p.exists():
        return p
    if name not in BORROWED:
        return None
    with _fetch:
        if p.exists():
            return p
        DIR.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(SOURCE.rstrip("/") + f"/{s[0]}.mp3", headers={"User-Agent": "Daf"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        if len(data) < 10000:
            raise RuntimeError("The sound didn't come")
        tmp = p.with_suffix(".part")
        tmp.write_bytes(data)
        tmp.replace(p)
    return p


# ---- the book in parts, and its paragraphs ---------------------------------------------------

def _book(conn, book_id):
    """(audiomap's book, its file's key) or (None, why)."""
    path, fmt = ebooks.book_file(conn, book_id)
    if not path:
        return None, "Daf has no file for this book"
    if fmt not in ("EPUB", "KEPUB"):
        return None, "Sound needs the book as an EPUB"
    st = path.stat()
    return audiomap.book(path), f"{st.st_size}:{st.st_mtime_ns}"


@functools.lru_cache(maxsize=4)
def _paras(path, key):
    """[(start, text)]: every paragraph in the book's text stream (audiomap's), in order."""
    B = audiomap.book(path)
    out = []
    with zipfile.ZipFile(path) as z:
        for s in B["secs"]:
            if not s["linear"] or not s["len"]:
                continue
            try:
                d = audiomap._section(z.read(s["href"]))
            except (KeyError, etree.XMLSyntaxError, ValueError):
                continue
            for el, at in d["el"].items():
                if not isinstance(el.tag, str) or etree.QName(el).localname not in LEAF:
                    continue
                if any(isinstance(k.tag, str) and etree.QName(k).localname in LEAF for k in el.iterdescendants()):
                    continue                     # only the innermost blocks
                text = " ".join("".join(el.itertext()).split())
                if len(text) > 1:
                    out.append((s["start"] + at, text))
    out.sort()
    return out


def parts(B, paras):
    """The book in the parts the model reads one at a time: [{start, end, title}]. Its chapters (the
    contents), a short one joined to the next, a long one cut at a paragraph."""
    total = B["total"]
    marks = sorted({0} | {e["pos"] for e in B["toc"] if 0 <= e["pos"] < total})
    out = []
    for i, a in enumerate(marks):
        b = marks[i + 1] if i + 1 < len(marks) else total
        if b > a:
            out.append({"start": a, "end": b, "title": audiomap.chapter_at(B, a) or ""})
    joined = []
    for p in out:
        if joined and joined[-1]["end"] - joined[-1]["start"] < PART_MIN:
            joined[-1]["end"] = p["end"]
            joined[-1]["title"] = joined[-1]["title"] or p["title"]
        else:
            joined.append(dict(p))
    starts = [s for s, _ in paras]
    cut = []
    for p in joined:
        a = p["start"]
        while p["end"] - a > PART_MAX:
            want = a + (p["end"] - a) // -(-(p["end"] - a) // PART_MAX)  # even pieces, each under PART_MAX
            k = bisect.bisect_left(starts, want)
            b = starts[k] if k < len(starts) and a < starts[k] < p["end"] else want
            cut.append({"start": a, "end": b, "title": p["title"]})
            a = b
        cut.append({"start": a, "end": p["end"], "title": p["title"]})
    return cut


def _part_at(P, c):
    for i, p in enumerate(P):
        if p["start"] <= c < p["end"]:
            return i
    return len(P) - 1 if P else None


# ---- the model reads a part -------------------------------------------------------------------

PROMPT = """You're the sound designer for someone reading a book. Under the page plays a quiet bed of
recorded background sound, and you choose it, scene by scene. Below is part of "{title}"{by}{where}.
Each paragraph starts with its number in brackets.

Split it into scenes by where it takes place and what can be heard there, and give each scene up to
three of these sounds (nothing else):
{sounds}

- Start a new scene only when the place, the weather or what a listener would hear really changes. A
  chapter usually has one to four; a long run of talk in one room is one.
- Choose the closest: a sound of the place itself (a train, a library, a forge, rain on a tent) over
  a general one, and add what's around it only when it would be heard.
- Each sound gets a level from 0.2 (just there) to 1 (full). It sits under reading, so keep it gentle;
  a storm the story is about can be loud.
- This is the ground under the scene, not effects: don't follow one door, one shot or one bell.
- The music sounds are for when no place can be heard: an essay, a reflection, a letter, a prayer, a
  memory. A book that is all argument or instruction can have one calm bed throughout, or nothing.
- Nothing fits, or anything would distract: give the scene no sounds.

Answer with JSON only, a list, the first scene at the first paragraph:
[{{"from": 1, "scene": "A few words, e.g. Rain on the moor", "sounds": {{"empty-wind": 0.6, "drizzle": 0.5}}}}]

{text}
"""


def _ask(meta, part, ps):
    by = f' by {meta["author"]}' if meta.get("author") else ""
    where = f', from "{part["title"]}"' if part.get("title") else ""
    can = offered()
    sounds = "\n".join(f"{k}: {v[1]}" for k, v in can.items())
    text = "\n".join(f"[{i + 1}] {t}" for i, (_, t) in enumerate(ps))
    out = ai.run(PROMPT.format(title=meta.get("title") or "a book", by=by, where=where, sounds=sounds, text=text), timeout=300)
    m = re.search(r"\[.*\]", out, re.S)
    if not m:
        raise RuntimeError("The model's answer had no scenes")
    raw = json.loads(m.group(0))
    scenes = []
    for x in raw if isinstance(raw, list) else []:
        if not isinstance(x, dict):
            continue
        try:
            n = int(x.get("from"))
        except (TypeError, ValueError):
            continue
        if not 1 <= n <= len(ps):
            continue
        snd = {}
        for k, v in (x.get("sounds") or {}).items() if isinstance(x.get("sounds"), dict) else ():
            if k in can:
                try:
                    snd[k] = round(min(1.0, max(0.1, float(v))), 2)
                except (TypeError, ValueError):
                    pass
        snd = dict(sorted(snd.items(), key=lambda kv: -kv[1])[:3])
        name = " ".join(str(x.get("scene") or "").split())
        if len(name) > 60:                            # at a word, without a dangling "the" or comma
            name, cut = name[:61].rsplit(" ", 1)[0], None
            while cut != name:
                cut, name = name, re.sub(r"[\s,;:–-]+(the|a|an|of|and|over|by|in|on|at|to|with|from)?$", "", name)
        scenes.append({"start": ps[n - 1][0], "scene": name, "sounds": snd})
    scenes.sort(key=lambda s: s["start"])
    if not scenes:
        raise RuntimeError("The model's answer had no scenes")
    scenes[0]["start"] = part["start"]               # the first scene holds from the part's start
    keep = []
    for s in scenes:
        if keep and s["start"] == keep[-1]["start"]:
            keep[-1] = s
        elif not keep or s["sounds"] != keep[-1]["sounds"]:
            keep.append(s)
    return keep


_busy = set()
_lock = threading.Lock()


def _make(book_id, path, key, part, meta, then=None):
    """Reads one part in its own thread and keeps the scenes (or the error); then the next, if asked."""
    c = db.connect()
    try:
        ps = [p for p in _paras(str(path), key) if part["start"] <= p[0] < part["end"]]
        try:
            scenes = _ask(meta, part, ps) if ps else [{"start": part["start"], "scene": "", "sounds": {}}]
            err = None
        except Exception as e:                        # noqa: BLE001 - kept, shown, tried again later
            log.warning("soundscape %s @%s: %s", book_id, part["start"], e)
            scenes, err = [], str(e)[:300]
        c.execute("INSERT OR REPLACE INTO soundscapes (book_id, file, start, end, scenes, made, model, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                  (book_id, key, part["start"], part["end"], json.dumps(scenes), int(time.time()), ai.model(), err))
        c.commit()
    finally:
        c.close()
        with _lock:
            _busy.discard((book_id, part["start"]))
    if then and not err:
        ensure(book_id, path, key, then, meta)


def _row(conn, book_id, key, start):
    return conn.execute("SELECT scenes, error, made FROM soundscapes WHERE book_id = ? AND file = ? AND start = ?",
                        (book_id, key, start)).fetchone()


def ensure(book_id, path, key, part, meta, then=None, conn=None):
    """Starts reading a part unless it's read, being read, or failed lately. True when it's being read."""
    c = conn or db.connect()
    try:
        r = _row(c, book_id, key, part["start"])
    finally:
        if conn is None:
            c.close()
    if r and (not r["error"] or time.time() - r["made"] < RETRY):
        return False
    with _lock:
        if (book_id, part["start"]) in _busy:
            return True
        _busy.add((book_id, part["start"]))
    threading.Thread(target=_make, args=(book_id, path, key, part, meta, then), daemon=True, name="soundscape").start()
    return True


# ---- where you are → the scene -----------------------------------------------------------------

def at(conn, book_id, place):
    """The scene at a place in a book: {state: "ready" | "reading" | "failed" | "none", scene, sounds,
    part, why}. "reading": the model is on it, ask again in a few seconds."""
    B, key = _book(conn, book_id)
    if B is None:
        return {"state": "none", "why": key}
    path = B["path"]
    paras = _paras(str(path), key)
    P = parts(B, paras)
    if not P:
        return {"state": "none", "why": "This book has no text to go by"}
    c = audiomap.char_of(B, place or {})
    i = _part_at(P, c)
    part = P[i]
    nxt = P[i + 1] if i + 1 < len(P) else None
    b = conn.execute("SELECT title, author FROM books WHERE id = ?", (book_id,)).fetchone()
    meta = {"title": b["title"] if b else None, "author": b["author"] if b else None}
    r = _row(conn, book_id, key, part["start"])
    out = {"book_id": book_id, "title": meta["title"], "part": part["title"], "at": c}
    if not r or (r["error"] and time.time() - r["made"] >= RETRY):
        ensure(book_id, path, key, part, meta, then=nxt, conn=conn)
        return {**out, "state": "reading"}
    if r["error"]:
        return {**out, "state": "failed", "why": r["error"]}
    if nxt and c > part["start"] + 0.5 * (part["end"] - part["start"]):
        ensure(book_id, path, key, nxt, meta, conn=conn)   # read on ahead
    scenes = json.loads(r["scenes"])
    s = scenes[0] if scenes else {"scene": "", "sounds": {}}
    for x in scenes:
        if x["start"] <= c:
            s = x
    return {**out, "state": "ready", "scene": s["scene"], "sounds": s["sounds"]}


def forget(conn, book_id):
    """The scenes kept for a book go, so it's read again (the model, or the book, changed)."""
    conn.execute("DELETE FROM soundscapes WHERE book_id = ?", (book_id,))


# ---- the Kindle: the page the plugin last said it was on ----------------------------------------

def kindle_where(conn, book_id, text, fraction):
    w = {"book_id": book_id, "text": (text or "")[:600], "fraction": fraction, "at": time.time()}
    conn.execute("INSERT INTO kv (k, v) VALUES ('kindle_where', ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", (json.dumps(w),))
    return w


def kindle_now(conn):
    r = conn.execute("SELECT v FROM kv WHERE k = 'kindle_where'").fetchone()
    return json.loads(r[0]) if r else None


def kindle_scene(conn):
    w = kindle_now(conn)
    if not w:
        return {"state": "none", "why": "", "at": 0}
    place = {"text": w.get("text") or None, "fraction": w.get("fraction")}
    r = at(conn, w["book_id"], {k: v for k, v in place.items() if v is not None})
    return {**r, "seen": w["at"]}


# ---- the routes ---------------------------------------------------------------------------------

def router():
    import asyncio

    from fastapi import APIRouter, Depends, HTTPException
    from fastapi.responses import FileResponse
    from starlette.concurrency import run_in_threadpool

    from . import library
    from .app import conn, device, json_body, user, user_or_device

    r = APIRouter()

    @r.get("/api/sounds/{name}.mp3", dependencies=[Depends(user_or_device)])
    async def get_sound(name: str):
        """One of SOUNDS' recordings (a seamless loop, PAD seconds either side)."""
        if name not in SOUNDS:
            raise HTTPException(404, "No such sound")
        try:
            p = await run_in_threadpool(sound_file, name)
        except Exception as e:                    # noqa: BLE001
            raise HTTPException(502, f"The sound didn't come: {e}") from e
        if p is None:                             # one of Daf's own that this copy hasn't got
            raise HTTPException(404, "This sound isn't here")
        return FileResponse(p, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=31536000, immutable"})

    @r.post("/api/ebooks/{book_id}/sound", dependencies=[Depends(user)])
    async def post_book_sound(book_id: str, b=Depends(json_body), c=Depends(conn)):
        """{cfi, fraction, text}: the reader's place (without one, the book's kept place) → the scene there and its sounds (at)."""
        place = {k: b.get(k) for k in ("cfi", "fraction", "text") if b.get(k) is not None}
        if not place:                             # no page sent: the place Daf keeps for the book
            pos = c.execute("SELECT cfi, fraction FROM book_positions WHERE book_id = ?", (book_id,)).fetchone()
            place = {k: v for k, v in dict(pos).items() if v is not None} if pos else {}
        return await run_in_threadpool(at, c, book_id, place)

    @r.post("/api/kindle/where")
    def post_kindle_where(b=Depends(json_body), name=Depends(device), c=Depends(conn)):
        """{md5, text, fraction}: the page the Kindle is on, from the plugin when Sound is on there."""
        md5 = str(b.get("md5") or "").strip().lower()
        bid = library.book_for_md5(c, md5) if re.fullmatch(r"[0-9a-f]{32}", md5) else None
        if not bid:
            return {"ok": False}
        try:
            f = float(b.get("fraction")) if b.get("fraction") is not None else None
        except (TypeError, ValueError):
            f = None
        kindle_where(c, bid, str(b.get("text") or ""), f)
        return {"ok": True}

    @r.get("/api/sound/kindle", dependencies=[Depends(user)])
    async def get_kindle_sound(after: float = 0, wait: int = 0):
        """The scene on the Kindle's page. With `after`, waits (up to `wait` seconds, at most 25) for a
        page newer than that, so a page can listen without a timer."""
        end = time.time() + min(max(wait, 0), 25)
        while True:
            c = db.connect()
            try:
                w = kindle_now(c)
                if not after or (w and w["at"] > after) or time.time() >= end:
                    return await run_in_threadpool(kindle_scene, c)
            finally:
                c.close()
            await asyncio.sleep(1)

    @r.get("/api/sound/sounds", dependencies=[Depends(user)])
    def get_sounds():
        return {"sounds": [{"id": k, "about": v[1]} for k, v in offered().items()]}

    return r
