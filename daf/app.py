"""The HTTP API and the web app."""
import asyncio
import hashlib
import json
import logging
import re
import threading
import time
from urllib.parse import quote as _urlq
from datetime import date, datetime, timedelta

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from fastapi.responses import HTMLResponse, RedirectResponse

from . import ai, auth, config, db, digest, ebooks, feedback, goals, gpodder, imports, jump, library, lookup, media, notes, paper_pages, phone, reader, review, sync, today as T, torah, vaultnotes
from .sources import checks, kindle, paper

log = logging.getLogger(__name__)

app = FastAPI(title="Daf", docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def headers(request: Request, call_next):
    """How long a device may keep each file (webcache.py): a fingerprinted script or style (?v=)
    for good; the readers' libraries for an hour, then still while it checks; fonts for a month; the
    page itself and unfingerprinted scripts are asked about each time. Plus the usual headers for a
    site on the open web."""
    resp = await call_next(request)
    path = request.url.path
    if path.endswith((".js", ".mjs", ".css", ".webmanifest")) and request.query_params.get("v") and resp.status_code == 200:
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path.startswith("/vendor/"):
        resp.headers["Cache-Control"] = "public, max-age=3600, stale-while-revalidate=604800"
    elif path.startswith("/fonts/") and path.endswith(".woff2"):
        resp.headers["Cache-Control"] = "public, max-age=2592000, immutable"
    elif path.endswith((".js", ".css", ".webmanifest", ".html")) or path == "/":
        resp.headers["Cache-Control"] = "no-cache"
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    return resp


def _via_tunnel(request):
    """cloudflared runs on this host, so tunnel requests arrive from loopback with Cloudflare's headers."""
    host = request.client.host if request.client else ""
    return host in ("127.0.0.1", "::1") and bool(request.headers.get("cf-connecting-ip"))


def client_ip(request):
    if _via_tunnel(request):
        return request.headers["cf-connecting-ip"]
    return request.client.host if request.client else "?"


def is_https(request):
    return _via_tunnel(request) and (request.headers.get("x-forwarded-proto") == "https"
                                     or "https" in request.headers.get("cf-visitor", ""))


def set_session(r, request):
    r.set_cookie(auth.COOKIE, auth.make_cookie(), max_age=auth.COOKIE_DAYS * 86400, httponly=True,
                 samesite="lax", secure=is_https(request))
    return r


# Failed sign-ins: 5 from one address in 15 minutes locks that address for 15 minutes;
# 20 from anywhere in an hour pauses all sign-ins for 15 minutes. Signal says so (at most every 6 h).
_fails = {}
_paused_until = 0.0
_last_alert = 0.0


def _alert(text):
    global _last_alert
    import subprocess
    if time.time() - _last_alert < 6 * 3600:
        return
    _last_alert = time.time()
    try:
        subprocess.Popen(["/srv/obsidian/Synergathan/.claude/scripts/notify.sh", "Daf", text],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        log.warning("couldn't send the sign-in alert")


def _throttled(ip):
    now = time.time()
    recent = [t for t in _fails.get(ip, []) if now - t < 900]
    _fails[ip] = recent
    return now < _paused_until or len(recent) >= 5


def _failed(ip):
    global _paused_until
    now = time.time()
    _fails.setdefault(ip, []).append(now)
    everyone = sum(1 for ts in _fails.values() for t in ts if now - t < 3600)
    if len([t for t in _fails[ip] if now - t < 900]) == 5:
        log.warning("sign-in locked for %s", ip)
        _alert(f"Five wrong sign-ins to Daf from {ip}. That address waits 15 minutes.")
    if everyone >= 20 and now >= _paused_until:
        _paused_until = now + 900
        log.warning("all sign-ins paused")
        _alert(f"{everyone} wrong sign-ins to Daf in the last hour. Sign-in is paused for 15 minutes.")


def conn():
    c = db.connect()
    try:
        yield c
        c.commit()
    finally:
        c.close()


async def json_body(request: Request):
    """The request's JSON ({} when it isn't), read here so the route itself can be a plain def,
    which FastAPI runs on a worker thread: a route waiting on Karakeep, GitHub, Komga or the
    database's lock then holds up only itself, not every other request."""
    try:
        return await request.json()
    except ValueError:
        return {}


def user(request: Request):
    if not auth.check_cookie(request.cookies.get(auth.COOKIE)):
        raise HTTPException(401, "Sign in first")


def device(request: Request, c=Depends(conn)):
    h = request.headers.get("authorization", "")
    name = auth.check_device(c, h[7:].strip() if h.lower().startswith("bearer ") else None)
    if not name:
        raise HTTPException(401, "Unknown device")
    return name


OP_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


@app.middleware("http")
async def once_only(request: Request, call_next):
    """A write sent with X-Daf-Op (the pages' offline queue gives each one an id) is done once: sent
    again, after an answer that never arrived, it gets the first answer back instead of a second
    highlight, beat or review."""
    op = request.headers.get("x-daf-op")
    if not op or request.method not in ("POST", "PUT", "PATCH", "DELETE") or not request.url.path.startswith("/api/") or not OP_ID.match(op):
        return await call_next(request)
    if not (request.cookies.get(auth.COOKIE) or request.headers.get("authorization")):
        return await call_next(request)          # signed out: the route says so; nothing is replayed
    # The op is claimed (status 0) before the write runs, so a repeat that arrives while the first is
    # still running (the queue gives up after six seconds and sends again) waits for its answer
    # instead of doing the write twice. The database work runs off the event loop.
    r = await run_in_threadpool(_op_claim, op)
    for _ in range(40):
        if r != "busy":
            break
        await asyncio.sleep(0.5)
        r = await run_in_threadpool(_op_claim, op, False)
    if r == "busy":
        return JSONResponse({"detail": "Still working on it"}, status_code=503, headers={"Retry-After": "5"})
    if r:
        return Response(content=r["body"] or b"", status_code=r["status"], media_type=r["ctype"], headers={"X-Daf-Replay": "1"})
    try:
        resp = await call_next(request)
    except Exception:
        await run_in_threadpool(_op_release, op)
        raise
    if resp.status_code >= 500 or resp.status_code == 401:
        await run_in_threadpool(_op_release, op)    # it can run again when the queue retries
        return resp
    body = b"".join([chunk async for chunk in resp.body_iterator])
    await run_in_threadpool(_op_store, op, resp.status_code, resp.headers.get("content-type"), body)
    return Response(content=body, status_code=resp.status_code, headers={k: v for k, v in resp.headers.items() if k.lower() != "content-length"})


def _op_claim(op, claim=True):
    """The stored answer for an op, "busy" while another request is doing it, or None once this
    request has claimed it. A claim older than five minutes (a crash mid-write) is taken over."""
    c = db.connect()
    try:
        # The claim is one statement, so of several requests with the same op exactly one gets it.
        now = int(time.time())
        if c.execute("INSERT OR IGNORE INTO ops (id, at, status, ctype, body) VALUES (?, ?, 0, NULL, NULL)", (op, now)).rowcount:
            c.commit()
            return None
        if claim and c.execute("UPDATE ops SET at = ? WHERE id = ? AND status = 0 AND at < ?", (now, op, now - 300)).rowcount:
            c.commit()
            return None
        c.commit()
        r = c.execute("SELECT status, ctype, body FROM ops WHERE id = ?", (op,)).fetchone()
        return r if r and r["status"] else "busy"
    finally:
        c.close()


def _op_release(op):
    c = db.connect()
    try:
        c.execute("DELETE FROM ops WHERE id = ? AND status = 0", (op,))
        c.commit()
    finally:
        c.close()


def _op_store(op, status, ctype, body):
    c = db.connect()
    try:
        c.execute("UPDATE ops SET status = ?, ctype = ?, body = ?, at = ? WHERE id = ?", (status, ctype, body[:500_000], int(time.time()), op))
        c.commit()
    finally:
        c.close()


@app.get("/api/doc-tags", dependencies=[Depends(user)])
def get_doc_tags(c=Depends(conn)):
    """Preferences → Library tags: every document tag with how many use it, and the tidy-up."""
    from . import tagging
    return {"tags": [{"name": t, "n": k} for t, k in tagging.counts(c).items()], "tidy": tagging.proposal(c),
            "job": media.job_status(c, "tagtidy", "all")}


@app.post("/api/doc-tags/rename", dependencies=[Depends(user)])
def post_doc_tag_rename(b=Depends(json_body), c=Depends(conn)):
    """{from, to}: every document's tag renamed (merged, when to is in use already); to "" removes it."""
    from . import tagging
    old, new = str(b.get("from") or ""), str(b.get("to") or "")
    if not old:
        raise HTTPException(400, "Which tag?")
    return {"changed": tagging.rename(c, old, new)}


@app.post("/api/doc-tags/tidy", dependencies=[Depends(user)])
def post_doc_tag_tidy(c=Depends(conn)):
    """The model proposes a tidy-up of the whole list (a job: it takes a minute or two)."""
    media.queue(c, "tagtidy", "all")
    return {"job": media.job_status(c, "tagtidy", "all")}


@app.post("/api/doc-tags/apply", dependencies=[Depends(user)])
def post_doc_tag_apply(b=Depends(json_body), c=Depends(conn)):
    """{ids: [...]}: the proposed changes he ticked."""
    from . import tagging
    ids = [int(x) for x in b.get("ids") or [] if isinstance(x, int) or str(x).isdigit()]
    return {"changed": tagging.apply(c, ids), "tidy": tagging.proposal(c)}


def user_or_device(request: Request, c=Depends(conn)):
    """Signed in, or a device's token (the desk shows the Library's pictures too)."""
    if not auth.check_cookie(request.cookies.get(auth.COOKIE)):
        device(request, c)


@app.get("/api/thumb/{name}", dependencies=[Depends(user_or_device)])
def get_thumb(name: str):
    """A saved page's picture, kept on morten (pages.keep_thumb). The name is its content's hash."""
    from . import pages
    if not re.match(r"^[0-9a-f]{16}\.jpg$", name) or not (pages.THUMBS / name).is_file():
        raise HTTPException(404, "No such picture")
    return FileResponse(pages.THUMBS / name, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=31536000, immutable"})


@app.get("/api/health")
def health():
    from . import webcache
    return {"ok": True, "version": webcache.version()}


_app_files = {"key": None, "out": None}


@app.get("/api/app-files")
def app_files():
    """The web app's files (web/) with their hashes, for the apps' own copy: they start and show
    Daf with no network at all. No sign-in: the files are public anyway. Hashed again only when a
    file's time or size changes."""
    root = config.WEB_DIR
    paths = sorted(p for p in root.rglob("*") if p.is_file() and not any(x.startswith(".") for x in p.relative_to(root).parts))
    key = tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in paths)
    if _app_files["key"] != key:
        files = [{"path": "/" + p.relative_to(root).as_posix(), "sha1": hashlib.sha1(p.read_bytes()).hexdigest(), "size": p.stat().st_size}
                 for p in paths]
        # /sw.js is served with its version and file list filled in (webcache.py): the apps fetch it
        # by its path, so the list names what that path serves, and their copy matches the live site.
        from . import webcache
        sw = webcache.sw_js().encode()
        files = [dict(f, sha1=hashlib.sha1(sw).hexdigest(), size=len(sw)) if f["path"] == "/sw.js" else f for f in files]
        version = hashlib.sha1("".join(f["path"] + f["sha1"] for f in files).encode()).hexdigest()[:16]
        _app_files.update(key=key, out={"version": version, "files": files})
    return _app_files["out"]


@app.get("/api/me")
def me(request: Request):
    signed = auth.check_cookie(request.cookies.get(auth.COOKIE))
    return {"signed_in": signed, "has_password": auth.has_password(), **({"user": auth.username()} if signed else {})}


@app.post("/api/login")
async def login(request: Request):
    ip = client_ip(request)
    if _throttled(ip):
        raise HTTPException(429, "Too many tries. Wait 15 minutes and try again.")
    body = await _body(request)
    if not auth.check_login(str(body.get("user", "")), str(body.get("password", ""))):
        _failed(ip)
        raise HTTPException(401, "That username or password isn't right")
    _fails.pop(ip, None)
    return set_session(JSONResponse({"ok": True}), request)


@app.post("/api/logout")
def logout():
    r = JSONResponse({"ok": True})
    r.delete_cookie(auth.COOKIE)
    return r


@app.post("/api/account", dependencies=[Depends(user)])
async def change_account(request: Request):
    """Change the username and/or password. Needs the current password; a new password signs
    out every other browser (this one gets a fresh cookie)."""
    ip = client_ip(request)
    if _throttled(ip):
        raise HTTPException(429, "Too many tries. Wait 15 minutes and try again.")
    b = await _body(request)
    if not auth.check_password(str(b.get("current", ""))):
        _failed(ip)
        raise HTTPException(403, "Your current password isn't right")   # not 401: that means "signed out" to the app
    new_user = str(b.get("user") or "").strip().lower()
    new_pw = str(b.get("password") or "")
    if new_user and not re.fullmatch(r"[a-z0-9._@-]{2,40}", new_user):
        raise HTTPException(400, "Usernames are 2 to 40 letters, numbers, dots, dashes or @")
    if new_pw and len(new_pw) < 10:
        raise HTTPException(400, "Make the new password at least 10 characters")
    if new_pw:
        auth.set_password(new_pw, user=new_user or None, rotate=True)
    elif new_user:
        auth.set_user(new_user)
    return set_session(JSONResponse({"ok": True, "user": auth.username(), "signed_out_others": bool(new_pw)}), request)


@app.post("/api/account/signout-others", dependencies=[Depends(user)])
def signout_others(request: Request):
    auth.sign_out_everywhere()
    return set_session(JSONResponse({"ok": True}), request)


def _freshness(c):
    rows = c.execute("SELECT name, ok, checked, last_data, detail FROM source_status").fetchall()
    out = {r["name"]: {"ok": bool(r["ok"]), "checked": r["checked"], "last": r["last_data"], "detail": r["detail"]} for r in rows}
    out["kindle"] = {"last": kindle.newest_by_origin(c)}
    return out


@app.get("/api/today", dependencies=[Depends(user)])
def get_today(d: str | None = None, c=Depends(conn)):
    s = config.load_settings()
    day = date.fromisoformat(d) if d else T.today(s)
    out = T.day_summary(c, day, s)
    out["today"] = T.today(s).isoformat()
    out["week"] = T.week(c, s)
    out["year30"] = T.grid(c, config.YEAR30_START, s)
    out["shabbat"] = T.is_shabbat_window(s)
    out["settings"] = s
    out["labels"] = config.SOURCE_LABELS
    out["fresh"] = _freshness(c)
    r = review.day_items(c, s)
    out["review"] = {"done": r["done"], "total": r["total"], "first": r["items"][0] if r["items"] else None, "streak": r["streak"],
                     "books": list(dict.fromkeys(i["title"] for i in r["items"] if i.get("title")))[:3]}
    out["nightstand"] = [_book_card(b) for b in library.nightstand(c, s)]
    out["nightstand_suggested"] = [] if out["nightstand"] else [_book_card(b) for b in library.suggest_nightstand(c)]
    out["offstand"] = _offstand(c, s)
    from . import stats
    out["on_this_day"] = jump.add(c, stats.on_this_day(c, s, limit=2))
    from . import cards as _cards
    out["cards_due"] = len(_cards.due(c, s))
    try:
        from . import hardcover
        out["hc_finished"] = hardcover.finished_on_kindle(c, s) if c.execute("SELECT 1 FROM kv WHERE k = 'hardcover'").fetchone() else []
    except Exception:  # noqa: BLE001 - Hardcover down must not break Today
        out["hc_finished"] = []
    st = stats.streaks(c, s)
    out["streak"] = {"goal": st["goal"], "any": st["any"]}
    out["goals"] = goals.summary(c, s, day if day <= T.today(s) else None)
    out["main"] = goals.main_of(out["goals"])
    recent = (T.today(s) - timedelta(days=3)).isoformat()
    out["milestones_new"] = [m for m in goals.milestones(c, s) if m["reached"] and m["reached"] >= recent]
    return out


def _book_card(b):
    b = dict(b)
    return {k: b.get(k) for k in ("id", "title", "author", "progress", "progress_note", "last_read", "audio_pct",
                                  "audio_note", "vault_path", "status", "kind", "url")} | {"has_cover": bool(b.get("calibre_path"))}


def _offstand(c, s):
    """A book read on the Kindle in the last 3 days that isn't on the nightstand."""
    ids = set(s.get("nightstand") or [])
    if not ids:
        return None
    import time as _t
    for r in c.execute("SELECT * FROM books WHERE kind = 'book' AND private = 0 AND last_read > ? ORDER BY last_read DESC",
                       (int(_t.time()) - 3 * 86400,)):
        if r["id"] not in ids and r["id"] not in (s.get("not_nightstand") or []):
            return _book_card(r)
    return None


@app.get("/api/year/{which}", dependencies=[Depends(user)])
def get_year(which: int, c=Depends(conn)):
    if which not in (29, 30):
        raise HTTPException(404, "Year 29 or 30")
    s = config.load_settings()
    return T.grid(c, config.YEAR30_START if which == 30 else config.YEAR29_START, s)


@app.post("/api/paper", dependencies=[Depends(user)])
def post_paper(body=Depends(json_body), c=Depends(conn)):
    """Paper minutes: a line in the vault's reading log, read back at once. Only the paper log is
    read again here (not a whole sync, which waits for the sync thread and reaches every service),
    so the answer comes quickly and a retry from the offline queue can't add the line twice."""
    try:
        minutes = int(body.get("minutes", 0))
    except (TypeError, ValueError):
        minutes = 0
    if not 1 <= minutes <= 720:
        raise HTTPException(400, "Minutes should be between 1 and 720")
    try:
        pages = int(body.get("pages") or 0)
    except (TypeError, ValueError):
        pages = 0
    if not 0 <= pages <= 2000:
        raise HTTPException(400, "Pages should be between 0 and 2000")
    s = config.load_settings()
    if body.get("shabbat"):
        day = T.last_shabbat(s)
    elif body.get("date"):
        try:
            day = date.fromisoformat(str(body["date"]))
        except ValueError:
            raise HTTPException(400, "date: YYYY-MM-DD")
    else:
        day = T.today(s)
    path = paper.append(day, minutes, str(body.get("note") or ""), pages=pages)
    try:
        paper.import_entries(c, T.tz_of(s))
    except Exception as e:  # noqa: BLE001 - the line is in the vault; the next sync reads it
        log.warning("paper log after append: %s", e)
    return {"ok": True, "date": day.isoformat(), "note": str(path.relative_to(config.VAULT))}


@app.get("/api/recovery", dependencies=[Depends(user)])
def get_recovery(c=Depends(conn)):
    """The Recovery page: the Big Book by its chapters, the Step 10 and 11 readings, prayers, the other A.A. books."""
    from . import recovery
    return recovery.page(c, config.load_settings())


@app.get("/api/goals", dependencies=[Depends(user)])
def get_goals(c=Depends(conn)):
    s = config.load_settings()
    return _goals_out(c, s)


def _goals_out(c, s):
    t = T.today(s)
    every = goals.all_goals(s)
    cache = {}
    return {"today": t.isoformat(), "goals": [goals.progress(c, s, g, t, cache) | {"history": g["history"]} for g in every],
            "kinds": {k: {"label": v["label"], "unit": v["unit"], "periods": [{"id": p, "words": goals.period_words(p, t)[0]} for p in v["periods"]],
                          "default": v["default"], "range": v["range"]} for k, v in goals.KINDS.items()},
            "presets": goals.PRESETS, "pace": goals.pace(c, s), "milestones": goals.milestones(c, s),
            "minutes_day": goals.minutes_day(s, t)}


@app.put("/api/goals", dependencies=[Depends(user)])
async def put_goals(request: Request, c=Depends(conn)):
    body = await _body(request)
    s = config.load_settings()
    incoming = body.get("goals")
    if body.get("preset"):
        p = goals.PRESETS.get(body["preset"])
        if not p:
            raise HTTPException(400, "No such preset")
        first = next(iter(p["goals"]))
        incoming = [{"id": gid, **v, "main": gid == first} for gid, v in p["goals"].items()]
    if not isinstance(incoming, list):
        raise HTTPException(400, "goals: a list")
    _, saved = goals.save(s, incoming, T.today(s))
    s["goals"] = saved
    config.save_settings(s)
    return _goals_out(c, config.load_settings())


@app.get("/api/sources", dependencies=[Depends(user)])
def get_sources(c=Depends(conn)):
    return {"checks": checks.run_all(c)}


@app.post("/api/sync", dependencies=[Depends(user)])
def post_sync():
    return sync.run()


@app.get("/api/settings", dependencies=[Depends(user)])
def get_settings():
    return config.load_settings()


@app.put("/api/settings", dependencies=[Depends(user)])
async def put_settings(request: Request):
    body = await request.json()
    s = config.load_settings()
    if isinstance(body.get("home_tz"), str):
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(body["home_tz"])
            s["home_tz"] = body["home_tz"]
        except Exception:  # noqa: BLE001
            raise HTTPException(400, "Unknown time zone")
    for k, v in (body.get("count") or {}).items():
        if k in s["count"] and k != "podcast":
            s["count"][k] = bool(v)
    if isinstance(body.get("review_size"), int) and 1 <= body["review_size"] <= 20:
        s["review_size"] = body["review_size"]
    if isinstance(body.get("tts_voice"), str) and len(body["tts_voice"]) < 40:
        s["tts_voice"] = body["tts_voice"]
    if isinstance(body.get("tts_speed"), (int, float)) and 0.5 <= body["tts_speed"] <= 2:
        s["tts_speed"] = float(body["tts_speed"])
    if isinstance(body.get("feed_expire_days"), int) and 3 <= body["feed_expire_days"] <= 3650:
        s["feed_expire_days"] = body["feed_expire_days"]
    for k in ("hc_progress", "hc_autostart"):
        if isinstance(body.get(k), bool):
            s[k] = body[k]
    if isinstance(body.get("cards_per_day"), int) and 0 <= body["cards_per_day"] <= 30:
        s["cards_per_day"] = body["cards_per_day"]
    if isinstance(body.get("appearance"), dict):
        s["appearance"] = config.clean_appearance(body["appearance"])
    config.save_settings(s)
    return s


# ---- Preferences: AI, the morning email, keys, feedback, imports ----------------

@app.get("/api/ai", dependencies=[Depends(user)])
def get_ai():
    return ai.public()


@app.put("/api/ai", dependencies=[Depends(user)])
async def put_ai(request: Request):
    """{auto_summary?, model?, prompts?: {name: text}, questions?, book_questions?}: a prompt left empty
    or the same as Daf's own goes back to Daf's own."""
    body = await _body(request)
    s = config.load_settings()
    cur = ai.settings(s)
    for k in ("auto_summary", "auto_tags", "model", "questions", "book_questions"):
        if k in body:
            cur[k] = body[k]
    if isinstance(body.get("prompts"), dict):
        cur["prompts"] = {**cur["prompts"], **body["prompts"]}
        cur["prompts"] = {k: v for k, v in cur["prompts"].items() if isinstance(v, str) and v.strip()}
    s["ai"] = ai.clean(cur)
    config.save_settings(s)
    return ai.public(s)


@app.get("/api/digest", dependencies=[Depends(user)])
def get_digest(c=Depends(conn)):
    s = config.load_settings()
    d = digest.build(c, s)
    return {"digest": digest.clean(s.get("digest")), "configured": digest.configured(), "last": digest.status(c),
            "now": {"new": len(d["new"]), "feed": d["feed"]["count"]}}


@app.put("/api/digest", dependencies=[Depends(user)])
async def put_digest(request: Request):
    body = await _body(request)
    s = config.load_settings()
    s["digest"] = digest.clean({**digest.clean(s.get("digest")), **{k: v for k, v in body.items() if k in ("on", "hour", "feed", "from")}})
    config.save_settings(s)
    return {"digest": s["digest"]}


@app.get("/api/digest/preview", dependencies=[Depends(user)])
def get_digest_preview(c=Depends(conn)):
    """The email as it would go now, to look at."""
    s = config.load_settings()
    subject, body, _ = digest.render(digest.build(c, s), s)
    import html as H
    return HTMLResponse(f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'><title>{H.escape(subject)}</title>"
                        f"<body style='margin:0'>{body}</body>")


@app.post("/api/digest/send", dependencies=[Depends(user)])
def post_digest_send(c=Depends(conn)):
    try:
        return digest.send(c, config.load_settings(), force=True)
    except Exception as e:  # noqa: BLE001 - the Bridge said no
        raise HTTPException(502, f"The email didn't go: {e}")


KEY_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,29}$")


TIP_ID = re.compile(r"^[a-z0-9-]{1,48}$")


def _tips(s):
    """Preferences → Tips: which feature tips you've seen, the newest What's new item you've read,
    and whether tips show at all. Kept on the server, so a tip seen on the Mac doesn't come back on
    the phone."""
    t = s.get("tips") if isinstance(s.get("tips"), dict) else {}
    seen = t.get("seen") if isinstance(t.get("seen"), dict) else {}
    return {"off": t.get("off") is True,
            "seen": {k: v for k, v in seen.items() if TIP_ID.match(str(k)) and isinstance(v, int)},
            "news": t["news"] if isinstance(t.get("news"), str) and TIP_ID.match(t["news"]) else ""}


@app.get("/api/tips", dependencies=[Depends(user)])
def get_tips():
    return _tips(config.load_settings())


@app.post("/api/tips", dependencies=[Depends(user)])
def post_tips(body=Depends(json_body)):
    """{seen: id} a tip done with, {news: id} What's new read up to there, {off: bool}, {reset: true}."""
    s = config.load_settings()
    t = _tips(s)
    if isinstance(body.get("seen"), str) and TIP_ID.match(body["seen"]):
        t["seen"][body["seen"]] = int(time.time())
    if isinstance(body.get("news"), str) and TIP_ID.match(body["news"]):
        t["news"] = body["news"]
    if isinstance(body.get("off"), bool):
        t["off"] = body["off"]
    if body.get("reset") is True:
        t["seen"] = {}
    s["tips"] = t
    config.save_settings(s)
    return t


@app.put("/api/keys", dependencies=[Depends(user)])
async def put_keys(request: Request):
    """{keys: {scope: {action: key}}}: the shortcuts changed from Daf's (web/keys.js knows the rest).
    A key is what the browser calls it (e.key): "d", "D" for Shift D, "ArrowLeft"; "" turns one off."""
    body = await _body(request)
    keys = body.get("keys")
    if not isinstance(keys, dict):
        raise HTTPException(400, "keys: {scope: {action: key}}")
    out = {}
    for scope, acts in list(keys.items())[:12]:
        if KEY_NAME.match(str(scope)) and isinstance(acts, dict):
            out[scope] = {a: k for a, k in list(acts.items())[:60] if KEY_NAME.match(str(a)) and isinstance(k, str) and len(k) <= 16}
    s = config.load_settings()
    s["keys"] = {k: v for k, v in out.items() if v}
    config.save_settings(s)
    return {"keys": s["keys"]}


@app.post("/api/feedback", dependencies=[Depends(user)])
def post_feedback(body=Depends(json_body), c=Depends(conn)):
    """{text, ctx: {route, title, device, app, size, theme, online, errors}}. GitHub can take a while:
    a plain def, so it waits on a worker thread."""
    try:
        return feedback.send(c, body.get("text"), body.get("ctx"))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/feedback", dependencies=[Depends(user)])
def get_feedback(c=Depends(conn)):
    return {"feedback": feedback.recent(c)}


@app.post("/api/import", dependencies=[Depends(user)])
async def post_import(request: Request, name: str = "", c=Depends(conn)):
    """The export file as the body (?name= its file name). Answers what's in it; nothing happens
    until /start."""
    data = await request.body()
    try:
        return await run_in_threadpool(imports.create, c, name, data)     # a big export takes a moment to read
    except imports.NotAnExport as e:
        raise HTTPException(400, str(e))


@app.get("/api/imports", dependencies=[Depends(user)])
def get_imports(c=Depends(conn)):
    return {"imports": imports.listing(c), "labels": imports.LABELS}


@app.get("/api/import/{iid}", dependencies=[Depends(user)])
def get_import(iid: str, c=Depends(conn)):
    r = imports.get(c, iid)
    if not r:
        raise HTTPException(404, "Not found")
    return r


@app.post("/api/import/{iid}/start", dependencies=[Depends(user)])
async def post_import_start(iid: str, request: Request, c=Depends(conn)):
    """{archived: bring the read ones too, folders: feeds into their folders}."""
    try:
        imports.start(c, iid, await _body(request))
    except KeyError:
        raise HTTPException(404, "Not found")
    return imports.get(c, iid)


@app.post("/api/import/{iid}/stop", dependencies=[Depends(user)])
def post_import_stop(iid: str, c=Depends(conn)):
    imports.stop(c, iid)
    return imports.get(c, iid)


@app.delete("/api/import/{iid}", dependencies=[Depends(user)])
def delete_import(iid: str, c=Depends(conn)):
    c.execute("DELETE FROM imports WHERE id = ? AND state != 'running'", (iid,))
    return {"ok": True}


# ---- review, highlights, books, notes ------------------------------------------

@app.get("/api/review", dependencies=[Depends(user)])
def get_review(day: str = "", c=Depends(conn)):
    """Today's review, or (day=YYYY-MM-DD, up to a week ahead) a coming day's, built now so the apps
    can keep it for reading offline; that day then shows the same highlights."""
    s = config.load_settings()
    d = None
    if day:
        try:
            d = date.fromisoformat(day)
        except ValueError:
            raise HTTPException(400, "day: YYYY-MM-DD")
        t = T.today(s)
        if not (t - timedelta(days=7) <= d <= t + timedelta(days=7)):
            raise HTTPException(400, "Within a week of today")
    out = review.day_items(c, s, d)
    jump.add(c, out["items"])
    return out


@app.get("/api/review/themed", dependencies=[Depends(user)])
def get_review_themed(tag: str = "", fav: int = 0, source: str = "", color: str = "", q: str = "", n: int = 10, book: str = "", c=Depends(conn)):
    """A review of some highlights by theme (a tag, favorites, a color), apart from the daily five,
    like Readwise's themed reviews. Long enough to be worth reviewing, never private, shuffled."""
    import random
    where, args = _hl_filter(q, book, 0, source, color, tag, fav)
    rows = [r for r in _hl_rows(c, where + " AND length(h.text) >= 20 AND COALESCE(s.status, '') != 'never'", args)]
    random.shuffle(rows)
    items = [{"id": r["id"], "text": r["text"], "note": r["note"], "user_note": r["user_note"], "book_id": r["book_id"],
              "title": r["book_title"], "author": r["book_author"], "kind": r["kind"], "source": r["source"], "chapter": r["chapter"],
              "page": r["page"], "created": r["created"], "reviews": 0, "action": None, "color": r["color"], "pos": r["pos"],
              "tags": r["tags"], "fav": bool(r["fav"]), "open": r["open"]} for r in rows[:max(1, min(30, n))]]
    bt = c.execute("SELECT title FROM books WHERE id = ? AND private = 0", (book,)).fetchone() if book else None
    return {"items": items, "total": len(rows),
            "theme": ("#" + tag) if tag else "Favorites" if fav else color.capitalize() if color else bt[0].split(":")[0] if bt else "These highlights"}


@app.post("/api/review/{hl_id}", dependencies=[Depends(user)])
async def post_review(hl_id: str, request: Request, c=Depends(conn)):
    body = await request.json()
    action = body.get("action")
    if action not in ("keep", "less", "note", "later", "never", "back"):
        raise HTTPException(400, "Unknown action")
    s = config.load_settings()
    out = review.act(c, s, hl_id, action, note=body.get("note") if action == "note" else None, day=_day_of(body.get("at"), s))
    if action == "note":
        b = c.execute("SELECT book_id FROM highlights WHERE id = ?", (hl_id,)).fetchone()
        out["vault"] = vaultnotes.write_for(c, s, b[0]) if b and b[0] else "no book"
    return out


def _day_of(at, s):
    """The local day of `at` (epoch seconds) when it's within the last week: what was done offline
    counts on the day it was done."""
    try:
        at = int(at)
    except (TypeError, ValueError):
        return None
    if not (time.time() - 7 * 86400 <= at <= time.time() + 60):
        return None
    return datetime.fromtimestamp(at, T.tz_of(s)).date()


def _hl_rows(c, where="", args=(), order="COALESCE(h.created, 0) DESC"):
    return jump.add(c, [dict(r) for r in c.execute(
        "SELECT h.id, h.book_id, h.source, h.text, h.note, h.chapter, h.page, h.created, h.pos, h.color, s.user_note, s.status AS r_status, "
        "s.due, s.tags, s.fav, (SELECT COUNT(*) FROM cards c WHERE c.hl_id = h.id) AS cards, b.title AS book_title, b.author AS book_author, b.private, b.kind, b.vault_path, b.calibre_path "
        "FROM highlights h LEFT JOIN books b ON b.id = h.book_id LEFT JOIN review_state s ON s.hl_id = h.id "
        "WHERE h.deleted = 0 " + where + " ORDER BY " + order, args)])


HL_SOURCES = {"kindle": "h.source = 'kindle'", "daf": "h.source IN ('epub', 'daf')", "articles": "b.kind = 'article'",
              "audio": "h.source IN ('audiobookshelf', 'clip')", "paper": "h.source = 'paper'",
              "readwise": "h.source = 'readwise'"}


def _hl_filter(q="", book="", private=0, source="", color="", tag="", fav=0):
    where, args = "", []
    if not private:
        where += " AND COALESCE(b.private, 0) = 0"
    if book:
        where += " AND h.book_id = ?"
        args.append(book)
    if source in HL_SOURCES:
        where += " AND " + HL_SOURCES[source]
    if color in reader.COLORS:
        where += " AND COALESCE(h.color, 'yellow') = ?"
        args.append(color)
    if tag:
        where += " AND s.tags LIKE ?"
        args.append('%"' + tag.replace('"', "") + '"%')
    if fav:
        where += " AND s.fav = 1"
    if q:
        where += " AND (h.text LIKE ? OR h.note LIKE ? OR s.user_note LIKE ? OR b.title LIKE ? OR b.author LIKE ? OR s.tags LIKE ?)"
        args += [f"%{q}%"] * 6
    return where, args


@app.get("/api/highlights", dependencies=[Depends(user)])
def get_highlights(q: str = "", book: str = "", private: int = 0, source: str = "", color: str = "", tag: str = "", fav: int = 0,
                   sort: str = "recent", c=Depends(conn)):
    where, args = _hl_filter(q, book, private, source, color, tag, fav)
    rows = _hl_rows(c, where, args, "COALESCE(h.created, 0) ASC" if sort == "oldest" else "COALESCE(h.created, 0) DESC")
    groups = {}
    for r in rows:
        g = groups.setdefault(r["book_id"], {"book_id": r["book_id"], "title": r["book_title"], "author": r["book_author"],
                                             "vault_path": r["vault_path"], "kind": r["kind"], "has_cover": bool(r["calibre_path"]),
                                             "items": [], "latest": 0, "notes": 0})
        g["items"].append(r)
        g["latest"] = max(g["latest"], r["created"] or 0)
        g["notes"] += 1 if (r["user_note"] or r["note"]) else 0
    gl = list(groups.values())
    if sort == "book":
        gl.sort(key=lambda g: (g["title"] or "").lower())
        for g in gl:
            g["items"].sort(key=lambda r: r["order"])
    elif sort == "oldest":
        gl.sort(key=lambda g: min(r["created"] or 0 for r in g["items"]))
    else:
        gl.sort(key=lambda g: -g["latest"])
    return {"count": len(rows), "books": len(gl), "notes": sum(g["notes"] for g in gl), "groups": gl,
            "tags": review.all_tags(c), "sources": [k for k in HL_SOURCES]}


@app.get("/api/highlights/tags", dependencies=[Depends(user)])
def get_highlight_tags(c=Depends(conn)):
    return {"tags": review.all_tags(c)}


@app.get("/api/cards/export", dependencies=[Depends(user)])
def export_cards(c=Depends(conn)):
    """Every flashcard as an Anki import file: tab-separated, cloze cards as {{c1::…}},
    question-and-answer cards as front and back, the book in a third column and as a tag."""
    import io
    rows = c.execute("SELECT c.kind, c.front, c.back, b.title, b.private FROM cards c JOIN highlights h ON h.id = c.hl_id "
                     "LEFT JOIN books b ON b.id = h.book_id WHERE h.deleted = 0 ORDER BY c.created").fetchall()
    buf = io.StringIO()
    buf.write("#separator:tab\n#html:false\n#notetype column:1\n#tags column:5\n")
    clean = lambda x: " ".join(str(x or "").split())
    for kind, front, back, title, private in rows:
        source = "" if private else (title or "").split(":")[0]
        tag = "daf " + ("daf::" + re.sub(r"[^\w-]+", "_", source)[:60] if source else "")
        if kind == "cloze":
            n = [0]
            def cz(m):
                n[0] += 1
                return "{{c%d::%s}}" % (n[0], m.group(1))
            buf.write("\t".join(["Cloze", clean(re.sub(r"\{\{(.+?)\}\}", cz, front)), "", clean(source), tag.strip()]) + "\n")
        else:
            buf.write("\t".join(["Basic", clean(front), clean(back), clean(source), tag.strip()]) + "\n")
    name = "daf-flashcards-" + datetime.now().strftime("%Y-%m-%d") + ".txt"
    return Response(buf.getvalue(), media_type="text/plain; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/highlights/export", dependencies=[Depends(user)])
def export_highlights(fmt: str = "md", q: str = "", book: str = "", private: int = 0, source: str = "", color: str = "", tag: str = "",
                      fav: int = 0, c=Depends(conn)):
    """The filtered highlights as Markdown (grouped by book, in reading order), CSV or JSON."""
    import csv
    import io
    import json as _json
    where, args = _hl_filter(q, book, private, source, color, tag, fav)
    rows = _hl_rows(c, where, args)
    stamp = datetime.now().strftime("%Y-%m-%d")
    name = "daf-highlights-" + stamp
    if fmt == "json":
        keep = ("id", "book_title", "book_author", "text", "note", "user_note", "chapter", "page", "source", "color", "tags", "created")
        body = _json.dumps([{k: r.get(k) for k in keep} for r in rows], ensure_ascii=False, indent=1)
        media_type, ext = "application/json", "json"
    elif fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Highlight", "Title", "Author", "Note", "Chapter", "Page", "Source", "Color", "Tags", "Date"])
        for r in rows:
            w.writerow([r["text"], r["book_title"], r["book_author"], "\n".join(x for x in (r["note"], r["user_note"]) if x), r["chapter"] or "",
                        r["page"] or "", r["source"], r["color"] or "yellow", " ".join(r["tags"]),
                        datetime.fromtimestamp(r["created"]).strftime("%Y-%m-%d") if r["created"] else ""])
        body, media_type, ext = buf.getvalue(), "text/csv", "csv"
    else:
        by = {}
        for r in rows:
            by.setdefault(r["book_id"], []).append(r)
        out = []
        for _, items in sorted(by.items(), key=lambda kv: (kv[1][0]["book_title"] or "").lower()):
            items.sort(key=lambda r: r["order"])
            h = items[0]
            out += [f"## {h['book_title'] or 'Untitled'}" + (f" — {h['book_author']}" if h["book_author"] else ""), ""]
            chapter = None
            for r in items:
                if r["chapter"] and r["chapter"] != chapter:
                    chapter = r["chapter"]
                    out += [f"### {chapter}", ""]
                out += ["\n".join("> " + line for line in (r["text"] or "").strip().splitlines())]
                meta = [f"p. {r['page']}" if r["page"] else "", " ".join("#" + t for t in r["tags"])]
                if any(meta):
                    out += ["", " · ".join(m for m in meta if m)]
                for n in (r["note"], r["user_note"]):
                    if n:
                        out += ["", "**Note:** " + n.strip()]
                out += [""]
        body, media_type, ext = "\n".join(out), "text/markdown", "md"
        if book and rows:
            name = re.sub(r"[^\w\- ]+", "", rows[0]["book_title"] or "highlights")[:60].strip() + " highlights"
    return Response(body, media_type=media_type + "; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename=\"daf-highlights.{ext}\"; filename*=UTF-8''{_urlq(name + '.' + ext)}"})


