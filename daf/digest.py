"""The morning email, like Readwise Reader's Daily Summaries: what came into the Library in the last
day, each with its two or three lines, how many new posts wait in the Feed, and yesterday's minutes.

It goes from daf@tiresia.xyz (settings digest.from; tiresia.xyz is a custom domain on the owner's Proton
account) to the account's own address, through the Bridge on morten (the office agent's PROTON_* keys, the same
ones the newsletters read with). Settings "digest": {on, hour, feed}; the
sync loop sends it once a day, at that hour in the home time zone, and only when something came in.
"""
import html
import json
import re
import smtplib
import ssl
import time
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from . import config, db, library, today as T
from .sources import newsletters


SENDER = "daf@tiresia.xyz"     # an address on the Proton account's own domain (since 2026-10-13)


def clean(d):
    d = d if isinstance(d, dict) else {}
    hour = d.get("hour")
    sender = d.get("from") if isinstance(d.get("from"), str) and re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", d.get("from"), re.I) else SENDER
    return {"on": d.get("on") is True, "hour": hour if isinstance(hour, int) and 3 <= hour <= 12 else 7,
            "feed": d.get("feed") is not False, "from": sender}


def configured():
    return newsletters.configured()


def build(conn, settings, since=None):
    """What the email says: {new: [...], feed: {count, folders}, yesterday: {minutes, goal}}."""
    since = since or int(time.time()) - 86400
    new = []
    for r in conn.execute("SELECT id, kind, title, author, source, url, words, duration, summary, ai_summary FROM docs "
                          "WHERE where_ = 'library' AND status IN ('inbox', 'later') AND added >= ? ORDER BY added DESC LIMIT 40", (since,)):
        if library.is_private(f"{r['title']} {r['source'] or ''} {r['author'] or ''}", settings):
            continue
        mins = round(r["duration"] / 60) if r["duration"] else max(1, round((r["words"] or 0) / 238)) if r["words"] else None
        title, summary = r["title"] or r["url"] or "Untitled", r["ai_summary"] or r["summary"] or ""
        m = TWEET.match(title) if r["kind"] == "tweet" else None
        if m:                                  # X's "(2) Name on X: "the tweet" / X"
            title, summary = m.group(1) + " on X", summary or m.group(2)
        new.append({"id": r["id"], "kind": r["kind"], "title": title, "by": r["author"] or r["source"] or "",
                    "mins": mins, "summary": _short(summary)})
    feed = {"count": 0, "folders": []}
    if clean(settings.get("digest"))["feed"]:
        rows = conn.execute("SELECT COALESCE(NULLIF(category, ''), 'Other') AS f, COUNT(*) AS n FROM docs WHERE where_ = 'feed' "
                            "AND status = 'unseen' AND added >= ? GROUP BY f ORDER BY n DESC", (since,)).fetchall()
        feed = {"count": sum(r["n"] for r in rows), "folders": [{"name": r["f"], "count": r["n"]} for r in rows[:6]]}
    y = T.today(settings) - timedelta(days=1)
    s = T.day_summary(conn, y, settings)
    return {"new": new, "feed": feed, "yesterday": {"minutes": round(s["counted"]), "goal": round(s["goal"] or 0)}}


TWEET = re.compile(r'^(?:\(\d+\)\s*)?(.+?) on X:\s*["“]([\s\S]*)["”]\s*/\s*X$')


def _short(t, n=320):
    """A summary cut at a sentence, or else a word, near n characters."""
    t = " ".join((t or "").split())
    if len(t) <= n:
        return t
    cut = t[:n]
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    return cut[:end + 1] if end > n * 0.5 else cut.rsplit(" ", 1)[0] + "…"


def _plural(n, one, many=None):
    return f"{n} {one if n == 1 else (many or one + 's')}"


