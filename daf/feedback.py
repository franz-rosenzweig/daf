"""Send feedback (⌘K → Send feedback, or Preferences): a note about Daf, with where Daf was and what
went wrong lately, kept here and filed as an issue on the private repo, labelled "feedback", where
the next working session picks it up. GitHub through `gh` as lander (the service's own user).

A private title never goes to GitHub: the page's title is left out when it is one.
"""
import json
import os
import subprocess
import time

from . import config, db, library

# Private: a report carries what you wrote and what went wrong. Never the public code repo.
REPO = os.environ.get("DAF_FEEDBACK_REPO", "franz-rosenzweig/old-daf")
GH = "/usr/bin/gh"


def _body(text, ctx, settings):
    ctx = dict(ctx or {})
    title = ctx.pop("title", None)
    if title and library.is_private(title, settings):
        title = "(a private title)"
    errors = ctx.pop("errors", None) or []
    lines = [text.strip(), "", "---", "", "| | |", "|---|---|"]
    for k, label in (("route", "Where"), ("device", "Device"), ("app", "App"), ("size", "Window"), ("theme", "Theme"), ("online", "Online")):
        if ctx.get(k) not in (None, ""):
            lines.append(f"| {label} | `{str(ctx[k])[:200]}` |")
    if title:
        lines.append(f"| Page | {str(title)[:200]} |")
    if errors:
        lines += ["", "<details><summary>What went wrong lately</summary>", "", "```"]
        lines += [str(e)[:400] for e in errors[-12:]]
        lines += ["```", "</details>"]
    lines += ["", "_Sent from Daf's Send feedback._"]
    return "\n".join(lines)


def file_issue(title, body):
    """The issue's address. Raises RuntimeError."""
    subprocess.run([GH, "label", "create", "feedback", "-R", REPO, "--color", "c2a26b", "--description", "From Daf's Send feedback"],
                   capture_output=True, text=True, timeout=30)          # already there is fine
    r = subprocess.run([GH, "issue", "create", "-R", REPO, "--title", title, "--body", body, "--label", "feedback"],
                       capture_output=True, text=True, timeout=60)
    url = (r.stdout or "").strip().splitlines()[-1:] or [""]
    if r.returncode != 0 or not url[0].startswith("https://"):
        raise RuntimeError((r.stderr or r.stdout or "gh said nothing").strip()[-300:])
    return url[0]


def _title(text):
    first = " ".join(text.strip().splitlines()[0].split()) if text.strip() else "Feedback"
    return first if len(first) <= 80 else first[:77].rsplit(" ", 1)[0] + "…"


def send(conn, text, ctx):
    """Keeps it, then files it. Returns {id, issue?, error?}."""
    text = str(text or "").strip()[:8000]
    if not text:
        raise ValueError("Write something first")
    ctx = ctx if isinstance(ctx, dict) else {}
    cur = conn.execute("INSERT INTO feedback (at, text, ctx) VALUES (?, ?, ?)", (int(time.time()), text, json.dumps(ctx)[:20000]))
    fid = cur.lastrowid
    conn.commit()
    try:
        url = file_issue(_title(text), _body(text, ctx, config.load_settings()))
        conn.execute("UPDATE feedback SET issue = ?, error = NULL WHERE id = ?", (url, fid))
        return {"id": fid, "issue": url}
    except Exception as e:  # noqa: BLE001 - kept; the sync loop tries again
        conn.execute("UPDATE feedback SET error = ? WHERE id = ?", (str(e)[:300], fid))
        return {"id": fid, "error": str(e)[:300]}


def retry():
    """From the sync loop: what couldn't reach GitHub, for a day. Only ones whose first try failed
    (error set), and not in the first two minutes, so a request still filing it isn't doubled. One
    given up on is said on Signal, once, so it isn't lost."""
    now = int(time.time())
    with db.session() as c:
        rows = [dict(r) for r in c.execute("SELECT id, text, ctx FROM feedback WHERE issue IS NULL AND error IS NOT NULL "
                                           "AND at > ? AND at < ? ORDER BY id LIMIT 5", (now - 86400, now - 120))]
        lost = [dict(r) for r in c.execute("SELECT id, text FROM feedback WHERE issue IS NULL AND at <= ? AND COALESCE(error, '') NOT LIKE 'told:%'",
                                           (now - 86400,))]
    s = config.load_settings()
    for r in rows:
        try:
            url = file_issue(_title(r["text"]), _body(r["text"], json.loads(r["ctx"] or "{}"), s))
        except Exception as e:  # noqa: BLE001
            with db.session() as c:
                c.execute("UPDATE feedback SET error = ? WHERE id = ?", (str(e)[:300], r["id"]))
            break
        with db.session() as c:
            c.execute("UPDATE feedback SET issue = ?, error = NULL WHERE id = ?", (url, r["id"]))
    for r in lost:
        config.notify("Daf", "Feedback that never reached GitHub (it's still in Daf, Preferences → Feedback):\n\n" + r["text"][:600])
        with db.session() as c:
            c.execute("UPDATE feedback SET error = 'told: ' || COALESCE(error, '') WHERE id = ?", (r["id"],))


def recent(conn, n=10):
    return [dict(r) for r in conn.execute("SELECT id, at, text, issue, error FROM feedback ORDER BY id DESC LIMIT ?", (n,))]
