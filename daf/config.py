"""Paths, constants and the settings file.

Everything Daf knows that isn't in a source or the vault lives in STATE
(/srv/docker/daf): the index database, the password hash, settings. The index
can be deleted and rebuilt with `daf sync`; the vault is the record.
"""
import json
import os
import shutil
from datetime import date
from pathlib import Path

STATE = Path(os.environ.get("DAF_STATE", "/srv/docker/daf"))
DB_PATH = STATE / "daf.db"
AUTH_PATH = STATE / "auth.json"
SETTINGS_PATH = STATE / "settings.json"



def _env_file():
    """STATE/daf.env: KEY=value lines, read by the server, the CLI and cron alike (secrets.py reads it too)."""
    out = {}
    try:
        for line in open(STATE / "daf.env", encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


_FILE = _env_file()


def setting(name, default=""):
    """A DAF_* value: the environment first, then STATE/daf.env, then the default."""
    return os.environ.get(name) or _FILE.get(name) or default


# The Obsidian vault the reading log and book notes live in.
VAULT = Path(setting("DAF_VAULT", str(Path.home() / "vault")))
READING_LOG_DIR = VAULT / "Reference" / "reading"

KOINSIGHT_DB = Path("/srv/docker/koinsight/prod.sqlite3")
ABS_DB = Path("/srv/docker/audiobookshelf/config/absdatabase.sqlite")
ABS_USER = "Franz_Rosenzweig"
CALIBRE_DBS = [Path("/srv/docker/cwa-library/metadata.db"), Path("/srv/docker/cwa-libros/metadata.db")]
KARAKEEP_DB = Path("/srv/docker/karakeep-app/db.db")
# Calibre-Web-Automated imports whatever lands here into the Calibre library (then Daf's Books).
CWA_INGEST = Path(os.environ.get("DAF_CWA_INGEST", "/srv/docker/cwa-ingest"))
FRESHRSS_URL = os.environ.get("DAF_FRESHRSS_URL", "http://127.0.0.1:8080")   # a sandbox points it elsewhere
KARAKEEP_URL = "https://keep.tiresia.xyz"

# The addresses to listen on, e.g. "127.0.0.1,<a tailnet address>". Binding an address that isn't up yet at
# boot needs net.ipv4.ip_nonlocal_bind=1.
HOSTS = [h for h in setting("DAF_HOSTS", "127.0.0.1").split(",") if h]
PORT = int(os.environ.get("DAF_PORT", "8440"))

# A command run as `NOTIFY "Daf" "<text>"` for alerts and the morning message (a Signal or ntfy script, say).
NOTIFY = setting("DAF_NOTIFY")


def notify(title, text, timeout=60):
    """Sends an alert through NOTIFY. Returns the command's exit code, or 1 when there's no command."""
    import subprocess
    if not NOTIFY:
        return 1
    try:
        return subprocess.run([NOTIFY, title, text], timeout=timeout, check=False).returncode
    except (OSError, subprocess.TimeoutExpired):
        return 1

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# The Claude CLI (on the subscription): asked for summaries, tags, answers and OCR.
CLAUDE = os.environ.get("DAF_CLAUDE") or shutil.which("claude") or str(Path.home() / ".local/bin/claude")

YEAR30_START = date(2026, 10, 9)   # the first day of Year 30
YEAR29_START = date(2025, 10, 9)
GOAL_MINUTES = 60                  # the starting goal; the goals themselves live in settings (goals.py)

# A Kindle page turn more than this long after the last one starts a new session.
SESSION_GAP_SECONDS = 10 * 60
SYNC_EVERY_SECONDS = 5 * 60

SOURCES = ["kindle", "ebook", "manga", "audio", "article", "paper", "podcast", "video"]
SOURCE_LABELS = {
    "kindle": "Kindle",
    "ebook": "Books in Daf",
    "manga": "Manga in Daf",
    "audio": "Audiobooks",
    "article": "Articles in Daf",
    "paper": "Paper",
    "podcast": "Podcasts",
    "video": "Videos",
}

DEFAULT_SETTINGS = {
    "home_tz": "UTC",
    # What counts toward the hour. Podcasts never do (decided 2026-10-09).
    "count": {"kindle": True, "ebook": True, "manga": True, "audio": True, "article": True, "paper": True, "podcast": False, "video": False},
    "review_size": 5,
    "feed_expire_days": 30,
    "hc_progress": True,      # Hardcover: send progress from Daf's book reader
    "hc_autostart": True,     # Hardcover: a Want-to-read book started in Daf becomes Reading
    "cards_per_day": 5,       # flashcards in the daily review
    "newsletters": [],        # sender addresses whose emails come into Daf (sources/newsletters.py)
    "tts_voice": "af_heart",
    "tts_speed": 1.0,
    "nightstand": [],
    # Reels (social.py): the extension sends Instagram's cookies only when this says so.
    "instagram": {"from_browser": False},
    "podcasts": {"transcribe": True},                 # transcribe an episode you play or open (episodes.py)
    # the sidebar's Pinned places (web/app.js renderSide), below Today, Review, Library, Books, Feed and Highlights
    "nav_pins": ["podcasts", "manga", "torah", "recovery", "shortlist"],
    # Books whose titles contain any of these never appear by name outside Daf's own pages:
    # not in review, the morning message, the nightstand or the Kindle. More live in settings.json.
    "private_titles": ["alcoholics anonymous", "big book", "twelve steps", "twelve and twelve"],
}


def clean_appearance(a):
    ok = lambda v: isinstance(v, str) and 0 < len(v) <= 30 and v.replace("-", "").isalnum()
    return {"mode": a.get("mode") if a.get("mode") in ("system", "light", "dark") else "system",
            "light": a.get("light") if ok(a.get("light")) else "daf", "dark": a.get("dark") if ok(a.get("dark")) else "daf"}


def load_settings():
    s = json.loads(json.dumps(DEFAULT_SETTINGS))
    try:
        saved = json.loads(SETTINGS_PATH.read_text())
    except (FileNotFoundError, ValueError):
        return s
    if isinstance(saved.get("home_tz"), str):
        s["home_tz"] = saved["home_tz"]
    for k, v in (saved.get("count") or {}).items():
        if k in s["count"] and k != "podcast":
            s["count"][k] = bool(v)
    if isinstance(saved.get("review_size"), int) and 1 <= saved["review_size"] <= 20:
        s["review_size"] = saved["review_size"]
    if isinstance(saved.get("nightstand"), list):
        s["nightstand"] = [x for x in saved["nightstand"] if isinstance(x, str)][:3]
    for k in ("tts_voice",):
        if isinstance(saved.get(k), str):
            s[k] = saved[k]
    for k in ("tts_speed",):
        if isinstance(saved.get(k), (int, float)):
            s[k] = float(saved[k])
    if isinstance(saved.get("feed_expire_days"), int):
        s["feed_expire_days"] = saved["feed_expire_days"]
    if saved.get("koinsight") in ("on", "off"):          # "off" since 2026-10-20: the Daf plugin sends the Kindle's pages itself
        s["koinsight"] = saved["koinsight"]
    for k in ("hc_progress", "hc_autostart"):
        if isinstance(saved.get(k), bool):
            s[k] = saved[k]
    if isinstance(saved.get("newsletters"), list):
        s["newsletters"] = [str(x).lower() for x in saved["newsletters"] if isinstance(x, str)][:200]
    if isinstance(saved.get("cards_per_day"), int):
        s["cards_per_day"] = saved["cards_per_day"]
    if isinstance(saved.get("public_url"), str):
        s["public_url"] = saved["public_url"]
    if isinstance(saved.get("not_nightstand"), list):
        s["not_nightstand"] = [x for x in saved["not_nightstand"] if isinstance(x, str)][-20:]
    a = saved.get("appearance")                         # the theme (web/themes.js): one for light, one for dark, and when
    if isinstance(a, dict):
        s["appearance"] = clean_appearance(a)
    if isinstance(saved.get("fonts"), list):            # your own font files (STATE/fonts), for the reading views
        s["fonts"] = [f for f in saved["fonts"] if isinstance(f, dict) and isinstance(f.get("file"), str)][:30]
    for k in ("ai", "digest", "keys", "tips", "library", "instagram", "anilist", "podcasts"):   # Preferences → AI (ai.py), the morning email (digest.py), key bindings, tips (app.py), who keeps the Library (karakeep.mode)
        if isinstance(saved.get(k), dict):
            s[k] = saved[k]
    if isinstance(saved.get("vault_search_exclude"), list):   # vault folders ⌘K never searches (vaultsearch.py)
        s["vault_search_exclude"] = [x for x in saved["vault_search_exclude"] if isinstance(x, str)][:50]
    if isinstance(saved.get("nav_pins"), list):       # Preferences → Sidebar
        s["nav_pins"] = [x for x in saved["nav_pins"] if isinstance(x, str)][:20]
    if isinstance(saved.get("views"), list):          # saved Library and Feed views (Readwise's filtered views)
        s["views"] = [v for v in saved["views"] if isinstance(v, dict) and isinstance(v.get("id"), str)][:30]
    if isinstance(saved.get("goals"), list):
        s["goals"] = [g for g in saved["goals"] if isinstance(g, dict)]      # checked in goals.all_goals
    for k in ("feed_full", "feed_notify"):          # the Feed's per-feed switches: full article, notify
        if isinstance(saved.get(k), list):
            s[k] = [x for x in saved[k] if isinstance(x, str)][:500]
    if isinstance(saved.get("private_titles"), list):
        s["private_titles"] = sorted(set(s["private_titles"]) | {str(x).lower() for x in saved["private_titles"]})
    return s


def save_settings(s):
    STATE.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, indent=2))
    tmp.replace(SETTINGS_PATH)


def public_url(settings=None):
    """Where links in messages point: the HTTPS address once it exists, else the last address it listens on."""
    s = settings if settings is not None else load_settings()
    return (s.get("public_url") or f"http://{HOSTS[-1]}:{PORT}").rstrip("/")
