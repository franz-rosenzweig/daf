"""Tags for what's saved to the Library, from the model (Preferences → AI → Tags for what you save):
Karakeep's AI tagging, but leaning on the tags already in use, so the list stays short. A save that
already has tags (given by hand, or brought from Karakeep or another app) keeps them; a private one
is never sent to the model.

Also the tag list's upkeep (Preferences → Tags): rename, merge and remove a document tag everywhere,
and the tidy-up: the model proposes merges for the whole list, you tick the ones you want.
"""
import json
import re
import time

from . import ai, config, library, reader

MAX_TEXT = 6000


def _clean(t):
    return " ".join(str(t).split()).strip().lstrip("#")[:40]


def _json_list(out):
    """The answer's list of strings, wherever it is in the answer (a code fence, a sentence before it)."""
    for m in [re.search(r"\[[\s\S]*\]", out or "")] + list(re.finditer(r"\[[^\[\]]*\]", out or "")):
        if not m:
            continue
        try:
            v = json.loads(m.group(0))
        except ValueError:
            continue
        if isinstance(v, list) and any(isinstance(x, str) for x in v):
            return [x for x in v if isinstance(x, str)]
    return []


def tag_doc(conn, doc_id):
    """The "tags" job: two to four tags for a new save without any."""
    s = config.load_settings()
    if not ai.settings(s).get("auto_tags", True):
        return
    d = conn.execute("SELECT * FROM docs WHERE id = ?", (doc_id,)).fetchone()
    if not d or d["where_"] != "library" or d["status"] == "deleted" or (d["tags"] and json.loads(d["tags"])):
        return
    if library.is_private(f"{d['title'] or ''} {d['source'] or ''} {d['author'] or ''}", s):
        return
    row = conn.execute("SELECT blocks FROM doc_content WHERE id = ?", (doc_id,)).fetchone()
    text = ""
    if row and row[0]:
        text = " ".join(b.get("x", "") for b in json.loads(row[0]) if b.get("t") != "img")[:MAX_TEXT]
    text = text or (d["ai_summary"] or d["summary"] or "")
    if len(text) < 80 and not d["title"]:
        return                                     # nothing to go on
    mine = reader.all_doc_tags(conn)[:250]
    conn.commit()                                  # the model takes a while: hold no lock meanwhile
    ask = (ai.prompt("tags", s) + "\n\nHis tags, the most used first: " + (", ".join(mine) if mine else "(none yet)") +
           "\n\nAnswer with JSON only: a list of 2 to 4 strings.\n\nTitle: " + (d["title"] or "") +
           "\nSite: " + (d["source"] or "") + "\n\n" + text)
    tags = pick(_json_list(ai.run(ask, timeout=150, s=s)), mine)
    if not tags:
        return
    # given meanwhile by hand: those win
    if not conn.execute("SELECT 1 FROM docs WHERE id = ? AND (tags IS NULL OR tags = '[]')", (doc_id,)).fetchone():
        return
    conn.execute("UPDATE docs SET tags = ? WHERE id = ?", (json.dumps(tags), doc_id))


def pick(proposed, mine, n=4):
    """The model's tags, spelled the way your own are when they're the same word, at most n."""
    have = {t.lower(): t for t in mine}
    out = []
    for t in proposed:
        t = _clean(t)
        if not t:
            continue
        t = have.get(t.lower(), t)
        if t.lower() not in {x.lower() for x in out}:
            out.append(t)
    return out[:n]


# ---- the tag list ------------------------------------------------------------------------------------

def counts(conn):
    """{tag: how many documents}, the most used first."""
    n = {}
    for (tags,) in conn.execute("SELECT tags FROM docs WHERE tags IS NOT NULL AND tags != '[]' AND status != 'deleted'"):
        for t in json.loads(tags):
            n[t] = n.get(t, 0) + 1
    return dict(sorted(n.items(), key=lambda x: (-x[1], x[0].lower())))


def rename(conn, old, new):
    """Every document tagged old is tagged new instead (a merge, when new is in use already); new
    empty removes old. Returns how many documents changed."""
    new = _clean(new) if new else ""
    n = 0
    for r in conn.execute("SELECT id, tags FROM docs WHERE tags IS NOT NULL AND instr(tags, ?) > 0", (json.dumps(old)[1:-1],)).fetchall():
        tags = json.loads(r["tags"])
        if old not in tags:
            continue
        out = []
        for t in tags:
            t = new if t == old else t
            if t and t.lower() not in {x.lower() for x in out}:
                out.append(t)
        conn.execute("UPDATE docs SET tags = ? WHERE id = ?", (json.dumps(out) if out else None, r["id"]))
        n += 1
    return n


def propose(conn):
    """The tidy-up: the model looks at the whole list and proposes merges (near-duplicates, a
    plural and its singular, one subject under three names) and tags to drop (used once, saying
    nothing). Kept in kv until you apply or throw it away."""
    s = config.load_settings()
    c = counts(conn)
    if len(c) < 8:
        return {"at": int(time.time()), "changes": []}
    conn.commit()
    lst = "\n".join(f"{t} ({k})" for t, k in c.items())
    ask = ("Here are the tags on the documents in a personal reading library, with how many documents each has. "
           "There are too many, many used once. Propose a tidy-up into a few dozen clear tags: merge near-duplicates and "
           "tags for the same subject into one (keep the better-used or clearer name, or a short new one), and drop tags "
           "that say nothing useful. Keep tags that are specific and used. Answer with JSON only: a list of objects "
           '{"from": [tags], "to": "tag", "why": "a few words"}; "to" is "" for a drop.\n\n' + lst)
    out = ai.run(ask, timeout=400, s=s)
    m = re.search(r"\[[\s\S]*\]", out or "")
    changes = []
    if m:
        try:
            raw = json.loads(m.group(0))
        except ValueError:
            raw = []
        for i, x in enumerate(raw if isinstance(raw, list) else []):
            if not isinstance(x, dict):
                continue
            frm = [t for t in (x.get("from") or []) if isinstance(t, str) and t in c]
            to = _clean(x.get("to") or "")
            if not frm or (len(frm) == 1 and frm[0] == to):
                continue
            changes.append({"id": i, "from": frm, "to": to, "why": str(x.get("why") or "")[:120],
                            "docs": sum(c[t] for t in frm)})
    p = {"at": int(time.time()), "changes": changes}
    conn.execute("INSERT OR REPLACE INTO kv (k, v) VALUES ('tag_tidy', ?)", (json.dumps(p),))
    return p


def proposal(conn):
    r = conn.execute("SELECT v FROM kv WHERE k = 'tag_tidy'").fetchone()
    return json.loads(r[0]) if r else None


def apply(conn, ids):
    """The changes you ticked. Returns how many documents changed."""
    p = proposal(conn) or {"changes": []}
    n = 0
    for x in p["changes"]:
        if x["id"] in ids:
            for t in x["from"]:
                if t != x["to"]:
                    n += rename(conn, t, x["to"])
    p["changes"] = [x for x in p["changes"] if x["id"] not in ids]
    p["applied"] = int(time.time())
    conn.execute("INSERT OR REPLACE INTO kv (k, v) VALUES ('tag_tidy', ?)", (json.dumps(p),))
    return n