@app.put("/api/highlights/{hl_id}/tags", dependencies=[Depends(user)])
async def put_tags(hl_id: str, request: Request, c=Depends(conn)):
    b = await _body(request)
    tags = b.get("tags")
    if not isinstance(tags, list):
        raise HTTPException(400, "tags: a list")
    tags = review.set_tags(c, hl_id, tags)
    h = c.execute("SELECT book_id, source FROM highlights WHERE id = ?", (hl_id,)).fetchone()
    if h and h[0]:
        s = config.load_settings()
        try:
            vaultnotes.write_for(c, s, h[0])
        except Exception as e:  # noqa: BLE001
            log.warning("vault note after tags: %s", e)
    return {"tags": tags, "all": review.all_tags(c)}


@app.put("/api/highlights/{hl_id}/fav", dependencies=[Depends(user)])
async def put_fav(hl_id: str, request: Request, c=Depends(conn)):
    b = await _body(request)
    review.set_fav(c, hl_id, bool(b.get("fav")))
    return {"ok": True}


@app.put("/api/highlights/{hl_id}/note", dependencies=[Depends(user)])
async def put_note(hl_id: str, request: Request, c=Depends(conn)):
    body = await request.json()
    s = config.load_settings()
    review.set_note(c, hl_id, str(body.get("note") or ""))
    b = c.execute("SELECT book_id, source FROM highlights WHERE id = ?", (hl_id,)).fetchone()
    if not b or not b[0]:
        return {"ok": True, "vault": "no book"}
    return {"ok": True, "vault": vaultnotes.write_for(c, s, b[0])}