def render(d, settings):
    """(subject, html, text)."""
    base = config.public_url(settings).rstrip("/")
    n = len(d["new"])
    subject = ("Daf: " + _plural(n, "new thing") + " in your Library") if n else "Daf: nothing new in your Library"
    y = d["yesterday"]
    ytext = f"Yesterday you read {y['minutes']} of {y['goal']} minutes." if y["goal"] else f"Yesterday you read {y['minutes']} minutes."
    text = [ytext, ""]
    rows = []
    for x in d["new"]:
        link = f"{base}/#read/{x['id']}"
        meta = " · ".join(p for p in (x["by"], f"{x['mins']} min" if x["mins"] else "") if p)
        text += [x["title"], meta, x["summary"], link, ""]
        rows.append(
            f'<tr><td style="padding:14px 0;border-top:1px solid #e6dfd2">'
            f'<a href="{html.escape(link)}" style="color:#2a2622;font:600 17px/1.35 Georgia,serif;text-decoration:none">{html.escape(x["title"])}</a>'
            + (f'<div style="color:#8a8073;font:13px/1.5 -apple-system,Segoe UI,sans-serif;margin-top:3px">{html.escape(meta)}</div>' if meta else "")
            + (f'<div style="color:#4a443d;font:15px/1.55 Georgia,serif;margin-top:6px">{html.escape(x["summary"])}</div>' if x["summary"] else "")
            + "</td></tr>")
    f = d["feed"]
    if f["count"]:
        folders = ", ".join(f"{x['name']} {x['count']}" for x in f["folders"])
        text += [f"The Feed has {_plural(f['count'], 'new post')}: {folders}.", f"{base}/#feed"]
    body = (
        '<div style="background:#f6f1e7;padding:24px 12px"><table role="presentation" width="100%" style="max-width:560px;margin:0 auto;'
        'background:#fffdf8;border-radius:12px;padding:8px 24px 20px"><tr><td style="padding:16px 0 4px">'
        '<div style="color:#8a8073;font:600 12px/1 -apple-system,Segoe UI,sans-serif;letter-spacing:.06em;text-transform:uppercase">Daf · this morning</div>'
        f'<div style="color:#2a2622;font:22px/1.3 Georgia,serif;margin-top:8px">{html.escape(subject[5:6].upper() + subject[6:])}</div>'
        f'<div style="color:#4a443d;font:14px/1.5 -apple-system,Segoe UI,sans-serif;margin-top:6px">{html.escape(ytext)}</div></td></tr>'
        + "".join(rows)
        + (f'<tr><td style="padding:14px 0;border-top:1px solid #e6dfd2;color:#4a443d;font:14px/1.5 -apple-system,Segoe UI,sans-serif">'
           f'The Feed has {_plural(f["count"], "new post")}: {html.escape(", ".join(x["name"] + " " + str(x["count"]) for x in f["folders"]))}. '
           f'<a href="{html.escape(base)}/#feed" style="color:#1a7da4">Open the Feed</a></td></tr>' if f["count"] else "")
        + f'<tr><td style="padding:16px 0 0;color:#a39a8c;font:12px/1.5 -apple-system,Segoe UI,sans-serif">Turn this off or change the hour in '
          f'<a href="{html.escape(base)}/#prefs/digest" style="color:#a39a8c">Preferences → Morning email</a>.</td></tr></table></div>')
    return subject, body, "\n".join(text).strip() + "\n"


def send_mail(subject, body_html, body_text):
    """From daf@tiresia.xyz (settings digest.from), an address on the Proton account, to the account's own
    address, through the Bridge. Proton sends only from the account's own addresses: one that isn't
    makes the Bridge refuse the message, and the error says so."""
    c = newsletters._creds()
    if not (c.get("PROTON_USER") and c.get("PROTON_BRIDGE_PASSWORD")):
        raise RuntimeError("Proton Mail Bridge isn't set up on morten")
    sender = clean(config.load_settings().get("digest"))["from"]
    m = EmailMessage()
    m["From"] = f"Daf <{sender}>"
    m["To"] = c["PROTON_USER"]
    m["Subject"] = subject
    m["Date"] = formatdate(localtime=True)
    m["Message-ID"] = make_msgid(domain="daf.tiresia.xyz")
    m.set_content(body_text)
    m.add_alternative(body_html, subtype="html")
    with smtplib.SMTP(c.get("PROTON_SMTP_HOST", c.get("PROTON_IMAP_HOST", "127.0.0.1")), int(c.get("PROTON_SMTP_PORT", "1025")), timeout=60) as s:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            s.starttls(context=ctx)
        except smtplib.SMTPNotSupportedError:
            pass
        s.login(c["PROTON_USER"], c["PROTON_BRIDGE_PASSWORD"])
        s.send_message(m)


def send(conn, settings, force=False):
    """Builds and sends it. Without force, a day with nothing new sends nothing. Returns what it did."""
    d = build(conn, settings)
    if not force and not d["new"]:
        return {"sent": False, "new": 0, "why": "nothing new"}
    subject, body, text = render(d, settings)
    send_mail(subject, body, text)
    return {"sent": True, "new": len(d["new"]), "subject": subject}


def maybe_send():
    """From the sync loop: once a day, at the hour, in the home time zone."""
    s = config.load_settings()
    dg = clean(s.get("digest"))
    if not dg["on"]:
        return None
    now = datetime.now(T.tz_of(s))
    if now.hour < dg["hour"]:
        return None
    day = now.date().isoformat()
    with db.session() as c:
        last = c.execute("SELECT v FROM kv WHERE k = 'digest_last'").fetchone()
        if last and json.loads(last[0]).get("day") == day:
            return None
        d = build(c, s)
    out = {"day": day, "at": int(time.time()), "new": len(d["new"])}
    if d["new"]:
        subject, body, text = render(d, s)
        try:
            send_mail(subject, body, text)
            out["sent"] = True
        except Exception as e:  # noqa: BLE001 - try again next sync, but not forever
            out["error"] = str(e)[:300]
            with db.session() as c:
                tries = c.execute("SELECT v FROM kv WHERE k = 'digest_tries'").fetchone()
                n = (json.loads(tries[0]).get(day, 0) if tries else 0) + 1
                c.execute("INSERT OR REPLACE INTO kv (k, v) VALUES ('digest_tries', ?)", (json.dumps({day: n}),))
            if n < 3:
                return out
            # The third failure today: said on Signal, so a broken Bridge doesn't go unnoticed.
            import subprocess
            from .cli import NOTIFY
            subprocess.run([NOTIFY, "Daf", f"This morning's email didn't go after three tries: {out['error'][:200]}"], timeout=60, check=False)
    with db.session() as c:
        c.execute("INSERT OR REPLACE INTO kv (k, v) VALUES ('digest_last', ?)", (json.dumps(out),))
    return out


def status(conn):
    last = conn.execute("SELECT v FROM kv WHERE k = 'digest_last'").fetchone()
    return json.loads(last[0]) if last else None
