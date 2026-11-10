"""The Edition: a short paper each morning (ten pieces by default), chosen for you from more than you
could read.

Candidates are the last day or two of the Feed, new uploads from the YouTube channels you follow on
Invidious, and new episodes of the podcasts you follow (AntennaPod's subscriptions, through Daf's gpodder
service). What you actually read, watch and listen to becomes a taste (`taste()`): Daf's reading sessions,
opened and saved documents and their highlights, Invidious's watch history, podcast plays, the books read
on the Kindle, and your thumbs on past editions, with older habits fading (`halflife`, in days). A piece
an edition showed you and you never opened counts a little against its source and its words.

Every candidate gets a score from that taste (how much its source means to you, how much its words do,
and its topic, which you can turn up, down or off). The best few dozen, a few from outside your usual and
the week's parasha go to the model with the mix rules; it picks the edition, orders it like a paper and
says in a few words why each piece is there, from the facts it was given about that piece. If the model
is off or fails, the same rules pick from the scores alone and the reasons are made from the facts.

Settings "edition" (see DEFAULTS); the sync loop builds one a day at `hour` in the home time zone on
`days` (sync.extras -> maybe_build), into the editions table; `daf edition` builds or shows one.
Invidious is read from its own database: DAF_INVIDIOUS_PSQL is the command that runs psql against it
(e.g. "docker exec -i invidious-db psql -U kemal -d invidious") and DAF_INVIDIOUS_USER the account.
"""
import hashlib
import json
import logging
import math
import random
import re
import shlex
import subprocess
import threading
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from . import config, db, today as T

log = logging.getLogger("daf.edition")

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DEFAULTS = {
    "on": False,            # build one each morning
    "pieces": 10,
    "videos": 0,            # at most: a paper is something to read, so none unless you ask
    "podcasts": 0,          # at most
    "torah": 1,             # at least, when there is one
    "wildcard": 1,          # from outside your usual
    "longest": 45,          # minutes; nothing longer
    "halflife": 30,         # days for a habit to count half as much
    "days": ["sun", "mon", "tue", "wed", "thu", "fri"],
    "hour": 5,              # ready by, in the home time zone
    "kindle": True,         # send each edition to the Kindle
    "ai": True,             # let the model pick and order it
    "topics": [],           # [{name, words: [...], adj: "more" | "less" | "mute" | ""}]
    "sources": {},          # {source: "more" | "less" | "mute"}; "folder:Name" mutes a Feed folder
}
ADJ = {"more": 1.6, "less": 0.55, "mute": 0.0, "": 1.0}
WATCHES_PER_DAY = 7         # Invidious keeps the order you watched in, not the dates: plays a day turn places into days
                            # (measured from iv-suggest's dated plays when it's there, see invidious())
BOOST, FLOOR = 2.0, 0.7     # a source's multiplier: the one you return to most at BOOST, one you never touched at FLOOR
RISING = {"recent": 14, "baseline": 90, "min_recent": 3, "min_lift": 3.0}   # days, and the floors a rising word must clear
PER_SOURCE = 2              # in one edition
MIN_WORDS = 150             # an article must have at least this much real text (a teaser, a paid post's lead-in, a link: out)
WHOLE = 400                 # a feed body this long is the article itself; anything shorter is checked against its page
STOP = set("""a about above after again against all also am an and any are aren't as at be because been before being
below between both but by can can't cannot could couldn't did didn't do does doesn't doing don't down during each few for
from further get gets got had hadn't has hasn't have haven't having he he'd he'll he's her here here's hers herself him
himself his how how's i i'd i'll i'm i've if in into is isn't it it's its itself just let's like make makes me more most
much must mustn't my myself new no nor not now of off on once only or other ought our ours ourselves out over own part
same say says she she'd she'll she's should shouldn't so some such than that that's the their theirs them themselves then
there there's these they they'd they'll they're they've this those through to too under until up us very was wasn't we
we'd we'll we're we've were weren't what what's when when's where where's which while who who's whom why why's will with
won't would wouldn't you you'd you'll you're you've your yours yourself yourselves one two three first last next year
years day days week weeks time times way ways thing things people man woman men women really still even back made know
take see look want use used using via vs per may might new news latest update updates video videos episode episodes
podcast full live official watch read here's what's why how com www http https org net html source season part series
chapter ever big need bad send someone page feel get got lot lots thing via says said new best top inside""".split())
WORD = re.compile(r"[a-zא-ת][a-z0-9א-ת'’+\-]{2,}")
PLATFORM = {"invidious", "youtube", "substack", "google news", "rss", "podcast", "articles", "feed"}
_building = threading.Lock()


# ---- settings -------------------------------------------------------------------------------------

def settings(s=None):
    s = s if s is not None else config.load_settings()
    e = dict(DEFAULTS)
    e.update({k: v for k, v in (s.get("edition") or {}).items() if k in DEFAULTS})
    for k in ("pieces", "videos", "podcasts", "torah", "wildcard", "longest", "halflife", "hour"):
        try:
            e[k] = int(e[k])
        except (TypeError, ValueError):
            e[k] = DEFAULTS[k]
    e["pieces"] = max(3, min(20, e["pieces"]))
    e["hour"] = max(3, min(11, e["hour"]))
    e["halflife"] = max(3, min(365, e["halflife"]))
    e["days"] = [d for d in e["days"] if d in DAYS] if isinstance(e["days"], list) else DEFAULTS["days"]
    e["topics"] = [t for t in e["topics"] if isinstance(t, dict) and t.get("name")] if isinstance(e["topics"], list) else []
    e["sources"] = e["sources"] if isinstance(e["sources"], dict) else {}
    return e


def save(changes):
    """Merge changes into settings "edition" (the Taste page's controls)."""
    s = config.load_settings()
    cur = dict(s.get("edition") or {})
    for k, v in (changes or {}).items():
        if k in DEFAULTS:
            cur[k] = v
    s["edition"] = cur
    config.save_settings(s)
    return settings(s)


# ---- words and sources ----------------------------------------------------------------------------

def words(text):
    out = []
    for w in WORD.findall((text or "").lower().replace("’", "'")):
        w = w.strip("'-+")
        if w.endswith("'s"):
            w = w[:-2]
        if len(w) < 3 or w in STOP or w.isdigit():
            continue
        if len(w) > 4 and w.endswith("s") and not w.endswith(("ss", "us", "is", "ous")):
            w = w[:-1]
        if len(w) > 16:          # run-together names and addresses ("theconversation")
            continue
        out.append(w)
    return out


def source_key(name):
    """One name per publication: "Health + Medicine – Articles – The Conversation" and "Politics + Society –
    Articles – The Conversation" are both The Conversation; "Big Think | Invidious" is Big Think."""
    name = (name or "").split(" | ")[0]          # "Show | Platform", "Name | name in another script"
    parts = [p.strip() for p in re.split(r"\s+–\s+|\s+--\s+", name) if p.strip()]
    parts = [p for p in parts if p.lower() not in PLATFORM] or parts
    return (parts[-1] if parts else name).strip()


def dek(text, most=320):
    """A summary cut where a sentence ends, or at a word with an ellipsis."""
    text = (text or "").strip()
    if len(text) <= most:
        return text
    cut = text[:most]
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    return cut[:end + 1] if end > most // 2 else cut.rsplit(" ", 1)[0].rstrip(",;:–-") + "…"


def norm_title(t):
    return re.sub(r"\W+", " ", (t or "").lower()).strip()


# ---- what you read, watch and listen to -----------------------------------------------------------