@app.get("/api/books", dependencies=[Depends(user)])
def get_books(private: int = 0, c=Depends(conn)):
    s = config.load_settings()
    stand = library.nightstand(c, s)
    ids = {b["id"] for b in stand}
    readable = ebooks.readable_ids(c)
    hl = {r[0]: r[1] for r in c.execute("SELECT book_id, COUNT(*) FROM highlights WHERE deleted = 0 GROUP BY book_id")}
    # Manga volumes read on the Kindle are on the Manga page, by series, not here one by one.
    reading = [dict(r) for r in c.execute(
        "SELECT * FROM books WHERE kind = 'book' AND (status = 'reading' OR last_read IS NOT NULL OR audio_pct IS NOT NULL) "
        "AND id NOT IN (SELECT book_id FROM manga_books) "
        + ("" if private else "AND private = 0 ") + "ORDER BY COALESCE(last_read, 0) DESC")]
    out = []
    for b in reading:
        if b["id"] in ids:
            continue
        card = _book_card(b)
        card["highlights"] = hl.get(b["id"], 0)
        out.append(card)
    stand_cards = []
    for b in stand:
        card = _book_card(b)
        card["highlights"] = hl.get(b["id"], 0)
        card["readable"] = b["id"] in readable
        stand_cards.append(card)
    for card in out:
        card["readable"] = card["id"] in readable
    return {"nightstand": stand_cards, "suggested": [] if stand else [_book_card(b) | {"readable": b["id"] in readable} for b in library.suggest_nightstand(c)],
            "others": out, "marked_reading": sum(1 for b in reading if b["status"] == "reading"),
            "manga": c.execute("SELECT COUNT(DISTINCT series) FROM manga_books").fetchone()[0]}


@app.put("/api/nightstand", dependencies=[Depends(user)])
async def put_nightstand(request: Request, c=Depends(conn)):
    body = await request.json()
    ids = [i for i in body.get("ids", []) if isinstance(i, str)]
    if len(ids) > 3:
        raise HTTPException(400, "Three books at most. Take one off first.")
    known = {r[0] for r in c.execute(f"SELECT id FROM books WHERE id IN ({','.join('?' * len(ids))})", ids)} if ids else set()
    s = config.load_settings()
    s["nightstand"] = [i for i in ids if i in known]
    if body.get("not_nightstand"):
        s["not_nightstand"] = list({*(s.get("not_nightstand") or []), body["not_nightstand"]})[-20:]
    config.save_settings(s)
    return {"nightstand": s["nightstand"]}


@app.get("/api/books/{book_id}", dependencies=[Depends(user)])
def get_book(book_id: str, c=Depends(conn)):
    b = c.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    if not b:
        raise HTTPException(404, "No such book")
    secs = c.execute("SELECT source, SUM(seconds) FROM sessions s JOIN book_keys k ON k.key = 'md5:' || s.item "
                     "WHERE k.book_id = ? GROUP BY source", (book_id,)).fetchall()
    card = _book_card(b)
    card["private"] = bool(b["private"])
    card["minutes_kindle"] = round(sum(r[1] for r in secs) / 60) if secs else 0
    card["highlights"] = _hl_rows(c, " AND h.book_id = ?", (book_id,))
    card["notes"] = [dict(r) for r in c.execute("SELECT * FROM reading_notes WHERE book_id = ? ORDER BY created DESC", (book_id,))]
    card["bookmarks"] = [dict(r) for r in c.execute("SELECT * FROM audio_bookmarks WHERE book_id = ? ORDER BY at", (book_id,))]
    card["on_nightstand"] = book_id in (config.load_settings().get("nightstand") or [])
    card["readable"] = ebooks.book_file(c, book_id)[0] is not None
    pos = c.execute("SELECT fraction, chapter, updated FROM book_positions WHERE book_id = ?", (book_id,)).fetchone()
    card["daf_position"] = dict(pos) if pos else None
    from . import bookstats
    card["stats"] = bookstats.stats(c, config.load_settings(), book_id, b["progress"], pos["fraction"] if pos else None)
    f = c.execute("SELECT freq FROM book_review WHERE book_id = ?", (book_id,)).fetchone()
    card["review_freq"] = f[0] if f else "normal"
    card["shelves"] = [r[0] for r in c.execute("SELECT shelf_id FROM shelf_books WHERE book_id = ?", (book_id,))]
    return card


# ---- shelves ------------------------------------------------------------------------

def _shelf_list(c):
    out = []
    for r in c.execute("SELECT id, name, created, hc_list FROM shelves ORDER BY lower(name)"):
        ids = [x for (x,) in c.execute("SELECT book_id FROM shelf_books WHERE shelf_id = ? ORDER BY added DESC", (r["id"],))]
        out.append({"id": r["id"], "name": r["name"], "count": len(ids), "covers": ids[:4], "hardcover": bool(r["hc_list"])})
    return out


@app.get("/api/shelves", dependencies=[Depends(user)])
def get_shelves(c=Depends(conn)):
    return {"shelves": _shelf_list(c)}


@app.post("/api/shelves", dependencies=[Depends(user)])
async def post_shelf(request: Request, c=Depends(conn)):
    b = await _body(request)
    name = " ".join(str(b.get("name") or "").split())[:60]
    if not name:
        raise HTTPException(400, "A name, please")
    if c.execute("SELECT 1 FROM shelves WHERE lower(name) = lower(?)", (name,)).fetchone():
        raise HTTPException(400, "There's a shelf by that name")
    sid = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:30] or "shelf"
    while c.execute("SELECT 1 FROM shelves WHERE id = ?", (sid,)).fetchone():
        sid += "-" + hashlib.sha1(f"{name}{time.time()}".encode()).hexdigest()[:4]
    c.execute("INSERT INTO shelves (id, name, created) VALUES (?, ?, ?)", (sid, name, int(time.time())))
    book = b.get("book")
    if isinstance(book, str) and c.execute("SELECT 1 FROM books WHERE id = ?", (book,)).fetchone():
        c.execute("INSERT OR IGNORE INTO shelf_books (shelf_id, book_id, added) VALUES (?, ?, ?)", (sid, book, int(time.time())))
    return {"id": sid, "shelves": _shelf_list(c)}


@app.get("/api/shelves/{shelf_id}", dependencies=[Depends(user)])
def get_shelf(shelf_id: str, c=Depends(conn)):
    sh = c.execute("SELECT id, name, hc_list FROM shelves WHERE id = ?", (shelf_id,)).fetchone()
    if not sh:
        raise HTTPException(404, "No such shelf")
    from . import hardcover
    readable = ebooks.readable_ids(c)
    hl = {r[0]: r[1] for r in c.execute("SELECT book_id, COUNT(*) FROM highlights WHERE deleted = 0 GROUP BY book_id")}
    books = [_book_card(r) | {"readable": r["id"] in readable, "highlights": hl.get(r["id"], 0)} for r in c.execute(
        "SELECT b.* FROM shelf_books s JOIN books b ON b.id = s.book_id WHERE s.shelf_id = ? ORDER BY s.added DESC", (shelf_id,))]
    return {"id": sh["id"], "name": sh["name"], "books": books, "hardcover": bool(sh["hc_list"]),
            "hardcover_url": hardcover.list_url(c, sh["hc_list"]) if sh["hc_list"] else None}


@app.put("/api/shelves/{shelf_id}", dependencies=[Depends(user)])
async def put_shelf(shelf_id: str, request: Request, c=Depends(conn)):
    name = " ".join(str((await _body(request)).get("name") or "").split())[:60]
    if not name:
        raise HTTPException(400, "A name, please")
    from . import hardcover
    try:
        hardcover.list_rename(c, shelf_id, name)      # a Hardcover list is renamed there too
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Hardcover didn't rename the list: {e}")
    c.execute("UPDATE shelves SET name = ? WHERE id = ?", (name, shelf_id))
    return {"shelves": _shelf_list(c)}


