"""The Edition to listen to: each morning's paper as one spoken episode, in a private podcast feed.

Once the day's edition is made, the model writes it as a script for one voice: the day and the headlines,
then every piece in the paper's order, told from its own text, and a line or two to end. Kokoro reads it in
Listen's voice (settings tts_voice and tts_speed), a paragraph at a time, and the paragraphs become one MP3
with a chapter for each piece (in the file, and in a chapters file whose links open the piece in Daf) and a
transcript timed to the paragraph, so neither the podcast app nor Daf has to transcribe it. If the model is
off or fails, the script is made from each piece's opening lines.

The feed is /api/edition/listen/<token>/feed.xml, where the token is a Daf device named "listen"
(`daf listen-feed` makes one and prints the address; making another ends the old one), so a podcast app
subscribes without signing in. Plays come back through Daf's gpodder service (gpodder.actions_upload ->
heard): a piece whose chapter was played through counts as opened, for the Edition's marks and its taste.

Settings "edition": audio (make one each morning), audio_minutes (about how long). The sync loop makes it
once the day's edition is there (sync.extras -> maybe_make); `daf edition --audio` makes it now. The files
live in STATE/edition-audio for KEEP_DAYS.
"""
import hashlib
import json
import logging
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from email.utils import format_datetime
from html import escape

from . import config, db, today as T

log = logging.getLogger("daf.edition_audio")

DIR = config.STATE / "edition-audio"
PARTS = DIR / "parts"
KEEP_DAYS = 14
WPM = 155                  # Kokoro's words a minute at speed 1 with the pauses (measured: 4,460 words in 28.5 minutes)
FRAME = (150, 50)          # words for the opening (the day and the headlines) and for the end
PIECE_WORDS = 1800         # of each piece's text, for the model
RATE = 24000               # Kokoro's PCM: 16-bit, mono
GAP = {"para": 0.45, "turn": 0.3, "part": 1.6}       # seconds of quiet between paragraphs, between hosts' turns, and between pieces
DEVICE = "listen"
PATH = "/api/edition/listen/"
NAME = "Daf Edition"
EPISODE = re.compile(r"\d{4}-\d{2}-\d{2}-\d+\.json")     # an episode's facts (not its script waiting to be read)
MARK = re.compile(r"^\s*={2,}\s*(intro|end|\d{1,2})\b[^\n=]*={2,}\s*$", re.M | re.I)
_making = threading.Lock()


def settings(s=None):
    from . import edition
    s = s if s is not None else config.load_settings()
    e = edition.settings(s)
    one = [{"name": "", "voice": s.get("tts_voice") or "af_heart", "speed": float(s.get("tts_speed") or 1.0)}]
    return {"on": bool(e["on"] and e["audio"]), "minutes": e["audio_minutes"],
            "hosts": e["audio_hosts"] if len(e["audio_hosts"]) >= 2 else one}


# ---- what it says ---------------------------------------------------------------------------------

def _text(conn, doc_id, most=PIECE_WORDS):
    """A piece's own text, paragraph by paragraph, cut after `most` words."""
    r = conn.execute("SELECT blocks FROM doc_content WHERE id = ?", (doc_id,)).fetchone()
    try:
        blocks = json.loads(r[0]) if r and r[0] else []
    except ValueError:
        blocks = []
    out, n = [], 0
    for b in blocks:
        x = " ".join(str(b.get("x") or "").split())
        if b.get("t") == "img" or len(x) < 2:
            continue
        out.append(x)
        n += len(x.split())
        if n >= most:
            break
    return "\n\n".join(out)


def pieces(conn, ed):
    """The edition's pieces as the script needs them: section, publication, title and text."""
    from . import edition
    out = []
    for n, it in enumerate(ed["items"], 1):
        text = _text(conn, it["id"]) or (it.get("summary") or "")
        out.append({"n": n, "id": it["id"], "section": it.get("section") or "", "title": it.get("title") or "",
                    "publication": it.get("publication") or edition.source_key(it.get("source")) or it.get("source") or "",
                    "kind": it.get("kind") or "article", "minutes": it.get("minutes"), "text": text,
                    "callback": it.get("callback")})
    return out


