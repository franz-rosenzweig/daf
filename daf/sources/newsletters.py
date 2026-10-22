"""Email newsletters, from the owner's Proton mailbox through Proton Mail Bridge (IMAP on 127.0.0.1).

Read-only: messages are fetched with BODY.PEEK, so nothing is marked read and nothing moves.
Daf finds the senders that send as newsletters (a List-Unsubscribe or List-Id header) and
lists them in Preferences; issues from the ones you tick become Library documents of
kind "email" (Readwise's Emails), with ids "nl:<hash of the Message-ID>". Their reading
state lives in Daf only.

Credentials are the office agent's, read from /srv/office/.env (PROTON_* keys only).
"""
import email
import hashlib
import html as _html
import imaplib
import json
import re
import ssl
import time
from datetime import datetime, timedelta
from email import policy
from email.utils import parseaddr, parsedate_to_datetime

from .. import content

ENV = "/srv/office/.env"
FOLDER = '"All Mail"'


class MailError(Exception):
    pass


def _creds():
    out = {}
    try:
        for line in open(ENV, encoding="utf-8"):
            m = re.match(r"^\s*(PROTON_[A-Z_]+)\s*=\s*(.*?)\s*$", line)
            if m:
                out[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def configured():
    c = _creds()
    return bool(c.get("PROTON_USER") and c.get("PROTON_BRIDGE_PASSWORD"))


def _connect():
    c = _creds()
    if not (c.get("PROTON_USER") and c.get("PROTON_BRIDGE_PASSWORD")):
        raise MailError("Proton Mail Bridge isn't set up (PROTON_USER and PROTON_BRIDGE_PASSWORD in /srv/office/.env)")
    m = imaplib.IMAP4(c.get("PROTON_IMAP_HOST", "127.0.0.1"), int(c.get("PROTON_IMAP_PORT", "1143")), timeout=60)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        m.starttls(ssl_context=ctx)
    except Exception:  # noqa: BLE001 - a Bridge set to plain IMAP on localhost
        pass
    m.login(c["PROTON_USER"], c["PROTON_BRIDGE_PASSWORD"])
    typ, _ = m.select(FOLDER, readonly=True)
    if typ != "OK":
        m.select("INBOX", readonly=True)
    return m


def _since(days):
    return (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")


def _headers(m, uids):
    out = {}
    for i in range(0, len(uids), 200):
        chunk = b",".join(uids[i:i + 200])
        typ, data = m.uid("FETCH", chunk, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID LIST-UNSUBSCRIBE LIST-ID)])")
        if typ != "OK":
            continue
        # The UID can come before the literal or after it (Proton Bridge puts it after).
        for i, part in enumerate(data):
            if not isinstance(part, tuple):
                continue
            uid = re.search(rb"UID (\d+)", part[0])
            if not uid and i + 1 < len(data) and isinstance(data[i + 1], bytes):
                uid = re.search(rb"UID (\d+)", data[i + 1])
            if uid:
                out[uid.group(1)] = email.message_from_bytes(part[1], policy=policy.default)
    return out


def scan(conn, days=45):
    """Senders that sent newsletters in the last weeks: [{address, name, count, last_subject, last}]."""
    m = _connect()
    try:
        typ, data = m.uid("SEARCH", None, "SINCE", _since(days))
        uids = data[0].split() if typ == "OK" and data and data[0] else []
        hs = _headers(m, uids[-1500:])
    finally:
        try:
            m.logout()
        except Exception:  # noqa: BLE001
            pass
    senders = {}
    for h in hs.values():
        if not (h.get("List-Unsubscribe") or h.get("List-Id")):
            continue
        name, addr = parseaddr(str(h.get("From") or ""))
        addr = addr.lower()
        if not addr:
            continue
        try:
            when = int(parsedate_to_datetime(str(h.get("Date"))).timestamp())
        except Exception:  # noqa: BLE001
            when = 0
        s = senders.setdefault(addr, {"address": addr, "name": name or addr.split("@")[0], "count": 0, "last": 0, "last_subject": ""})
        s["count"] += 1
        if when >= s["last"]:
            s["last"], s["last_subject"] = when, str(h.get("Subject") or "")[:160]
    out = sorted(senders.values(), key=lambda s: (-s["count"], -s["last"]))
    conn.execute("INSERT INTO kv (k, v) VALUES ('nl_senders', ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v",
                 (json.dumps({"at": int(time.time()), "senders": out}),))
    return out


TRACKER = re.compile(r"(open|track|pixel|beacon|/o/|/e/o|imp\?|\.gif(\?|$))", re.I)
WEB = re.compile(r"view (it |this (email|post) )?(in|on) (your |the )?(browser|web)|view online|read online|open in browser|read on the web", re.I)


def _body(msg):
    html = text = None
    for part in msg.walk():
        ct = part.get_content_type()
        if part.get_content_disposition() == "attachment":
            continue
        if ct == "text/html" and html is None:
            html = part.get_content()
        elif ct == "text/plain" and text is None:
            text = part.get_content()
    return html, text


def _web_link(html):
    links = re.findall(r'<a\b[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>', html or "", re.I | re.S)
    for href, label in links:
        if WEB.search(re.sub(r"<[^>]+>", " ", label)):
            return href.replace("&amp;", "&")
    for href, _ in links:                      # Substack and others: the post's own page
        m = re.match(r"(https://[^\s\"?]+/p/[^\s\"?]+)", href.replace("&amp;", "&"))
        if m and "/subscribe" not in m.group(1):
            return m.group(1)
    return None