def _psql(sql):
    """Rows from Invidious's database, through DAF_INVIDIOUS_PSQL. [] when it isn't set up."""
    cmd = config.setting("DAF_INVIDIOUS_PSQL")
    if not cmd:
        return []
    try:
        r = subprocess.run(shlex.split(cmd) + ["-At", "-F", "\t", "-c", sql], capture_output=True, text=True, timeout=60)
    except (subprocess.SubprocessError, OSError) as e:   # hung, or no docker: as if psql failed
        raise RuntimeError(f"psql: {e}"[:300]) from e
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "psql failed").strip()[:300])
    return [line.split("\t") for line in r.stdout.splitlines() if line]


def _iv_user():
    u = config.setting("DAF_INVIDIOUS_USER")
    return u if u and re.fullmatch(r"[\w.@+\-]+", u) else ""


def invidious():
    """What the Edition reads from Invidious, all of it read-only and in one go: the watch history with
    titles (iv-suggest's video cache first, when iv-suggest runs there), real plays a day, the account's
    own playlists, iv-suggest's lanes and the topics named in them. Empty when it isn't set up."""
    out = {"hist": [], "watched": set(), "rate": WATCHES_PER_DAY, "playlists": [], "lanes": [], "named": [], "suggest": False}
    user = _iv_user()
    if not user:
        return out
    q = f"'{user}'"
    hist_sql = ("SELECT w.v, COALESCE({m}author, cv.author, vi.info::json->>'author'), COALESCE({m}title, cv.title, vi.info::json->>'title'), {g} "
                "FROM users u CROSS JOIN LATERAL unnest(u.watched) WITH ORDINALITY AS w(v, ord) {join}"
                "LEFT JOIN channel_videos cv ON cv.id = w.v LEFT JOIN videos vi ON vi.id = w.v "
                f"WHERE u.email = {q} ORDER BY w.ord")
    try:
        rows = _psql(hist_sql.format(m="m.", g="m.genre", join="LEFT JOIN suggest.video_meta m ON m.vid = w.v "))
        out["suggest"] = True
    except RuntimeError:            # no iv-suggest: Invidious's own tables
        try:
            rows = _psql(hist_sql.format(m="", g="NULL", join="").replace("COALESCE(author, ", "COALESCE(").replace("COALESCE(title, ", "COALESCE("))
        except RuntimeError as ex:
            log.warning("invidious history: %s", ex)
            return out
    out["hist"] = [{"id": r[0], "author": r[1] or None, "title": r[2] or None, "genre": r[3] or None} for r in rows if len(r) >= 4]
    out["watched"] = {v["id"] for v in out["hist"]}
    lanes = f"SELECT plid FROM suggest.lanes WHERE account = {q}" if out["suggest"] else "SELECT NULL WHERE false"
    try:
        out["playlists"] = [{"list": r[0], "id": r[1], "title": r[2], "author": r[3]} for r in _psql(
            "SELECT p.title, pv.id, pv.title, pv.author FROM playlists p JOIN playlist_videos pv ON pv.plid = p.id "
            f"WHERE p.author = {q} AND p.id NOT IN ({lanes})") if len(r) >= 4]
    except RuntimeError as ex:
        log.warning("invidious playlists: %s", ex)
    if not out["suggest"]:
        return out
    try:
        n, days = _psql(f"SELECT COUNT(*), GREATEST(1, LEAST(14, EXTRACT(epoch FROM now() - MIN(played)) / 86400)) FROM suggest.plays "
                        f"WHERE account = {q} AND outcome = 'watched' AND played > now() - interval '14 days'")[0]
        if int(n) >= 10:
            out["rate"] = max(1.0, int(n) / float(days))
        out["named"] = [r[0] for r in _psql(f"SELECT title FROM suggest.lanes WHERE account = {q} AND lane LIKE 'topic-%' ORDER BY title")]
        out["lanes"] = [{"id": r[0], "lane": r[1], "list": r[2], "added": int(float(r[3] or 0)), "title": r[4], "author": r[5],
                         "seconds": int(r[6] or 0), "genre": r[7] or None, "published": int(float(r[8] or 0))} for r in _psql(
            "SELECT i.vid, l.lane, l.title, EXTRACT(epoch FROM i.added), COALESCE(m.title, pv.title), COALESCE(m.author, pv.author), "
            "COALESCE(m.seconds, pv.length_seconds), m.genre, EXTRACT(epoch FROM pv.published) "
            "FROM suggest.items i JOIN suggest.lanes l ON l.account = i.account AND l.lane = i.lane "
            "LEFT JOIN suggest.video_meta m ON m.vid = i.vid LEFT JOIN playlist_videos pv ON pv.plid = l.plid AND pv.id = i.vid "
            f"WHERE i.account = {q} AND i.added > now() - interval '10 days'") if len(r) >= 9]
    except (RuntimeError, ValueError, IndexError) as ex:
        log.warning("iv-suggest: %s", ex)
    return out


