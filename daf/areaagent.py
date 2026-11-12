"""Learn's area agent (web/learn.js: an area's Overview, Plan and Ask).

Three things the model does for one area, each in the background (an answer takes a minute or so):
- ask: an answer from the area's own things (a book's highlights and notes, an article's paragraphs, a
  video's transcript), or from anywhere as well. Every paragraph says where it came from, and each of
  those opens there: the highlight, the paragraph, the moment in the video. Kept in area_chat.
- plan: weeks of steps from the area's things in an order that builds, with parts and minutes, things
  to do, and what's missing from outside (offered to add). areas.plan_draft until Keep makes it
  areas.plan; a step is ticked off there, or by finishing what it points to.
- layout: the area's Overview as a dashboard for its subject, in sections of fixed kinds (SECTIONS)
  that the model picks, titles and fills. areas.layout_draft until Keep; Undo drops it. Without a
  layout of its own the Overview has DEFAULT.

Nothing private goes to the model: a private book never shows in an area, and a private article is left
out here.
"""
import json
import re
import secrets
import threading
import time
import urllib.parse

from . import ai, areas, db

SECTIONS = ("plan", "continue", "next", "highlights", "things", "questions", "feeds", "suggestions")
DEFAULT = [{"kind": "plan", "wide": True}, {"kind": "continue"}, {"kind": "next", "wide": True}, {"kind": "questions"},
           {"kind": "highlights", "wide": True}, {"kind": "feeds"}, {"kind": "suggestions"}]
KNAME = {"book": "Book", "article": "Article", "video": "Video"}

_working = {}           # (area id, "plan" | "layout") -> when it began
_errors = {}            # (area id, "plan" | "layout") -> what went wrong last time


def _now():
    return int(time.time())


def _json(text):
    """The first JSON object in the model's answer, or None."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        v = json.loads(m.group(0))
    except ValueError:
        return None
    return v if isinstance(v, dict) else None


def _clip(v, n):
    return " ".join(str(v or "").split())[:n]


def _mins(v, top=600):
    try:
        return max(1, min(top, int(v)))
    except (TypeError, ValueError):
        return 0


def _t(sec):
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _private(c, item_id):
    r = c.execute("SELECT private FROM books WHERE id = ?", (item_id,)).fetchone()
    return bool(r and r["private"])


def _area(c, aid):
    a = c.execute("SELECT * FROM areas WHERE id = ?", (aid,)).fetchone()
    if not a:
        raise KeyError(aid)
    return a


def _things(c, aid):
    """The area's things that aren't feeds and aren't private, as areas._resolve gives them."""
    return [x for x in areas._items(c, aid) if x["kind"] != "feed" and x.get("id") and not _private(c, x["id"])]


# ---- what the model reads -----------------------------------------------------------------------