def day_facts(conn, day, ed):
    """The day as the opening says it: weekday and date, the Hebrew date, the week's parasha."""
    from . import torah
    try:
        h = torah.hebrew_date(conn, day) or {}
    except Exception:  # noqa: BLE001 - the date is a nicety
        h = {}
    return {"date": f"{day.strftime('%A')}, {day.day} {day.strftime('%B')}", "hebrew": h.get("text") or "",
            "parasha": ed.get("parasha") or ""}


def words_for(minutes, hosts=None):
    """How many words fill that many minutes, at the voices' own speed (a host at 1.2 gets through a fifth more)."""
    speeds = [float(h.get("speed") or 1.0) for h in hosts or []] or [1.0]
    return round(minutes * WPM * sum(speeds) / len(speeds))


def budgets(ps, minutes, hosts=None):
    """Words for each piece: the time left after the opening and the end, shared by how long each is to
    read (by its square root, so a long read gets more but doesn't swallow the rest), the lead a bit more.
    The model was a third over when it had only the total to go by."""
    left = max(60 * len(ps), words_for(minutes, hosts) - sum(FRAME))
    w = [max(1.0, min(25.0, float(p.get("minutes") or 4))) ** 0.5 * (1.3 if p["section"] == "Lead" else 1.0) for p in ps]
    return [max(60, round(left * x / sum(w) / 10) * 10) for x in w]


def prompt(ps, facts, minutes, hosts=None):
    words = words_for(minutes, hosts)
    each = budgets(ps, minutes, hosts)
    names = [h["name"] for h in hosts or []] if hosts and len(hosts) >= 2 else []
    day = (facts["date"] + (f", {facts['hebrew']}" if facts["hebrew"] else "")
           + (f"; this week's parasha is {facts['parasha']}" if facts["parasha"] else ""))
    length = (f"It should take about {minutes} minutes to read aloud: about {words} words in all, and no more than {round(words * 1.1)}. "
              "Each piece below has its length in words; keep to it, since the listener's walk is only so long. Choose what matters "
              "most rather than squeezing everything in.\n\n")
    if names:
        a, b = names[0], names[1]
        cast = (f"{a} and {b}" if len(names) == 2 else ", ".join(names[:-1]) + f" and {names[-1]}")
        head = (
            f"Write today's Edition as a conversation between the hosts of a morning podcast, {cast}, made for one listener, "
            "who will hear it through earphones on a walk or a bike ride and hasn't read any of it.\n\n"
            f"{a} has read everything and brings most of the stories. {b} has read them too but comes at each one fresh: reacts, asks "
            "the question the listener would ask, pushes back when something doesn't add up, and now and then ties it to something "
            f"earlier in the show. Now and then {b} brings a story instead. They like each other, they're curious and a little funny, "
            "and they talk like two friends at a kitchen table, not like an advert.\n\n"
            + length +
            "How it goes:\n"
            f"- Open with the day ({day}), then the two of them run through what's coming, a short phrase for each story, passed back and forth.\n"
            "- Then every piece, in the order given, none left out. Whoever brings it says where it's from in passing (the publication, "
            "or the writer when the text names one), and between them they tell it: what happened or what the writer argues, the best "
            "detail or two, and why it matters.\n"
            "- The facts come only from the text: no facts, numbers, names or quotes it doesn't have, and when the text is unclear, "
            "leave that part out rather than guess. The hosts may react, wonder, joke and disagree, but that is their own take, and "
            "it should sound like a take, never like a fact. When a piece doesn't say something, they simply don't go there: they "
            "talk about the article, the writer or the study as readers would, and never mention a text, a script or these notes.\n"
            "- A natural line to move to the next piece. No \"welcome back\", no \"stay tuned\", no slogans, no sponsors.\n"
            "- Pieces marked \"Second look\" ran in an earlier edition and weren't opened; say so in a few words before the first of them.\n"
            "- End with each host naming the one piece they'd read in full, and a quick goodbye.\n\n"
            "How they talk:\n"
            "- Mostly short turns of one to three sentences, a longer one when someone is explaining. They can cut in or finish "
            "each other's thought.\n"
            "- None of the tics of made-up podcasts: don't open replies with \"Exactly\", \"Absolutely\", \"Right\", \"Totally\" or "
            "\"Wow\"; no \"that's wild\", \"mind-blowing\", \"let's dive in\" or \"unpack\"; no praising each other's points. "
            "They rarely need to say each other's names.\n"
            f"- Every turn is its own line starting with the speaker's name and a colon ({a}: ...), with a blank line between turns. "
            "Only the words they say: no stage directions, sound effects, or notes on how a line is said.\n\n"
            "Written for the ear:\n"
            "- Short sentences. Spell out numbers, dates and money the way they're said "
        )
    else:
        head = (
        "Write today's Edition as a script for one voice to read aloud: a short morning programme made for one listener, "
        "who will hear it through earphones on a walk or a bike ride and hasn't read any of it.\n\n"
        + length +
        "How it goes:\n"
        f"- Begin with the day ({day}), then run through the headlines quickly, a short phrase for each, so the listener knows what's coming.\n"
        "- Then every piece, in the order given, none left out. Say where it's from in passing (the publication, or the writer "
        "when the text names one), then tell it: what happened or what the writer argues, the best detail or two, and why it "
        "matters. Keep to what the text says. Add no facts, numbers, quotes or opinions of your own; when the text is unclear, "
        "leave that part out rather than guess.\n"
        "- A plain line to move from one piece to the next. No \"welcome back\", no hype, no jokes, no \"stay tuned\", no slogans.\n"
        "- Pieces marked \"Second look\" ran in an earlier edition and weren't opened; say so in a few words before the first of them.\n"
        "- End with a line or two: the one or two pieces most worth reading in full, and that's the edition.\n\n"
        "Written for the ear:\n"
        "- Short sentences, in paragraphs of two to five sentences. Spell out numbers, dates and money the way they're said "
        )
    head += (
        "(\"about three hundred million dollars\", \"the nineteen-forties\"). No abbreviations, symbols, lists, headings, links, "
        "brackets, slashes or emoji: the voice reads every character.\n"
        "- Hebrew, Yiddish and Aramaic words, and Israeli names and places, are read by an English voice, so write them in English "
        "letters the way they're said: hyphens between syllables (Va-yish-lakh, Ye-ru-sha-la-yim), an apostrophe for a short "
        "vowel between consonants (Kir-yat Sh'mo-na), kh for the throaty sound, gh for a hard g before e or i (Gheh-ma-ra). "
        "Words most English speakers know stay as they are (Shabbat, Torah, Talmud, Rosh Hashanah, Netanyahu, Tel Aviv, "
        "Jerusalem). Never Hebrew script.\n"
        "- Quote the text only when a line is worth hearing in its own words, and say whose words they are.\n\n"
        "Write exactly this shape and nothing before or after it, each marker on its own line:\n"
        "=== intro ===\n(the day and the headlines)\n"
        + "".join(f"=== {p['n']} ===\n(piece {p['n']})\n" for p in ps[:2])
        + ("...\n" if len(ps) > 2 else "")
        + "=== end ===\n(the closing lines)\n\n"
        "The pieces:\n")
    body = []
    for p, n in zip(ps, each):
        body.append(f"--- {p['n']} ---\nSection: {p['section']}\nFrom: {p['publication']}\nTitle: {p['title']}\nLength: about {n} words\n"
                    + (f"First ran: {p['callback']}\n" if p.get("callback") else "")
                    + f"Text:\n{p['text']}\n")
    return head + "\n".join(body)