INVISIBLE = re.compile(r"[\u034f\u00ad\u200b-\u200f\u2060\ufeff\s]+")
CHROME = re.compile(r"^(forwarded this (email|message)\??.*|subscribe( here)?( for more)?|read in (the )?app|view (it |this (email|post) )?(in|on) (your |the )?(browser|web)|"
                    r"view online|like|comment|restack|share|reply|upgrade to paid|listen now|open in app|get the app|start writing)\.?$", re.I)
ICON = re.compile(r"[/,_]w_(\d{1,2}|1[0-4]\d)\b|icon|logo|avatar|emoji|spacer|badge", re.I)


def _clean(bl, title):
    """Newsletter chrome out: the preheader and its invisible padding, app buttons, tiny icons,
    the title again, and the footer."""
    out, t = [], re.sub(r"\W+", " ", (title or "").lower()).strip()
    for b in bl:
        if b["t"] == "img":
            if TRACKER.search(b.get("src") or "") or ICON.search(b.get("src") or ""):
                continue
            out.append(b)
            continue
        x = INVISIBLE.sub(" ", b["x"]).strip()
        if len(x) < 2 or CHROME.match(x):
            continue
        if b["t"] in ("h1", "h2") and re.sub(r"\W+", " ", x.lower()).strip() == t:
            continue
        if not out and t and re.sub(r"\W+", " ", x.lower()).strip().startswith(t) and len(x) < 400:
            continue                                   # the preheader: "Title" + "subtitle" run together
        b = dict(b, x=x)
        out.append(b)
    cut = next((i for i, b in enumerate(out) if b["t"] != "img" and i > len(out) * 0.5 and
                re.search(r"\bunsubscribe\b|you('| a)re (receiving|getting) this|update your preferences|manage (your )?subscription|^©|\bAll rights reserved\b", b["x"], re.I)), None)
    return out[:cut] if cut is not None else out


def _blocks(html, text, title=None):
    if html:
        bl = _clean(content.blocks(html), title)
        if bl:
            return bl
    paras = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    return [{"t": "p", "h": _html.escape(p), "x": p} for p in paras]


LIKELY = re.compile(r"substack\.com|patreon\.com|beehiiv|buttondown|ghost\.io|convertkit|kit\.com|mailerlite|googlegroups\.com|"
                    r"tinyletter|revue|every\.to|stratechery|theatlantic|nytimes|newsletter|digest|weekly|daily", re.I)
SHOPS = re.compile(r"etsy|staples|paypal|lyft|airbnb|amazon|pinterest|linkedin|reddit|github|ancestry|uber|doordash|walmart|target|"
                   r"meetup|freetaxusa|netdata|bank|visa|mastercard|apple\.com|google\.com", re.I)


def ranked(conn, settings, senders):
    """Likely newsletters first; shops and services after; private ones never."""
    from .. import library
    out = []
    for s in senders:
        if library.is_private(f"{s['name']} {s['address']} {s['last_subject']}", settings):
            continue
        hay = f"{s['address']} {s['name']}"
        s["likely"] = bool(LIKELY.search(hay)) and not SHOPS.search(hay)
        out.append(s)
    return out


def sync(conn, settings, days=30):
    """New issues from the senders you chose, as Library documents of kind email. Returns how many."""
    chosen = [a.lower() for a in (settings.get("newsletters") or []) if isinstance(a, str)]
    if not chosen:
        return 0
    known = {r[0] for r in conn.execute("SELECT ext_id FROM docs WHERE id LIKE 'nl:%'")}
    m = _connect()
    n = 0
    try:
        for addr in chosen:
            typ, data = m.uid("SEARCH", None, "SINCE", _since(days), "FROM", f'"{addr}"')
            uids = data[0].split() if typ == "OK" and data and data[0] else []
            if not uids:
                continue
            hs = _headers(m, uids[-40:])
            for uid, h in hs.items():
                mid = str(h.get("Message-ID") or "").strip() or f"{addr}:{uid.decode()}"
                if mid in known:
                    continue
                typ, raw = m.uid("FETCH", uid, "(BODY.PEEK[])")
                if typ != "OK" or not raw or not isinstance(raw[0], tuple):
                    continue
                msg = email.message_from_bytes(raw[0][1], policy=policy.default)
                html, text = _body(msg)
                bl = _blocks(html, text, str(msg.get("Subject") or ""))
                if not bl:
                    continue
                name, frm = parseaddr(str(msg.get("From") or ""))
                try:
                    when = int(parsedate_to_datetime(str(msg.get("Date"))).timestamp())
                except Exception:  # noqa: BLE001
                    when = int(time.time())
                did = "nl:" + hashlib.sha1(mid.encode()).hexdigest()[:20]
                title = str(msg.get("Subject") or "Newsletter").strip()[:300]
                conn.execute(
                    "INSERT INTO docs (id, kind, where_, status, title, author, source, category, url, published, added, words, summary, ext_id, thumb) "
                    "VALUES (?, 'email', 'library', 'inbox', ?, ?, ?, '', ?, ?, ?, ?, ?, ?, NULL) ON CONFLICT(id) DO NOTHING",
                    (did, title, name or frm, name or frm.split("@")[-1], _web_link(html), when, when, content.words(bl), content.summary(bl), mid))
                conn.execute("INSERT OR REPLACE INTO doc_content (id, blocks, fetched) VALUES (?, ?, ?)", (did, json.dumps(bl), int(time.time())))
                known.add(mid)
                n += 1
    finally:
        try:
            m.logout()
        except Exception:  # noqa: BLE001
            pass
    return n