def taste(conn, e=None, now=None, iv=None):
    """{sources: {key: 0..1 on a log curve}, mult: {key: FLOOR..BOOST}, words: {word: weight -1..1}, rising: [{word, recent, lift}],
    facts: {key: Counter}, topics: [{name, weight, trend}], seen: {fact: count}, recent: [titles finished lately],
    down: [titles you turned down], named: [topics named in iv-suggest]}."""
    e = e or settings()
    now = now or time.time()
    half = e["halflife"] * 86400
    events = []          # (when, weight, source key, text, fact)

    def add(when, w, src, text, fact=None):
        events.append((when or now, w, source_key(src) if src else "", text or "", fact))

    # Daf: documents opened, read for a while, highlighted, saved, starred
    per = defaultdict(lambda: {"w": 0.0, "when": 0, "src": None, "title": "", "text": "", "facts": set()})

    def doc(r, title, summary):
        p = per[r]
        p["title"], p["text"] = title or "", f'{title or ""} {(summary or "")[:300]}'
        return p

    for r in conn.execute("SELECT id, source, title, summary, opened, progress, starred, where_, added FROM docs "
                          "WHERE kind IN ('article', 'video', 'podcast', 'tweet', 'pdf') AND (opened IS NOT NULL OR where_ = 'library' OR starred)"):
        p = doc(r["id"], r["title"], r["summary"])
        p["src"] = r["source"]
        if r["opened"]:
            p["w"] += 1 + 2 * min(1.0, r["progress"] or 0)
            p["when"] = max(p["when"], r["opened"])
            p["facts"].add("opened")
        if r["where_"] == "library":
            p["w"] += 1.5
            p["when"] = max(p["when"], r["added"] or 0)
            p["facts"].add("saved")
        if r["starred"]:
            p["w"] += 1
    for r in conn.execute("SELECT s.item, s.seconds, s.start, d.source, d.title, d.summary FROM sessions s JOIN docs d ON d.id = s.item "
                          "WHERE s.source IN ('article', 'video')"):
        p = doc(r["item"], r["title"], r["summary"])
        p["src"] = r["source"]
        p["w"] += 2 * min(1.0, (r["seconds"] or 0) / 300)
        p["when"] = max(p["when"], r["start"] or 0)
        if (r["seconds"] or 0) >= 120:
            p["facts"].add("finished")
    for r in conn.execute("SELECT h.book_id, COUNT(*), MAX(h.created), d.source, d.title, d.summary FROM highlights h "
                          "JOIN docs d ON d.id = h.book_id WHERE h.deleted IS NULL OR h.deleted = 0 GROUP BY h.book_id"):
        p = doc(r[0], r[4], r[5])
        p["src"] = r[3]
        p["w"] += 1.5 * min(3, r[1])
        p["when"] = max(p["when"], r[2] or 0)
        p["facts"].add("highlighted")
    recent = []
    for p in per.values():
        if p["w"] <= 0:
            continue
        add(p["when"], p["w"], p["src"], p["text"], "opened" if p["facts"] & {"opened", "finished"} else "saved")
        if "highlighted" in p["facts"]:
            add(p["when"], 0, p["src"], "", "highlighted")
        if p["facts"] & {"finished", "highlighted"} and p["when"] and now - p["when"] < 30 * 86400:
            recent.append((p["when"], p["title"][:120]))

    # Invidious: what you watched, newest last (places become days at the measured plays a day), and your own
    # playlists: a video you put on a list is a choice, the list's name says what about, "Blocked" says no
    iv = iv if iv is not None else invidious()
    n = len(iv["hist"])
    for i, v in enumerate(iv["hist"]):
        if (v["author"] or v["title"]) and v.get("genre") != "Music":
            add(now - (n - i) / iv["rate"] * 86400, 1.5, v["author"], v["title"], "watched")
    for v in iv["playlists"]:
        name = (v["list"] or "").lower()
        if "block" in name:
            add(now - 7 * 86400, -3.0, v["author"], v["title"], "down")
        else:
            add(now - 21 * 86400, 0.8 if "later" in name else 2.0, v["author"], v["title"], "saved")

    # podcasts: AntennaPod's plays (gpodder) and Audiobookshelf's episodes
    for r in conn.execute("SELECT a.position, a.total, a.timestamp, e.title, e.podcast_title FROM gp_actions a "
                          "LEFT JOIN gp_episodes e ON e.url = a.episode WHERE a.action = 'play'"):
        share = min(1.0, (r["position"] or 0) / r["total"]) if r["total"] else 0.3
        add(r["timestamp"], 0.5 + 1.5 * share, r["podcast_title"], r["title"], "played")
    for r in conn.execute("SELECT title, author, seconds, start FROM sessions WHERE source = 'podcast' AND origin = 'audiobookshelf'"):
        add(r["start"], 0.4 + min(1.0, (r["seconds"] or 0) / 1800), r["author"], r["title"], "played")

    # books on the Kindle: what they're about, lightly
    for r in conn.execute("SELECT title, MAX(author), SUM(seconds), MAX(start) FROM sessions WHERE source = 'kindle' "
                          "AND start > ? GROUP BY title", (now - 180 * 86400,)):
        add(r[3], 0.3 * min(5.0, (r[2] or 0) / 3600), None, f"{r[0] or ''} {r[1] or ''}")

    # your thumbs, and what an edition showed you that you left alone
    down = []
    for r in conn.execute("SELECT vote, at, source, title FROM edition_votes"):
        add(r["at"], 4.0 * r["vote"], r["source"], r["title"], "up" if r["vote"] > 0 else "down")
        if r["vote"] < 0:
            down.append(r["title"])
    for d, w, src, text in skipped(conn, now):
        add(d, w, src, text, "skipped")

    src_w, word_w, facts = Counter(), Counter(), defaultdict(Counter)
    seen = Counter()
    for when, w, src, text, fact in events:
        k = 0.5 ** (max(0.0, now - when) / half)
        if src:
            src_w[src] += w * k
            if fact:
                facts[src][fact] += 1
        if fact:
            seen[fact] += 1
        ws = set(words(text))
        if ws and w:
            share = w * k / math.sqrt(len(ws))
            for t in ws:
                word_w[t] += share
    top_word = max([abs(v) for v in word_w.values()] or [1.0])
    vocab = {t: round(v / top_word, 4) for t, v in sorted(word_w.items(), key=lambda kv: -abs(kv[1]))[:1500]}
    # Log, not linear (iv-suggest's lesson): one show played 94 times would otherwise leave every other
    # source near nothing. The top source gets BOOST, the rest fall along a log curve, and a source with no
    # history at all gets FLOOR: missing data isn't dislike. One you turned down drops below the floor.
    pos = {s: v for s, v in src_w.items() if v > 0}
    top = max(pos.values() or [0])
    sources = {s: round(math.log1p(v) / math.log1p(top), 4) for s, v in pos.items()} if top > 0 else {}
    mult = {s: round(FLOOR + (BOOST - FLOOR) * x, 4) for s, x in sources.items()}
    mult.update({s: round(FLOOR * 0.6, 4) for s, v in src_w.items() if v < -0.5})
    return {"sources": sources, "mult": mult, "words": vocab, "rising": rising(events, now),
            "facts": {s: dict(c) for s, c in facts.items()}, "topics": topic_weights(events, e, now), "seen": dict(seen),
            "recent": [t for _, t in sorted(recent, reverse=True)[:12]], "down": down[-12:], "named": iv["named"]}


def rising(events, now):
    """Words you've taken up lately (iv-suggest's burst): in at least min_recent things you engaged with
    in the last `recent` days, and min_lift times commoner there than in the `baseline` before. Both
    floors, because either alone is noise: lift alone promotes a word seen twice, a count alone promotes
    what you always read."""
    r0, b0 = now - RISING["recent"] * 86400, now - RISING["baseline"] * 86400
    rc, bc, rn, bn = Counter(), Counter(), 0, 0
    seen = set()
    for when, w, _src, text, _fact in sorted(events, key=lambda ev: -ev[0]):
        if w <= 0 or when < b0 or text in seen:      # an episode played eight times is one thing taken up, not eight
            continue
        seen.add(text)
        ws = set(words(text))
        if not ws:
            continue
        if when >= r0:
            rc.update(ws)
            rn += 1
        else:
            bc.update(ws)
            bn += 1
    if not rn:
        return []
    out = []
    for w_, n in rc.items():
        lift = (n / rn) / ((bc[w_] + 1) / max(1, bn))
        if n >= RISING["min_recent"] and lift >= RISING["min_lift"]:
            out.append({"word": w_, "recent": n, "lift": round(lift, 1)})
    return sorted(out, key=lambda x: (-x["recent"] * x["lift"]))[:12]


def topic_of(ws, topics):
    """The topic whose words this text shares most, or None."""
    best, hits = None, 0
    for t in topics:
        tw = {w for x in t.get("words") or [] for w in words(x)}
        h = len(ws & tw)
        if h > hits:
            best, hits = t, h
    return best


def topic_weights(events, e, now):
    """Each named topic's share of what you engaged with, now and a month ago (for the arrow)."""
    if not e["topics"]:
        return []
    half = e["halflife"] * 86400
    cur, old = Counter(), Counter()
    for when, w, _src, text, _fact in events:
        if w <= 0:
            continue
        t = topic_of(set(words(text)), e["topics"])
        if not t:
            continue
        cur[t["name"]] += w * 0.5 ** (max(0.0, now - when) / half)
        if now - when > 30 * 86400:
            old[t["name"]] += w * 0.5 ** (max(0.0, now - 30 * 86400 - when) / half)
    top, top_old = max(cur.values() or [1]), max(old.values() or [1])
    out = []
    for t in e["topics"]:
        a, b = cur[t["name"]] / top, old[t["name"]] / top_old
        out.append({"name": t["name"], "weight": round(a, 3), "trend": "up" if a - b > 0.12 else "down" if b - a > 0.12 else "steady",
                    "adj": t.get("adj") or "", "words": t.get("words") or []})
    return out


