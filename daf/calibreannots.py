"""Daf's own highlights in Calibre's viewer: the highlights made in Daf's book reader go into
Calibre's annotations for the book, the way Calibre's viewer saves its own (merge_annotations_for_book,
as the "local viewer" user, through calibrewrite's lock and calibre-debug), so Calibre on the Mac
shows them in the book, in its Highlights panel and in Browse annotations.

Which ones: highlights made in Daf's reader (source "epub"), in a book whose EPUB is the file Daf's
reader opens, so their places are places in the very file Calibre's viewer opens. The Kindle's
aren't sent: KOReader keeps its places in its own terms (xpointers in the Kindle's copy, often
another file), and Daf has a CFI for one only for as long as the reader has it open. Readwise,
paper and audiobook highlights have no place in the file at all.

Each one is a Calibre annotation of Calibre's own shape: a uuid made from its Daf id
(calibrehl.daf_uuid), Calibre's start_cfi and end_cfi (its own way of counting offsets, the reverse
of calibrehl.place, and checked by turning it back with place: the same words in the same spot, or
it isn't sent), the highlighted words, Daf's note, the colour as one of Calibre's, the chapter, and
when. Only what changed since the last sync is sent (calibre_pushed keeps what was sent); a
highlight removed in Daf is marked removed in Calibre, the way Calibre's viewer removes one.
calibrehl skips these uuids when it reads Calibre's highlights, so nothing comes back as a copy.

And back (pull, before each push): a note, a colour, new ends or a removal made in Calibre's viewer
to one of these comes into the Daf highlight it came from; when both sides changed it since the last
sync, the newer one wins. calibre_pushed keeps both sides as they were left (hash: Daf's, seen:
Calibre's), so a change taken from Calibre isn't sent back and nothing goes back and forth.
"""
import hashlib
import json
import logging
import re
import time
from collections import Counter
from datetime import datetime, timezone

from . import ebooks
from .sources import calibrehl as H

log = logging.getLogger("daf.calibreannots")
STYLE = {"yellow": "yellow", "green": "green", "blue": "blue", "pink": "red", "purple": "purple"}     # Daf's → Calibre's


def _iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_cfi(cfi):
    """The reader's CFI ("epubcfi(/6/24!/4/14,/1:95,/1:160)", or one point) → (the spine's steps,
    the start's steps, the end's steps), the last two from the root element's children."""
    m = re.fullmatch(r"epubcfi\((.*)\)", str(cfi or "").strip())
    if not m or m.group(1).count("!") != 1:
        return None
    base, local = m.group(1).split("!")
    parts = local.split(",")
    if len(parts) == 3:
        start, end = parts[0] + parts[1], parts[0] + parts[2]
    elif len(parts) == 1:
        start = end = parts[0]
    else:
        return None
    b, s, e = H._steps(base), H._steps(start), H._steps(end)
    return (b, s, e) if b and s and e else None


def _kids(el):
    return [c for c in el if isinstance(c.tag, str)]