STAGE = re.compile(r"[\[(]\s*(?:laugh|chuckl|sigh|paus|beat|smil|grin|both)\w*[^\])\n]*[\])]", re.I)


def _turns(text, names):
    """A conversation as the voice needs it: each host's turn its own paragraph, starting "Name: ", and no
    stage directions (Kokoro would read them out)."""
    t = STAGE.sub("", re.sub(r"[*_]{1,3}", "", text or ""))
    if names:
        canon = {n.lower(): n for n in names}
        alt = "|".join(re.escape(n) for n in names)
        t = re.sub(rf"^[ \t]*({alt})[ \t]*:[ \t]*", lambda m: "\n" + canon[m.group(1).lower()] + ": ", t, flags=re.M | re.I)
    return t


def parse(out, ps, names=()):
    """The model's script as parts [{key, text}] in the paper's order: "intro", each piece's number, "end".
    A piece it left out gets the rules' few lines, so every chapter is there. With hosts' names, each turn
    is a paragraph starting with its host's name."""
    found = {}
    marks = list(MARK.finditer(out or ""))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(out)
        text = speakable(_turns(out[m.end():end], names))
        if text:
            found[m.group(1).lower()] = text
    if not found.get("intro") or sum(1 for p in ps if str(p["n"]) in found) < max(1, len(ps) // 2):
        raise ValueError("The script didn't come back in its shape")
    rules = {x["key"]: x["text"] for x in script_rules(ps, None, 0)}
    parts = [{"key": "intro", "text": found["intro"]}]
    for p in ps:
        parts.append({"key": str(p["n"]), "text": found.get(str(p["n"])) or rules[str(p["n"])]})
    parts.append({"key": "end", "text": found.get("end") or "That's the edition."})
    return parts


def speakable(text):
    """What the voice should read: no markup, links, brackets or stray symbols, paragraphs kept."""
    t = re.sub(r"<[^>\n]{1,40}>", "", text or "")                 # stray markup
    t = re.sub(r"\[([^\]\n]*)\]\([^)\n]*\)", r"\1", t)            # a link keeps its words
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"[*_#`>|\[\]{}<>/\\]+", " ", t)
    t = re.sub(r"\(\s*\)", "", t)
    t = re.sub(r"^[ \t]*[-•][ \t]+", "", t, flags=re.M)
    paras = [" ".join(p.split()) for p in re.split(r"\n\s*\n", t)]
    return "\n\n".join(p for p in paras if p)