def skipped(conn, now):
    """Pieces an edition showed you at least two days ago that you never opened: (when, weight, source, text)."""
    out = []
    for r in conn.execute("SELECT day, made, items FROM editions WHERE made < ?", (now - 2 * 86400,)):
        for it in json.loads(r["items"] or "[]"):
            d = conn.execute("SELECT opened FROM docs WHERE id = ?", (it.get("id"),)).fetchone()
            touched = (d and d["opened"]) or conn.execute("SELECT 1 FROM sessions WHERE item = ?", (it.get("id"),)).fetchone() \
                or conn.execute("SELECT 1 FROM edition_votes WHERE id = ?", (it.get("id"),)).fetchone()
            if not touched:
                out.append((r["made"], -0.5, it.get("source"), it.get("title")))
    return out


# ---- candidates -----------------------------------------------------------------------------------

def _minutes(kind, words_, seconds):
    if kind == "article":
        return max(1, round((words_ or 0) / 230))
    return max(1, round((seconds or 0) / 60)) if seconds else None


def candidates(conn, e, now, used, iv=None):
    """Everything new enough to go in today's edition."""
    days = 3 if datetime.fromtimestamp(now).weekday() == 6 else 2      # Sunday's covers Shabbat too
    since = now - days * 86400
    out = []
    titles = {norm_title(r[0]) for r in conn.execute(        # read already, in another feed's copy or the Library
        "SELECT title FROM docs WHERE (opened IS NOT NULL OR where_ = 'library') AND COALESCE(published, added) >= ?", (since - 30 * 86400,))}

    def keep(c):
        t = norm_title(c["title"])
        if not t or t in titles or c["id"] in used:
            return
        if c["minutes"] and c["minutes"] > e["longest"]:
            return
        titles.add(t)
        out.append(c)

    for r in conn.execute(
            "SELECT d.id, d.kind, d.title, d.source, d.url, d.summary, d.words, d.duration, d.thumb, d.published, d.added, "
            "d.enclosure, f.folder, d.where_ FROM docs d LEFT JOIN feeds f ON f.id = d.feed WHERE d.where_ IN ('feed', 'pool') AND d.status != 'deleted' "
            "AND (d.deleted IS NULL OR d.deleted = 0) AND d.opened IS NULL AND COALESCE(d.published, d.added) >= ? "
            "AND d.kind IN ('article', 'video', 'podcast')", (since,)):
        if (r["kind"] == "video" and not e["videos"]) or (r["kind"] == "podcast" and not e["podcasts"]):
            continue
        if re.match(r"\s*\[sponsor", r["title"] or "", re.I):
            continue
        summary = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r["summary"] or "")).strip()
        if r["kind"] == "article" and (r["words"] or 0) < 120 and len(summary) < 150:
            continue        # an index page, a release line, a comment
        keep({"id": r["id"], "kind": r["kind"], "title": r["title"] or "", "source": r["source"] or "", "folder": r["folder"] or "",
              "url": r["url"], "summary": summary[:400], "minutes": _minutes(r["kind"], r["words"], r["duration"]),
              "thumb": r["thumb"] if r["thumb"] and not r["thumb"].startswith("http") else (r["thumb"] or ""),
              "published": r["published"] or r["added"], "origin": r["where_"]})

    iv = iv if iv is not None else invidious()
    user = _iv_user()

    def video(vid, author, title, secs, pub, origin, lane=None, added=None):
        if not re.fullmatch(r"[\w-]{11}", vid or "") or vid in iv["watched"] or not title:
            return
        if secs and not 180 <= secs <= e["longest"] * 60:
            return
        keep({"id": f"yt:{vid}", "kind": "video", "title": title, "source": author or "", "folder": "", "summary": "",
              "url": f"https://www.youtube.com/watch?v={vid}", "minutes": _minutes("video", 0, secs), "lane": lane,
              "thumb": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg", "published": int(added or pub or now), "origin": origin})

    if not e["videos"]:
        iv = dict(iv, lanes=[])
        user = ""
    # iv-suggest's lanes first: it already found these for you beyond your subscriptions (no songs)
    for v in sorted(iv["lanes"], key=lambda v: -v["added"]):
        if "music" in v["lane"] or v["genre"] == "Music":
            continue
        video(v["id"], v["author"], v["title"], v["seconds"], v["published"], "lane", lane=v["list"], added=v["added"])
    if user:
        try:
            rows = _psql(
                "SELECT id, author, title, length_seconds, extract(epoch FROM published)::bigint FROM channel_videos "
                f"WHERE ucid IN (SELECT unnest(subscriptions) FROM users WHERE email = '{user}') "
                f"AND published > to_timestamp({int(since)}) AND NOT live_now "
                "AND (premiere_timestamp IS NULL OR premiere_timestamp < now()) ORDER BY published DESC LIMIT 600")
        except Exception as ex:  # noqa: BLE001
            log.warning("invidious subscriptions: %s", ex)
            rows = []
        for r in rows:
            if len(r) != 5:                     # a tab or a line break in a title splits its row
                continue
            vid, author, title, secs, pub = r
            try:
                video(vid, author, title, int(float(secs or 0)), int(float(pub or now)), "youtube")
            except ValueError:
                continue

    for r in conn.execute("SELECT e.url, e.link, e.title, e.podcast_title, e.published, e.duration, e.notes, e.image FROM gp_episodes e "
                          "JOIN gp_subs s ON s.url = e.podcast WHERE s.removed IS NULL AND e.published >= ? AND ?",
                          (since, 1 if e["podcasts"] else 0)):
        notes = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r["notes"] or "")).strip()
        keep({"id": "ep:" + hashlib.sha1(r["url"].encode()).hexdigest()[:16], "kind": "podcast", "title": r["title"] or "",
              "source": r["podcast_title"] or "", "folder": "", "url": r["link"] or r["url"], "enclosure": r["url"],
              "summary": notes[:400], "minutes": _minutes("podcast", 0, r["duration"]), "thumb": r["image"] or "",
              "published": r["published"], "origin": "podcast"})
    return out


def _muted(c, e):
    adj = e["sources"]
    if adj.get(c["source"]) == "mute" or adj.get(source_key(c["source"])) == "mute":
        return True
    return bool(c.get("folder")) and adj.get("folder:" + c["folder"]) == "mute"


def score(cands, prof, e, now, parasha=None):
    """Adds c["score"], c["topic"], c["facts"] to each candidate; drops what you muted."""
    from . import torah
    kept = []
    raw = []
    for c in cands:
        if _muted(c, e):
            continue
        ws = set(words(f'{c["title"]} {c["summary"][:300]}'))
        tm = sum(prof["words"].get(w, 0) for w in ws) / (math.sqrt(len(ws)) + 1) if ws else 0
        raw.append(tm)
        c["_ws"], c["_tm"] = ws, tm
        kept.append(c)
    hi = sorted(raw)[int(len(raw) * 0.95)] if raw else 1
    hi = hi if hi > 0 else 1
    rise = {r["word"] for r in prof.get("rising") or []}
    any_src = bool(prof.get("mult"))
    for c in kept:
        key = source_key(c["source"])
        src = prof["sources"].get(key, 0.0)
        mult = prof["mult"].get(key, FLOOR if any_src else 1.0)
        t = topic_of(c["_ws"], e["topics"])
        c["topic"] = t["name"] if t else ""
        tmult = ADJ.get((t or {}).get("adj") or "", 1.0)
        smult = ADJ.get(e["sources"].get(key) or e["sources"].get(c["source"]) or "", 1.0)
        fresh = 0.5 ** (max(0, now - (c["published"] or now)) / 86400)
        c["rising"] = sorted(c["_ws"] & rise)
        # relevance: a floor, so a piece from a source you love still counts when its words are new to Daf
        rel = 0.35 + 0.65 * max(-0.5, min(1.5, c["_tm"] / hi))
        rel += 0.12 * min(2, len(c["rising"])) + (0.18 if c.get("lane") else 0) + 0.08 * fresh
        c["torah"] = bool(c.get("folder") == "Divrei Torah" or (parasha and torah.on_parasha(c, parasha)))
        c["parasha"] = bool(parasha and torah.on_parasha(c, parasha))
        c["score"] = round(rel * mult * tmult * smult + (0.25 if c["parasha"] else 0), 4)
        f = prof["facts"].get(key) or {}
        c["facts"] = {k: f[k] for k in ("watched", "opened", "played", "highlighted", "saved", "up", "down") if f.get(k)}
        c["familiar"] = src > 0.25 or bool(c.get("lane"))
        del c["_ws"], c["_tm"]
    return kept


