"""Enough of the gpodder.net API (v2) for AntennaPod's "gpodder.net" sync, pointed at Daf.

AntennaPod logs in with HTTP Basic auth: any username, and as password the token of the
Daf device named "antennapod" (Preferences → Phone). It then uploads subscriptions and
episode actions (play, with started/position seconds), which Daf turns into listening
time. Podcasts never count toward the hour; they show as their own line.
"""
import json
import re
import time
from datetime import datetime, timezone

from . import config


def _ts(s):
    if isinstance(s, (int, float)):
        return int(s)
    try:
        return int(datetime.fromisoformat(str(s).replace("Z", "+00:00")).replace(tzinfo=timezone.utc).timestamp())
    except ValueError:
        return int(time.time())


def subs_changes(conn, since):
    add = [r[0] for r in conn.execute("SELECT url FROM gp_subs WHERE removed IS NULL AND added > ?", (since,))]
    rem = [r[0] for r in conn.execute("SELECT url FROM gp_subs WHERE removed IS NOT NULL AND removed > ?", (since,))]
    return {"add": add, "remove": rem, "timestamp": int(time.time())}


def subs_upload(conn, body):
    now = int(time.time())
    for u in body.get("add", []) or []:
        conn.execute("INSERT INTO gp_subs (url, added, removed) VALUES (?, ?, NULL) ON CONFLICT(url) DO UPDATE SET added = excluded.added, removed = NULL", (u, now))
    for u in body.get("remove", []) or []:
        conn.execute("UPDATE gp_subs SET removed = ? WHERE url = ?", (now, u))
    return {"timestamp": now, "update_urls": []}


def subs_replace(conn, urls):
    """The older PUT-a-whole-list form."""
    now = int(time.time())
    keep = set(urls)
    for (u,) in conn.execute("SELECT url FROM gp_subs WHERE removed IS NULL").fetchall():
        if u not in keep:
            conn.execute("UPDATE gp_subs SET removed = ? WHERE url = ?", (now, u))
    for u in keep:
        conn.execute("INSERT INTO gp_subs (url, added, removed) VALUES (?, ?, NULL) ON CONFLICT(url) DO UPDATE SET removed = NULL", (u, now))