def _opening(text, most):
    """The first `most` words or so of a text, ending on a sentence."""
    words = (text or "").split()
    if len(words) <= most:
        return " ".join(words)
    cut = " ".join(words[:most])
    stop = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    return cut[:stop + 1] if stop > len(cut) // 3 else cut + "."


def script_rules(ps, facts, minutes):
    """Without the model: the day, the headlines, then each piece's opening lines."""
    share = max(60, int(minutes * WPM / max(1, len(ps)))) if minutes else 90
    parts = []
    if facts is not None:
        heads = " ".join(f"{p['title'].rstrip('.')}." for p in ps)
        parts.append({"key": "intro", "text": f"This is the Edition for {facts['date']}. {len(ps)} pieces today.\n\n{heads}"})
    for p in ps:
        lead = f"From {p['publication']}: {p['title'].rstrip('.')}." if p["publication"] else f"{p['title'].rstrip('.')}."
        parts.append({"key": str(p["n"]), "text": speakable(lead + "\n\n" + _opening(p["text"], share))})
    if facts is not None:
        parts.append({"key": "end", "text": "That's the edition. Everything in it is in Daf, to read in full."})
    return parts


def script(conn, ed, day, minutes, use_ai=True, hosts=None):
    """(parts, how): the script, by the model or by the rules."""
    from . import ai
    ps = pieces(conn, ed)
    facts = day_facts(conn, day, ed)
    conn.commit()                         # the Hebrew date's cache row: not held through the model
    if use_ai:
        try:
            names = [h["name"] for h in hosts or [] if h["name"]] if hosts and len(hosts) >= 2 else []
            return parse(ai.run(prompt(ps, facts, minutes, hosts), timeout=900), ps, names), "model"
        except Exception as ex:  # noqa: BLE001 - the rules still make an episode
            log.warning("edition audio: the model didn't write it (%s); the rules do", ex)
            return script_rules(ps, facts, minutes), f"rules ({str(ex)[:120]})"
    return script_rules(ps, facts, minutes), "rules"


# ---- the voice ------------------------------------------------------------------------------------

def speak(text, voice, speed, tries=4):
    """Kokoro's PCM for one paragraph, kept by text and voice so a second try picks up where it stopped.
    Kokoro's memory only grows, so its container is capped and restarts itself when it reaches the cap,
    which a long read can do: then this waits for it to come back and asks again."""
    PARTS.mkdir(parents=True, exist_ok=True)
    path = PARTS / (hashlib.sha1(f"{voice}|{speed}|{text}".encode()).hexdigest() + ".pcm")
    if not path.exists():
        for n in range(tries):
            try:
                data = _kokoro_pcm(text, voice, speed)
                break
            except OSError as ex:            # refused, dropped, timed out, or a 5xx while it starts
                if n == tries - 1 or (isinstance(ex, urllib.error.HTTPError) and ex.code < 500):
                    raise
                log.info("edition audio: Kokoro went away (%s); waiting for it", str(ex)[:80])
                _wait_for_kokoro()
        if len(data) < RATE // 10:
            raise RuntimeError("Kokoro sent no sound")
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
    return path.read_bytes()