# ---- the whole text -------------------------------------------------------------------------------

def body_words(conn, doc_id):
    from . import content
    r = conn.execute("SELECT blocks FROM doc_content WHERE id = ?", (doc_id,)).fetchone()
    try:
        return content.words(json.loads(r[0])) if r and r[0] else 0
    except (ValueError, KeyError, TypeError):
        return 0


def with_text(conn, short, keep=True):
    """Only pieces Daf can show in full: an article whose feed sent the whole thing passes; any other is
    fetched from its page (fulltext, trafilatura) and kept, so the reader and the Kindle have it too; one
    whose page won't give MIN_WORDS of text (a robot check, a paywall, a link with nothing behind it) is
    dropped. Videos and episodes pass as they are. Fetches run with nothing open in the database."""
    from concurrent.futures import ThreadPoolExecutor
    from . import content, fulltext
    out, need = [], []
    for c in short:
        if c["kind"] != "article":
            out.append(c)
            continue
        full = conn.execute("SELECT full FROM docs WHERE id = ?", (c["id"],)).fetchone()
        w = body_words(conn, c["id"])
        if w >= WHOLE or (full and full[0] and w >= MIN_WORDS):
            c["words"] = w
            out.append(c)
        else:
            need.append(c)
    conn.commit()

    def one(c):
        try:
            return c, fulltext.page_blocks(c["url"])
        except Exception as ex:  # noqa: BLE001 - one page that won't open costs only its piece
            log.info("edition: no text for %s (%s)", c["url"], str(ex)[:80])
            return c, None
    with ThreadPoolExecutor(6) as pool:
        got = list(pool.map(one, need))
    for c, bl in got:
        w = content.words(bl) if bl else 0
        if w < MIN_WORDS:
            continue
        if keep:
            fulltext._keep(conn, c["id"], bl)
        c["words"], c["minutes"] = w, _minutes("article", w, None)
        if not c.get("summary"):
            c["summary"] = content.summary(bl, 400)
        out.append(c)
    if keep:
        conn.commit()
    log.info("edition: %d of %d shortlisted have their whole text (%d fetched, %d kept)",
             len([c for c in out if c["kind"] == "article"]), len([c for c in short if c["kind"] == "article"]), len(need),
             len([1 for c, bl in got if bl and content.words(bl) >= MIN_WORDS]))
    return [c for c in short if c in out]


# ---- choosing -------------------------------------------------------------------------------------

def shortlist(cands, e, day):
    """What the model sees: the best by score (three a source at most), the parasha's, and a handful
    of decent pieces from sources you don't know yet, for the wildcard."""
    ranked = sorted(cands, key=lambda c: -c["score"])
    per, out = Counter(), []
    for c in ranked:
        k = source_key(c["source"])
        if per[k] >= 3:
            continue
        per[k] += 1
        out.append(c)
        if len(out) >= 60:
            break
    out += [c for c in ranked if c["parasha"] and c not in out][:4]
    rng = random.Random(day.isoformat())
    strangers = [c for c in cands if not c["familiar"] and c not in out and c["score"] >= 0
                 and ((c["kind"] == "article" and ((c["minutes"] or 0) >= 4 or len(c["summary"]) >= 150))   # with_text checks the rest
                      or (c["kind"] != "article" and (c["minutes"] or 0) >= 8))]
    rng.shuffle(strangers)
    for c in strangers[:12]:
        c["stranger"] = True
        out.append(c)
    return out


def fact_line(c, parasha=None):
    """A reason made only from facts."""
    f = c.get("facts") or {}
    name = short_name(c["source"])
    if c.get("stranger"):
        return "Outside your usual"
    if c.get("parasha") and parasha:
        return f"On this week's parasha, {parasha.get('name')}"
    if f.get("up"):
        return f"You liked {name} before"
    if c.get("lane"):
        return f"From your “{c['lane']}” lane"
    if f.get("watched"):
        return f"You've watched {f['watched']} from {name}"
    if f.get("played"):
        return f"You've played {f['played']} episode{'s' if f['played'] > 1 else ''} of {name}"
    if f.get("opened", 0) >= 3:
        return f"You've opened {f['opened']} from {name}"
    if f.get("highlighted"):
        return f"You've highlighted {name} before"
    if f.get("opened"):
        return f"You've opened {name} before"
    if c.get("rising"):
        return f"You've been into {c['rising'][0]} lately"
    if c.get("topic"):
        return c["topic"]
    return "New from " + name


def short_name(source):
    """A source as a reason names it: "The Recovery Radio Podcast - KMP3 - Long-Term Sobriety…" -> "The Recovery Radio Podcast"."""
    n = source_key(source)
    if len(n) > 30:
        n = re.split(r"\s+[-:(]\s*", n)[0]
    return n[:40]


def pick_local(short, e):
    """The mix rules over the scores, without the model."""
    chosen, per, kinds = [], Counter(), Counter()
    cap = {"video": e["videos"], "podcast": e["podcasts"]}

    def ok(c):
        k = source_key(c["source"])
        return c not in chosen and per[k] < PER_SOURCE and kinds[c["kind"]] < cap.get(c["kind"], 99)

    def take(c, section):
        chosen.append(c)
        per[source_key(c["source"])] += 1
        kinds[c["kind"]] += 1
        c["section"] = section

    ranked = sorted([c for c in short if not c.get("stranger")], key=lambda c: -c["score"])
    lead = next((c for c in ranked if c["kind"] == "article" and 4 <= (c["minutes"] or 0) <= 25), None)
    if lead:
        take(lead, "Lead")
    for c in [c for c in ranked if c["torah"]][:e["torah"]]:
        if ok(c):
            take(c, "Torah")
    for c in ranked:
        if len(chosen) >= e["pieces"] - e["wildcard"]:
            break
        if ok(c):
            take(c, section_for(c))
    for c in sorted([c for c in short if c.get("stranger")], key=lambda c: -c["score"])[:e["wildcard"]]:
        if ok(c):
            take(c, "Wildcard")
    for c in ranked:                     # still short (no wildcard, caps): fill from the rest
        if len(chosen) >= e["pieces"]:
            break
        if ok(c):
            take(c, section_for(c))
    return chosen


def section_for(c):
    from .sources import rss
    if c["kind"] == "video":
        return "Watch"
    if c["kind"] == "podcast":
        return "Listen"
    if c.get("torah"):
        return "Torah"
    pool = c["folder"][len(rss.POOL):] if rss.is_pool(c.get("folder")) else ""
    return ((c.get("topic") or pool).split(" & ")[0].split(",")[0][:18]) or "Read"