@app.delete("/api/shelves/{shelf_id}", dependencies=[Depends(user)])
def delete_shelf(shelf_id: str, c=Depends(conn)):
    if c.execute("SELECT 1 FROM shelves WHERE id = ? AND hc_list IS NOT NULL", (shelf_id,)).fetchone():
        raise HTTPException(400, "This shelf is one of your Hardcover lists. Delete the list on Hardcover and the shelf stays here as an ordinary one")
    c.execute("DELETE FROM shelf_books WHERE shelf_id = ?", (shelf_id,))
    c.execute("DELETE FROM shelves WHERE id = ?", (shelf_id,))
    return {"shelves": _shelf_list(c)}


@app.put("/api/shelves/{shelf_id}/books/{book_id}", dependencies=[Depends(user)])
def put_shelf_book(shelf_id: str, book_id: str, c=Depends(conn)):
    if not c.execute("SELECT 1 FROM shelves WHERE id = ?", (shelf_id,)).fetchone() or not c.execute("SELECT 1 FROM books WHERE id = ?", (book_id,)).fetchone():
        raise HTTPException(404, "No such shelf or book")
    from . import hardcover
    try:
        hardcover.list_add(c, shelf_id, book_id)
    except hardcover.HardcoverError as e:
        raise HTTPException(400, str(e))
    c.execute("INSERT OR IGNORE INTO shelf_books (shelf_id, book_id, added) VALUES (?, ?, ?)", (shelf_id, book_id, int(time.time())))
    return {"ok": True}


@app.delete("/api/shelves/{shelf_id}/books/{book_id}", dependencies=[Depends(user)])
def delete_shelf_book(shelf_id: str, book_id: str, c=Depends(conn)):
    from . import hardcover
    try:
        hardcover.list_remove(c, shelf_id, book_id)
    except hardcover.HardcoverError as e:
        raise HTTPException(502, f"Hardcover didn't take it off the list: {e}")
    c.execute("DELETE FROM shelf_books WHERE shelf_id = ? AND book_id = ?", (shelf_id, book_id))
    return {"ok": True}


@app.put("/api/books/{book_id}/review", dependencies=[Depends(user)])
async def put_book_review(book_id: str, request: Request, c=Depends(conn)):
    """How often this book comes up in the daily review: more, normal, less or never."""
    f = (await _body(request)).get("freq")
    if f not in ("more", "normal", "less", "never"):
        raise HTTPException(400, "more, normal, less or never")
    if not c.execute("SELECT 1 FROM books WHERE id = ?", (book_id,)).fetchone():
        raise HTTPException(404, "No such book")
    if f == "normal":
        c.execute("DELETE FROM book_review WHERE book_id = ?", (book_id,))
    else:
        c.execute("INSERT INTO book_review (book_id, freq) VALUES (?, ?) ON CONFLICT(book_id) DO UPDATE SET freq = excluded.freq", (book_id, f))
    return {"freq": f}


@app.get("/api/cover/{book_id}", dependencies=[Depends(user)])
def get_cover(book_id: str, c=Depends(conn)):
    p = library.cover_path(c, book_id)
    if not p:
        raise HTTPException(404, "No cover")
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=604800, stale-while-revalidate=2592000"})


@app.post("/api/notes", dependencies=[Depends(user)])
async def post_note(request: Request, c=Depends(conn)):
    body = await request.json()
    text = str(body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "Empty note")
    s = config.load_settings()
    book_id = body.get("book_id")
    if not book_id:
        cur = library.current_kindle_book(c)
        if not cur or not cur["book"]:
            raise HTTPException(400, "No book to file it under")
        book_id, page, total = cur["book"]["id"], cur["page"], cur["total"]
    else:
        page, total = body.get("page"), None
    _nid, res = notes.add_reading_note(c, s, book_id, text, page, total, "text")
    return {"ok": True, "vault": res}


# ---- the reader -----------------------------------------------------------------

@app.get("/api/docs", dependencies=[Depends(user)])
def get_docs(where: str = "feed", tab: str = "", kind: str = "", cat: str = "", feed: str = "", limit: int = 100, offset: int = 0,
             sort: str = "new", source: str = "", author: str = "", minlen: float = 0, maxlen: float = 0, since: int = 0,
             hl: int = 0, fresh: int = 0, c=Depends(conn)):
    s = config.load_settings()
    if where not in ("feed", "library"):
        raise HTTPException(400, "feed or library")
    flt = {"source": source, "author": author, "minlen": minlen, "maxlen": maxlen, "since": since, "hl": hl, "fresh": fresh}
    items = reader.list_docs(c, s, where, tab or ("unseen" if where == "feed" else "inbox"), kind or None, cat or None,
                             min(max(limit, 1), 300), max(offset, 0), sort, feed or None, flt)
    return {"items": items, "counts": reader.counts(c, s)}


@app.get("/api/docs/counts", dependencies=[Depends(user)])
def get_doc_counts(c=Depends(conn)):
    return reader.counts(c, config.load_settings())


VIEW_KEYS = {"name": 60, "where": 10, "arg": 120, "tab": 10, "tag": 60, "sort": 12}


@app.get("/api/views", dependencies=[Depends(user)])
def get_views():
    return {"views": config.load_settings().get("views") or []}


@app.put("/api/views", dependencies=[Depends(user)])
async def put_views(request: Request):
    """Saved views: [{id, name, where (library|feed), arg (a kind or a feed folder), tab, tag, sort}]."""
    body = await _body(request)
    out = []
    for v in (body.get("views") or [])[:30]:
        if not isinstance(v, dict) or v.get("where") not in ("library", "feed") or not str(v.get("name") or "").strip():
            continue
        x = {k: str(v.get(k) or "")[:n] for k, n in VIEW_KEYS.items()}
        x["name"] = " ".join(x["name"].split())
        f = v.get("filter") if isinstance(v.get("filter"), dict) else {}
        x["filter"] = {k: f[k] for k in ("source", "author", "minlen", "maxlen", "since", "hl", "fresh")
                       if k in f and isinstance(f[k], (str, int, float, bool)) and f[k] not in ("", 0, False, None)}
        x["id"] = re.sub(r"[^a-z0-9-]", "", str(v.get("id") or "").lower())[:24] or hashlib.sha1(json.dumps(x, sort_keys=True).encode()).hexdigest()[:10]
        out.append(x)
    s = config.load_settings()
    s["views"] = out
    config.save_settings(s)
    return {"views": out}


@app.get("/api/docs/tags", dependencies=[Depends(user)])
def get_doc_tags(c=Depends(conn)):
    return {"tags": reader.all_doc_tags(c)}


@app.get("/api/docs/{doc_id}", dependencies=[Depends(user)])
def get_doc(doc_id: str, prefetch: int = 0, c=Depends(conn)):
    d = reader.get_doc(c, doc_id, prefetch=bool(prefetch))
    if not d:
        raise HTTPException(404, "Not found")
    from . import kindlesend
    d["kindle_sent"] = kindlesend.sent(c, doc_id)
    d["questions"] = ai.questions()
    return d


@app.post("/api/kindle/send", dependencies=[Depends(user)])
def post_kindle_send(b=Depends(json_body), c=Depends(conn)):
    """Articles to the Kindle: one EPUB (a digest for several) into the Syncthing folder it shares."""
    from . import kindlesend
    ids = [i for i in ((b if isinstance(b, dict) else {}).get("ids") or []) if isinstance(i, str)][:50]
    if not ids:
        raise HTTPException(400, "Which documents?")
    try:
        return kindlesend.make_epub(c, ids)
    except ValueError as e:
        raise HTTPException(400, str(e))


async def _body(request):
    try:
        return await request.json()
    except ValueError:
        return {}


@app.post("/api/docs/{doc_id}/status", dependencies=[Depends(user)])
def post_doc_status(doc_id: str, body=Depends(json_body), c=Depends(conn)):
    try:
        reader.set_status(c, doc_id, body.get("status"))
    except KeyError:
        raise HTTPException(404, "Not found")
    except ValueError:
        raise HTTPException(400, "Unknown status")
    except Exception as e:  # noqa: BLE001 - FreshRSS or Karakeep said no
        raise HTTPException(502, str(e))
    return {"ok": True}


@app.put("/api/docs/{doc_id}/tags", dependencies=[Depends(user)])
def put_doc_tags(doc_id: str, body=Depends(json_body), c=Depends(conn)):
    try:
        tags = reader.set_doc_tags(c, doc_id, body.get("tags") or [])
    except KeyError:
        raise HTTPException(404, "Not found")
    except Exception as e:  # noqa: BLE001 - Karakeep said no
        raise HTTPException(502, str(e))
    return {"tags": tags, "all": reader.all_doc_tags(c)}


@app.post("/api/docs/bulk", dependencies=[Depends(user)])
def post_docs_bulk(body=Depends(json_body), c=Depends(conn)):
    """Many documents at once: {"ids": [...], "status": "archive" | "later" | "inbox" | "seen" | "unseen" | "deleted"}.
    Each one goes through the same path as a single change; the ones that fail are listed (one
    that's gone from Karakeep, say, when an Undo puts a batch back)."""
    ids = [i for i in (body.get("ids") or []) if isinstance(i, str)][:500]
    status = body.get("status")
    if status not in ("archive", "later", "inbox", "seen", "unseen", "deleted"):
        raise HTTPException(400, "Unknown status")
    done, failed = [], []
    for i in ids:
        try:
            reader.set_status(c, i, status)
            done.append(i)
        except Exception as e:  # noqa: BLE001 - one refusal must not stop the rest
            failed.append({"id": i, "error": str(e)[:200]})
    return {"done": done, "failed": failed}


@app.post("/api/docs/{doc_id}/full", dependencies=[Depends(user)])
def post_doc_full(doc_id: str, c=Depends(conn)):
    """The whole article from the item's page, for a feed that sends a summary."""
    from . import fulltext
    try:
        before, now = fulltext.load(c, doc_id)
    except KeyError:
        raise HTTPException(404, "Not found")
    except fulltext.FullTextError as e:
        raise HTTPException(422, str(e))
    return {"before": before, "words": now}


@app.post("/api/docs/{doc_id}/save", dependencies=[Depends(user)])
def post_doc_save(doc_id: str, c=Depends(conn)):
    try:
        return {"id": reader.save_to_library(c, doc_id)}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, str(e))


@app.post("/api/add/link", dependencies=[Depends(user)])
def add_link(b=Depends(json_body), c=Depends(conn)):
    """A link typed or pasted into Daf: straight to Karakeep, then into the Library (its row is made
    now, as the extension's are, instead of reading all of Karakeep again)."""
    from . import pages
    url = str(b.get("url") or "").strip()
    if not re.match(r"^https?://\S+$", url):
        raise HTTPException(400, "A link starting with http:// or https://, please")
    try:
        doc_id, _ = pages.save_page(c, url, (b.get("title") or "").strip() or None)
    except Exception:  # noqa: BLE001 - Karakeep down: keep it in the inbox for the next sync
        phone.save_shared(c, url, str(b.get("title") or ""), "")
        return {"where": "inbox", "id": None}
    return {"where": "library", "id": doc_id}


# ---- Hardcover ----------------------------------------------------------------------

def _hc(fn, *a, **kw):
    from . import hardcover
    try:
        return fn(*a, **kw)
    except hardcover.HardcoverError as e:
        raise HTTPException(502, str(e))


@app.get("/api/hardcover", dependencies=[Depends(user)])
def hc_info(c=Depends(conn)):
    from . import hardcover
    if not hardcover._key():
        return {"connected": False}
    d = _hc(hardcover.fetch, c)
    counts = {}
    for ub in d["books"]:
        counts[hardcover.STATUS.get(ub["status_id"], "?")] = counts.get(hardcover.STATUS.get(ub["status_id"], "?"), 0) + 1
    last = c.execute("SELECT v FROM kv WHERE k = 'hc_last'").fetchone()
    return {"connected": True, "user": d["user"], "at": d["at"], "counts": counts, "linked": len(hardcover.hc_map(c)),
            "last": json.loads(last[0]) if last else None}


@app.get("/api/hardcover/shelf", dependencies=[Depends(user)])
def hc_shelf(status: int = 1, c=Depends(conn)):
    from . import hardcover
    return {"books": _hc(hardcover.shelf, c, status)}


@app.get("/api/hardcover/book/{book_id}", dependencies=[Depends(user)])
def hc_book(book_id: str, c=Depends(conn)):
    from . import hardcover
    return _hc(hardcover.book_status, c, book_id)


@app.put("/api/hardcover/book/{book_id}", dependencies=[Depends(user)])
async def hc_book_put(book_id: str, request: Request, c=Depends(conn)):
    from . import hardcover
    b = await _body(request)
    return _hc(hardcover.set_status, c, book_id, int(b["status_id"]) if b.get("status_id") else None,
               b.get("rating") if "rating" in b else None)


@app.post("/api/hardcover/book/{book_id}/finish", dependencies=[Depends(user)])
async def hc_book_finish(book_id: str, request: Request, c=Depends(conn)):
    from . import hardcover
    b = await _body(request)
    out = _hc(hardcover.finish, c, book_id, b.get("rating"), b.get("date"))
    hardcover.dismiss_finish(c, book_id)
    return out


@app.post("/api/hardcover/book/{book_id}/notyet", dependencies=[Depends(user)])
def hc_book_notyet(book_id: str, c=Depends(conn)):
    from . import hardcover
    hardcover.dismiss_finish(c, book_id)
    return {"ok": True}


@app.get("/api/hardcover/search", dependencies=[Depends(user)])
def hc_search(book_id: str = "", q: str = "", c=Depends(conn)):
    from . import hardcover
    return {"hits": _hc(hardcover.search, c, book_id or None, q or None)}


@app.post("/api/hardcover/book/{book_id}/link", dependencies=[Depends(user)])
async def hc_book_link(book_id: str, request: Request, c=Depends(conn)):
    from . import hardcover
    b = await _body(request)
    if not str(b.get("hc_book_id") or "").isdigit():
        raise HTTPException(400, "Which Hardcover book?")
    hardcover.link(c, book_id, int(b["hc_book_id"]))
    if b.get("status_id"):
        return _hc(hardcover.set_status, c, book_id, int(b["status_id"]))
    return _hc(hardcover.book_status, c, book_id)


# ---- flashcards ------------------------------------------------------------------------

@app.get("/api/cards/due", dependencies=[Depends(user)])
def cards_due(c=Depends(conn)):
    from . import cards
    items = cards.due(c, config.load_settings())
    for x in items:
        x["open"] = jump.href({"id": x["hl_id"], "book_id": x["book_id"]}, ebooks.readable_ids(c), set()) if x.get("book_id") else None
    return {"items": items}


@app.get("/api/highlights/{hl_id}/cards", dependencies=[Depends(user)])
def hl_cards(hl_id: str, c=Depends(conn)):
    from . import cards
    return {"cards": cards.for_highlight(c, hl_id)}


@app.post("/api/highlights/{hl_id}/cards", dependencies=[Depends(user)])
async def hl_card_save(hl_id: str, request: Request, c=Depends(conn)):
    from . import cards
    b = await _body(request)
    try:
        cid = cards.save(c, hl_id, b.get("kind"), b.get("front"), b.get("back"), b.get("id"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"id": cid, "cards": cards.for_highlight(c, hl_id)}


@app.post("/api/highlights/{hl_id}/cards/suggest", dependencies=[Depends(user)])
async def hl_card_suggest(hl_id: str, c=Depends(conn)):
    from . import cards
    import asyncio
    try:
        return await asyncio.to_thread(cards.suggest, c, hl_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, str(e))


@app.delete("/api/cards/{card_id}", dependencies=[Depends(user)])
def card_delete(card_id: str, c=Depends(conn)):
    from . import cards
    cards.delete(c, card_id)
    return {"ok": True}


@app.post("/api/cards/{card_id}/grade", dependencies=[Depends(user)])
async def card_grade(card_id: str, request: Request, c=Depends(conn)):
    from . import cards
    b = await _body(request)
    try:
        return cards.grade(c, config.load_settings(), card_id, b.get("grade"))
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---- newsletters ------------------------------------------------------------------------

@app.get("/api/newsletters", dependencies=[Depends(user)])
def get_newsletters(c=Depends(conn)):
    from .sources import newsletters
    if not newsletters.configured():
        return {"configured": False}
    s = config.load_settings()
    row = c.execute("SELECT v FROM kv WHERE k = 'nl_senders'").fetchone()
    cached = json.loads(row[0]) if row else None
    if not cached or time.time() - cached["at"] > 86400:
        try:
            cached = {"at": int(time.time()), "senders": newsletters.scan(c)}
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"Proton Mail Bridge didn't answer: {e}")
    return {"configured": True, "at": cached["at"], "senders": newsletters.ranked(c, s, cached["senders"]), "chosen": s["newsletters"],
            "count": c.execute("SELECT COUNT(*) FROM docs WHERE id LIKE 'nl:%'").fetchone()[0]}