def _kokoro_pcm(text, voice, speed):
    from . import reader
    body = json.dumps({"model": "kokoro", "input": text[:4000], "voice": voice, "response_format": "pcm",
                       "speed": speed, "stream": False}).encode()
    try:
        base = reader._kokoro()
    except RuntimeError as ex:               # not running at all (between a stop and its restart)
        raise ConnectionError(str(ex)) from ex
    req = urllib.request.Request(base + "/v1/audio/speech", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def _wait_for_kokoro(most=180):
    from . import reader
    end = time.time() + most
    time.sleep(5)
    while time.time() < end:
        try:
            with urllib.request.urlopen(reader._kokoro() + "/v1/audio/voices", timeout=10) as r:
                r.read()
            return
        except Exception:  # noqa: BLE001 - still starting
            time.sleep(5)


def _quiet(sec):
    return b"\x00\x00" * int(RATE * sec)


def who(para, hosts):
    """(the host's index or None, the words) for a paragraph: a host's turn starts with their name and a colon."""
    m = re.match(r"([A-Za-z][A-Za-z .'-]{0,23}):\s+", para)
    if m:
        for i, h in enumerate(hosts):
            if h["name"] and h["name"].lower() == m.group(1).strip().lower():
                return i, para[m.end():].strip()
    return None, para.strip()


def voice(parts, hosts):
    """All the parts read, each turn in its host's voice and speed (one host: every paragraph in the one
    voice), as one PCM stream, with each part's [start, end] and each paragraph's [start, end, text, host's
    name] in seconds. A paragraph without a name is the last speaker's."""
    pcm = bytearray()
    times, lines = [], []
    cur = 0
    for i, part in enumerate(parts):
        if i:
            pcm += _quiet(GAP["part"])
        start = len(pcm) / 2 / RATE
        first = True
        for para in part["text"].split("\n\n"):
            n, words = who(para, hosts)
            if not words:
                continue
            nxt = cur if n is None else n
            if not first:
                pcm += _quiet(GAP["turn"] if nxt != cur else GAP["para"])
            cur, first = nxt, False
            h = hosts[cur]
            a = len(pcm) / 2 / RATE
            got = speak(words, h["voice"], h["speed"])
            pcm += got[: len(got) - len(got) % 2]
            lines.append([round(a, 2), round(len(pcm) / 2 / RATE, 2), words, h["name"]])
        times.append([round(start, 2), round(len(pcm) / 2 / RATE, 2)])
    return bytes(pcm), times, lines


def encode(pcm, out, title, chapters):
    """MP3 (64k mono, louder to the podcast level of -16 LUFS) with ID3 chapters."""
    meta = [";FFMETADATA1", f"title={_ff(title)}", f"artist={NAME}", f"album={NAME}"]
    for c in chapters:
        meta += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(c['start'] * 1000)}", f"END={int(c['end'] * 1000)}", f"title={_ff(c['title'])}"]
    tmp = out.with_suffix(".tmp.mp3")
    metafile = out.with_suffix(".ffmeta")
    metafile.write_text("\n".join(meta) + "\n")
    try:
        r = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                            "-f", "s16le", "-ar", str(RATE), "-ch_layout", "mono", "-i", "pipe:0", "-i", str(metafile),
                            "-map_metadata", "1", "-map_chapters", "1", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                            "-ar", "44100", "-ac", "1", "-c:a", "libmp3lame", "-b:a", "64k", "-id3v2_version", "3", str(tmp)],
                           input=pcm, capture_output=True, timeout=1800)
        if r.returncode:
            raise RuntimeError((r.stderr or b"").decode("utf-8", "replace")[-300:] or "ffmpeg failed")
        tmp.replace(out)
    finally:
        metafile.unlink(missing_ok=True)
        tmp.unlink(missing_ok=True)


def _ff(s):
    return re.sub(r"([=;#\\\n])", r"\\\1", str(s or ""))


# ---- making it ------------------------------------------------------------------------------------

def key_of(ed):
    return f"{ed['day']}-{ed['made']}"


def get(day):
    """The episode's facts for a day (the newest, if the edition was made again), or None."""
    day = day.isoformat() if isinstance(day, date) else day
    found = sorted(p for p in DIR.glob(f"{day}-*.json") if EPISODE.fullmatch(p.name)) if DIR.exists() else []
    for p in reversed(found):
        try:
            m = json.loads(p.read_text())
        except ValueError:
            continue
        if (DIR / f"{m['key']}.mp3").exists():
            return m
    return None