def actions_since(conn, since):
    rows = conn.execute("SELECT * FROM gp_actions WHERE received > ? ORDER BY id", (since,)).fetchall()
    out = []
    for r in rows:
        a = {"podcast": r["podcast"], "episode": r["episode"], "action": r["action"],
             "timestamp": datetime.fromtimestamp(r["timestamp"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")}
        if r["guid"]:
            a["guid"] = r["guid"]
        if r["action"] == "play":
            a.update(started=r["started"] or 0, position=r["position"] or 0, total=r["total"] or 0)
        out.append(a)
    return {"actions": out, "timestamp": int(time.time())}


def actions_upload(conn, actions):
    now = int(time.time())
    for a in actions or []:
        if not isinstance(a, dict) or not a.get("episode"):
            continue
        cur = conn.execute(
            "INSERT INTO gp_actions (podcast, episode, action, position, started, total, timestamp, device, guid, received) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (a.get("podcast"), a["episode"], str(a.get("action", "")).lower(), a.get("position"), a.get("started"),
             a.get("total"), _ts(a.get("timestamp") or now), a.get("device"), a.get("guid"), now))
        if str(a.get("action", "")).lower() == "play":
            started, pos = int(a.get("started") or 0), int(a.get("position") or 0)
            secs = pos - started
            if 0 < secs < 4 * 3600:
                ep = conn.execute("SELECT title, podcast_title FROM gp_episodes WHERE url = ?", (a["episode"],)).fetchone()
                conn.execute("INSERT OR REPLACE INTO sessions (id, source, origin, item, title, author, start, seconds, day, private, note) "
                             "VALUES (?, 'podcast', 'gpodder', ?, ?, ?, ?, ?, NULL, 0, NULL)",
                             (f"gp:{cur.lastrowid}", a["episode"], ep["title"] if ep else "Podcast", ep["podcast_title"] if ep else None,
                              _ts(a.get("timestamp") or now) - secs, secs))
    return {"timestamp": now, "update_urls": []}


def refresh_feeds(conn, limit=15):
    """Titles and episodes for subscribed feeds, so clips and listening have names, and episode pages
    their show notes, transcripts and chapters (episodes.read_feed)."""
    from . import episodes
    day = int(time.time()) - 86400
    for (url,) in conn.execute("SELECT url FROM gp_subs WHERE removed IS NULL AND (checked IS NULL OR checked < ?) LIMIT ?", (day, limit)).fetchall():
        ptitle = episodes.read_feed(conn, url, max_age=3600)
        if ptitle is not None:
            conn.execute("UPDATE gp_subs SET title = ?, checked = ? WHERE url = ?", (ptitle, int(time.time()), url))
        else:                                    # a dead feed shouldn't stop the others
            conn.execute("UPDATE gp_subs SET checked = ? WHERE url = ?", (int(time.time()), url))
    # Name listening sessions that arrived before their feed was read.
    conn.execute("UPDATE sessions SET title = (SELECT title FROM gp_episodes e WHERE e.url = sessions.item), "
                 "author = (SELECT podcast_title FROM gp_episodes e WHERE e.url = sessions.item) "
                 "WHERE origin = 'gpodder' AND title = 'Podcast' AND item IN (SELECT url FROM gp_episodes)")


def overview(conn):
    """The Podcasts page: what you listened to lately (one row an episode, with how far), the clips
    (highlights on episodes, and the older clip-only rows), and the subscriptions."""
    from . import episodes
    subs = [dict(r) | {"image": episodes.show_image(conn, r["url"])}
            for r in conn.execute("SELECT url, title, added FROM gp_subs WHERE removed IS NULL ORDER BY COALESCE(title, url)")]
    recent = []
    for r in conn.execute("SELECT item, title, author, MAX(start + seconds) AS last, SUM(seconds) AS seconds FROM sessions "
                          "WHERE origin = 'gpodder' AND item IS NOT NULL GROUP BY item ORDER BY last DESC LIMIT 20"):
        p = episodes.position(conn, r["item"])
        ep = episodes.meta(conn, r["item"]) or {}
        dur = (p or {}).get("total") or ep.get("duration")
        recent.append({"audio": r["item"], "title": r["title"], "author": r["author"], "start": r["last"], "seconds": r["seconds"],
                       "at": (p or {}).get("t"), "duration": dur, "doc": episodes.doc_for(conn, r["item"], create=False),
                       "transcript": bool(episodes.transcript(conn, r["item"]))})
    clips = [dict(r) for r in conn.execute(
        "SELECT h.id, h.text, h.pos, h.created, d.title, d.source AS author, d.id AS doc FROM highlights h JOIN docs d ON d.id = h.book_id "
        "WHERE d.kind = 'podcast' AND h.deleted = 0 "
        "UNION ALL SELECT h.id, h.text, h.pos, h.created, b.title, b.author, NULL FROM highlights h JOIN books b ON b.id = h.book_id "
        "WHERE h.source = 'clip' AND h.deleted = 0 AND h.book_id LIKE 'pod:%' ORDER BY created DESC LIMIT 30")]
    last = conn.execute("SELECT MAX(received) FROM gp_actions WHERE device IS NOT 'daf'").fetchone()[0]
    return {"subs": subs, "recent": recent, "clips": clips, "last_sync": last}


# ---- moving over from the Nextcloud GPodder Sync app ------------------------------------------
# Its two tables (oc_gpodder_subscriptions, oc_gpodder_episode_action) hold what AntennaPod synced
# there: read once, through psql in the Nextcloud AIO database container, and never written.

NC_DB = ["docker", "exec", "nextcloud-aio-database", "psql", "-U", "oc_nextcloud", "-d", "nextcloud_database", "-At", "-c"]


def _nc(sql):
    import subprocess
    out = subprocess.run(NC_DB + [sql], capture_output=True, text=True, timeout=60)
    if out.returncode:
        raise RuntimeError(out.stderr.strip()[:300] or "psql failed")
    return json.loads(out.stdout.strip() or "null") or []


def import_nextcloud(conn, user="admin"):
    """Subscriptions and play history from Nextcloud's gpodder app into Daf's. Run again, it only adds
    what's new. Returns {subs, removed, actions}."""
    u = user.replace("'", "''")
    subs = _nc(f"SELECT json_agg(t) FROM (SELECT url, subscribed, extract(epoch FROM updated)::int AS at FROM oc_gpodder_subscriptions WHERE user_id = '{u}') t")
    acts = _nc(f"SELECT json_agg(t) FROM (SELECT podcast, episode, lower(action) AS action, position, started, total, guid, "
               f"COALESCE(NULLIF(timestamp_epoch, 0), extract(epoch FROM timestamp)::int) AS ts FROM oc_gpodder_episode_action WHERE user_id = '{u}' ORDER BY ts) t")
    n_sub = n_rm = 0
    for s in subs:
        if s["subscribed"]:
            n_sub += conn.execute("INSERT INTO gp_subs (url, added, removed) VALUES (?, ?, NULL) ON CONFLICT(url) DO NOTHING", (s["url"], s["at"])).rowcount
        else:
            n_rm += conn.execute("INSERT INTO gp_subs (url, added, removed) VALUES (?, ?, ?) ON CONFLICT(url) DO NOTHING", (s["url"], s["at"], s["at"])).rowcount
    new = [{"podcast": a["podcast"], "episode": a["episode"], "action": a["action"], "position": a["position"], "started": a["started"],
            "total": a["total"], "guid": a["guid"], "timestamp": a["ts"], "device": "nextcloud"} for a in acts
           if not conn.execute("SELECT 1 FROM gp_actions WHERE episode = ? AND timestamp = ?", (a["episode"], a["ts"])).fetchone()]
    actions_upload(conn, new)
    return {"subs": n_sub, "removed": n_rm, "actions": len(new)}