@app.post("/api/newsletters/scan", dependencies=[Depends(user)])
def scan_newsletters(c=Depends(conn)):
    from .sources import newsletters
    try:
        out = newsletters.scan(c)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Proton Mail Bridge didn't answer: {e}")
    return {"senders": newsletters.ranked(c, config.load_settings(), out)}


@app.put("/api/newsletters", dependencies=[Depends(user)])
async def put_newsletters(request: Request, c=Depends(conn)):
    from .sources import newsletters
    import asyncio
    b = await _body(request)
    chosen = [str(x).lower() for x in (b.get("chosen") or []) if isinstance(x, str) and "@" in x][:200]
    s = config.load_settings()
    s["newsletters"] = chosen
    config.save_settings(s)
    try:
        n = await asyncio.to_thread(newsletters.sync, c, s)
    except Exception as e:  # noqa: BLE001
        return {"chosen": chosen, "imported": 0, "error": str(e)}
    return {"chosen": chosen, "imported": n}


@app.get("/api/feed/folders", dependencies=[Depends(user)])
def feed_folders():
    from .sources import freshrss
    try:
        return {"folders": freshrss.folders()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"FreshRSS didn't answer: {e}")


@app.get("/api/feed/sources", dependencies=[Depends(user)])
def get_feed_sources(c=Depends(conn)):
    """Folders and feeds with their unseen counts, for the Feed's source picker."""
    return reader.feed_sources(c, config.load_settings())


@app.get("/api/feed/icon/{h}", dependencies=[Depends(user)])
def get_feed_icon(h: str):
    from .sources import freshrss
    if not re.fullmatch(r"[0-9a-f]{4,40}", h):
        raise HTTPException(404, "No such icon")
    try:
        data, kind = freshrss.icon(h)
    except Exception:  # noqa: BLE001
        raise HTTPException(404, "No icon")
    return Response(data, media_type=kind, headers={"Cache-Control": "private, max-age=604800"})


@app.post("/api/feed/seen", dependencies=[Depends(user)])
async def post_feed_seen(request: Request, c=Depends(conn)):
    """Mark all seen: {"cat"?: a folder, "feed"?: "feed/12", "older"?: seconds}. Returns the ids, so it can be undone."""
    b = await _body(request)
    try:
        ids = reader.mark_feed_seen(c, config.load_settings(), str(b.get("cat") or "") or None, str(b.get("feed") or "") or None,
                                    int(b["older"]) if str(b.get("older") or "").isdigit() else None)
    except Exception as e:  # noqa: BLE001 - FreshRSS said no
        raise HTTPException(502, f"FreshRSS didn't take it: {e}")
    return {"ids": ids}


@app.post("/api/feed/refresh", dependencies=[Depends(user)])
def post_feed_refresh(c=Depends(conn)):
    """Pull to refresh: ask FreshRSS for what's new now, without waiting for the five-minute sync."""
    from .sources import freshrss
    if not sync._lock.acquire(timeout=45):
        return {"new": 0, "busy": True}
    try:
        new, total = freshrss.sync(c, config.load_settings())
        reader.apply_edits(c)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"FreshRSS didn't answer: {e}")
    finally:
        sync._lock.release()
    return {"new": new, "counts": reader.counts(c, config.load_settings())}


@app.put("/api/feed/sources", dependencies=[Depends(user)])
async def put_feed_source(request: Request, c=Depends(conn)):
    """Rename a feed or move it: {"feed": "feed/12", "title"?: ..., "folder"?: ...}."""
    b = await _body(request)
    try:
        return reader.edit_feed(c, str(b.get("feed") or ""), b.get("title"), b.get("folder") if "folder" in b else None,
                                bool(b["full"]) if "full" in b else None, bool(b["notify"]) if "notify" in b else None)
    except KeyError:
        raise HTTPException(404, "Daf doesn't know that feed")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"FreshRSS didn't take it: {e}")


@app.delete("/api/feed/sources", dependencies=[Depends(user)])
def delete_feed_source(feed: str, c=Depends(conn)):
    """Unfollow a feed."""
    try:
        reader.unfollow_feed(c, feed)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"FreshRSS didn't take it: {e}")
    return {"ok": True}


@app.post("/api/add/feed", dependencies=[Depends(user)])
async def add_feed(request: Request):
    """Follow a site or feed in FreshRSS, in a folder; new posts show up in the Feed."""
    from .sources import freshrss
    import asyncio
    b = await _body(request)
    url = str(b.get("url") or "").strip()
    if not re.match(r"^https?://\S+$", url):
        raise HTTPException(400, "A link starting with http:// or https://, please")
    try:
        name = await asyncio.to_thread(freshrss.subscribe, url, str(b.get("folder") or "").strip() or None)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"FreshRSS didn't take it: {e}")
    return {"name": name}


BOOK_EXTS = {".epub", ".kepub", ".mobi", ".azw3", ".azw", ".fb2", ".cbz"}


@app.post("/api/add/file", dependencies=[Depends(user)])
async def add_file(request: Request, c=Depends(conn)):
    """A file dropped on Daf. Books go to Calibre through Calibre-Web-Automated's ingest folder
    (then Books, readable in Daf); PDFs go to Karakeep (then the Library's PDFs)."""
    form = await request.form()
    f = form.get("file")
    if f is None or not getattr(f, "filename", None):
        raise HTTPException(400, "No file")
    name = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", " ", f.filename).strip()[:150] or "book"
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    data = await f.read(200_000_001)
    if len(data) > 200_000_000:
        raise HTTPException(413, "Over 200 MB")
    if ext in BOOK_EXTS:
        config.CWA_INGEST.mkdir(parents=True, exist_ok=True)
        dest = config.CWA_INGEST / name
        n = 2
        while dest.exists():
            dest = config.CWA_INGEST / f"{name.rsplit('.', 1)[0]} ({n}){ext}"
            n += 1
        tmp = dest.with_name("." + dest.name + ".part")
        tmp.write_bytes(data)
        tmp.replace(dest)
        return {"where": "books", "name": dest.name}
    if ext == ".pdf":
        from .sources import karakeep
        import asyncio
        if not karakeep.writes():
            # Daf keeps the Library: the PDF is kept on morten (pdfdoc's folder) and read there
            from . import media, pages, pdfdoc
            if not data.startswith(b"%PDF"):
                raise HTTPException(400, "That isn't a PDF")
            new_id = pages.make_id()
            pdfdoc.DIR.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(pdfdoc.path_for(new_id).write_bytes, data)
            title = " ".join(str(form.get("title") or name.rsplit(".", 1)[0]).split())[:300]
            c.execute("INSERT INTO docs (id, kind, where_, status, title, author, source, category, url, added) "
                      "VALUES (?, 'pdf', 'library', 'inbox', ?, '', 'PDF', '', NULL, ?)", (new_id, title, int(time.time())))
            media.queue(c, "pdf", new_id)
            return {"where": "library", "id": new_id}
        try:
            bm = await asyncio.to_thread(karakeep.upload_pdf, name, data, form.get("title") or None)
            await asyncio.to_thread(karakeep.sync, c)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"Karakeep didn't take it: {e}")
        return {"where": "library", "id": "kk:" + bm["id"] if bm.get("id") else None}
    raise HTTPException(400, "Daf takes links, EPUB, MOBI, AZW3, FB2, CBZ and PDF")


@app.put("/api/docs/{doc_id}/star", dependencies=[Depends(user)])
def put_doc_star(doc_id: str, b=Depends(json_body), c=Depends(conn)):
    try:
        reader.set_starred(c, doc_id, bool(b.get("starred")))
    except KeyError:
        raise HTTPException(404, "No such document")
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Karakeep didn't answer: {e}")
    return {"ok": True}


@app.post("/api/docs/{doc_id}/summary", dependencies=[Depends(user)])
async def post_doc_summary(doc_id: str, c=Depends(conn)):
    """Summarize one document now (the Feed's aren't done ahead of time)."""
    import asyncio
    try:
        out = await asyncio.to_thread(reader.summarize, c, doc_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, str(e))
    if not out:
        raise HTTPException(400, "Too short to summarize")
    return {"ai_summary": out}


@app.put("/api/docs/{doc_id}/meta", dependencies=[Depends(user)])
async def put_doc_meta(doc_id: str, request: Request, c=Depends(conn)):
    b = await _body(request)
    try:
        reader.edit_meta(c, doc_id, b.get("title"), b.get("author"))
    except KeyError:
        raise HTTPException(404, "No such document")
    d = c.execute("SELECT title, author FROM docs WHERE id = ?", (doc_id,)).fetchone()
    return {"title": d["title"], "author": d["author"]}


@app.post("/api/docs/{doc_id}/highlights", dependencies=[Depends(user)])
def post_doc_highlight(doc_id: str, b=Depends(json_body), c=Depends(conn)):
    try:
        # A highlight made on a PDF's page may have no place in the text view (b is null); it keeps its page.
        nob = b.get("b") is None and isinstance(b.get("pdf"), dict)
        at = int(b["at"]) if b.get("at") is not None and time.time() - 30 * 86400 < int(b["at"]) <= time.time() + 60 else None   # made offline
        hid = reader.add_highlight(c, config.load_settings(), doc_id, None if nob else int(b["b"]), None if nob else int(b["s"]),
                                   None if nob else int(b["e"]), str(b["text"]), b.get("note"),
                                   float(b["t"]) if b.get("t") is not None else None, b.get("color"),
                                   int(b["be"]) if b.get("be") is not None else None, b.get("replaces"), b.get("pdf"), created=at,
                                   img=str(b["img"]) if b.get("img") else None)
    except (KeyError, ValueError, TypeError):
        raise HTTPException(400, "Bad highlight")
    # A Feed item you highlight is one you want to keep: it goes to the Library, as in Readwise.
    d = c.execute("SELECT where_ FROM docs WHERE id = ?", (doc_id,)).fetchone()
    if d and d["where_"] == "feed":
        try:
            return {"id": hid, "saved_as": reader.save_to_library(c, doc_id)}
        except Exception as e:  # noqa: BLE001 - the highlight stands on the Feed item
            log.warning("save on highlight: %s", e)
            return {"id": hid, "save_error": str(e)}
    return {"id": hid}


@app.put("/api/highlights/{hl_id}/color", dependencies=[Depends(user)])
async def put_highlight_color(hl_id: str, request: Request, c=Depends(conn)):
    b = await _body(request)
    color = b.get("color")
    if color not in reader.COLORS:
        raise HTTPException(400, "yellow, green, blue, pink or purple")
    c.execute("UPDATE highlights SET color = ? WHERE id = ?", (None if color == "yellow" else color, hl_id))
    return {"ok": True}


@app.post("/api/highlights/{hl_id}/restore", dependencies=[Depends(user)])
def restore_highlight(hl_id: str, c=Depends(conn)):
    try:
        reader.restore_highlight(c, config.load_settings(), hl_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"ok": True}


# ---- books read in Daf (EPUB and friends, from Calibre) -----------------------------

@app.get("/api/stats", dependencies=[Depends(user)])
def get_stats(c=Depends(conn)):
    from . import stats
    return stats.stats(c, config.load_settings())


@app.get("/api/home", dependencies=[Depends(user)])
def get_home(c=Depends(conn)):
    from . import home
    return home.shelves(c, config.load_settings())


@app.get("/api/ebooks", dependencies=[Depends(user)])
def list_ebooks(q: str = "", c=Depends(conn)):
    ids = ebooks.readable_ids(c)
    pos = {r[0]: r[1] for r in c.execute("SELECT book_id, fraction FROM book_positions")}
    rows = [dict(r) for r in c.execute("SELECT * FROM books WHERE kind = 'book' AND private = 0 ORDER BY COALESCE(last_read, 0) DESC, title")
            if r["id"] in ids]
    if q.strip():
        ql = q.strip().lower()
        rows = [r for r in rows if ql in (r["title"] or "").lower() or ql in (r["author"] or "").lower()]
    return {"books": [_book_card(r) | {"daf_fraction": pos.get(r["id"])} for r in rows]}


@app.get("/api/ebooks/{book_id}", dependencies=[Depends(user)])
def get_ebook(book_id: str, c=Depends(conn)):
    d = ebooks.details(c, book_id)
    if not d or not d["format"]:
        raise HTTPException(404, "No readable file for this book in Calibre")
    d["questions"] = ai.questions(book=True)
    return d


@app.get("/api/ebooks/{book_id}/file", dependencies=[Depends(user)])
def get_ebook_file(book_id: str, c=Depends(conn)):
    p, fmt = ebooks.book_file(c, book_id)
    if not p:
        raise HTTPException(404, "No readable file for this book in Calibre")
    return FileResponse(p, media_type=ebooks.MIME.get(fmt, "application/octet-stream"),
                        headers={"Cache-Control": "private, max-age=86400"})


@app.delete("/api/ebooks/{book_id}/position", dependencies=[Depends(user)])
def delete_ebook_position(book_id: str, c=Depends(conn)):
    """Forget my place in Daf: the book opens at its start (or where the Kindle is) next time."""
    c.execute("DELETE FROM book_positions WHERE book_id = ?", (book_id,))
    return {"ok": True}


@app.put("/api/ebooks/{book_id}/position", dependencies=[Depends(user)])
async def put_ebook_position(book_id: str, request: Request, c=Depends(conn)):
    b = await _body(request)
    if not b.get("cfi"):
        raise HTTPException(400, "No position")
    kept = ebooks.save_position(c, book_id, str(b["cfi"])[:2000], b.get("fraction"), b.get("chapter"), b.get("at"))
    pages = [str(p)[:40] for p in (b.get("pages") or []) if isinstance(p, (str, int))][:200]
    if pages:                                   # pages shown for 5 seconds or more, for page goals, on the day they were
        day = datetime.fromtimestamp(ebooks.when(b.get("at")), T.tz_of(config.load_settings())).date().isoformat()
        c.executemany("INSERT OR IGNORE INTO ebook_pages (book_id, day, page) VALUES (?, ?, ?)", [(book_id, day, p) for p in pages])
    return {"ok": True, "kept": kept}