def make(day=None, use_ai=None, minutes=None):
    """Write, read and save the day's episode. Returns its facts."""
    s = config.load_settings()
    a = settings(s)
    day = day or T.today(s)
    minutes = int(minutes or a["minutes"])
    from . import edition
    with db.session() as conn:
        ed = edition.get(conn, day)
        if not ed or not ed["items"]:
            raise ValueError("No edition for that day")
        DIR.mkdir(parents=True, exist_ok=True)
        kept = DIR / f"{key_of(ed)}.script.json"      # a second try reads the same script, so the voice's parts are still good
        try:
            got = json.loads(kept.read_text())
            if got.get("minutes") != minutes or got.get("hosts") != [h["name"] for h in a["hosts"]]:
                raise ValueError("another length or other hosts")
            parts, how = got["parts"], got["how"]
        except (OSError, ValueError, KeyError):
            parts, how = script(conn, ed, day, minutes, use_ai=edition.settings(s)["ai"] if use_ai is None else use_ai, hosts=a["hosts"])
            kept.write_text(json.dumps({"parts": parts, "how": how, "minutes": minutes, "hosts": [h["name"] for h in a["hosts"]]},
                                       ensure_ascii=False))
        ps = pieces(conn, ed)
    t0 = time.time()
    pcm, times, lines = voice(parts, a["hosts"])
    base = config.public_url(s)
    chapters = []
    for part, (start, end) in zip(parts, times):
        if part["key"] == "end":
            if chapters:
                chapters[-1]["end"] = end          # the closing lines belong to the last piece's chapter
            continue
        if part["key"] == "intro":
            chapters.append({"start": start, "end": end, "title": "Headlines"})
            continue
        p = ps[int(part["key"]) - 1]
        chapters.append({"start": start, "end": end, "title": p["title"], "id": p["id"], "publication": p["publication"],
                         "url": f"{base}/#read/{p['id']}", "heard": [start, end]})
    key = f"{ed['day']}-{int(time.time())}"         # its own name each time, so a podcast app sees an episode made again as new
    title = f"{day.strftime('%A')}, {day.day} {day.strftime('%B')}"
    encode(pcm, DIR / f"{key}.mp3", title, chapters)
    meta = {"key": key, "day": ed["day"], "made": ed["made"], "title": title, "how": how, "minutes": minutes,
            "hosts": a["hosts"], "seconds": round(len(pcm) / 2 / RATE, 1),
            "bytes": (DIR / f"{key}.mp3").stat().st_size, "spoken": int(time.time()), "took": int(time.time() - t0),
            "chapters": chapters, "lines": lines, "parts": parts}
    tmp = DIR / f"{key}.json.tmp"
    tmp.write_text(json.dumps(meta, ensure_ascii=False))
    tmp.replace(DIR / f"{key}.json")
    (DIR / f"{key_of(ed)}.script.json").unlink(missing_ok=True)       # it's in the episode's facts now
    for old in DIR.glob(f"{ed['day']}-*"):           # an edition made again replaces its episode
        if not old.name.startswith(key + "."):
            old.unlink(missing_ok=True)
    prune()
    log.info("edition audio %s: %d min (%s), read in %d s", key, round(meta["seconds"] / 60), how, meta["took"])
    return meta


def prune(now=None):
    """Episodes older than KEEP_DAYS, and the voice's paragraphs once they're two days old."""
    now = now or time.time()
    if not DIR.exists():
        return
    for p in DIR.glob("????-??-??-*"):
        try:
            d = date.fromisoformat(p.name[:10])
        except ValueError:
            continue
        if (date.fromtimestamp(now) - d).days > KEEP_DAYS:
            p.unlink(missing_ok=True)
    if PARTS.exists():
        for p in PARTS.iterdir():
            if now - p.stat().st_mtime > 2 * 86400:
                p.unlink(missing_ok=True)


