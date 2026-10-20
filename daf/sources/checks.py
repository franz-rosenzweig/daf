"""`daf doctor`: every source, whether it answers, and how fresh its data is.

Each check returns a dict: name, ok, detail, phase (the build phase that needs it).
A source a later phase needs can be missing without making today's Daf unhealthy.
"""
import json
import os
import shutil
import subprocess
import time
import urllib.request

from .. import config
from ..db import read_only


def _age(ts):
    if not ts:
        return "never"
    d = int(time.time()) - int(ts)
    if d < 3600:
        return f"{d // 60} min ago"
    if d < 86400 * 2:
        return f"{d // 3600} h ago"
    return f"{d // 86400} days ago"


def _http(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read(300)
    except Exception as e:  # noqa: BLE001 - any failure means "doesn't answer"
        return None, str(e).encode()


def _docker_ip(name):
    try:
        out = subprocess.run(["docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", name],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def check_kindle(conn):
    newest = {r["origin"]: r["m"] for r in conn.execute("SELECT origin, MAX(start) AS m FROM pages GROUP BY origin")}
    plugin = newest.get("plugin")
    ko = newest.get("koinsight")
    online = None
    try:
        out = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=10)
        for p in json.loads(out.stdout).get("Peer", {}).values():
            if "100.66.33.78" in (p.get("TailscaleIPs") or []):
                online = p.get("Online")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    where = "online" if online else "asleep or offline" if online is False else "not seen on Tailscale"
    if plugin:
        detail = f"Daf plugin last sent pages {_age(plugin)} · Kindle {where}"
    else:
        detail = f"no Daf plugin yet; KoInsight's newest page turn {_age(ko)} · Kindle {where}"
    return {"name": "Kindle", "ok": bool(plugin or ko), "detail": detail, "phase": 1, "last": plugin or ko}


def check_koinsight():
    if config.load_settings().get("koinsight") == "off":
        return None                   # retired: the Daf plugin sends the Kindle's pages
    try:
        c = read_only(config.KOINSIGHT_DB)
        n, m = c.execute("SELECT COUNT(*), MAX(start_time) FROM page_stat").fetchone()
        c.close()
        return {"name": "KoInsight", "ok": True, "detail": f"{n:,} page turns, newest {_age(m)}", "phase": 1, "last": m}
    except Exception as e:  # noqa: BLE001
        return {"name": "KoInsight", "ok": False, "detail": str(e), "phase": 1}


def check_abs(conn):
    r = conn.execute("SELECT COUNT(*), MAX(start) FROM sessions WHERE origin = 'audiobookshelf'").fetchone()
    try:
        c = read_only(config.ABS_DB)
        c.execute("SELECT 1 FROM playbackSessions LIMIT 1")
        c.close()
        return {"name": "Audiobookshelf", "ok": True, "detail": f"{r[0]} listening sessions, newest {_age(r[1])}",
                "phase": 1, "last": r[1]}
    except Exception as e:  # noqa: BLE001
        return {"name": "Audiobookshelf", "ok": False, "detail": str(e), "phase": 1}


def check_calibre():
    parts, ok = [], True
    for p in config.CALIBRE_DBS:
        try:
            c = read_only(p)
            n = c.execute("SELECT COUNT(*) FROM books").fetchone()[0]
            c.close()
            parts.append(f"{p.parent.name} {n}")
        except Exception as e:  # noqa: BLE001
            ok = False
            parts.append(f"{p.parent.name}: {e}")
    return {"name": "Calibre", "ok": ok, "detail": " · ".join(parts) + " books", "phase": 2}


def check_vault():
    d = config.READING_LOG_DIR
    parent = d if d.exists() else d.parent
    ok = parent.exists() and os.access(parent, os.W_OK)
    return {"name": "Obsidian vault", "ok": ok,
            "detail": f"{'writable' if ok else 'NOT writable'}: {d.relative_to(config.VAULT)}", "phase": 1}


def _status(conn, source):
    r = conn.execute("SELECT ok, detail, last_data AS last_ok, checked FROM source_status WHERE name = ?", (source,)).fetchone() if conn else None
    return dict(r) if r else None


def check_freshrss(conn=None):
    code, body = _http(config.FRESHRSS_URL + "/api/greader.php")
    up = code == 200 and body.strip().startswith(b"OK")
    st = _status(conn, "freshrss")
    if not up:
        return {"name": "FreshRSS", "ok": False, "detail": f"no answer: {body[:80]!r}", "phase": 4}
    if st and not st["ok"]:
        return {"name": "FreshRSS", "ok": False, "detail": f"last sync failed: {st['detail']}", "phase": 4}
    return {"name": "FreshRSS", "ok": True, "detail": (st["detail"] + ", synced " + _age(st["last_ok"])) if st else "answers; not synced yet", "phase": 4}


def check_sefaria(conn):
    st = _status(conn, "sefaria")
    if not st:
        return {"name": "Sefaria", "ok": True, "detail": "not synced yet", "phase": 7}
    return {"name": "Sefaria", "ok": bool(st["ok"]), "detail": f"{st['detail']}, {_age(st['last_ok'])}" if st["ok"] else st["detail"], "phase": 7}


def check_jobs(conn):
    q = conn.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued', 'running')").fetchone()[0]
    bad = conn.execute("SELECT kind, error FROM jobs WHERE status = 'failed' AND finished > ? ORDER BY id DESC",
                       (int(time.time()) - 86400,)).fetchall()
    detail = f"{q} waiting" + (f" · {len(bad)} failed today, last: {bad[0]['kind']}: {(bad[0]['error'] or '')[:80]}" if bad else "")
    return {"name": "Transcripts", "ok": not bad and q < 20, "detail": detail, "phase": 5}


def check_podcasts(conn):
    last = conn.execute("SELECT MAX(received) FROM gp_actions").fetchone()[0]
    subs = conn.execute("SELECT COUNT(*) FROM gp_subs WHERE removed IS NULL").fetchone()[0]
    return {"name": "AntennaPod", "ok": True, "phase": 5,
            "detail": f"{subs} subscriptions, last sync {_age(last)}" if last else "not connected (Preferences → Podcasts)"}


def check_karakeep():
    from . import karakeep
    m = karakeep.mode()
    if m == "off":
        return None                                   # Daf keeps the Library alone: nothing to check
    code, _ = _http("http://127.0.0.1:3000/api/health")
    try:
        c = read_only(config.KARAKEEP_DB)
        n = c.execute("SELECT COUNT(*) FROM bookmarks").fetchone()[0]
        h = c.execute("SELECT COUNT(*) FROM highlights").fetchone()[0]
        c.close()
        detail = f"{n} saved, {h} highlights" + ("" if code == 200 else " · web app not answering") + \
            (" · read only: Daf keeps the Library, and takes in what's saved here" if m == "read" else "")
        return {"name": "Karakeep", "ok": code == 200, "detail": detail, "phase": 2}
    except Exception as e:  # noqa: BLE001
        return {"name": "Karakeep", "ok": False, "detail": str(e), "phase": 2}


def check_kokoro():
    ip = _docker_ip("kokoro-tts")
    if not ip:
        return {"name": "Kokoro voice", "ok": False, "detail": "container not running", "phase": 4}
    code, body = _http(f"http://{ip}:8880/v1/audio/voices")
    return {"name": "Kokoro voice", "ok": code == 200, "detail": "answers" if code == 200 else "no answer", "phase": 4}


def check_tools():
    whisper = subprocess.run(["/usr/bin/python3", "-c", "import faster_whisper"], capture_output=True, timeout=30).returncode == 0
    have = {
        "claude": os.path.exists(config.CLAUDE),
        "faster-whisper": whisper,
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "yt-dlp": bool(shutil.which("yt-dlp")),
        "signal-cli": bool(shutil.which("signal-cli")),
    }
    missing = [k for k, v in have.items() if not v]
    return {"name": "Host tools", "ok": not missing,
            "detail": ", ".join(have) + " all present" if not missing else "missing: " + ", ".join(missing),
            "phase": 2}


def run_all(conn):
    return [x for x in [check_kindle(conn), check_koinsight(), check_abs(conn), check_vault(), check_calibre(),
            check_karakeep(), check_freshrss(conn), check_kokoro(), check_sefaria(conn), check_podcasts(conn),
            check_jobs(conn), check_tools()] if x]
