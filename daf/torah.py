"""The Torah shelf: this week's parasha and haftarah from Sefaria, as readable docs.

Each reading is a doc (where_ 'torah', kind 'torah') whose blocks are verses: Hebrew
(nikud kept, cantillation dropped) beside English, with aliyah headings. Highlights and
notes work as on any doc and go to Reference/torah in the vault. Time spent reading here
counts like an article. The Ruach feed folder in FreshRSS supplies the week's divrei Torah.
"""
import hashlib
import html
import json
import logging
import re
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

from . import config, content, today as T

log = logging.getLogger(__name__)
API = "https://www.sefaria.org/api"
ALIYOT = ["Rishon", "Sheni", "Shlishi", "Revi'i", "Chamishi", "Shishi", "Shvi'i", "Maftir"]
CANTILLATION = re.compile("[֑-ֽ֯׀׃׆]")


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Daf/1.0 (personal reader)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def clean_he(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    s = re.sub(r"\{[פס]\}", "", s)
    s = html.unescape(s)
    s = CANTILLATION.sub("", s)
    s = s.replace("־", "-")          # maqaf as a plain hyphen, so words wrap and select
    return re.sub(r"\s+", " ", s).strip()


def clean_en(s):
    s = re.sub(r'<sup class="footnote-marker">.*?</sup>', "", s or "", flags=re.S)
    s = re.sub(r'<i class="footnote">.*?</i>', "", s, flags=re.S)
    s = re.sub(r"<br\s*/?>", " ", s)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def calendar(conn, day=None):
    """Sefaria's calendar for a day (diaspora), cached for the day."""
    s = config.load_settings()
    day = day or T.today(s)
    key = f"torah:cal:{day.isoformat()}"
    row = conn.execute("SELECT v FROM kv WHERE k = ?", (key,)).fetchone()
    if row:
        return json.loads(row[0])
    q = urllib.parse.urlencode({"diaspora": 1, "timezone": s.get("home_tz", "America/Phoenix"),
                                "year": day.year, "month": day.month, "day": day.day})
    d = _get(f"{API}/calendars?{q}")
    items = {}
    for it in d.get("calendar_items", []):
        name = (it.get("title") or {}).get("en")
        if name in ("Parashat Hashavua", "Haftarah") and name not in items:
            items[name] = {"name": (it.get("displayValue") or {}).get("en"), "he": (it.get("displayValue") or {}).get("he"),
                           "ref": it.get("ref"), "aliyot": (it.get("extraDetails") or {}).get("aliyot") or []}
    conn.execute("INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)", (key, json.dumps(items)))
    return items


def hebrew_date(conn, day=None):
    """The Hebrew date, like "9 Cheshvan" (Hebcal's converter), cached for the day. None when Hebcal
    can't be reached and nothing is cached. Note: after sunset it's still the civil day's date."""
    s = config.load_settings()
    day = day or T.today(s)
    key = f"torah:hdate:{day.isoformat()}"
    row = conn.execute("SELECT v FROM kv WHERE k = ?", (key,)).fetchone()
    if row:
        return json.loads(row[0])
    try:
        d = _get("https://www.hebcal.com/converter?" + urllib.parse.urlencode(
            {"cfg": "json", "gy": day.year, "gm": day.month, "gd": day.day, "g2h": 1}), timeout=10)
    except Exception:  # noqa: BLE001 - the date is a nicety
        return None
    out = {"day": d.get("hd"), "month": d.get("hm"), "year": d.get("hy"), "he": d.get("hebrew")}
    if not out["day"] or not out["month"]:
        return None
    out["text"] = f"{out['day']} {out['month']}"
    conn.execute("INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)", (key, json.dumps(out)))
    return out


def _verse_starts(ref):
    """'Genesis 1:1-2:3' -> ('Genesis', (1, 1)); 'I Samuel 20:18-42' -> ('I Samuel', (20, 18))."""
    m = re.match(r"^(.*?)\s+(\d+):(\d+)", ref or "")
    return (m.group(1), (int(m.group(2)), int(m.group(3)))) if m else (None, None)


def build_blocks(ref, aliyot=()):
    q = urllib.parse.quote(ref)
    d = _get(f"{API}/v3/texts/{q}?version=hebrew&version=english&return_format=default")
    vers = {v.get("language"): v.get("text") for v in d.get("versions", [])}
    he, en = vers.get("he") or [], vers.get("en") or []
    if he and isinstance(he[0], str):       # a single chapter comes back flat
        he, en = [he], [en]
    c0, v0 = int(d["sections"][0]), int(d["sections"][1]) if len(d["sections"]) > 1 else 1
    heads = {}
    for i, a in enumerate(aliyot or []):
        _b, start = _verse_starts(a)
        if start and start not in heads:
            heads[start] = ALIYOT[i] if i < len(ALIYOT) else f"Aliyah {i + 1}"
        elif start and i == len(aliyot) - 1:
            heads[start] = heads[start] + " · Maftir"
    blocks, words = [], 0
    for ci, chap in enumerate(he):
        cnum = c0 + ci
        for vi, hv in enumerate(chap):
            vnum = (v0 if ci == 0 else 1) + vi
            if (cnum, vnum) in heads:
                blocks.append({"t": "h3", "h": html.escape(heads[(cnum, vnum)]), "x": heads[(cnum, vnum)]})
            ev = en[ci][vi] if ci < len(en) and vi < len(en[ci]) else ""
            h_txt, e_txt = clean_he(hv), clean_en(ev)
            if not h_txt and not e_txt:
                continue
            words += len(e_txt.split())
            blocks.append({"t": "verse", "n": f"{cnum}:{vnum}", "he": h_txt, "x": e_txt,
                           "h": html.escape(e_txt)})
    return blocks, words, d.get("heRef")


def _shabbat(day):
    return day + timedelta(days=(5 - day.weekday()) % 7)


def ensure_week(conn, day=None):
    """Make this week's parasha and haftarah docs if they don't exist. Returns their ids."""
    s = config.load_settings()
    day = day or T.today(s)
    cal = calendar(conn, day)
    sat = _shabbat(day)
    out = []
    for key, author in (("Parashat Hashavua", "Torah"), ("Haftarah", "Haftarah")):
        it = cal.get(key)
        if not it or not it.get("ref"):
            continue
        did = "sef:" + it["ref"].replace(" ", "_")
        out.append(did)
        if conn.execute("SELECT 1 FROM doc_content WHERE id = ?", (did,)).fetchone():
            continue
        try:
            blocks, words, he_ref = build_blocks(it["ref"], it.get("aliyot") if key == "Parashat Hashavua" else ())
        except Exception as e:  # noqa: BLE001 - Sefaria down: try on the next sync
            log.warning("sefaria %s: %s", it["ref"], e)
            continue
        title = f"Parashat {it['name']}" if key == "Parashat Hashavua" else f"Haftarah for {cal.get('Parashat Hashavua', {}).get('name') or it['name']}"
        summary = f"{it['ref']} · Shabbat {sat.strftime('%B')} {sat.day}" + (f" · {it['he']}" if it.get("he") else "")
        published = int(datetime(sat.year, sat.month, sat.day, 9).timestamp())
        conn.execute("INSERT OR REPLACE INTO docs (id, kind, where_, status, title, author, source, category, url, published, added, words, summary) "
                     "VALUES (?, 'torah', 'torah', 'inbox', ?, ?, 'Sefaria', ?, ?, ?, ?, ?, ?)",
                     (did, title, author, sat.isoformat(), "https://www.sefaria.org/" + urllib.parse.quote(it["ref"].replace(" ", "_")),
                      published, int(time.time()), words, summary))
        conn.execute("INSERT OR REPLACE INTO doc_content (id, blocks, fetched) VALUES (?, ?, ?)",
                     (did, json.dumps(blocks, ensure_ascii=False), int(time.time())))
    return out


NIKUD = re.compile("[\u0591-\u05C7]")


def _skeleton(s):
    """Transliterations vary (Bereshit, Bereishis, Breishit); their consonants mostly don't."""
    s = re.sub(r"[^a-z]", "", (s or "").lower())
    return re.sub(r"[aeiou]", "", s.replace("sh", "s").replace("ch", "h").replace("kh", "h"))


def mentions(title, name, he):
    t = title or ""
    if he and NIKUD.sub("", he) and NIKUD.sub("", he) in NIKUD.sub("", t):
        return True
    words = [_skeleton(w) for w in re.split(r"[\s\-:,.!?'’]+", t) if w]
    parts = [_skeleton(w) for w in re.split(r"[\s\-]+", name or "") if w]
    if not parts or not parts[0]:
        return False
    k = parts[0][:3]
    for i, w in enumerate(words):
        if (w.startswith(k) if len(k) >= 2 else w == k) and (len(parts) == 1 or (i + 1 < len(words) and words[i + 1].startswith(parts[1][:2]))):
            return True
    return False


def _front(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    out = {}
    for line in (m.group(1).splitlines() if m else []):
        k, _, v = line.partition(":")
        if v.strip():
            out[k.strip()] = v.strip().strip('"')
    return out


def essays(conn, name):
    """Vault notes filed under this parasha (Reference/torah/<parasha>/), e.g. Covenant & Conversation."""
    root = config.VAULT / "Reference" / "torah"
    if not name or not root.is_dir():
        return []
    out = []
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or not mentions(folder.name.replace("-", " "), name, None):
            continue
        for p in sorted(folder.glob("*.md")):
            try:
                fm = _front(p.read_text(encoding="utf-8")[:3000])
            except OSError:
                continue
            rel = str(p.relative_to(config.VAULT))
            did = "ve:" + hashlib.sha1(rel.encode()).hexdigest()[:16]
            title = (fm.get("title") or p.stem.replace("-", " ").capitalize()).split(" | ")[0]
            hl = conn.execute("SELECT COUNT(*) FROM highlights WHERE book_id = ? AND deleted = 0", (did,)).fetchone()[0]
            d = conn.execute("SELECT progress FROM docs WHERE id = ?", (did,)).fetchone()
            out.append({"path": rel, "title": title, "author": fm.get("author"), "words": int(fm["word_count"]) if str(fm.get("word_count", "")).isdigit() else None,
                        "series": (fm.get("title") or "").split(" | ")[-1] if " | " in (fm.get("title") or "") else folder.name, "id": did,
                        "highlights": hl, "progress": d["progress"] if d else None})
    return out


def open_essay(conn, rel):
    """Make a vault note readable in Daf (reading time counts; highlights go back into the same note)."""
    p = (config.VAULT / rel).resolve()
    root = (config.VAULT / "Reference" / "torah").resolve()
    if root not in p.parents or p.suffix != ".md" or not p.exists():
        raise ValueError("not a Torah note in the vault")
    text = p.read_text(encoding="utf-8")
    fm = _front(text)
    blocks = content.md_blocks(text)
    did = "ve:" + hashlib.sha1(rel.encode()).hexdigest()[:16]
    title = (fm.get("title") or p.stem).split(" | ")[0]
    conn.execute("INSERT INTO docs (id, kind, where_, status, title, author, source, category, url, published, added, words, summary) "
                 "VALUES (?, 'article', 'torah', 'inbox', ?, ?, ?, NULL, ?, NULL, ?, ?, ?) "
                 "ON CONFLICT(id) DO UPDATE SET title = excluded.title, source = excluded.source, category = NULL, "
                 "words = excluded.words, summary = excluded.summary",
                 (did, title, fm.get("author"), ((fm.get("title") or "").split(" | ")[-1] if " | " in (fm.get("title") or "") else "Your vault"),
                  fm.get("source"), int(time.time()),
                  content.words(blocks), content.summary(blocks)))
    conn.execute("INSERT OR REPLACE INTO doc_content (id, blocks, fetched) VALUES (?, ?, ?)", (did, json.dumps(blocks, ensure_ascii=False), int(time.time())))
    conn.execute("INSERT INTO books (id, kind, title, author, url, vault_path, private) VALUES (?, 'article', ?, ?, ?, ?, 0) "
                 "ON CONFLICT(id) DO UPDATE SET vault_path = excluded.vault_path, title = excluded.title",
                 (did, title, fm.get("author"), fm.get("source"), rel))
    return did


def shelf(conn):
    """What the Torah page shows: this week's readings, the week's divrei Torah, earlier weeks."""
    s = config.load_settings()
    day = T.today(s)
    try:
        ids = ensure_week(conn, day)
        cal = calendar(conn, day)
    except Exception as e:  # noqa: BLE001
        log.warning("torah shelf: %s", e)
        ids, cal = [], {}
    def card(r):
        hl = conn.execute("SELECT COUNT(*) FROM highlights WHERE book_id = ? AND deleted = 0", (r["id"],)).fetchone()[0]
        return {"id": r["id"], "title": r["title"], "author": r["author"], "summary": r["summary"], "words": r["words"],
                "progress": r["progress"], "highlights": hl, "category": r["category"]}
    week = [card(r) for i in ids for r in conn.execute("SELECT * FROM docs WHERE id = ?", (i,))]
    par = cal.get("Parashat Hashavua") or {}
    since = int(time.time()) - 10 * 86400
    ruach = [dict(r) for r in conn.execute(
        "SELECT id, title, author, source, added, status, words FROM docs WHERE where_ = 'feed' AND category = 'Ruach' AND status != 'deleted' AND added > ? "
        "ORDER BY added DESC LIMIT 40", (since,))]
    for r in ruach:
        r["this_parasha"] = bool(par) and mentions(r["title"], par.get("name"), par.get("he"))
    ruach.sort(key=lambda r: (not r["this_parasha"], -(r["added"] or 0)))
    earlier = [card(r) for r in conn.execute(
        "SELECT * FROM docs WHERE where_ = 'torah' AND id LIKE 'sef:%%' AND id NOT IN (%s) ORDER BY published DESC LIMIT 30" % ",".join("?" * len(ids)), ids)] if ids else \
        [card(r) for r in conn.execute("SELECT * FROM docs WHERE where_ = 'torah' AND id LIKE 'sef:%' ORDER BY published DESC LIMIT 30")]
    try:
        mine = essays(conn, par.get("name"))
    except Exception as e:  # noqa: BLE001
        log.warning("torah essays: %s", e)
        mine = []
    return {"parasha": cal.get("Parashat Hashavua"), "haftarah": cal.get("Haftarah"), "week": week, "essays": mine,
            "ruach": ruach[:12], "earlier": earlier}