def maybe_make():
    """From the sync loop: today's episode once today's edition is there (and again if it was made
    again), three tries a day."""
    s = config.load_settings()
    if not settings(s)["on"]:
        return
    from . import edition
    day = T.today(s)
    with db.session() as conn:
        ed = edition.get(conn, day)
        if not ed or not ed["items"] or edition.is_building():
            return
        m = get(day)
        if m and m["made"] == ed["made"]:
            return
        tries = conn.execute("SELECT v FROM kv WHERE k = 'edition_audio_tries'").fetchone()
        t = json.loads(tries[0]) if tries else {}
        if t.get("key") == key_of(ed) and t.get("n", 0) >= 3:
            return
    if not _making.acquire(blocking=False):
        return
    try:
        with db.session() as conn:
            conn.execute("INSERT OR REPLACE INTO kv (k, v) VALUES ('edition_audio_tries', ?)",
                         (json.dumps({"key": key_of(ed), "n": (t.get("n", 0) + 1) if t.get("key") == key_of(ed) else 1}),))
        make(day)
    finally:
        _making.release()


def is_making():
    return _making.locked()


# ---- the feed -------------------------------------------------------------------------------------

def feed_token(conn):
    """A new address for the feed: the old one stops working."""
    from . import auth
    conn.execute("DELETE FROM devices WHERE name = ?", (DEVICE,))
    return auth.new_device_token(conn, DEVICE)


def feed_url(token, s=None):
    return f"{config.public_url(s)}{PATH}{token}/feed.xml"


def episodes():
    out = []
    for p in sorted((p for p in DIR.glob("????-??-??-*.json") if EPISODE.fullmatch(p.name)), reverse=True) if DIR.exists() else []:
        try:
            m = json.loads(p.read_text())
        except ValueError:
            continue
        if (DIR / f"{m['key']}.mp3").exists():
            out.append(m)
    return out


def feed(token, s=None):
    """The podcast feed (RSS with the iTunes and Podcasting 2.0 tags a podcast app reads)."""
    s = s if s is not None else config.load_settings()
    base = config.public_url(s)
    here = f"{base}{PATH}{token}/"
    items = []
    for m in episodes():
        pub = datetime.fromtimestamp(m.get("spoken") or m["made"], timezone.utc)
        rows = [c for c in m["chapters"] if c.get("id")]
        text = "\n".join(f"{n}. {c['title']}" + (f" ({c['publication']})" if c.get("publication") else "") for n, c in enumerate(rows, 1))
        html = "<ol>" + "".join(f'<li><a href="{escape(c["url"])}">{escape(c["title"])}</a>'
                                + (f" · {escape(c['publication'])}" if c.get("publication") else "") + "</li>" for c in rows) + "</ol>"
        items.append(
            "<item>"
            f"<title>{escape(m['title'])}</title>"
            f'<guid isPermaLink="false">daf-edition-{escape(m["key"])}</guid>'
            f"<pubDate>{format_datetime(pub)}</pubDate>"
            f"<description>{escape(text)}</description>"
            f"<content:encoded><![CDATA[{html}]]></content:encoded>"
            f'<enclosure url="{escape(here + m["key"])}.mp3" length="{m["bytes"]}" type="audio/mpeg"/>'
            f"<itunes:duration>{int(m['seconds'])}</itunes:duration>"
            f'<podcast:chapters url="{escape(here + m["key"])}.chapters.json" type="application/json+chapters"/>'
            f'<podcast:transcript url="{escape(here + m["key"])}.transcript.json" type="application/json"/>'
            "</item>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" '
            'xmlns:podcast="https://podcastindex.org/namespace/1.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">'
            "<channel>"
            f"<title>{NAME}</title><link>{escape(base)}/#edition</link>"
            "<description>The day's Edition, read aloud.</description><language>en</language>"
            f"<itunes:author>Daf</itunes:author><itunes:image href=\"{escape(base)}/icon-512.png\"/>"
            f"<image><url>{escape(base)}/icon-512.png</url><title>{NAME}</title><link>{escape(base)}/#edition</link></image>"
            "<itunes:block>Yes</itunes:block><itunes:explicit>false</itunes:explicit>"
            + "".join(items) + "</channel></rss>")


def chapters_json(m):
    """Podcasting 2.0 chapters: each piece with a link that opens it in Daf."""
    return {"version": "1.2.0", "chapters": [{"startTime": c["start"], "endTime": c["end"], "title": c["title"]}
                                             | ({"url": c["url"]} if c.get("url") else {}) for c in m["chapters"]]}