PROMPT = """You are choosing today's edition of a personal morning paper for one reader. They want a short, finished
paper, not a feed: pick the {n} best pieces for them from the candidates below.

Rules:
- {n} pieces, fewer only if fewer are worth their time. At most {videos} videos (kind video) and {podcasts} podcast episodes.
- At least {torah} piece on Torah or Jewish learning, if a candidate fits (TORAH or PARASHA in its facts).
- {wildcard} wildcard: a good piece from a candidate marked STRANGER, with section "Wildcard".
- At most {per} pieces from the same source. Prefer substance and things they would be glad to have read over
  churn, ads, listicles, release notes, comment threads and near-duplicates of each other.
- The first piece is the lead: the best read of the day, an article of about 4 to 25 minutes when there is one.
- Order the rest the way a good paper would: vary the kinds and the topics.
- For each piece: "section", one or two words (e.g. Ideas, Torah, Watch, Listen, Privacy, Craft, Science, Israel,
  Wildcard; "Lead" for the first), and "why": the reason it is here, spoken to the reader in at most eight words,
  using ONLY that candidate's facts and the reader's taste below. Don't repeat the title or the length, and never
  invent a fact or a number. Good: "You've watched 24 Fireship videos", "This week's parasha", "You've opened 20 from
  The Conversation", "Recovery runs through what you listen to", "Outside your usual" (always this for the wildcard).

The reader's taste (what they actually read, watch and listen to; weights 0..1):
{taste}

Candidates, one per line: id | kind | source | minutes | title | summary | facts
{lines}

Answer with JSON only, no prose: {{"pieces": [{{"id": "...", "section": "...", "why": "..."}}]}}"""


def _taste_text(prof):
    topics = ", ".join(f'{t["name"]} {t["weight"]:.2f}' + (f' ({t["adj"]})' if t["adj"] else "") for t in prof["topics"]) or "none named"
    srcs = sorted(prof["sources"].items(), key=lambda kv: -kv[1])
    likes = ", ".join(f"{k} {v:.2f}" for k, v in srcs[:25] if v > 0)
    words_ = ", ".join(w for w, v in sorted(prof["words"].items(), key=lambda kv: -kv[1])[:60] if v > 0)
    rise = ", ".join(r["word"] for r in prof.get("rising") or []) or "nothing in particular"
    named = ", ".join(prof.get("named") or []) or "none"
    return (f"- topics: {topics}\n- topics they named themselves: {named}\n- sources: {likes}\n"
            f"- words that recur in what they finish: {words_}\n- taken up lately: {rise}\n"
            f"- recently finished: {'; '.join(prof['recent'][:10]) or 'nothing yet'}\n"
            f"- turned down: {'; '.join(prof['down'][:8]) or 'nothing yet'}")


def _facts_text(c, parasha):
    f = [f"{k} {v}" for k, v in (c.get("facts") or {}).items()]
    if c.get("topic"):
        f.append("topic " + c["topic"])
    if (c.get("folder") or "").startswith("Pool · "):
        f.append("from the wider pool: " + c["folder"][7:])
    if c.get("parasha") and parasha:
        f.append(f"PARASHA {parasha.get('name')}")
    elif c.get("torah"):
        f.append("TORAH")
    if c.get("lane"):
        f.append(f"from their \"{c['lane']}\" lane of video suggestions")
    if c.get("rising"):
        f.append("rising for them lately: " + ", ".join(c["rising"]))
    if c.get("stranger"):
        f.append("STRANGER (outside their usual)")
    return ", ".join(f) or "-"


def pick_ai(short, prof, e, parasha):
    from . import ai
    clean = lambda s: re.sub(r"[|\n]+", " ", s or "").strip()      # noqa: E731
    lines = "\n".join(f'{c["id"]} | {c["kind"]} | {clean(c["source"])} | {c["minutes"] or "?"} | {clean(c["title"])} | '
                      f'{clean(c["summary"])[:160]} | {_facts_text(c, parasha)}' for c in short)
    text = PROMPT.format(n=e["pieces"], videos=e["videos"], podcasts=e["podcasts"], torah=e["torah"], wildcard=e["wildcard"],
                         per=PER_SOURCE, taste=_taste_text(prof), lines=lines)
    out = ai.run(text, timeout=300)
    m = re.search(r"\{.*\}", out, re.S)
    got = json.loads(m.group(0) if m else out).get("pieces") or []
    by_id = {c["id"]: c for c in short}
    chosen, per, kinds = [], Counter(), Counter()
    cap = {"video": e["videos"], "podcast": e["podcasts"]}
    for g in got:
        c = by_id.get(str(g.get("id")))
        if not c or c in chosen:
            continue
        k = source_key(c["source"])
        if per[k] >= PER_SOURCE or kinds[c["kind"]] >= cap.get(c["kind"], 99):
            continue
        per[k] += 1
        kinds[c["kind"]] += 1
        c["section"] = re.sub(r"\s+", " ", str(g.get("section") or section_for(c)))[:20].strip() or section_for(c)
        why = re.sub(r"\s+", " ", str(g.get("why") or "")).strip().rstrip(".")
        c["why"] = why[:80] if why else fact_line(c, parasha)
        chosen.append(c)
        if len(chosen) >= e["pieces"]:
            break
    if len(chosen) < min(e["pieces"], len(short)) // 2:
        raise RuntimeError(f"the model picked {len(chosen)} usable pieces")
    if e["wildcard"] and not any(c.get("stranger") for c in chosen):     # the one rule it most often forgets
        for c in sorted([c for c in short if c.get("stranger") and c not in chosen], key=lambda c: -c["score"]):
            if per[source_key(c["source"])] < PER_SOURCE and kinds[c["kind"]] < cap.get(c["kind"], 99):
                c["section"], c["why"] = "Wildcard", "Outside your usual"
                (chosen.append if len(chosen) < e["pieces"] else chosen.__setitem__)(*([c] if len(chosen) < e["pieces"] else [-1, c]))
                break
    if chosen:
        chosen[0]["section"] = "Lead"
    return chosen


TOPICS_PROMPT = """Below is what one reader actually reads, watches and listens to: the sources they spend time with,
the words that recur in what they finish, and titles they finished lately. Name the {n} topics that describe their
interests best, the way a newspaper would name its sections for them (short names, e.g. "Torah & Jewish thought",
"AI & tools", "Writing craft"). For each topic give 10 to 20 lowercase keywords that would appear in the title or
summary of an article, video or episode on it (single words, no phrases).

{taste}

Answer with JSON only: {{"topics": [{{"name": "...", "words": ["...", "..."]}}]}}"""


def seed_topics(conn=None, n=10):
    """Ask the model to name the reader's topics from their taste, once (and on "Name them again")."""
    from . import ai
    own = conn is None
    conn = conn or db.connect()
    try:
        prof = taste(conn)
    finally:
        if own:
            conn.close()
    out = ai.run(TOPICS_PROMPT.format(n=n, taste=_taste_text(prof)), timeout=240)
    m = re.search(r"\{.*\}", out, re.S)
    got = json.loads(m.group(0) if m else out).get("topics") or []
    old = {t["name"]: t for t in settings()["topics"]}
    topics = []
    for g in got[:16]:
        name = re.sub(r"\s+", " ", str(g.get("name") or "")).strip()[:40]
        ws = sorted({w for x in g.get("words") or [] for w in words(str(x))})[:30]
        if name and ws:
            topics.append({"name": name, "words": ws, "adj": (old.get(name) or {}).get("adj") or ""})
    if not topics:
        raise RuntimeError("the model named no topics")
    return save({"topics": topics})["topics"]