def _spec_at(root, at, steps):
    """Where a spec path (foliate-js's) lands in the chapter's flat text, or None."""
    el = root
    for n, _i, _o in steps[:-1]:
        kids = _kids(el)
        if n % 2 or not 0 < n // 2 <= len(kids):
            return None
        el = kids[n // 2 - 1]
    n, _i, off = steps[-1]
    if n % 2:
        size = dict(H._chunks(el)).get(n)
        return at[(el, n)] + (off or 0) if size is not None and (off or 0) <= size else None
    kids = _kids(el)
    return at[(kids[n // 2 - 1], 1)] if 0 < n // 2 <= len(kids) else None      # an element: the start of what's in it


def _spans(root, at):
    """Every chunk of text in the chapter, in order: (start, length, element, offset of the chunk
    in the element's own text)."""
    out = []
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        cum = 0
        for k, size in H._chunks(el):
            out.append((at[(el, k)], size, el, cum))
            cum += size
    out.sort(key=lambda s: s[0])
    return out


def _encode(root, ids, el, off):
    """Calibre's CFI for an offset across an element's own text, as its viewer writes one: the path
    from the document ("/2" is the root element, ids asserted where they're unique), then the
    element's first child (/1, or /2 when that's an element) and the offset."""
    steps, node = [], el
    while node is not root:
        parent = node.getparent()
        j = _kids(parent).index(node)
        ident = node.get("id")
        steps.insert(0, f"/{(j + 1) * 2}" + (f"[{H._esc(ident)}]" if ident and ids[ident] == 1 else ""))
        node = parent
    first = 2 if len(el) and isinstance(el[0].tag, str) and not el.text else 1
    return "/2" + "".join(steps) + f"/{first}:{off}"


def calibre_reads(root, at, cfi):
    """Where Calibre's viewer puts one of its CFIs in the chapter's flat text: at the edge between
    two pieces of text it takes the end of the first (read_book/cfi's node_for_text_offset)."""
    steps = H._steps(cfi)
    pts = H._points(root, at, steps[1:]) if steps and len(steps) > 1 and steps[0][0] == 2 else []
    return pts[0][0] if pts else None


def _calibre_at(root, at, spans, ids, x, end):
    """A place in the flat text → a Calibre CFI that Calibre reads back as that very place. The start
    of text that comes right after an element can't be said as an offset in it (Calibre would read
    the end of the text before the element, and the highlight would take in the element's words),
    so it's said as the end of the text before it instead."""
    if end:
        cands = [(el, cum + x - st) for st, size, el, cum in spans if size and st < x <= st + size]
        cands += [(el, cum) for st, size, el, cum in spans if st == x]
    else:
        cands = [(el, cum + x - st) for st, size, el, cum in spans if size and st <= x < st + size]
        cands += [(el, cum + size) for st, size, el, cum in spans if size and st + size == x]
    for el, off in cands:
        cfi = _encode(root, ids, el, off)
        if calibre_reads(root, at, cfi) == x:
            return cfi
    return None


def annotation(path, h, uuid):
    """One Daf highlight as Calibre's annotation, or None when Calibre couldn't be shown it exactly."""
    pos = json.loads(h["pos"]) if h["pos"] and str(h["pos"]).startswith("{") else {}
    parsed = parse_cfi(pos.get("cfi")) if not pos.get("pdf") else None
    if not parsed:
        return None
    base, start, end = parsed
    bk = H._book(path)
    want = [s[0] for s in base]
    i = next((j for j, it in enumerate(bk["items"]) if [s[0] for s in H._steps(it[1])] == want), None)
    if i is None:
        return None
    root, text, at = H._doc(path, bk, i)
    s, e = _spec_at(root, at, start), _spec_at(root, at, end)
    if s is None or e is None or e <= s:
        return None
    words = text[2 * s:2 * e].decode("utf-16-le", "replace")
    if H._norm(words).casefold() != H._norm(h["text"]).casefold():
        return None                                     # the file has changed since it was made
    spans = _spans(root, at)
    ids = Counter(el.get("id") for el in root.iter() if isinstance(el.tag, str) and el.get("id"))
    a = {"type": "highlight", "uuid": uuid, "highlighted_text": words, "start_cfi": _calibre_at(root, at, spans, ids, s, False),
         "end_cfi": _calibre_at(root, at, spans, ids, e, True), "spine_index": i, "spine_name": bk["items"][i][0],
         "style": {"type": "builtin", "kind": "color", "which": STYLE.get(h["color"] or "yellow", "yellow")}}
    if not a["start_cfi"] or not a["end_cfi"]:
        return None
    if h["chapter"]:
        a["toc_family_titles"] = [h["chapter"]]
    if (h["user_note"] or "").strip():
        a["notes"] = h["user_note"].strip()
    back = parse_cfi(H.place(path, a).get("cfi"))      # read back the way Daf reads Calibre's: the same spot
    if not back or (_spec_at(root, at, back[1]), _spec_at(root, at, back[2])) != (s, e):
        return None
    return a


def _hash(a):
    return hashlib.sha1(json.dumps({k: v for k, v in a.items() if k != "timestamp"}, sort_keys=True).encode()).hexdigest()[:20]


def plan(conn, now=None):
    """What to send: ([{op: annotations, id, fmt, annots}], [rows for calibre_pushed])."""
    now = now or int(time.time())
    sent = {r["hl_id"]: dict(r) for r in conn.execute("SELECT * FROM calibre_pushed")}
    rows = conn.execute(
        "SELECT h.id, h.book_id, h.text, h.chapter, h.created, h.pos, h.color, h.deleted, s.user_note, b.calibre_id "
        "FROM highlights h JOIN books b ON b.id = h.book_id LEFT JOIN review_state s ON s.hl_id = h.id "
        "WHERE h.source = 'epub' AND b.calibre_id IS NOT NULL").fetchall()
    files, ops, done, seen = {}, {}, [], set()
    for h in rows:
        seen.add(h["id"])
        u, prev = H.daf_uuid(h["id"]), sent.get(h["id"])
        if h["deleted"]:
            if prev and not prev["removed"]:
                stub = {"type": "highlight", "uuid": u, "removed": True, "timestamp": _iso(now)}
                ops.setdefault((prev["cal_id"], prev["fmt"]), []).append(stub)
                done.append((h["id"], u, prev["cal_id"], prev["fmt"], prev["hash"], 1, now, _hash(stub)))
            continue
        bid = h["book_id"]
        if bid not in files:
            files[bid] = ebooks.book_file(conn, bid)
        path, fmt = files[bid]
        if fmt != "EPUB":
            continue
        try:
            a = annotation(path, h, u)
        except Exception:  # noqa: BLE001 - one book Daf can't read this way doesn't stop the rest
            log.exception("highlight %s for Calibre", h["id"])
            a = None
        if not a:
            continue
        key, cid = _hash(a), h["calibre_id"]
        if prev and prev["hash"] == key and not prev["removed"] and prev["cal_id"] == cid:
            continue
        a["timestamp"] = _iso(now if prev else (h["created"] or now))     # a change is newer than what Calibre has
        ops.setdefault((cid, "EPUB"), []).append(a)
        done.append((h["id"], u, cid, "EPUB", key, 0, now, key))
    for hid, prev in sent.items():                       # gone from Daf altogether
        if hid not in seen and not prev["removed"]:
            stub = {"type": "highlight", "uuid": prev["uuid"], "removed": True, "timestamp": _iso(now)}
            ops.setdefault((prev["cal_id"], prev["fmt"]), []).append(stub)
            done.append((hid, prev["uuid"], prev["cal_id"], prev["fmt"], prev["hash"], 1, now, _hash(stub)))
    return [{"op": "annotations", "id": cid, "fmt": fmt, "annots": annots} for (cid, fmt), annots in ops.items()], done


def push(conn, settings=None):
    """Send what changed to Calibre (one run of calibre-debug, under calibrewrite's lock). Returns how many."""
    from . import calibrewrite
    ops, done = plan(conn)
    if not ops:
        return 0
    # A change must be newer than the version Calibre has, or Calibre's merge keeps its own (the Mac's
    # clock may be ahead of the server's); a first one Calibre doesn't have yet keeps its own time.
    known = {d[1]: {"cal_id": d[2], "fmt": d[3]} for d in done}
    try:
        theirs = {u: H._epoch_ms(a["data"].get("timestamp")) for u, a in _calibre_side(known).items()}
    except Exception:  # noqa: BLE001 - a library without Calibre's annotations yet: nothing there to be newer than
        theirs = {}
    for op in ops:
        for a in op["annots"]:
            t = theirs.get(a["uuid"])
            if t is not None and H._epoch_ms(a["timestamp"]) <= t:
                a["timestamp"] = _iso((t + 1) / 1000)
    conn.commit()                    # nothing of the sync's held open while Calibre's run brings Daf's book rows along (calibrewrite._follow)
    calibrewrite.run(ops, timeout=300)
    conn.executemany("INSERT OR REPLACE INTO calibre_pushed (hl_id, uuid, cal_id, fmt, hash, removed, at, seen) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", done)
    return len(done)


# ---------- the other way: what was done in Calibre to Daf's own highlights ----------
def _calibre_side(sent):
    """Calibre's version now of each highlight Daf sent it (the newest, should two users have one): {uuid: annotation}."""
    out = {}
    for a in H.annotations():
        p = sent.get(a["uuid"])
        if not p or a["book"] != p["cal_id"] or a["format"] != p["fmt"]:
            continue
        cur = out.get(a["uuid"])
        if not cur or (H._epoch(a["data"].get("timestamp")) or 0) > (H._epoch(cur["data"].get("timestamp")) or 0):
            out[a["uuid"]] = a
    return out


def pull(conn, settings):
    """Changes made in Calibre (its viewer on the Mac) to the highlights Daf sent it, back into Daf.

    Calibre's side changed when its version isn't the one Daf last knew (`seen`; Calibre's viewer
    doesn't always move a highlight's time, a note alone keeps it). Daf's side changed when what Daf
    would send now isn't what it last sent (`hash`), or Daf removed it. If only Calibre's changed, Daf
    takes it; if both did, the newer wins: Calibre's time for its version against the time the
    highlight last changed in Daf (highlights.changed, its note's note_updated), and a Daf win is
    sent by push() as usual. Taken from Calibre: the note, the colour, the ends (only when Calibre's
    place for them holds its words in the file Daf reads; otherwise Daf keeps its place), removed
    (Daf's own removal: deleted = 1, which can be undone) and, for one Daf had removed and Calibre
    changed later, brought back. Only ever for a highlight made in Daf's reader whose uuid is Daf's
    own for it. Afterwards both sides are recorded as they now are, so nothing goes back and forth.
    Returns how many highlights changed in Daf."""
    from . import review, vaultnotes
    sent = {r["uuid"]: dict(r) for r in conn.execute("SELECT * FROM calibre_pushed WHERE removed = 0")}
    if not sent:
        return 0
    files, taken = {}, 0
    for u, theirs in _calibre_side(sent).items():
        p, d = sent[u], theirs["data"]
        if _hash(d) == (p["seen"] or p["hash"]):
            continue                                     # as Daf left it
        h = conn.execute("SELECT h.*, s.user_note, s.note_updated FROM highlights h LEFT JOIN review_state s ON s.hl_id = h.id "
                         "WHERE h.id = ?", (p["hl_id"],)).fetchone()
        if not h or h["source"] != "epub" or H.daf_uuid(h["id"]) != u:
            continue                                     # only Daf's own, by its own uuid
        bid = h["book_id"]
        if bid not in files:
            files[bid] = ebooks.book_file(conn, bid)
        path, fmt = files[bid]
        try:
            mine = annotation(path, h, u) if path and fmt == "EPUB" else None
        except Exception:  # noqa: BLE001
            mine = None
        daf_changed = bool(h["deleted"]) or (mine is not None and _hash(mine) != p["hash"])
        if daf_changed and max(h["changed"] or 0, h["note_updated"] or 0, h["created"] or 0) >= (H._epoch(d.get("timestamp")) or 0):
            continue                                     # Daf's change is the newer: push() sends it
        before = (h["deleted"], h["user_note"], h["color"], h["pos"], h["text"])
        if d.get("removed"):
            if not h["deleted"]:
                conn.execute("UPDATE highlights SET deleted = 1 WHERE id = ?", (h["id"],))
        else:
            if h["deleted"]:
                conn.execute("UPDATE highlights SET deleted = 0 WHERE id = ?", (h["id"],))
            note = (d.get("notes") or "").strip() or None
            if note != ((h["user_note"] or "").strip() or None):
                review.set_note(conn, h["id"], note)
            c = H.color(d.get("style"))
            if c != (h["color"] or "yellow"):
                conn.execute("UPDATE highlights SET color = ? WHERE id = ?", (None if c == "yellow" else c, h["id"]))
            ends = (d.get("start_cfi"), d.get("end_cfi"))
            if mine is not None and ends != (mine["start_cfi"], mine["end_cfi"]) and fmt == theirs["format"]:
                at = H.place(path, d)
                if at.get("cfi"):                        # Calibre's new ends hold its words in this file
                    pos = json.loads(h["pos"]) if h["pos"] and str(h["pos"]).startswith("{") else {}
                    pos.update(cfi=at["cfi"], fraction=at.get("fraction"))
                    toc = [str(t).strip() for t in d.get("toc_family_titles") or [] if str(t).strip()] if isinstance(d.get("toc_family_titles"), list) else []
                    conn.execute("UPDATE highlights SET pos = ?, text = ?, chapter = COALESCE(?, chapter) WHERE id = ?",
                                 (json.dumps(pos), d["highlighted_text"].strip(), toc[-1][:200] if toc else None, h["id"]))
        h2 = conn.execute("SELECT h.*, s.user_note FROM highlights h LEFT JOIN review_state s ON s.hl_id = h.id WHERE h.id = ?", (h["id"],)).fetchone()
        try:
            now_mine = annotation(path, h2, u) if path and fmt == "EPUB" and not h2["deleted"] else None
        except Exception:  # noqa: BLE001
            now_mine = None
        conn.execute("UPDATE calibre_pushed SET hash = ?, seen = ?, removed = ?, at = ? WHERE hl_id = ?",
                     (_hash(now_mine) if now_mine else p["hash"], _hash(d), 1 if h2["deleted"] else 0, int(time.time()), h["id"]))
        if before != (h2["deleted"], h2["user_note"], h2["color"], h2["pos"], h2["text"]):
            taken += 1
            vaultnotes.write_for(conn, settings, bid)    # as Daf's own removal and edits do
    return taken