@app.post("/api/ebooks/{book_id}/bookmarks", dependencies=[Depends(user)])
async def post_ebook_bookmark(book_id: str, request: Request, c=Depends(conn)):
    b = await _body(request)
    try:
        mid = ebooks.add_bookmark(c, book_id, str(b.get("cfi") or "")[:2000], b.get("fraction"), b.get("chapter"), b.get("excerpt"), b.get("at"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"id": mid}


@app.delete("/api/ebooks/{book_id}/bookmarks/{mark_id}", dependencies=[Depends(user)])
def delete_ebook_bookmark(book_id: str, mark_id: str, c=Depends(conn)):
    c.execute("DELETE FROM book_marks WHERE id = ? AND book_id = ?", (mark_id, book_id))
    return {"ok": True}


@app.post("/api/ebooks/{book_id}/highlights", dependencies=[Depends(user)])
async def post_ebook_highlight(book_id: str, request: Request, c=Depends(conn)):
    b = await _body(request)
    try:
        hid = ebooks.add_highlight(c, config.load_settings(), book_id, str(b.get("cfi") or ""), str(b.get("text") or "")[:5000],
                                   b.get("chapter"), b.get("fraction"), b.get("note"), b.get("color"), b.get("replaces"), b.get("at"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"id": hid}


@app.post("/api/ebooks/{book_id}/ask", dependencies=[Depends(user)])
async def post_ebook_ask(book_id: str, request: Request, c=Depends(conn)):
    import asyncio
    b = await _body(request)
    q = str(b.get("q") or "").strip()
    if not q:
        raise HTTPException(400, "Ask something")
    try:
        a = await asyncio.to_thread(ebooks.ask, c, book_id, q, b.get("quote"), b.get("context"))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, str(e))
    return {"a": a}


@app.delete("/api/highlights/{hl_id}", dependencies=[Depends(user)])
def delete_highlight(hl_id: str, c=Depends(conn)):
    try:
        reader.remove_highlight(c, config.load_settings(), hl_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.delete("/api/docs/{doc_id}/progress", dependencies=[Depends(user)])
def reset_doc_progress(doc_id: str, c=Depends(conn)):
    c.execute("UPDATE docs SET progress = 0 WHERE id = ?", (doc_id,))
    return {"ok": True}


@app.put("/api/docs/{doc_id}/progress", dependencies=[Depends(user)])
async def put_doc_progress(doc_id: str, request: Request, c=Depends(conn)):
    b = await _body(request)
    reader.set_progress(c, doc_id, b.get("pct", 0))
    return {"ok": True}


@app.put("/api/docs/{doc_id}/note", dependencies=[Depends(user)])
async def put_doc_note(doc_id: str, request: Request, c=Depends(conn)):
    b = await _body(request)
    reader.set_note(c, config.load_settings(), doc_id, str(b.get("note") or ""))
    return {"ok": True}


@app.post("/api/read/beat", dependencies=[Depends(user)])
def post_beat(b=Depends(json_body), c=Depends(conn)):
    if b.get("book_id"):
        ebooks.beat(c, config.load_settings(), str(b["book_id"]), b.get("seconds") or 0, b.get("at"))
    else:
        reader.beat(c, config.load_settings(), str(b.get("doc_id") or ""), b.get("seconds") or 0, b.get("at"))
    return {"ok": True}


@app.post("/api/docs/{doc_id}/ask", dependencies=[Depends(user)])
async def post_ask(doc_id: str, request: Request):
    b = await _body(request)
    q = str(b.get("q") or "").strip()
    if not q:
        raise HTTPException(400, "Ask something")
    import asyncio

    def run():
        c = db.connect()
        try:
            a = reader.ask(c, doc_id, q, (b.get("quote") or None))
            c.commit()
            return a
        finally:
            c.close()
    try:
        return {"a": await asyncio.to_thread(run)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Ask failed: {e}")


@app.post("/api/tts/text", dependencies=[Depends(user)])
async def post_tts_text(request: Request):
    """Speech for a paragraph of a book (the book reader sends the text itself)."""
    import asyncio
    b = await _body(request)
    text = re.sub(r"\s+", " ", str(b.get("text") or "")).strip()[:4000]
    if not text:
        raise HTTPException(400, "Nothing to read")
    s = config.load_settings()
    try:
        path = await asyncio.to_thread(reader.tts, text, str(b.get("voice") or s.get("tts_voice") or "af_heart"),
                                       float(b.get("speed") or s.get("tts_speed") or 1.0))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Kokoro didn't answer: {e}")
    return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=604800"})


@app.get("/api/tts", dependencies=[Depends(user)])
def get_tts(doc: str, b: int, voice: str = "", c=Depends(conn)):
    row = c.execute("SELECT blocks FROM doc_content WHERE id = ?", (doc,)).fetchone()
    if not row:
        raise HTTPException(404, "No text")
    import json as _json
    blocks = _json.loads(row[0])
    if not 0 <= b < len(blocks) or blocks[b].get("t") == "img":
        raise HTTPException(404, "No such paragraph")
    s = config.load_settings()
    try:
        path = reader.tts(blocks[b]["x"], voice or s.get("tts_voice") or "af_heart", float(s.get("tts_speed") or 1.0))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Kokoro: {e}")
    return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": "max-age=604800"})


@app.get("/api/voices", dependencies=[Depends(user)])
def get_voices():
    return {"voices": reader.voices()}


@app.post("/api/feed/expire", dependencies=[Depends(user)])
def post_feed_expire(c=Depends(conn)):
    try:
        return {"before": reader.expire_in_freshrss(c, config.load_settings())}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, str(e))


@app.get("/api/search", dependencies=[Depends(user)])
def get_search(q: str = "", c=Depends(conn)):
    q = q.strip()
    if len(q) < 2:
        return {"docs": [], "highlights": [], "books": []}
    like = f"%{q}%"
    docs = [dict(r) for r in c.execute(
        "SELECT id, title, source, kind, where_ FROM docs WHERE (title LIKE ? OR source LIKE ? OR author LIKE ?) AND status != 'deleted' "
        "ORDER BY added DESC LIMIT 12", (like, like, like))]
    books = [dict(r) for r in c.execute(
        "SELECT id, title, author FROM books WHERE kind = 'book' AND private = 0 AND (title LIKE ? OR author LIKE ?) "
        "ORDER BY COALESCE(last_read, 0) DESC LIMIT 8", (like, like))]
    hls = [dict(r) for r in c.execute(
        "SELECT h.id, h.text, h.book_id, b.title FROM highlights h LEFT JOIN books b ON b.id = h.book_id "
        "LEFT JOIN review_state s ON s.hl_id = h.id WHERE h.deleted = 0 AND COALESCE(b.private, 0) = 0 "
        "AND (h.text LIKE ? OR s.user_note LIKE ?) LIMIT 10", (like, like))]
    # Inside the text of saved articles, emails and feed items (FTS5); the last word as a prefix.
    words = [w for w in re.findall(r"[\w'’-]+", q) if w]
    text = []
    if words:
        match = " ".join('"' + w.replace('"', '""') + '"' for w in words[:-1]) + (" " if len(words) > 1 else "") + '"' + words[-1].replace('"', '""') + '"*'
        have = {d["id"] for d in docs}
        try:
            for r in c.execute("SELECT f.id, snippet(docs_fts, 2, char(2), char(3), '…', 14) AS snip, d.title, d.source, d.where_ "
                               "FROM docs_fts f JOIN docs d ON d.id = f.id WHERE docs_fts MATCH ? AND d.status != 'deleted' ORDER BY bm25(docs_fts) LIMIT 15", (match,)):
                if r["id"] not in have:
                    text.append(dict(r))
        except Exception:  # noqa: BLE001 - an odd query must not break search
            pass
    from . import vaultsearch
    vault = vaultsearch.search(q, config.load_settings()) if len(q) >= 3 else []
    return {"docs": docs, "highlights": hls, "books": books, "vault": vault, "text": text[:10]}


# ---- videos, podcasts, clips (Phase 5) --------------------------------------------

@app.post("/api/docs/{doc_id}/transcript", dependencies=[Depends(user)])
async def post_transcript(doc_id: str, request: Request, c=Depends(conn)):
    b = await _body(request)
    media.queue(c, "whisper" if b.get("whisper") else "captions", doc_id)
    return {"ok": True}


@app.get("/api/docs/{doc_id}/transcript", dependencies=[Depends(user)])
def get_transcript_status(doc_id: str, c=Depends(conn)):
    row = c.execute("SELECT blocks FROM doc_content WHERE id = ?", (doc_id,)).fetchone()
    return {"captions": media.job_status(c, "captions", doc_id), "whisper": media.job_status(c, "whisper", doc_id),
            "pdf": media.job_status(c, "pdf", doc_id), "page": media.job_status(c, "page", doc_id),
            "ready": bool(row and row[0] not in ("[]", ""))}


@app.get("/api/docs/{doc_id}/pdf", dependencies=[Depends(user)])
def get_doc_pdf(doc_id: str, c=Depends(conn)):
    from . import pdfdoc
    p = pdfdoc.path_for(doc_id)
    if not p.exists():
        try:
            p = pdfdoc.download(c, doc_id)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(404, f"No PDF: {e}")
    return FileResponse(p, media_type="application/pdf", headers={"Content-Disposition": "inline"})


@app.get("/api/podcasts", dependencies=[Depends(user)])
def get_podcasts(c=Depends(conn)):
    o = gpodder.overview(c)
    o["device"] = bool(c.execute("SELECT 1 FROM devices WHERE name = 'antennapod'").fetchone())
    return o


@app.post("/api/podcasts/token", dependencies=[Depends(user)])
def post_podcast_token(c=Depends(conn)):
    c.execute("DELETE FROM devices WHERE name = 'antennapod'")
    return {"token": auth.new_device_token(c, "antennapod")}


def _gp_auth(request: Request, c):
    import base64
    h = request.headers.get("authorization", "")
    if h.lower().startswith("basic "):
        try:
            _u, _, pw = base64.b64decode(h[6:]).decode().partition(":")
        except ValueError:
            pw = ""
        if auth.check_device(c, pw) == "antennapod":
            return
    if request.cookies.get("daf_gp") and auth.check_device(c, request.cookies.get("daf_gp")) == "antennapod":
        return
    raise HTTPException(401, "gpodder login needed", headers={"WWW-Authenticate": 'Basic realm="Daf"'})


@app.post("/api/2/auth/{username}/login.json")
def gp_login(username: str, request: Request, c=Depends(conn)):
    """AntennaPod sends Basic auth only here, then relies on the session cookie."""
    import base64
    _gp_auth(request, c)
    pw = base64.b64decode(request.headers.get("authorization", "")[6:] or b"").decode(errors="ignore").partition(":")[2]
    r = JSONResponse({})
    if pw:
        r.set_cookie("daf_gp", pw, max_age=400 * 86400, httponly=True, samesite="lax", secure=is_https(request))
    return r


@app.post("/api/2/auth/{username}/logout.json")
def gp_logout(username: str):
    r = JSONResponse({})
    r.delete_cookie("daf_gp")
    return r


@app.get("/api/2/devices/{username}.json")
def gp_devices(username: str, request: Request, c=Depends(conn)):
    _gp_auth(request, c)
    n = c.execute("SELECT COUNT(*) FROM gp_subs WHERE removed IS NULL").fetchone()[0]
    return [{"id": "antennapod", "caption": "AntennaPod", "type": "mobile", "subscriptions": n}]


@app.post("/api/2/devices/{username}/{device}.json")
def gp_device_update(username: str, device: str, request: Request, c=Depends(conn)):
    _gp_auth(request, c)
    return JSONResponse({})


@app.get("/api/2/subscriptions/{username}/{device}.json")
def gp_subs_get(username: str, device: str, request: Request, since: int = 0, c=Depends(conn)):
    _gp_auth(request, c)
    return gpodder.subs_changes(c, since)


@app.post("/api/2/subscriptions/{username}/{device}.json")
async def gp_subs_post(username: str, device: str, request: Request, c=Depends(conn)):
    _gp_auth(request, c)
    return gpodder.subs_upload(c, await _body(request))


@app.put("/subscriptions/{username}/{device}.json")
async def gp_subs_put(username: str, device: str, request: Request, c=Depends(conn)):
    _gp_auth(request, c)
    body = await _body(request)
    gpodder.subs_replace(c, body if isinstance(body, list) else [])
    return JSONResponse({})


@app.get("/api/2/episodes/{username}.json")
def gp_episodes_get(username: str, request: Request, since: int = 0, c=Depends(conn)):
    _gp_auth(request, c)
    return gpodder.actions_since(c, since)


@app.post("/api/2/episodes/{username}.json")
async def gp_episodes_post(username: str, request: Request, c=Depends(conn)):
    _gp_auth(request, c)
    body = await _body(request)
    return gpodder.actions_upload(c, body if isinstance(body, list) else body.get("actions", []))


# ---- paper pages (Phase 7) -------------------------------------------------------

def _page_out(c, row):
    d = paper_pages.to_json(row)
    b = c.execute("SELECT id, title, author FROM books WHERE id = ?", (d["book_id"],)).fetchone() if d["book_id"] else None
    d["book"] = dict(b) if b else None
    d["job"] = media.job_status(c, "ocr", d["id"])
    return d


@app.get("/api/paper/pages", dependencies=[Depends(user)])
def get_paper_pages(c=Depends(conn)):
    return {"pages": [_page_out(c, r) for r in c.execute("SELECT * FROM paper_pages ORDER BY created DESC LIMIT 200")]}


@app.post("/api/paper/pages", dependencies=[Depends(user)])
async def post_paper_page(request: Request, caption: str = "", c=Depends(conn)):
    """The raw photo as the body (no multipart), from the web app's file picker or the share target."""
    import tempfile
    data = await request.body()
    if len(data) < 1000 or len(data) > 25_000_000:
        raise HTTPException(400, "That doesn't look like a photo")
    with tempfile.NamedTemporaryFile(suffix=".img") as f:
        f.write(data)
        f.flush()
        pid = paper_pages.add_photo(c, f.name, caption)
    media.queue(c, "ocr", pid)
    return {"id": pid}


@app.get("/api/paper/pages/{pid}", dependencies=[Depends(user)])
def get_paper_page(pid: str, c=Depends(conn)):
    r = c.execute("SELECT * FROM paper_pages WHERE id = ?", (pid,)).fetchone()
    if not r:
        raise HTTPException(404, "No such page")
    return _page_out(c, r)


@app.get("/api/paper/pages/{pid}/photo", dependencies=[Depends(user)])
def get_paper_photo(pid: str, c=Depends(conn)):
    r = c.execute("SELECT photo FROM paper_pages WHERE id = ?", (pid,)).fetchone()
    if not r or not (paper_pages.PAGES / r[0]).exists():
        raise HTTPException(404, "No photo")
    return FileResponse(paper_pages.PAGES / r[0], headers={"Cache-Control": "max-age=604800"})


@app.post("/api/paper/pages/{pid}", dependencies=[Depends(user)])
async def save_paper_page(pid: str, request: Request, c=Depends(conn)):
    b = await _body(request)
    if not c.execute("SELECT 1 FROM paper_pages WHERE id = ?", (pid,)).fetchone():
        raise HTTPException(404, "No such page")
    book = b.get("book_id")
    if not book and b.get("new_title"):
        book = library.add_paper_book(c, str(b["new_title"]), b.get("new_author"))
    if not book or not c.execute("SELECT 1 FROM books WHERE id = ?", (book,)).fetchone():
        raise HTTPException(400, "Choose the book first")
    page = int(b["page"]) if str(b.get("page") or "").isdigit() else None
    made, res = paper_pages.save(c, config.load_settings(), pid, [i for i in b.get("chosen", []) if isinstance(i, int)], book, page)
    return {"ok": True, "highlights": len(made), "vault": res.get(book)}


@app.post("/api/paper/pages/{pid}/read", dependencies=[Depends(user)])
def reread_paper_page(pid: str, c=Depends(conn)):
    media.queue(c, "ocr", pid)
    return {"ok": True}


@app.delete("/api/paper/pages/{pid}", dependencies=[Depends(user)])
def delete_paper_page(pid: str, c=Depends(conn)):
    r = c.execute("SELECT * FROM paper_pages WHERE id = ?", (pid,)).fetchone()
    if not r:
        raise HTTPException(404, "No such page")
    paper_pages.save(c, config.load_settings(), pid, [], r["book_id"], r["page"]) if r["book_id"] and r["lines"] else None
    c.execute("DELETE FROM paper_pages WHERE id = ?", (pid,))
    (paper_pages.PAGES / r["photo"]).unlink(missing_ok=True)
    return {"ok": True}


@app.get("/api/booksearch", dependencies=[Depends(user)])
def search_books(q: str = "", c=Depends(conn)):
    q = q.strip()
    if not q:
        rows = c.execute("SELECT id, title, author FROM books WHERE kind = 'book' AND private = 0 "
                         "ORDER BY COALESCE(last_read, 0) DESC, title LIMIT 12").fetchall()
    else:
        rows = c.execute("SELECT id, title, author FROM books WHERE kind = 'book' AND private = 0 AND (title LIKE ? OR author LIKE ?) "
                         "ORDER BY COALESCE(last_read, 0) DESC, title LIMIT 12", (f"%{q}%", f"%{q}%")).fetchall()
    return {"books": [dict(r) for r in rows]}


# ---- the Torah shelf and lookup (Phase 7) -----------------------------------------

@app.get("/api/torah", dependencies=[Depends(user)])
def get_torah(c=Depends(conn)):
    return torah.shelf(c)


@app.post("/api/torah/essay", dependencies=[Depends(user)])
async def post_torah_essay(request: Request, c=Depends(conn)):
    b = await _body(request)
    try:
        return {"id": torah.open_essay(c, str(b.get("path") or ""))}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/lookup", dependencies=[Depends(user)])
def get_lookup(q: str = "", c=Depends(conn)):
    try:
        return lookup.lookup(c, q)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"The dictionary didn't answer: {e}")


@app.post("/api/lookup/context", dependencies=[Depends(user)])
async def post_lookup_context(request: Request):
    import asyncio
    b = await _body(request)
    word, sentence = str(b.get("word") or "").strip(), str(b.get("sentence") or "").strip()[:1500]
    if not word:
        raise HTTPException(400, "Which word?")
    try:
        return await asyncio.to_thread(lookup.in_context, word, sentence)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, str(e))


# ---- the phone ------------------------------------------------------------------

@app.get("/api/phone/nudge")
def phone_nudge(app_name: str = "", force: int = 0, name=Depends(device), c=Depends(conn)):
    return phone.nudge(c, config.load_settings(), app_name, bool(force))