# ---- building -------------------------------------------------------------------------------------

def _materialize(conn, c):
    """A video or episode from outside the Feed becomes a Feed document, so Daf can play it, show its
    transcript and send it to the Kindle like any other post."""
    if c["origin"] == "feed":
        return
    if c["origin"] == "pool":          # from the pool into the Feed, read already, so it opens and keeps like any post
        conn.execute("UPDATE docs SET where_ = 'feed', status = 'seen' WHERE id = ? AND where_ = 'pool'", (c["id"],))
        return
    now = int(time.time())
    conn.execute(
        "INSERT INTO docs (id, kind, where_, status, title, author, source, url, published, added, summary, thumb, enclosure, duration) "
        "VALUES (?, ?, 'feed', 'unseen', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO NOTHING",
        (c["id"], c["kind"], c["title"], c["source"], c["source"], c["url"], c["published"], now, c["summary"] or None,
         c["thumb"] or None, c.get("enclosure"), (c["minutes"] or 0) * 60 or None))
    if c["kind"] == "video":
        from . import media
        media.queue(conn, "captions", c["id"])


def build(day=None, use_ai=None, dry=False, conn=None):
    """Make the edition for a day (today in the home time zone). Returns it."""
    s = config.load_settings()
    e = settings(s)
    day = day or T.today(s)
    now = time.time()
    own = conn is None
    conn = conn or db.connect()
    try:
        from . import torah
        try:
            parasha = (torah.calendar(conn, day) or {}).get("Parashat Hashavua")
        except Exception:  # noqa: BLE001 - Sefaria down: no parasha today
            parasha = None
        conn.commit()                       # the calendar's cache row: not held through psql and the model
        used = set()
        for r in conn.execute("SELECT items FROM editions WHERE day >= ? AND day != ?", ((day - timedelta(days=21)).isoformat(), day.isoformat())):
            used |= {it.get("id") for it in json.loads(r[0] or "[]")}
        if not e["topics"] and (e["ai"] if use_ai is None else use_ai) and not dry:
            try:
                seed_topics(conn)
                e = settings()
            except Exception as ex:  # noqa: BLE001
                log.warning("edition topics: %s", ex)
        iv = invidious()
        prof = taste(conn, e, now, iv)
        cands = score(candidates(conn, e, now, used, iv), prof, e, now, parasha)
        short = with_text(conn, shortlist(cands, e, day), keep=not dry)
        how = "rules"
        chosen = None
        if (e["ai"] if use_ai is None else use_ai) and short:
            try:
                chosen = pick_ai(short, prof, e, parasha)
                how = "model"
            except Exception as ex:  # noqa: BLE001 - the rules still make an edition
                log.warning("edition: the model didn't pick (%s); the rules do", ex)
                how = f"rules ({str(ex)[:120]})"
        if not chosen:
            chosen = pick_local(short, e)
            for c in chosen:
                c["why"] = fact_line(c, parasha)
        items = [{"id": c["id"], "kind": c["kind"], "section": c["section"], "why": c.get("why") or "", "title": c["title"],
                  "source": c["source"], "publication": source_key(c["source"]), "minutes": c["minutes"], "thumb": c["thumb"], "url": c["url"], "summary": dek(c["summary"]),
                  "score": c["score"]} for c in chosen]
        ed = {"day": day.isoformat(), "made": int(now), "items": items, "how": how, "candidates": len(cands),
              "parasha": (parasha or {}).get("name")}
        if dry:
            ed["shortlist"] = [{k: c.get(k) for k in ("id", "kind", "source", "title", "minutes", "score", "topic", "facts", "stranger")} for c in short]
            return ed
        for c in chosen:
            _materialize(conn, c)
        conn.execute("INSERT OR REPLACE INTO editions (day, made, items, how, kindle) VALUES (?, ?, ?, ?, NULL)",
                     (ed["day"], ed["made"], json.dumps(items), how))
        conn.commit()
        return ed
    finally:
        if own:
            conn.close()


def send_kindle(day=None):
    """The day's edition as one EPUB for the Kindle: a contents page with the sections and the reasons,
    then every piece Daf has text for (articles; videos and episodes once their transcripts are in)."""
    from . import kindlesend
    s = config.load_settings()
    day = day or T.today(s)
    with db.session() as conn:
        ed = get(conn, day)
        if not ed:
            raise ValueError("No edition for that day")
        when = datetime.combine(day, datetime.min.time())
        front = front_page(conn, ed, day)
        conn.commit()                       # the Hebrew date's cache row: not held through the pictures
        res = kindlesend.make_epub(conn, [it["id"] for it in ed["items"]], when=when,
                                   title=f"Daf, {day.strftime('%A')} {day.day} {day.strftime('%B')} {day.year}",
                                   fname=f"Daf {day.isoformat()} (Edition).epub", front=front)
        conn.execute("UPDATE editions SET kindle = ? WHERE day = ?", (res["file"], day.isoformat()))
        return res


def front_page(conn, ed, day):
    import html as H
    from . import torah
    try:
        heb = (torah.hebrew_date(conn, day) or {}).get("text") or ""
    except Exception:  # noqa: BLE001
        heb = ""
    rows = "".join(
        f'<li><p class="k">{H.escape(it["section"])}{" · " + {"video": "video", "podcast": "podcast"}[it["kind"]] if it["kind"] in ("video", "podcast") else ""}</p>'
        f'<p class="t">{H.escape(it["title"])}</p><p class="m">{H.escape(source_key(it["source"]))}{" · " + str(it["minutes"]) + " min" if it.get("minutes") else ""}'
        f'{" · " + H.escape(it["why"]) if it.get("why") else ""}</p></li>' for it in ed["items"])
    return (f'<h1 class="mast">Daf</h1><p class="date">{day.strftime("%A")}, {day.day} {day.strftime("%B")} {day.year}'
            f'{"<br/>" + H.escape(heb) if heb else ""}</p><ol class="toc">{rows}</ol>')


def get(conn, day):
    r = conn.execute("SELECT day, made, items, how, kindle FROM editions WHERE day = ?", (day.isoformat() if isinstance(day, date) else day,)).fetchone()
    if not r:
        return None
    return {"day": r["day"], "made": r["made"], "items": json.loads(r["items"] or "[]"), "how": r["how"], "kindle": r["kindle"]}


def maybe_build():
    """From the sync loop: today's edition once it's time (three tries a day), and its Kindle copy once
    the videos' transcripts are in, or 25 minutes after it was made, whichever comes first."""
    s = config.load_settings()
    e = settings(s)
    if not e["on"]:
        return
    now = datetime.now(T.tz_of(s))
    day = now.date()
    if DAYS[day.weekday()] not in e["days"] or now.hour < e["hour"] - 1:     # made in the hour before it's due
        return
    with db.session() as conn:
        ed = get(conn, day)
        if ed:
            if e["kindle"] and ed["kindle"] is None and ed["items"]:
                waiting = conn.execute(
                    "SELECT COUNT(*) FROM jobs WHERE kind = 'captions' AND status IN ('queued', 'running') AND ref IN (%s)"
                    % ",".join("?" * len(ed["items"])), [it["id"] for it in ed["items"]]).fetchone()[0]
                if waiting and time.time() - ed["made"] < 25 * 60:
                    return
            else:
                return
        else:
            tries = conn.execute("SELECT v FROM kv WHERE k = 'edition_tries'").fetchone()
            t = json.loads(tries[0]) if tries else {}
            if t.get("day") == day.isoformat() and t.get("n", 0) >= 3:
                return
    if not _building.acquire(blocking=False):
        return
    try:
        if not ed:
            with db.session() as conn:              # a try counts once it starts, not while another is still going
                tries = conn.execute("SELECT v FROM kv WHERE k = 'edition_tries'").fetchone()
                t = json.loads(tries[0]) if tries else {}
                conn.execute("INSERT OR REPLACE INTO kv (k, v) VALUES ('edition_tries', ?)",
                             (json.dumps({"day": day.isoformat(), "n": (t.get("n", 0) + 1) if t.get("day") == day.isoformat() else 1}),))
            build(day)
        elif e["kindle"]:
            try:
                send_kindle(day)
            except Exception:  # noqa: BLE001
                log.exception("edition kindle")
                with db.session() as conn:          # once a day is enough: don't try every five minutes
                    conn.execute("UPDATE editions SET kindle = '' WHERE day = ?", (day.isoformat(),))
    finally:
        _building.release()