def sources(c, aid, only=None, words=24000):
    """The area's things, numbered from 1, with what's in them: a book's highlights and notes, an
    article's paragraphs (p:<block>), a video's transcript (t:<seconds>). Each doc gets a fair share of
    `words`."""
    things = _things(c, aid)
    if only:
        things = [x for x in things if x["ref"] in set(only)]
    docs = sum(1 for x in things if x["go"].startswith("read/"))
    share = max(600, min(4000, words // max(1, docs)))
    out = []
    for n, x in enumerate(things, 1):
        s = {"n": n, "ref": x["ref"], "id": x["id"], "kind": x["kind"], "title": x["title"], "by": x["by"], "go": x["go"],
             "st": x["st"], "len": x["len"], "lines": [], "paras": {}, "times": set(), "hl": {}}
        if x["go"].startswith("read/"):
            row = c.execute("SELECT blocks FROM doc_content WHERE id = ?", (x["id"],)).fetchone()
            try:
                blocks = json.loads(row["blocks"]) if row else []
            except ValueError:
                blocks = []
            used = 0
            for i, b in enumerate(blocks if isinstance(blocks, list) else []):
                text = " ".join(str(b.get("x") or "").split()) if isinstance(b, dict) else ""
                if not text or b.get("t") in ("img", "pg"):
                    continue
                if b.get("t") == "cue" and b.get("ts") is not None:
                    s["lines"].append(f"(t:{int(b['ts'])}) {text}")
                    s["times"].add(int(b["ts"]))
                else:
                    s["paras"][i] = len(s["paras"]) + 1
                    s["lines"].append(f"(p:{i}) {text}")
                used += len(text.split())
                if used >= share:
                    s["lines"].append("[…]")
                    break
        for h in c.execute("SELECT id, text, note FROM highlights WHERE book_id = ? AND deleted = 0 ORDER BY created LIMIT 80", (x["id"],)):
            if (h["text"] or "").strip():
                s["hl"][str(h["id"])] = (_clip(h["text"], 600), _clip(h["note"], 300))
        out.append(s)
    return out


def _block(s, text=True):
    head = f"[{s['n']}] {KNAME.get(s['kind'], 'Article')}: {s['title']}" + (f" — {s['by']}" if s["by"] else "")
    meta = ", ".join(v for v in (s["len"], {"New": "not started", "Done": "finished", "Wanted": "not in Daf yet"}.get(s["st"], f"{s['st']} through" if s["st"] else "")) if v)
    lines = [head + (f" ({meta})" if meta else "")]
    if text:
        lines += ["  " + ln for ln in s["lines"]]
        if s["hl"]:
            lines.append("  Their highlights:")
            lines += [f"  (h:{hid}) \"{t}\"" + (f" (their note: {nt})" if nt else "") for hid, (t, nt) in s["hl"].items()]
    return "\n".join(lines)


def _cite(srcs, f):
    """Where a paragraph came from, as a chip that opens there: {label, go, kind}."""
    if not isinstance(f, dict):
        return None
    try:
        n = int(f.get("n"))
    except (TypeError, ValueError):
        return None
    s = next((x for x in srcs if x["n"] == n), None)
    if not s:
        return None
    go, label = s["go"], s["title"]
    m = re.match(r"^\s*(h|p|t):\s*(\S+)\s*$", str(f.get("at") or ""))
    if m:
        k, v = m.groups()
        if k == "h" and v in s["hl"]:
            go, label = go + "/hl:" + urllib.parse.quote(v, safe=""), label + " · my highlight"
        elif k == "p" and v.isdigit() and int(v) in s["paras"]:
            go, label = go + "/p:" + v, label + " · ¶ " + str(s["paras"][int(v)])
        elif k == "t" and v.isdigit() and int(v) in s["times"]:
            go, label = go + "/t:" + v, label + " · " + _t(int(v))
    return {"label": label, "go": go, "kind": s["kind"]}


def _outside(got, check=None):
    """Things from outside the area the model offers: only the ones whose link opens (a book needs none)."""
    keep = []
    for o in got if isinstance(got, list) else []:
        if not isinstance(o, dict) or o.get("kind") not in KNAME or not _clip(o.get("title"), 200):
            continue
        o = {"kind": o["kind"], "title": _clip(o["title"], 200), "by": _clip(o.get("by"), 120), "url": str(o.get("url") or "").strip()}
        o = (check or areas._checked)(o)
        if o:
            keep.append(o)
    return keep


def _goal(a):
    return f"Their goal: {a['goal']}\n" if a["goal"] else ""


# ---- Ask --------------------------------------------------------------------------------------------

ASK = """You're the helper in Learn, the part of a personal reading app where someone learns a whole subject.
Subject: {name}
{goal}Their own things for it are below, numbered: books (with their highlights and notes), articles (by paragraph, p:<n>) and videos (by moment, t:<seconds>).

{how}
Write a few short paragraphs, plain and direct: no headings, no markdown, a list only when they ask for one. With each paragraph say where it came from: the source's number and, when you can, the place in it, a highlight (h:<id>), a paragraph (p:<n>) or a moment (t:<seconds>). A paragraph that comes from what you know has an empty list.
{outside}
Reply with JSON only, nothing around it:
{{"paras": [{{"text": "...", "from": [{{"n": 1, "at": "p:4"}}]}}]{outside_key}}}

<sources>
{sources}
</sources>
{earlier}
Their question: {q}"""
MINE = "Answer from these sources. When they don't say, say so plainly in a sentence, and stop there."
ANY = "Answer from these sources first, and from what you know beyond them where that helps."
OUTSIDE = ('Also offer up to 3 things from outside their sources worth adding for this question (books, articles or videos, the '
           'best-known and most trusted), each with "kind", "title", "by" and "url" (for an article or a video; your best guess is '
           'fine, each is checked before it\'s shown).')


def ask_start(c, aid, q, anywhere=False, only=None):
    """A question to the area's helper: its row now (asking), its answer in the background."""
    _area(c, aid)
    q = _clip(q, 600)
    if not q:
        raise ValueError("A question, please")
    cid = "q" + secrets.token_hex(5)
    c.execute("INSERT INTO area_chat (id, area_id, q, anywhere, refs, state, made) VALUES (?, ?, ?, ?, ?, 'asking', ?)",
              (cid, aid, q, 1 if anywhere else 0, json.dumps(only) if only else None, _now()))
    c.commit()

    def go():
        c2 = db.connect()
        try:
            ask_now(c2, cid)
        finally:
            c2.close()
    threading.Thread(target=go, daemon=True).start()
    return cid


def ask_now(c, cid, run=None, check=None):
    r = c.execute("SELECT * FROM area_chat WHERE id = ?", (cid,)).fetchone()
    if not r:
        return None
    try:
        a = _area(c, r["area_id"])
        only = json.loads(r["refs"]) if r["refs"] else None
        srcs = sources(c, a["id"], only)
        earlier = c.execute("SELECT q, a FROM area_chat WHERE area_id = ? AND state = 'done' AND made <= ? AND id != ? ORDER BY made DESC LIMIT 3",
                            (a["id"], r["made"], cid)).fetchall()
        back = []
        for e in reversed(earlier):
            try:
                said = " ".join(p["text"] for p in json.loads(e["a"])["paras"])
            except (ValueError, KeyError, TypeError):
                said = ""
            back.append(f"Q: {e['q']}\nA: {_clip(said, 700)}")
        text = ASK.format(name=a["name"], goal=_goal(a), how=ANY if r["anywhere"] else MINE,
                          outside=OUTSIDE if r["anywhere"] else "", outside_key=', "outside": []' if r["anywhere"] else "",
                          sources="\n\n".join(_block(s) for s in srcs) or "(nothing yet)",
                          earlier=("Earlier here:\n" + "\n\n".join(back) + "\n") if back else "", q=r["q"])
        out = (run or ai.run)(text, timeout=300)
        got = _json(out)
        paras = []
        for p in (got or {}).get("paras") or []:
            t = _clip(p.get("text") if isinstance(p, dict) else p, 2000)
            if not t:
                continue
            chips, seen = [], set()
            for f in (p.get("from") if isinstance(p, dict) else None) or []:
                ch = _cite(srcs, f)
                if ch and ch["go"] not in seen:
                    seen.add(ch["go"])
                    chips.append(ch)
            paras.append({"text": t, "from": chips})
        if not paras:                       # not the JSON asked for: the words as they came
            t = _clip(re.sub(r"[{}\[\]\"]", " ", out), 2000) if not got else ""
            if not t:
                raise RuntimeError("The answer came back empty")
            paras = [{"text": t, "from": []}]
        answer = {"paras": paras, "outside": _outside((got or {}).get("outside"), check) if r["anywhere"] else []}
        c.execute("UPDATE area_chat SET a = ?, state = 'done' WHERE id = ?", (json.dumps(answer, ensure_ascii=False), cid))
    except Exception as e:  # noqa: BLE001 - shown with the question
        c.execute("UPDATE area_chat SET a = ?, state = 'error' WHERE id = ?", (str(e)[:300] or "No answer came back", cid))
    c.commit()
    return cid


def chats(c, aid, limit=30):
    out = []
    for r in c.execute("SELECT * FROM (SELECT * FROM area_chat WHERE area_id = ? ORDER BY made DESC, rowid DESC LIMIT ?) ORDER BY made, rowid", (aid, limit)):
        x = {"id": r["id"], "q": r["q"], "anywhere": bool(r["anywhere"]), "state": r["state"], "made": r["made"]}
        if r["state"] == "asking" and _now() - r["made"] > 900:          # the server went away while it asked
            x["state"], x["error"] = "error", "No answer came back"
        elif r["state"] == "error":
            x["error"] = r["a"] or "No answer came back"
        elif r["state"] == "done":
            try:
                x.update(json.loads(r["a"]))
            except (ValueError, TypeError):
                x.update({"paras": [], "outside": []})
            x["n"] = len({ch["go"].split("/")[1] for p in x.get("paras", []) for ch in p.get("from", [])})
        out.append(x)
    return out


def forget(c, aid, cid):
    c.execute("DELETE FROM area_chat WHERE id = ? AND area_id = ?", (cid, aid))
    c.commit()


# ---- the plan ----------------------------------------------------------------------------------------

PLAN = """You're the helper in Learn, the part of a personal reading app where someone learns a whole subject.
Subject: {name}
{goal}
Make them a study plan for {weeks} weeks, at about {mins} minutes a day, built from their own things below (by number), in an order that builds. A book too long for one step is split into parts (chapters or page ranges), each its own step. Give every step its minutes. Leave out what they've finished, unless it's worth a quick look back. Where the subject needs something they don't have, add it from outside (a well-known book, article or video, with its address when it has one); where it's learned by doing, add steps to do (practise, write, try), said in a few words. Name each week by what it's for, in two to four words, and give the plan a short title.

Reply with JSON only, nothing around it:
{{"title": "...", "weeks": [{{"name": "...", "steps": [{{"n": 1, "part": "ch. 1-4", "mins": 90}}, {{"do": "...", "mins": 30}}, {{"add": {{"kind": "article", "title": "...", "by": "...", "url": "..."}}, "mins": 10}}]}}]}}

<things>
{things}
</things>"""


def _plan_from(got, srcs, check=None):
    weeks = []
    for w in (got or {}).get("weeks") or []:
        if not isinstance(w, dict):
            continue
        steps = []
        for st in (w.get("steps") or [])[:8]:
            if not isinstance(st, dict):
                continue
            mins = _mins(st.get("mins"))
            if st.get("n") is not None:
                s = next((x for x in srcs if str(x["n"]) == str(st.get("n"))), None)
                if s:
                    steps.append({"ref": s["ref"], "title": s["title"], "kind": s["kind"], "part": _clip(st.get("part"), 60), "mins": mins, "done": False})
            elif st.get("do"):
                steps.append({"do": _clip(st["do"], 140), "mins": mins, "done": False})
            elif isinstance(st.get("add"), dict):
                o = _outside([st["add"]], check)
                if o:
                    steps.append({"add": o[0], "mins": mins, "done": False})
        if steps:
            weeks.append({"name": _clip(w.get("name"), 40) or f"Week {len(weeks) + 1}", "steps": steps})
    if not weeks:
        raise RuntimeError("The plan came back empty")
    return {"title": _clip((got or {}).get("title"), 80), "weeks": weeks[:12]}


def plan_now(c, aid, mins=30, weeks=4, run=None, check=None):
    a = _area(c, aid)
    srcs = sources(c, aid)
    text = PLAN.format(name=a["name"], goal=_goal(a), weeks=weeks, mins=mins,
                       things="\n".join(_block(s, text=False) for s in srcs) or "(nothing yet)")
    plan = _plan_from(_json((run or ai.run)(text, timeout=300)), srcs, check)
    plan.update({"mins": mins, "made": _now()})
    c.execute("UPDATE areas SET plan_draft = ? WHERE id = ?", (json.dumps(plan, ensure_ascii=False), aid))
    c.commit()
    return plan


def _start(aid, what, fn):
    """Run fn(c) in the background, once at a time per area and kind."""
    if (aid, what) in _working:
        return False
    _working[(aid, what)] = _now()
    _errors.pop((aid, what), None)

    def go():
        c = db.connect()
        try:
            fn(c)
        except Exception as e:  # noqa: BLE001 - shown on the page
            _errors[(aid, what)] = str(e)[:300]
        finally:
            c.close()
            _working.pop((aid, what), None)
    threading.Thread(target=go, daemon=True).start()
    return True


def plan_start(c, aid, mins=30, weeks=4):
    _area(c, aid)
    mins = mins if mins in (15, 20, 30, 45, 60, 90) else 30
    weeks = weeks if weeks in (1, 2, 3, 4, 6, 8, 12) else 4
    return _start(aid, "plan", lambda c2: plan_now(c2, aid, mins, weeks))


def _load(v):
    try:
        return json.loads(v) if v else None
    except ValueError:
        return None


def plan_change(c, aid, b):
    """Keep or drop the draft, clear the plan, tick a step, or add a step's thing to the area."""
    a = _area(c, aid)
    if b.get("keep"):
        draft = _load(a["plan_draft"])
        if not draft:
            raise ValueError("No plan to keep")
        draft["kept"] = _now()
        c.execute("UPDATE areas SET plan = ?, plan_draft = NULL WHERE id = ?", (json.dumps(draft, ensure_ascii=False), aid))
    elif b.get("drop"):
        c.execute("UPDATE areas SET plan_draft = NULL WHERE id = ?", (aid,))
    elif b.get("clear"):
        c.execute("UPDATE areas SET plan = NULL WHERE id = ?", (aid,))
    else:
        draft_or_plan = "plan_draft" if b.get("draft") else "plan"
        plan = _load(a[draft_or_plan])
        try:
            w, s = (int(x) for x in (b.get("tick") or b.get("add") or [])[:2])
            step = plan["weeks"][w]["steps"][s]
        except (TypeError, ValueError, KeyError, IndexError):
            raise ValueError("No such step")
        if b.get("tick") is not None:
            step["done"] = bool(b.get("done"))
        elif "add" in step:
            o = step["add"]
            r = areas.add(c, aid, _outside_ref(c, o))
            step.update({"ref": r, "title": o["title"], "kind": o["kind"]})
        c.execute(f"UPDATE areas SET {draft_or_plan} = ? WHERE id = ?", (json.dumps(plan, ensure_ascii=False), aid))
    c.commit()


def _outside_ref(c, o, save_link=None):
    """Something from outside, into the area: a book wanted, an article or a video saved to the Library."""
    if o["kind"] == "book":
        return "want:" + o["title"] + ("|" + o["by"] if o["by"] else "")
    did = (save_link or areas._save_link)(c, o["url"], o["title"])
    return ("doc:" + did) if did else ("url:" + o["url"])


def plan_view(c, plan, things):
    """A plan as the page shows it: each step with where it opens and whether it's done (ticked, or what
    it points to finished), and the week it's in now (the first with something left)."""
    if not plan:
        return None
    by_ref = {x["ref"]: x for x in things}
    weeks = []
    for w in plan.get("weeks") or []:
        steps = []
        for st in w.get("steps") or []:
            v = {"mins": st.get("mins") or 0, "done": bool(st.get("done"))}
            if st.get("ref"):
                x = by_ref.get(st["ref"]) or areas._resolve(c, st["ref"]) or {}
                v.update({"title": x.get("title") or st.get("title") or "", "kind": x.get("kind") or st.get("kind") or "article",
                          "part": st.get("part") or "", "go": x.get("go") or "", "auto": x.get("st") == "Done", "done": v["done"] or x.get("st") == "Done"})
            elif st.get("add"):
                o = st["add"]
                v.update({"title": o["title"], "kind": o["kind"], "by": o["by"], "url": o.get("url") or "", "add": True})
            else:
                v.update({"title": st.get("do") or "", "kind": "do"})
            steps.append(v)
        weeks.append({"name": w.get("name") or "", "steps": steps, "done": all(s["done"] for s in steps)})
    now = next((i for i, w in enumerate(weeks) if not w["done"]), len(weeks) - 1)
    return {"title": plan.get("title") or "", "mins": plan.get("mins") or 0, "weeks": weeks, "now": max(0, now)}


# ---- the layout --------------------------------------------------------------------------------------

LAYOUT = """You're the helper in Learn, the part of a personal reading app where someone learns a whole subject.
Subject: {name}
{goal}{how}
Arrange the area's page as a dashboard for learning this subject. Pick 4 to 7 sections, in order, from these kinds only:
- "plan": this week of their study plan{plan}
- "continue": the one thing to go on with
- "next": what's next, in order
- "highlights": their highlights, in groups you name (each group a short name and the highlight ids)
- "things": some of their things you pick (by number) under a title you give, like what to watch before something
- "questions": what they've asked about it here
- "feeds": the feeds they follow for it{feeds}
- "suggestions": things the helper suggests adding{sugg}
Each section has "kind", a short plain "title" ("" keeps the kind's own name) and "wide" (true for one that needs room). A
"highlights" section has "groups": [{{"name": "...", "hl": ["<id>", ...]}}]; a "things" section has "items": [<numbers>].

Reply with JSON only, nothing around it: {{"sections": [...]}}

<things>
{things}
</things>
<highlights>
{hls}
</highlights>
{asked}"""


def _hl_ids(c, things):
    ids = [x["id"] for x in things]
    if not ids:
        return {}
    q = ",".join("?" * len(ids))
    return {str(h["id"]): h for h in c.execute(
        f"SELECT h.id, h.text, h.note, h.book_id FROM highlights h WHERE h.deleted = 0 AND h.book_id IN ({q}) ORDER BY h.created DESC LIMIT 400", ids)}


def clean_sections(c, aid, got, things=None):
    """Sections as they're kept: known kinds only, what they point to checked against the area."""
    a = _area(c, aid)
    things = things if things is not None else _things(c, aid)
    hls = _hl_ids(c, things)
    nums = {str(i): x["ref"] for i, x in enumerate(things, 1)}
    refs = {x["ref"] for x in things}
    has = {"plan": bool(a["plan"]), "suggestions": bool(a["suggest"]),
           "feeds": bool(c.execute("SELECT 1 FROM area_items WHERE area_id = ? AND ref LIKE 'feed:%'", (aid,)).fetchone())}
    out = []
    for s in got if isinstance(got, list) else []:
        if not isinstance(s, dict) or s.get("kind") not in SECTIONS or has.get(s["kind"]) is False:
            continue
        v = {"kind": s["kind"], "title": _clip(s.get("title"), 50), "wide": bool(s.get("wide"))}
        if s["kind"] == "highlights" and s.get("groups"):
            groups = []
            for g in s["groups"][:5] if isinstance(s["groups"], list) else []:
                ids = [str(i) for i in (g.get("hl") or [])[:8] if str(i) in hls] if isinstance(g, dict) else []
                if ids:
                    groups.append({"name": _clip(g.get("name"), 40), "hl": ids})
            v["groups"] = groups
        if s["kind"] == "things":
            pick = [nums.get(str(n)) or (n if n in refs else None) for n in (s.get("items") or s.get("refs") or [])[:8]]
            v["refs"] = [r for r in pick if r]
            if not v["refs"]:
                continue
        out.append(v)
    return out[:8]


def layout_now(c, aid, how="", run=None):
    a = _area(c, aid)
    srcs = sources(c, aid)
    things = _things(c, aid)
    hls = _hl_ids(c, things)
    title = {x["id"]: x["title"] for x in things}
    asked = [r["q"] for r in c.execute("SELECT q FROM area_chat WHERE area_id = ? AND state = 'done' ORDER BY made DESC LIMIT 8", (aid,))]
    has_feeds = bool(c.execute("SELECT 1 FROM area_items WHERE area_id = ? AND ref LIKE 'feed:%'", (aid,)).fetchone())
    text = LAYOUT.format(name=a["name"], goal=_goal(a), how=f"What they want the page for: {how}\n" if how else "",
                         plan=" (they have one)" if a["plan"] else " (they have none yet: leave it out)",
                         feeds="" if has_feeds else " (none yet: leave it out)", sugg="" if a["suggest"] else " (turned off: leave it out)",
                         things="\n".join(_block(s, text=False) for s in srcs) or "(nothing yet)",
                         hls="\n".join(f"(h:{hid}) \"{_clip(h['text'], 240)}\" from {title.get(h['book_id'], '')}" for hid, h in list(hls.items())[:120]) or "(none yet)",
                         asked=("What they've asked here:\n" + "\n".join(f"- {q}" for q in asked)) if asked else "")
    got = _json((run or ai.run)(text, timeout=300))
    sections = clean_sections(c, aid, (got or {}).get("sections"), things)
    if not sections:
        raise RuntimeError("The layout came back empty")
    c.execute("UPDATE areas SET layout_draft = ? WHERE id = ?", (json.dumps({"sections": sections, "how": _clip(how, 120), "made": _now()}, ensure_ascii=False), aid))
    c.commit()
    return sections


def layout_start(c, aid, how=""):
    _area(c, aid)
    how = _clip(how, 200)
    return _start(aid, "layout", lambda c2: layout_now(c2, aid, how))


def layout_change(c, aid, b):
    """Keep or drop the draft, go back to the plain page, or save sections as edited."""
    a = _area(c, aid)
    if b.get("keep"):
        draft = _load(a["layout_draft"])
        if not draft:
            raise ValueError("No layout to keep")
        c.execute("UPDATE areas SET layout = ?, layout_draft = NULL WHERE id = ?", (json.dumps(draft, ensure_ascii=False), aid))
    elif b.get("drop"):
        c.execute("UPDATE areas SET layout_draft = NULL WHERE id = ?", (aid,))
    elif b.get("plain"):
        c.execute("UPDATE areas SET layout = NULL WHERE id = ?", (aid,))
    elif isinstance(b.get("sections"), list):
        sections = clean_sections(c, aid, b["sections"])
        old = _load(a["layout"]) or {}
        c.execute("UPDATE areas SET layout = ? WHERE id = ?", (json.dumps(dict(old, sections=sections, made=old.get("made") or _now()), ensure_ascii=False), aid))
    c.commit()


def sections_view(c, aid, sections, p, plan, chat):
    """Sections as the page draws them, each with what it shows."""
    things = p["items"]
    by_ref = {x["ref"]: x for x in things}
    hls = None
    out = []
    for at, s in enumerate(sections):
        v = dict(s, at=at)                  # (its place in the layout, for Edit)
        k = s["kind"]
        if k == "plan":
            if not plan:
                continue
            v["plan"] = plan
        elif k == "continue":
            nxt = next((x for x in p["next"] if x.get("go")), None)
            if not nxt:
                continue
            v["item"] = nxt
        elif k == "next":
            if not p["next"]:
                continue
            v["items"] = p["next"]
        elif k == "highlights":
            if s.get("groups"):
                if hls is None:
                    hls = _hl_ids(c, [x for x in things if x.get("id")])
                title = {x["id"]: x for x in things if x.get("id")}
                v["groups"] = [{"name": g["name"], "hls": [_hl(hls[i], title) for i in g["hl"] if i in hls]} for g in s["groups"]]
                v["groups"] = [g for g in v["groups"] if g["hls"]]
            else:
                title = {x["id"]: x for x in things if x.get("id")}
                v["groups"] = [{"name": "", "hls": [_hl(h, title) for h in p["highlights"][:6]]}] if p["highlights"] else []
            if not v["groups"]:
                continue
        elif k == "things":
            v["items"] = [by_ref[r] for r in s.get("refs") or [] if r in by_ref]
            if not v["items"]:
                continue
        elif k == "questions":
            done = [x for x in chat if x["state"] == "done"][-5:][::-1]
            if not done:
                continue
            v["asked"] = [{"id": x["id"], "q": x["q"], "n": x.get("n", 0)} for x in done]
        elif k == "feeds":
            if not p["feeds"]:
                continue
            v["feeds"] = p["feeds"]
        elif k == "suggestions":
            if not p["area"]["suggest"]:
                continue
            v["suggestions"] = p["suggestions"]
            v["looking"] = p["looking"]
        out.append(v)
    return out


def _hl(h, things):
    x = things.get(h["book_id"]) or {}
    go = x.get("go") or ""
    return {"id": str(h["id"]), "text": h["text"] or "", "note": h["note"] or "", "title": x.get("title") or "",
            "go": (go + "/hl:" + urllib.parse.quote(str(h["id"]), safe="")) if go else ""}


def extra(c, aid, p):
    """What an area's page has from its agent: the Overview's sections (and a new layout to keep or
    undo), the plan (and a new one), the questions, and what's being worked on."""
    a = _area(c, aid)
    chat = chats(c, aid)
    plan = plan_view(c, _load(a["plan"]), p["items"])
    layout = _load(a["layout"])
    draft = _load(a["layout_draft"])
    return {"plan": plan, "plan_draft": plan_view(c, _load(a["plan_draft"]), p["items"]),
            "sections": sections_view(c, aid, layout["sections"] if layout else DEFAULT, p, plan, chat),
            "layout": layout["sections"] if layout else None,
            "draft": sections_view(c, aid, draft["sections"], p, plan, chat) if draft else None,
            "chat": chat, "sources": [{"ref": x["ref"], "title": x["title"], "kind": x["kind"]} for x in _things(c, aid)],
            "working": {"plan": (aid, "plan") in _working, "layout": (aid, "layout") in _working},
            "failed": {"plan": _errors.get((aid, "plan"), ""), "layout": _errors.get((aid, "layout"), "")}}