@app.get("/api/phone/widget")
def phone_widget(name=Depends(device), c=Depends(conn)):
    return phone.widget(c, config.load_settings())


@app.get("/api/phone/feed-news")
def phone_feed_news(cursor: int = -1, name=Depends(device), c=Depends(conn)):
    """New posts in the feeds set to notify, for the apps' notifications. The cursor is Daf's own
    order of arrival (a doc's rowid), so an item that reaches Daf late is still new; the first ask
    (no cursor) only learns where things stand, so the backlog never rings."""
    s = config.load_settings()
    feeds = [f for f in s.get("feed_notify") or [] if isinstance(f, str)]
    top = c.execute("SELECT COALESCE(MAX(rowid), 0) FROM docs WHERE where_ = 'feed'").fetchone()[0]
    if cursor < 0 or not feeds:
        return {"cursor": top, "feeds": len(feeds), "items": []}
    rows = c.execute(f"SELECT rowid AS n, id, title, source, feed FROM docs WHERE where_ = 'feed' AND status = 'unseen' AND rowid > ? "
                     f"AND feed IN ({','.join('?' * len(feeds))}) ORDER BY rowid LIMIT 20", (cursor, *feeds)).fetchall()
    return {"cursor": top, "feeds": len(feeds),
            "items": [{"id": r["id"], "title": r["title"], "source": r["source"], "route": "#read/" + _urlq(r["id"], safe="")} for r in rows]}


@app.post("/api/save")
async def device_save(request: Request, name=Depends(device), c=Depends(conn)):
    """Save a link to the Library from a device (the Mac's share menu, a Shortcut): {url, title?, text?}."""
    b = await _body(request)
    url = str(b.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "A link, please")
    saved = phone.save_shared(c, url, str(b.get("title") or ""), str(b.get("text") or ""))
    return {"ok": True, "saved": saved}


# ---- local tools on morten (the desk, the office agent): the Library with a device token ----
# They used to ask Karakeep. A private title never leaves through here.

def _tool_item(r, base):
    return {"id": r["id"], "kind": r["kind"], "title": (r["title"] or r["url"] or "untitled").strip(), "url": r["url"] or "",
            "source": r["source"] or "", "author": r["author"] or "", "note": (r["note"] or "").strip(),
            "summary": (r["ai_summary"] or r["summary"] or "").strip(), "tags": json.loads(r["tags"]) if r["tags"] else [],
            "added": r["added"], "starred": bool(r["starred"]), "archived": r["status"] == "archive", "later": r["status"] == "later",
            "thumb": r["thumb"] if (r["thumb"] or "").startswith("/api/thumb/") else "", "open": base + "/#read/" + _urlq(r["id"], safe="")}


@app.get("/api/tools/library")
def tools_library(view: str = "inbox", limit: int = 40, days: int = 0, name=Depends(device), c=Depends(conn)):
    """What's in the Library, newest first: view inbox (Inbox and Later) | starred | archive;
    days limits it to what was saved lately. {items, counts}."""
    where = {"inbox": "status IN ('inbox', 'later')", "starred": "starred = 1 AND status != 'deleted'",
             "archive": "status = 'archive'"}.get(view)
    if not where:
        raise HTTPException(400, "view: inbox, starred or archive")
    args = [int(time.time()) - days * 86400] if days > 0 else []
    rows = c.execute(f"SELECT * FROM docs WHERE where_ = 'library' AND {where}" + (" AND added >= ?" if args else "") +
                     " ORDER BY added DESC LIMIT ?", (*args, max(1, min(200, limit)))).fetchall()
    s = config.load_settings()
    base = config.public_url(s).rstrip("/")
    priv = lambda r: library.is_private(f"{r['title'] or ''} {r['source'] or ''} {r['author'] or ''}", s)
    counts = {k: c.execute(f"SELECT COUNT(*) FROM docs WHERE where_ = 'library' AND {w}").fetchone()[0]
              for k, w in (("inbox", "status IN ('inbox', 'later')"), ("starred", "starred = 1 AND status != 'deleted'"))}
    return {"items": [_tool_item(r, base) for r in rows if not priv(r)], "counts": counts, "open": base + "/#library"}


@app.post("/api/tools/save")
def tools_save(b=Depends(json_body), name=Depends(device), c=Depends(conn)):
    """{url, title?, note?}: into the Library now (Daf reads the page). {id, already}."""
    from . import pages
    url = str(b.get("url") or "").strip()
    if not re.match(r"^https?://\S+$", url) or len(url) > 2000:
        raise HTTPException(400, "A link, please")
    doc_id, saved = pages.save_page(c, url, str(b.get("title") or "")[:300] or None)
    note = " ".join(str(b.get("note") or "").split())[:1000]
    if note:
        c.execute("UPDATE docs SET note = CASE WHEN COALESCE(note, '') = '' THEN ? ELSE note || char(10) || ? END WHERE id = ?", (note, note, doc_id))
    return {"id": doc_id, "already": not saved}


@app.post("/api/tools/docs/{doc_id}")
def tools_doc(doc_id: str, b=Depends(json_body), name=Depends(device), c=Depends(conn)):
    """{archived?, starred?} on a Library item."""
    d = c.execute("SELECT status, where_ FROM docs WHERE id = ?", (doc_id,)).fetchone()
    if not d or d["where_"] != "library":
        raise HTTPException(404, "Not in the Library")
    try:
        if "archived" in b:
            want = "archive" if b["archived"] else ("inbox" if d["status"] == "archive" else d["status"])
            if want != d["status"]:
                reader.set_status(c, doc_id, want)
        if "starred" in b:
            reader.set_starred(c, doc_id, bool(b["starred"]))
    except ValueError as e:
        raise HTTPException(400, str(e))
    r = c.execute("SELECT status, starred FROM docs WHERE id = ?", (doc_id,)).fetchone()
    return {"id": doc_id, "archived": r["status"] == "archive", "starred": bool(r["starred"])}


@app.get("/api/tools/kindle")
def tools_kindle(days: int = 30, name=Depends(device), c=Depends(conn)):
    """The Kindle's reading for local tools (the desk's Trends, the homepage tile; KoInsight's job
    until 2026-10-20): pages and minutes per day for the last `days` days in the home time zone,
    and today, the last 7 days and the last 30."""
    from datetime import datetime, timedelta
    tz = T.tz_of(config.load_settings())
    days = max(1, min(3660, days))
    today = datetime.now(tz).date()
    first = today - timedelta(days=max(days, 30) - 1)
    start = int(datetime.combine(first, datetime.min.time(), tz).timestamp())
    per = {}
    for ts, dur in c.execute("SELECT start, duration FROM pages WHERE start >= ?", (start,)):
        k = datetime.fromtimestamp(ts, tz).date()
        r = per.setdefault(k, [0, 0.0])
        r[0] += 1
        r[1] += (dur or 0) / 60
    def span(n):
        ds = [today - timedelta(days=i) for i in range(n)]
        return {"pages": sum(per.get(d, [0, 0])[0] for d in ds), "min": round(sum(per.get(d, [0, 0])[1] for d in ds))}
    out = [{"date": (today - timedelta(days=i)).isoformat(), "pages": per.get(today - timedelta(days=i), [0, 0])[0],
            "min": round(per.get(today - timedelta(days=i), [0, 0])[1])} for i in range(days - 1, -1, -1)]
    return {"days": out, "today": span(1), "week": span(7), "month": span(30)}


@app.get("/api/phone", dependencies=[Depends(user)])
def phone_info(c=Depends(conn)):
    devs = [dict(r) for r in c.execute("SELECT name, created, last_seen FROM devices ORDER BY created")]
    return {"devices": devs, "nudges": phone.nudge_stats(c),
            "inbox": [dict(r) for r in c.execute("SELECT * FROM inbox ORDER BY created DESC LIMIT 20")]}


@app.post("/api/phone/token", dependencies=[Depends(user)])
def phone_token(c=Depends(conn)):
    """A new token for the phone (Tasker and the widget). Shown once."""
    c.execute("DELETE FROM devices WHERE name = 'phone'")
    return {"token": auth.new_device_token(c, "phone")}


DEVICE_NAME = re.compile(r"^[a-z0-9-]{1,24}$")


@app.post("/api/devices", dependencies=[Depends(user)])
async def make_device(request: Request, c=Depends(conn)):
    """A token for a named device (the Mac app, the Android app), asked for by a signed-in window.
    A new one replaces that device's old token. Shown once. The Kindle's is made on morten."""
    b = await _body(request)
    name = str(b.get("name") or "").strip().lower()
    if not DEVICE_NAME.match(name):
        raise HTTPException(400, "A name of 1 to 24 lower-case letters, digits or dashes")
    if name == "kindle":
        raise HTTPException(400, "The Kindle's token is made on morten: daf kindle-token kindle")
    c.execute("DELETE FROM devices WHERE name = ?", (name,))
    if name.startswith("android-"):
        # each Android device has its own name now (android-<model>); the old shared "android" goes,
        # and a device still holding it makes its own on its next 401
        c.execute("DELETE FROM devices WHERE name = 'android'")
    return {"name": name, "token": auth.new_device_token(c, name)}


@app.delete("/api/devices/{name}", dependencies=[Depends(user)])
def delete_device(name: str, c=Depends(conn)):
    n = c.execute("DELETE FROM devices WHERE name = ?", (name,)).rowcount
    if not n:
        raise HTTPException(404, "No device by that name")
    return {"ok": True}


SHARED_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Saved to Daf</title><link rel="stylesheet" href="/style.css"></head><body><div class="login"><div style="display:flex;flex-direction:column;gap:14px;max-width:360px">
<h1 style="margin:0">Saved to Daf</h1><p class="mute" style="margin:0">{what}</p><a class="btn primary" href="/#today">Open Daf</a></div></div></body></html>"""


@app.get("/share", response_class=HTMLResponse)
def share(request: Request, url: str = "", title: str = "", text: str = "", c=Depends(conn)):
    if not auth.check_cookie(request.cookies.get(auth.COOKIE)):
        return RedirectResponse("/#today")
    import html
    # A link on some other site could point here with his cookie along (a top-level GET carries it):
    # from anywhere but the share menu or Daf itself, ask first, with a form that posts.
    if request.headers.get("sec-fetch-site", "none") not in ("none", "same-origin"):
        fields = "".join(f'<input type="hidden" name="{k}" value="{html.escape(v)}">' for k, v in (("url", url), ("title", title), ("text", text)))
        return HTMLResponse(SHARED_PAGE.replace(">Saved to Daf<", ">Save to Daf?<").replace("{what}", "Save <b>" + html.escape(title or url or text[:120] or "this link") + "</b> to Daf?"
                                                 '<form method="post" action="/share" style="margin-top:16px">' + fields +
                                                 '<button type="submit" style="font:inherit;padding:8px 18px">Save it</button></form>'))
    saved = phone.save_shared(c, url, title, text)
    what = html.escape(title or saved or text[:120] or "the link")
    return HTMLResponse(SHARED_PAGE.replace("{what}", what + "<br>It goes to your Library on the next sync."))


@app.post("/share")
async def share_post(request: Request, c=Depends(conn)):
    """The share target since Phase 7: a link (to the Library) or a photo (a paper page)."""
    if not auth.check_cookie(request.cookies.get(auth.COOKIE)):
        return RedirectResponse("/#today", status_code=303)
    form = await request.form()
    photo = form.get("photo")
    if photo is not None and hasattr(photo, "read"):
        import tempfile
        data = await photo.read()
        if len(data) > 1000:
            with tempfile.NamedTemporaryFile(suffix=".img") as f:
                f.write(data)
                f.flush()
                pid = paper_pages.add_photo(c, f.name, str(form.get("text") or ""))
            media.queue(c, "ocr", pid)
            return RedirectResponse(f"/#paper/{pid}", status_code=303)
    url, title, text = (str(form.get(k) or "") for k in ("url", "title", "text"))
    saved = phone.save_shared(c, url, title, text)
    import html
    what = html.escape(title or saved or text[:120] or "the link")
    return HTMLResponse(SHARED_PAGE.replace("{what}", what + "<br>It goes to your Library on the next sync."))


# ---- the Kindle plugin --------------------------------------------------------

@app.post("/api/kindle/pages")
async def kindle_pages(request: Request, name=Depends(device), c=Depends(conn)):
    body = await request.json()
    added = kindle.ingest_plugin(c, body.get("books"), body.get("pages"))
    if added:
        kindle.rebuild_sessions(c)
    return {"ok": True, "added": added}


@app.post("/api/kindle/annotations")
def kindle_annotations(b=Depends(json_body), name=Depends(device), c=Depends(conn)):
    """{books: [{md5, file, title, authors, annotations: [...]}]}: each book's KOReader highlights and
    notes, as the Daf plugin read them from its notes file. Kept per book (the newest replaces the
    last) and read on the next sync like a Syncthing copy (library.sidecars), within minutes. Since KoInsight went
    and Syncthing is off on the Kindle, this is how Kindle highlights reach Daf."""
    books = b.get("books")
    if not isinstance(books, list):
        raise HTTPException(400, "books: [...]")
    n = 0
    for x in books[:200]:
        md5 = str((x or {}).get("md5") or "")
        anns = x.get("annotations") if isinstance(x, dict) else None
        if not re.fullmatch(r"[0-9a-f]{32}", md5) or not isinstance(anns, (list, dict)):
            continue
        data = {"partial_md5_checksum": md5, "annotations": anns,
                "doc_props": {"title": str(x.get("title") or "")[:500], "authors": str(x.get("authors") or "")[:500]}}
        c.execute("INSERT OR REPLACE INTO kindle_sidecars (md5, file, data, received) VALUES (?, ?, ?, ?)",
                  (md5, str(x.get("file") or "")[:1000], json.dumps(data, ensure_ascii=False), int(time.time())))
        n += 1
    return {"ok": True, "books": n}             # the next sync (a few minutes) reads them into highlights


@app.get("/api/kindle/today")
def kindle_today(name=Depends(device), c=Depends(conn)):
    """What the Kindle needs for its sleep screen. The Kindle adds its own minutes
    (fresher than ours) to `other`, the counted minutes from every other source."""
    s = config.load_settings()
    day = T.today(s)
    summary = T.day_summary(c, day, s)
    y = T.grid(c, config.YEAR30_START, s)
    other = summary["counted"] - (summary["minutes"]["kindle"] if s["count"]["kindle"] else 0)
    offset = int(datetime.now(T.tz_of(s)).utcoffset().total_seconds())
    gl = goals.summary(c, s)
    m = goals.main_of(gl)
    # `goal` stays the day's minutes target: the Kindle adds its own fresher minutes to `other`.
    # `main` is the main goal, for the screen to show when it isn't minutes a day.
    return {"date": day.isoformat(), "tz_offset": offset, "goal": summary["goal"],
            "counted": summary["counted"], "kindle": summary["minutes"]["kindle"], "other": round(other, 1),
            "year_day": (y["today_index"] or 0) + 1, "year_hours": y["total_hours"], "days_goal": y["days_goal"],
            "main": m and {k: m[k] for k in ("id", "kind", "period", "label", "text", "done", "target", "unit", "met")}}


@app.get("/api/kindle/home")
def kindle_home(name=Depends(device), c=Depends(conn)):
    """Everything the Daf screen on the Kindle shows: today, the review, the nightstand.
    The plugin keeps the last answer, so the screen works with Wi-Fi off."""
    out = kindle_today(name, c)
    s = config.load_settings()
    from . import stats
    st = stats.streaks(c, s)
    out["streak_goal"], out["streak_any"] = st["goal"], st["any"]
    r = review.day_items(c, s)
    out["review"] = [{"id": i["id"], "text": reader.plain(i["text"]), "note": i["user_note"] or i["note"], "title": i["title"],
                      "author": i["author"], "chapter": i["chapter"], "page": i["page"], "action": i["action"]}
                     for i in r["items"]]
    chosen = library.nightstand(c, s)
    out["nightstand_chosen"] = bool(chosen)
    out["nightstand"] = []
    for b in chosen or library.suggest_nightstand(c):
        md5s = [k[4:] for (k,) in c.execute("SELECT key FROM book_keys WHERE book_id = ? AND key LIKE 'md5:%'", (b["id"],))]
        last = c.execute(f"SELECT page, total, start FROM pages WHERE md5 IN ({','.join('?' * len(md5s))}) ORDER BY start DESC LIMIT 1",
                         md5s).fetchone() if md5s else None
        private = bool(b.get("private"))          # still opens by its md5; its name stays in Daf
        out["nightstand"].append({"id": b["id"], "title": "A private book" if private else b["title"], "author": None if private else b["author"], "md5s": md5s,
                                  "page": last["page"] if last else None, "total": last["total"] if last else None,
                                  "last": last["start"] if last else None})
    # For the plugin's Home: today's Hebrew date and this week's parasha, and which books stay off
    # Home (their md5s: Home lists books from KOReader's own history).
    try:
        hd = torah.hebrew_date(c)
        out["hebrew_date"] = hd["text"] if hd else None
    except Exception:  # noqa: BLE001
        out["hebrew_date"] = None
    try:
        out["parasha"] = (torah.calendar(c).get("Parashat Hashavua") or {}).get("name")
    except Exception:  # noqa: BLE001
        out["parasha"] = None
    out["date"] = T.today(s).isoformat()
    priv = [r[0] for r in c.execute("SELECT id FROM books WHERE private = 1")]
    priv += [r[0] for r in c.execute("SELECT id, title, author FROM books WHERE private = 0") if library.is_private(f"{r[1] or ''} {r[2] or ''}", s)]
    out["private_md5s"] = sorted({k[4:] for b in priv for (k,) in c.execute("SELECT key FROM book_keys WHERE book_id = ? AND key LIKE 'md5:%'", (b,))})
    return out


@app.get("/api/kindle/book")
def kindle_book(md5: str = "", name=Depends(device), c=Depends(conn)):
    """For the book just opened on the Kindle: where Daf has Nathan in it, and the highlights made in
    Daf that the Kindle doesn't have yet (the plugin adds them to KOReader)."""
    bid = library.book_for_md5(c, md5.strip().lower())
    if not bid:
        return {"known": False}
    b = c.execute("SELECT title, private FROM books WHERE id = ?", (bid,)).fetchone()
    pos = c.execute("SELECT fraction, chapter, updated FROM book_positions WHERE book_id = ?", (bid,)).fetchone()
    hls = [dict(r) for r in c.execute(
        "SELECT h.id, h.text, h.chapter, h.color, s.user_note AS note FROM highlights h LEFT JOIN review_state s ON s.hl_id = h.id "
        "WHERE h.book_id = ? AND h.source = 'epub' AND h.deleted = 0 AND h.id NOT IN (SELECT hl_id FROM kindle_pushed) "
        "ORDER BY h.created", (bid,))]
    return {"known": True, "book_id": bid, "title": b["title"] if b else None,
            "daf": dict(pos) if pos else None, "highlights": hls}