def transcript_json(m):
    """Podcasting 2.0 transcript, a segment per paragraph (the times are the voice's own, not guessed)."""
    return {"version": "1.0.0", "segments": [{"startTime": l[0], "endTime": l[1], "body": l[2]}
                                             | ({"speaker": l[3]} if len(l) > 3 and l[3] else {}) for l in m["lines"]]}


def file_for(name):
    """(kind, payload) for a published file name: <key>.mp3, <key>.chapters.json or <key>.transcript.json."""
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2}-\d+)\.(mp3|chapters\.json|transcript\.json)", name or "")
    if not m:
        return None, None
    key, what = m.groups()
    if what == "mp3":
        p = DIR / f"{key}.mp3"
        return ("mp3", p) if p.exists() else (None, None)
    try:
        meta = json.loads((DIR / f"{key}.json").read_text())
    except (OSError, ValueError):
        return None, None
    return "json", chapters_json(meta) if what == "chapters.json" else transcript_json(meta)


# ---- back in Daf: what was heard, and the episode's page ------------------------------------------

def is_ours(url):
    return PATH in (url or "")


def meta_for(episode):
    """The saved facts of the episode an address points at, or None."""
    m = re.search(re.escape(PATH) + r"[^/]+/(\d{4}-\d{2}-\d{2}-\d+)\.mp3", episode or "")
    if not m:
        return None
    try:
        return json.loads((DIR / f"{m.group(1)}.json").read_text())
    except (OSError, ValueError):
        return None


def remember(conn, episode, s=None):
    """The episode in Daf's podcast list (gp_episodes) from its saved facts, so it has its name, chapters
    and transcript without Daf reading its own feed over the internet."""
    m = meta_for(episode)
    if not m:
        return None
    here = episode.rsplit("/", 1)[0] + "/"
    rows = [c for c in m["chapters"] if c.get("id")]
    notes = "<ol>" + "".join(f"<li>{escape(c['title'])}" + (f" · {escape(c['publication'])}" if c.get("publication") else "") + "</li>"
                             for c in rows) + "</ol>"
    conn.execute(
        "INSERT INTO gp_episodes (url, link, title, podcast, podcast_title, published, guid, author, image, duration, notes, "
        "transcript_url, transcript_type, chapters_url, checked) VALUES (?, ?, ?, ?, ?, ?, ?, 'Daf', ?, ?, ?, ?, 'application/json', ?, ?) "
        "ON CONFLICT(url) DO UPDATE SET title = excluded.title, podcast_title = excluded.podcast_title, duration = excluded.duration, "
        "notes = excluded.notes, checked = excluded.checked",
        (episode, f"{config.public_url(s)}/#edition", m["title"], here + "feed.xml", NAME, m.get("spoken") or m["made"],
         f"daf-edition-{m['key']}", f"{config.public_url(s)}/icon-512.png", int(m["seconds"]), notes,
         here + m["key"] + ".transcript.json", here + m["key"] + ".chapters.json", int(time.time())))
    return m


def store_transcript(audio):
    """episodes.transcribe for one of these: the script is the transcript, timed by the voice itself."""
    from . import episodes, media
    m = meta_for(audio)
    if not m:
        raise RuntimeError("That episode is gone")
    lines = [{"ts": int(l[0]), "spk": (l[3] if len(l) > 3 and l[3] else None), "x": l[2]} for l in m["lines"]]
    chapters = [{"t": float(c["start"]), "title": c["title"]} for c in m["chapters"]]
    bl = media._blocks_from_lines(lines, [{"start_time": c["t"], "title": c["title"]} for c in chapters])
    with db.session() as conn:
        remember(conn, audio)
        episodes._store(conn, audio, bl, chapters, "publisher", "en")
    return len(bl)


def heard(conn, episode, started, position, at):
    """A play AntennaPod reported on an episode of this feed: each piece whose chapter it covered (most
    of it) counts as opened at that time. Returns the pieces' ids."""
    meta = meta_for(episode)
    if not meta:
        return []
    a, b = float(started or 0), float(position or 0)
    out = []
    for c in meta["chapters"]:
        if not c.get("id"):
            continue
        s, e = c.get("heard") or [c["start"], c["end"]]
        if e > s and (min(b, e) - max(a, s)) >= 0.6 * (e - s):
            conn.execute("UPDATE docs SET opened = COALESCE(opened, ?) WHERE id = ?", (int(at), c["id"]))
            out.append(c["id"])
    return out