def vote(conn, doc_id, v):
    """Thumbs up (1), down (-1) or neither (0) on a piece."""
    if v == 0:
        conn.execute("DELETE FROM edition_votes WHERE id = ?", (doc_id,))
        return
    d = conn.execute("SELECT source, title FROM docs WHERE id = ?", (doc_id,)).fetchone()
    conn.execute("INSERT OR REPLACE INTO edition_votes (id, vote, at, source, title) VALUES (?, ?, ?, ?, ?)",
                 (doc_id, 1 if v > 0 else -1, int(time.time()), d["source"] if d else None, d["title"] if d else None))


# ---- for the app ----------------------------------------------------------------------------------

def is_building():
    return _building.locked()


def build_now(day=None, kindle=None):
    """Make (or remake) the edition in the background; the page asks again until it's there."""
    if not _building.acquire(blocking=False):
        return False

    def run():
        try:
            build(day)
            if kindle if kindle is not None else settings()["kindle"]:
                try:
                    send_kindle(day)
                except Exception:  # noqa: BLE001
                    log.exception("edition kindle")
        except Exception:  # noqa: BLE001
            log.exception("edition build")
        finally:
            _building.release()
    threading.Thread(target=run, name="edition-now", daemon=True).start()
    return True


def state(conn, it):
    """Where you are with a piece: opened, how far, your thumb."""
    d = conn.execute("SELECT opened, progress, thumb, status FROM docs WHERE id = ?", (it["id"],)).fetchone()
    secs = conn.execute("SELECT COALESCE(SUM(seconds), 0) FROM sessions WHERE item = ?", (it["id"],)).fetchone()[0]
    v = conn.execute("SELECT vote FROM edition_votes WHERE id = ?", (it["id"],)).fetchone()
    out = dict(it)
    out.pop("score", None)
    out["publication"] = source_key(it.get("source"))
    out["summary"] = dek(it.get("summary"))
    out["exists"] = bool(d)
    if d:
        out["thumb"] = d["thumb"] if d["thumb"] and not d["thumb"].startswith("http") else (it.get("thumb") or "")
        out["progress"] = d["progress"] or 0
    out["opened"] = bool(d and d["opened"]) or secs > 0
    out["done"] = bool(d and ((d["progress"] or 0) >= 85 or secs >= 120 or (it["kind"] == "article" and d["opened"] and (it.get("minutes") or 9) <= 2)))
    out["vote"] = v[0] if v else 0
    return out


def public(conn, day):
    """The page's edition for a day, with what you've done with each piece, and the days that have one."""
    ed = get(conn, day)
    days = [r[0] for r in conn.execute("SELECT day FROM editions ORDER BY day DESC LIMIT 60")]
    e = settings()
    out = {"day": day.isoformat(), "edition": None, "days": days, "building": is_building(),
           "settings": {k: e[k] for k in ("on", "pieces", "kindle", "hour", "days")}}
    if ed:
        items = [state(conn, it) for it in ed["items"]]
        left = sum((it.get("minutes") or 0) for it in items if not it["done"])
        out["edition"] = {"day": ed["day"], "made": ed["made"], "how": ed["how"], "kindle": ed["kindle"], "items": items,
                          "done": sum(1 for it in items if it["done"] or it["opened"]), "left": left,
                          "number": conn.execute("SELECT COUNT(*) FROM editions WHERE day <= ?", (ed["day"],)).fetchone()[0]}
        try:
            from . import torah
            out["edition"]["hebrew"] = (torah.hebrew_date(conn, day) or {}).get("text")
        except Exception:  # noqa: BLE001
            pass
    return out


def summary(conn, day):
    """For Today and the sidebar: how far you are in today's edition."""
    ed = get(conn, day)
    if not ed:
        return {"on": settings()["on"], "total": 0, "done": 0}
    items = [state(conn, it) for it in ed["items"]]
    return {"on": settings()["on"], "total": len(items), "done": sum(1 for it in items if it["done"] or it["opened"])}


def taste_page(conn):
    """The Taste page: topics with their weights and arrows, the sources that count most and what you
    muted, what it learned from, and the mix."""
    e = settings()
    p = taste(conn, e)
    top = sorted(((k, v) for k, v in p["sources"].items() if v > 0), key=lambda kv: -kv[1])[:24]
    muted = sorted(k for k, v in e["sources"].items() if v == "mute")
    adj = {k: v for k, v in e["sources"].items() if v in ("more", "less")}
    return {"topics": p["topics"], "sources": [{"name": k, "weight": round(v, 3), "facts": p["facts"].get(k) or {}, "adj": adj.get(k, "")} for k, v in top],
            "pool": pool_page(conn, e), "muted": [m for m in muted if not m.startswith("folder:Pool · ")], "seen": p["seen"], "rising": p["rising"], "named": p["named"], "report": report(conn),
            "settings": {k: v for k, v in e.items() if k not in ("topics", "sources")}}


def pool_page(conn, e):
    """The pool's categories: how many feeds, what came in the last two days, and whether it's muted."""
    from .sources import rss
    since = int(time.time()) - 2 * 86400
    posts = dict(conn.execute("SELECT f.folder, COUNT(*) FROM docs d JOIN feeds f ON f.id = d.feed WHERE d.added >= ? "
                              "AND f.folder LIKE ? GROUP BY f.folder", (since, rss.POOL + "%")).fetchall())
    out = []
    for folder, n in conn.execute("SELECT folder, COUNT(*) FROM feeds WHERE folder LIKE ? GROUP BY folder ORDER BY folder", (rss.POOL + "%",)):
        out.append({"name": folder[len(rss.POOL):], "folder": folder, "feeds": n, "posts": posts.get(folder, 0),
                    "muted": e["sources"].get("folder:" + folder) == "mute"})
    return out


def report(conn, days=14):
    """Is it working: of the pieces the last two weeks' editions showed, how many you opened, read, liked."""
    out = {"days": days, "editions": 0, "shown": 0, "opened": 0, "read": 0, "up": 0, "down": 0}
    since = (date.today() - timedelta(days=days)).isoformat()
    for r in conn.execute("SELECT day, made, items FROM editions WHERE day >= ?", (since,)):
        out["editions"] += 1
        for it in json.loads(r["items"] or "[]"):
            s = state(conn, it)
            out["shown"] += 1
            out["opened"] += bool(s["opened"])
            out["read"] += bool(s["done"])
            out["up"] += s["vote"] > 0
            out["down"] += s["vote"] < 0
    return out