@app.post("/api/kindle/highlights/ack")
async def kindle_highlights_ack(request: Request, name=Depends(device), c=Depends(conn)):
    b = await _body(request)
    ids = [i for i in (b.get("ids") or []) if isinstance(i, str)]
    c.executemany("INSERT OR REPLACE INTO kindle_pushed (hl_id, device, at) VALUES (?, ?, ?)", [(i, name, int(time.time())) for i in ids])
    return {"ok": True, "acked": len(ids)}


@app.post("/api/kindle/review")
async def kindle_review(request: Request, name=Depends(device), c=Depends(conn)):
    """Keep / Less / Later from the Kindle, one or a queued batch: {"actions": [{"id", "action"}]}."""
    body = await _body(request)
    s = config.load_settings()
    done = 0
    for a in (body.get("actions") if isinstance(body.get("actions"), list) else [body]):
        if isinstance(a, dict) and a.get("action") in ("keep", "less", "later") and \
                c.execute("SELECT 1 FROM highlights WHERE id = ?", (a.get("id"),)).fetchone():
            review.act(c, s, a["id"], a["action"])
            done += 1
    return {"ok": True, "done": done}


# ---- his own typefaces (a font he owns, like Bookerly from the Kindle), for the reading views -----

FONT_MAGIC = {b"\x00\x01\x00\x00": "ttf", b"true": "ttf", b"OTTO": "otf", b"wOFF": "woff", b"wOF2": "woff2"}
FONT_TYPES = {"ttf": "font/ttf", "otf": "font/otf", "woff": "font/woff", "woff2": "font/woff2"}


def _font_dir():
    d = config.STATE / "fonts"
    d.mkdir(parents=True, exist_ok=True)
    return d


@app.get("/api/fonts", dependencies=[Depends(user)])
def get_fonts():
    return {"fonts": config.load_settings().get("fonts", [])}


@app.post("/api/fonts", dependencies=[Depends(user)])
async def post_font(request: Request, name: str = ""):
    """The font file as the body; `name` its file name, which gives the family and the style
    ("Bookerly-BoldItalic.ttf" → Bookerly, bold, italic). Kept in STATE/fonts, for his devices only."""
    data = await request.body()
    kind = FONT_MAGIC.get(data[:4])
    if not kind or not (1000 < len(data) <= 8_000_000):
        raise HTTPException(400, "That isn't a font file Daf can use (TTF, OTF, WOFF or WOFF2, up to 8 MB)")
    stem = re.sub(r"\.(ttf|otf|woff2?)$", "", name.strip(), flags=re.I) or "Font"
    family = re.split(r"[-_ ](?=(?:Regular|Bold|Italic|Light|Medium|Semi|Book|Black|Oblique|Thin|Heavy|Roman))", stem, maxsplit=1, flags=re.I)[0]
    family = re.sub(r"[^\w .'-]", "", family.replace("_", " ")).strip()[:40] or "My font"
    weight = 700 if re.search(r"bold|black|heavy", stem, re.I) else 300 if re.search(r"light|thin", stem, re.I) else 400
    style = "italic" if re.search(r"italic|oblique", stem, re.I) else "normal"
    file = re.sub(r"[^A-Za-z0-9._-]", "-", stem)[:60] + "." + kind
    (_font_dir() / file).write_bytes(data)
    s = config.load_settings()
    fonts = [f for f in s.get("fonts", []) if f.get("file") != file] + [{"file": file, "family": family, "weight": weight, "style": style}]
    s["fonts"] = fonts[-30:]
    config.save_settings(s)
    return {"fonts": s["fonts"], "family": family}


@app.get("/api/fonts/{file}", dependencies=[Depends(user)])
def get_font(file: str):
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,70}\.(ttf|otf|woff2?)", file):
        raise HTTPException(404, "No such font")
    p = _font_dir() / file
    if not p.exists():
        raise HTTPException(404, "No such font")
    return FileResponse(p, media_type=FONT_TYPES[file.rsplit(".", 1)[1]], headers={"Cache-Control": "private, max-age=2592000"})


@app.delete("/api/fonts/{file}", dependencies=[Depends(user)])
def delete_font(file: str):
    s = config.load_settings()
    s["fonts"] = [f for f in s.get("fonts", []) if f.get("file") != file]
    config.save_settings(s)
    if re.fullmatch(r"[A-Za-z0-9._-]{1,70}\.(ttf|otf|woff2?)", file):
        (_font_dir() / file).unlink(missing_ok=True)
    return {"fonts": s["fonts"]}


# ---- offline: what the apps keep on the device ------------------------------------------------

@app.get("/api/offline/plan")
def offline_plan(request: Request, c=Depends(conn)):
    """What Daf for Android (and Mac) fetch ahead to read with no network: {urls} to GET and keep (the
    pages' own requests: a list's order and filters are the device's, so a list should also answer
    for its where/tab/kind/cat with any order), {docs} to keep with their images, {ebooks} to keep
    (their files), {images}. Signed in, or with a device token."""
    h = request.headers.get("authorization", "")
    if not auth.check_cookie(request.cookies.get(auth.COOKIE)) and not auth.check_device(c, h[7:].strip() if h.lower().startswith("bearer ") else None):
        raise HTTPException(401, "Sign in first")
    s = config.load_settings()
    t = T.today(s)
    # Character for character as the pages ask (the apps match on path and query).
    urls = ["/api/me", "/api/settings", "/api/today", "/api/home", "/api/books", "/api/highlights?sort=recent", "/api/stats", "/api/goals",
            "/api/docs/counts", "/api/torah", "/api/recovery", "/api/manga", "/api/manga/prefs", "/api/feed/sources"]
    urls += [f"/api/review?day={(t + timedelta(days=k)).isoformat()}" for k in range(0, 4)]
    lists = [("library", tab, f"&kind={k}") for tab in ("inbox", "later") for k in ("article", "video", "tweet", "pdf", "email")]
    lists += [("library", "inbox", "&kind=starred"), ("feed", "unseen", "&cat=")]
    urls += [f"/api/docs?where={w}&tab={tab}{q}&sort=new&limit=200" for w, tab, q in lists]
    docs = [r[0] for r in c.execute("SELECT id FROM docs WHERE where_ = 'library' AND status IN ('inbox', 'later') AND kind IN ('article', 'tweet', 'email', 'pdf') "
                                    "ORDER BY COALESCE(starred, 0) DESC, added DESC LIMIT 80")]
    docs += [r[0] for r in c.execute("SELECT id FROM docs WHERE where_ = 'feed' AND status = 'unseen' ORDER BY added DESC LIMIT 40")]
    readable = ebooks.readable_ids(c)
    stand = [b["id"] for b in (library.nightstand(c, s) or library.suggest_nightstand(c))]
    recent = [r[0] for r in c.execute("SELECT book_id FROM book_positions ORDER BY updated DESC LIMIT 6")]
    books = [b for b in dict.fromkeys(stand + recent) if b in readable]
    urls += [f"/api/ebooks/{b}" for b in books] + [f"/api/books/{b}" for b in stand]
    urls += ["/api/fonts"] + [f"/api/fonts/{f['file']}" for f in s.get("fonts", []) if f.get("file")]   # his own typefaces
    images = [f"/api/cover/{b}" for b in dict.fromkeys(stand + recent)]
    return {"version": 1, "day": t.isoformat(), "urls": urls, "docs": docs, "ebooks": books, "images": images}


# ---- manga (manga.py): Komga is the library, Daf is where it's read ---------------------------

KOMGA_ID = re.compile(r"^[0-9A-Za-z]{6,40}$")


def _kid(x):
    if not KOMGA_ID.match(x or ""):
        raise HTTPException(404, "No such manga")
    return x


def _manga(fn, *a, **k):
    from . import manga
    try:
        return fn(*a, **k)
    except KeyError:
        raise HTTPException(404, "Komga doesn't have that")
    except manga.MangaError as e:
        raise HTTPException(502, str(e))


@app.get("/api/manga", dependencies=[Depends(user)])
def get_manga():
    from . import manga
    return _manga(manga.shelf)


@app.get("/api/manga/series/{sid}", dependencies=[Depends(user)])
def get_manga_series(sid: str):
    from . import manga
    return _manga(manga.series, _kid(sid))


@app.get("/api/manga/books/{bid}", dependencies=[Depends(user)])
def get_manga_book(bid: str):
    from . import manga
    return _manga(manga.book, _kid(bid))


@app.get("/api/manga/books/{bid}/pages/{n}", dependencies=[Depends(user)])
def get_manga_page(bid: str, n: int, size: int = 1800, crop: int = 0):
    from . import manga
    data, ctype = _manga(manga.page_image, _kid(bid), max(1, n), size, bool(crop))
    return Response(data, media_type=ctype, headers={"Cache-Control": "private, max-age=2592000, immutable"})


@app.get("/api/manga/prefs", dependencies=[Depends(user)])
def get_manga_prefs(c=Depends(conn)):
    from . import manga
    return manga.prefs(c)


@app.put("/api/manga/prefs", dependencies=[Depends(user)])
async def put_manga_prefs(request: Request, c=Depends(conn)):
    from . import manga
    b = await _body(request)
    return _manga(manga.set_prefs, c, b.get("defaults"), b.get("series"))


@app.get("/api/manga/thumb/{kind}/{kid}", dependencies=[Depends(user)])
def get_manga_thumb(kind: str, kid: str):
    from . import manga
    if kind not in ("s", "b"):
        raise HTTPException(404, "No such cover")
    data, ctype = _manga(manga.thumb, kind, _kid(kid))
    return Response(data, media_type=ctype, headers={"Cache-Control": "private, max-age=604800, stale-while-revalidate=2592000"})


@app.put("/api/manga/books/{bid}/progress", dependencies=[Depends(user)])
def put_manga_progress(bid: str, b=Depends(json_body)):
    from . import manga
    try:
        page = int(b.get("page") or 1)
    except (TypeError, ValueError):
        raise HTTPException(400, "page: a number")
    try:
        at = int(b["at"]) if b.get("at") is not None else None
    except (TypeError, ValueError):
        at = None
    sent = _manga(manga.set_progress, _kid(bid), page, bool(b.get("completed")), at)
    return {"ok": True, "sent": sent}


@app.post("/api/manga/beat", dependencies=[Depends(user)])
def post_manga_beat(b=Depends(json_body), c=Depends(conn)):
    from . import manga
    try:
        _manga(manga.beat, c, config.load_settings(), _kid(str(b.get("book") or "")), int(b.get("seconds") or 0), b.get("at"))
    except (TypeError, ValueError):
        raise HTTPException(400, "Bad beat")
    return {"ok": True}


from . import webapi  # noqa: E402 - the browser extension's routes (/api/web); it uses conn and device from above
app.include_router(webapi.router)


@app.get("/api/extension/{name}", dependencies=[Depends(user)])
def get_extension(name: str):
    """The browser extension, packed by extension/build.sh: daf-extension.zip (Chrome, Arc) or .xpi (Firefox, Zen)."""
    if name not in ("daf-extension.zip", "daf-extension.xpi"):
        raise HTTPException(404, "No such file")
    root = config.WEB_DIR.parent / "extension"
    p = root / "dist" / name
    def ver(f):                                  # "…-0.3.0.xpi" → (0, 3, 0): the newest version, not the newest file
        m = re.search(r"-(\d+(?:\.\d+)*)\.xpi$", f.name)
        return tuple(int(x) for x in m.group(1).split(".")) if m else ()
    signed = sorted((root / "signed").glob("*.xpi"), key=ver) if name.endswith(".xpi") else []
    if signed:                                   # Mozilla's signed build, which Zen keeps for good
        p = signed[-1]
    if not p.exists():
        raise HTTPException(404, "Not packed yet: run extension/build.sh on morten")
    return FileResponse(p, media_type="application/zip" if name.endswith(".zip") else "application/x-xpinstall",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})


# The extension updates itself in Firefox and Zen: its manifest names /extension/updates.json
# (gecko.update_url), which they check about once a day, and a newer version there is installed
# without asking. Only Mozilla's signed builds (extension/signed/, from extension/sign.sh) are
# offered, since nothing else installs. Both routes are open, with no sign-in: they're signed builds
# of the extension's code, which is public, and nothing of anyone's.
def _signed_builds():
    root = config.WEB_DIR.parent / "extension"
    out = []
    for f in (root / "signed").glob("*.xpi"):
        m = re.search(r"-(\d+(?:\.\d+)+)\.xpi$", f.name)
        if m:
            out.append((tuple(int(x) for x in m.group(1).split(".")), m.group(1), f))
    return sorted(out)


@app.get("/extension/updates.json")
def extension_updates():
    root = config.WEB_DIR.parent / "extension"
    addon = json.loads((root / "manifest.json").read_text())["browser_specific_settings"]["gecko"]["id"]
    updates = []
    builds = _signed_builds()
    if builds:
        _, version, f = builds[-1]
        updates.append({"version": version,
                        "update_link": f"{config.public_url()}/extension/daf-{version}.xpi",
                        "update_hash": "sha256:" + hashlib.sha256(f.read_bytes()).hexdigest()})
    return JSONResponse({"addons": {addon: {"updates": updates}}}, headers={"Cache-Control": "private, no-cache"})


@app.get("/extension/daf-{version}.xpi")
def extension_build(version: str):
    for _, v, f in _signed_builds():
        if v == version:
            return FileResponse(f, media_type="application/x-xpinstall")
    raise HTTPException(404, "No such version")


# ---- the web app ----------------------------------------------------------------

@app.get("/")
def index():
    """The page, with its scripts and styles fingerprinted (webcache.py)."""
    from . import webcache
    return HTMLResponse(webcache.index_html(), headers={"Cache-Control": "no-cache"})


@app.get("/sw.js")
def service_worker():
    """The service worker, with this version's files and fingerprint filled in."""
    from . import webcache
    return Response(webcache.sw_js(), media_type="text/javascript", headers={"Cache-Control": "no-cache"})


app.mount("/", StaticFiles(directory=config.WEB_DIR), name="web")


def start_sync_thread():
    stop = threading.Event()
    t = threading.Thread(target=sync.loop, args=(stop,), name="daf-sync", daemon=True)
    t.start()
    return stop
