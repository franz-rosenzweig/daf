"""`daf`: the command line. Ezer and the desk call this; so can you.

    daf doctor                 every source and how fresh it is
    daf sync                   pull every source now
    daf today [--json] [--date YYYY-MM-DD]
    daf year [30|29] [--json]
    daf log-paper MINUTES [--date YYYY-MM-DD | --yesterday | --shabbat] [--pages N] [--note TEXT]
    daf set-password [--user NAME] [--random]   the web login (username "reader" unless changed)
    daf kindle-token NAME      make a token for a device (printed once)
    daf review [--json]        today's highlights
    daf morning [--send]       the morning highlight (with --send: to Signal, and remembered for replies)
    daf note TEXT              file a note (under the morning highlight, or the book open on the Kindle)
    daf voice-note FILE        transcribe a voice note and file it the same way
    daf nightstand [ID ...]    show, or set, the three books on the nightstand
    daf paper-page PHOTO [--caption "page 112 middlemarch"]   read a marked page into highlights
    daf clip TEXT              a podcast link with a time (shared from AntennaPod): transcribe the minute before it
    daf jobs                   transcripts and clips waiting or done
    daf vault-backfill [--dry-run DIR]   rewrite Daf's article notes in the vault the current way
"""
import argparse
import getpass
import json
import secrets
import sys
from datetime import date, timedelta

import subprocess

from . import auth, config, db, library, notes, review, sync, today as T
from .sources import checks, paper


def _bar(minutes, goal=60, width=20):
    filled = min(width, int(round(width * minutes / max(1, goal))))
    return "█" * filled + "░" * (width - filled)


def cmd_doctor(a):
    with db.session() as c:
        res = checks.run_all(c)
    if a.json:
        print(json.dumps(res, indent=2))
        return 0
    for r in res:
        mark = "ok " if r["ok"] else ("-- " if r.get("phase", 1) > 1 else "!! ")
        print(f"{mark} {r['name']:<15} {r['detail']}" + ("" if r["ok"] or r.get("phase", 1) <= 1 else f"  (needed in phase {r['phase']})"))
    return 0 if all(r["ok"] for r in res if r.get("phase", 1) <= 1) else 1


def cmd_sync(a):
    rep = sync.run()
    if not a.quiet:
        for k, v in rep.items():
            print(f"{k:<15} {v}")
    return 0


def cmd_today(a):
    s = config.load_settings()
    d = date.fromisoformat(a.date) if a.date else T.today(s)
    with db.session() as c:
        out = T.day_summary(c, d, s)
        y = T.grid(c, config.YEAR30_START, s)
    out["year30"] = {k: y[k] for k in ("total_hours", "days_read", "days_goal", "today_index")}
    if a.json:
        print(json.dumps(out, indent=2))
        return 0
    m = out["counted"]
    print(f"{d.isoformat()}  {int(m)} of {out['goal']:g} min  {_bar(m, out['goal'])}")
    for src, mins in out["minutes"].items():
        if mins:
            flag = "" if s["count"].get(src) else "  (not counted)"
            print(f"  {config.SOURCE_LABELS[src]:<16} {int(round(mins))} min{flag}")
    for it in out["sessions"]:
        if it["private"]:
            continue
        when = it["start"] or "     "
        print(f"  {when}  {it['title'][:48]:<48} {int(round(it['minutes']))} min")
    yi = y["today_index"]
    if yi is not None:
        print(f"Year 30, day {yi + 1}: {y['total_hours']} h · {y['days_read']} days read · {y['days_goal']} at the goal")
    return 0


def cmd_year(a):
    s = config.load_settings()
    start = config.YEAR30_START if a.which == 30 else config.YEAR29_START
    with db.session() as c:
        g = T.grid(c, start, s)
    if a.json:
        print(json.dumps(g))
        return 0
    print(f"Year {a.which} from {g['start']}: {g['total_hours']} h · {g['days_read']} days read · {g['days_goal']} at the goal")
    return 0


def cmd_log_paper(a):
    s = config.load_settings()
    if not 1 <= a.minutes <= 720:
        print("Minutes should be between 1 and 720", file=sys.stderr)
        return 2
    if a.shabbat:
        d = T.last_shabbat(s)
    elif a.yesterday:
        d = T.today(s) - timedelta(days=1)
    elif a.date:
        d = date.fromisoformat(a.date)
    else:
        d = T.today(s)
    note = a.note if a.note is not None else ("Shabbat" if a.shabbat else "")
    path = paper.append(d, a.minutes, note, pages=max(0, a.pages or 0))
    sync.run()
    with db.session() as c:
        out = T.day_summary(c, d, s)
    when = "today" if d == T.today(s) else d.strftime("%A %b %-d")
    print(f"Logged {a.minutes} min on paper for {when}. That day: {int(out['counted'])} of {out['goal']:g} min.")
    print(f"Vault: {path.relative_to(config.VAULT)}")
    return 0


def cmd_set_password(a):
    user = (a.user or "").strip().lower() or None
    if a.random:
        pw = "-".join(secrets.token_urlsafe(4) for _ in range(4))
        auth.set_password(pw, user=user, rotate=True)
        p = config.STATE / "initial-password.txt"
        p.write_text(pw + "\n")
        p.chmod(0o600)
        print(f"Password set; it is in {p} (readable only by you). Change it with `daf set-password`.")
        return 0
    pw = getpass.getpass("New Daf password: ")
    if len(pw) < 8 or pw != getpass.getpass("Again: "):
        print("Not set: too short, or the two didn't match.", file=sys.stderr)
        return 2
    auth.set_password(pw, user=user, rotate=True)
    (config.STATE / "initial-password.txt").unlink(missing_ok=True)
    print(f"Set. Sign in as {auth.username()} with the new password; other browsers are signed out.")
    return 0


def cmd_kindle_token(a):
    with db.session() as c:
        print(auth.new_device_token(c, a.name))
    return 0


def cmd_review(a):
    s = config.load_settings()
    with db.session() as c:
        r = review.day_items(c, s)
    if a.json:
        print(json.dumps(r, indent=2))
        return 0
    for i, it in enumerate(r["items"], 1):
        mark = f"[{it['action']}]" if it["action"] else "   "
        print(f"{i}. {mark} {it['text'][:110]}\n       {it['title'] or ''}")
    return 0


NOTIFY = config.NOTIFY   # kept for the modules that import it from here


def cmd_morning(a):
    s = config.load_settings()
    with db.session() as c:
        r = review.day_items(c, s)
        if not r["items"]:
            print("No highlights to review today.")
            return 0
        it = r["items"][0]
        title = (it["title"] or "").split(":")[0]
        by = f", {it['author']}" if it.get("author") else ""
        rest = len(r["items"]) - 1
        from . import reader
        msg = (f"today's highlight\n\n\u201c{reader.plain(it['text']).strip().strip('\u201c\u201d\"')}\u201d\n\u2014 {title}{by}\n\n"
               f"Reply with \"n:\" and a thought, and it goes under this highlight in your vault. "
               f"{rest} more in today's review: {config.public_url(s)}/#review")
        if a.send:
            rc = config.notify("Daf", msg, timeout=120)
            if rc != 0:
                print("The message didn't go (no DAF_NOTIFY command, or it failed).", file=sys.stderr)
                return 1
            notes.remember_morning(c, it["id"])
        print(msg)
    return 0


def cmd_note(a):
    s = config.load_settings()
    with db.session() as c:
        print(notes.file_note(c, s, a.text, source="text", explicit=True))
    return 0


def cmd_voice_note(a):
    s = config.load_settings()
    try:
        text = notes.transcribe(a.file)
    except Exception as e:  # noqa: BLE001
        print(f"Couldn't transcribe that voice note: {e}")
        return 1
    if not text:
        print("I couldn't make out any words in that voice note.")
        return 0
    with db.session() as c:
        reply = notes.file_note(c, s, text, source="voice", explicit=False)
    print(f"{reply}\n\n\u201c{text}\u201d")
    return 0


def cmd_nightstand(a):
    s = config.load_settings()
    with db.session() as c:
        if a.ids:
            if len(a.ids) > 3:
                print("Three books at most.", file=sys.stderr)
                return 2
            s["nightstand"] = a.ids
            config.save_settings(s)
        stand = library.nightstand(c, s) or library.suggest_nightstand(c)
    label = "Nightstand" if s.get("nightstand") else "Suggested (nothing chosen yet)"
    print(label + ":")
    for b in stand:
        print(f"  {b['id']:<12} {b['title'][:60]}  {b['progress_note'] or ''}")
    return 0


def cmd_paper_page(a):
    from . import paper_pages
    try:
        print(paper_pages.from_signal(a.photo, a.caption))
    except Exception as e:  # noqa: BLE001
        print(f"Couldn't read that page: {e}")
        return 1
    return 0


def cmd_clip(a):
    from . import media
    url, pos = media.parse_share(a.text)
    if not url:
        print("No link in that.")
        return 1
    try:
        title, pos, text = media.podcast_clip({"url": url, "pos": pos, "title": None})
    except Exception as e:  # noqa: BLE001
        print(f"Couldn't clip that: {e}")
        return 1
    t = int(pos)
    print(f"Clipped {t // 60}:{t % 60:02d} from {title}. It's in your highlights and the vault.\n\n\u201c{text}\u201d")
    return 0


def cmd_jobs(a):
    with db.session() as c:
        for r in c.execute("SELECT id, kind, ref, status, error, created FROM jobs ORDER BY id DESC LIMIT 20"):
            print(f"{r['id']:>4} {r['kind']:<12} {r['status']:<8} {r['ref'][:40]:<40} {(r['error'] or '')[:60]}")
    return 0


def cmd_backup(a):
    """A consistent copy of daf.db (SQLite's online backup, safe while Daf writes), checked and gzipped
    into STATE/backups, 14 kept. Cron runs it at 03:00 so borg-backup.sh (03:30) takes a clean copy
    off-site with the rest of /srv/docker. A failure says so over Signal (notify.sh)."""
    import gzip
    import shutil
    import sqlite3
    import subprocess
    import time as _t
    out_dir = config.STATE / "backups"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_dir.chmod(0o700)                         # your reading history: your eyes only, as Vaultwarden's bundles
    stamp = _t.strftime("%Y-%m-%d-%H%M")
    tmp = out_dir / f".daf-{stamp}.db"
    try:
        src = sqlite3.connect(config.DB_PATH, timeout=30)
        dst = sqlite3.connect(tmp)
        with dst:
            src.backup(dst)
        src.close()
        ok = dst.execute("PRAGMA integrity_check").fetchone()[0]
        dst.close()
        if ok != "ok":
            raise RuntimeError(f"integrity check: {ok}")
        gz = out_dir / f"daf-{stamp}.db.gz"
        with open(tmp, "rb") as f, gzip.open(gz, "wb", compresslevel=6) as g:
            shutil.copyfileobj(f, g)
        gz.chmod(0o600)
        tmp.unlink()
        olds = sorted(out_dir.glob("daf-*.db.gz"))[:-14]
        for o in olds:
            o.unlink()
        print(f"Backed up daf.db: {gz.name}, {gz.stat().st_size / 1e6:.1f} MB ({len(olds)} old ones removed)")
    except Exception as e:  # noqa: BLE001
        tmp.unlink(missing_ok=True)
        msg = f"Daf backup failed: {e}"
        print(msg, file=sys.stderr)
        config.notify("⚠️ Daf backup failed", str(e)[:300])
        return 1


def cmd_karakeep_import(a):
    """Daf takes the Library over from Karakeep (karakeep.take_over), and keeps it from then on."""
    from .sources import karakeep
    if karakeep.mode() != "on" and not a.again:
        print(f"Daf keeps the Library already (Karakeep: {karakeep.mode()}). --again fills in anything still missing.")
        return 0
    with db.session() as conn:
        n = karakeep.take_over(conn, config.load_settings())
    print("Daf keeps the Library now. From Karakeep: " + ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in n.items()))
    return 0


def cmd_podcasts_import(a):
    from . import gpodder
    with db.session() as c:
        r = gpodder.import_nextcloud(c, a.user)
    print(f"From Nextcloud: {r['subs']} subscriptions, {r['removed']} unsubscribed, {r['actions']} episodes' listening.")


def cmd_vault_backfill(a):
    """Daf's notes on articles, videos and podcasts, rewritten with the full text (vaultnotes.backfill).
    --dry-run DIR: copies of the notes as they'd be go there; the vault and Daf's data stay as they are."""
    from pathlib import Path
    from . import vaultnotes
    dry = Path(a.dry_run).resolve() if a.dry_run else None
    if dry and (dry == config.VAULT.resolve() or config.VAULT.resolve() in dry.parents):
        print("--dry-run needs a folder outside the vault", file=sys.stderr)
        return 2
    conn = db.connect()
    try:
        res = vaultnotes.backfill(conn, config.load_settings(), dry=dry)
        conn.rollback() if dry else conn.commit()
    finally:
        conn.close()
    for doc_id, (what, rel) in sorted(res.items(), key=lambda kv: (kv[1][0], kv[1][1] or "")):
        print(f"{what:18} {rel or doc_id}")
    print(("Dry run: the notes as they'd be are in " + str(dry)) if dry else "Done.")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="daf", description="Daf: reading time, highlights and review.")
    sub = p.add_subparsers(dest="cmd", required=True)
    x = sub.add_parser("doctor", help="check every source"); x.add_argument("--json", action="store_true"); x.set_defaults(f=cmd_doctor)
    x = sub.add_parser("backup", help="a consistent copy of daf.db into STATE/backups (cron, 03:00)"); x.set_defaults(f=cmd_backup)
    x = sub.add_parser("karakeep-import", help="Daf takes the Library over from Karakeep, once"); x.add_argument("--again", action="store_true"); x.set_defaults(f=cmd_karakeep_import)
    x = sub.add_parser("podcasts-import", help="subscriptions and listening from Nextcloud's GPodder Sync app"); x.add_argument("--user", default="admin"); x.set_defaults(f=cmd_podcasts_import)
    x = sub.add_parser("sync", help="pull every source now"); x.add_argument("--quiet", action="store_true"); x.set_defaults(f=cmd_sync)
    x = sub.add_parser("today", help="today's reading"); x.add_argument("--json", action="store_true"); x.add_argument("--date"); x.set_defaults(f=cmd_today)
    x = sub.add_parser("year", help="Year 30 or 29"); x.add_argument("which", nargs="?", type=int, default=30, choices=[29, 30]); x.add_argument("--json", action="store_true"); x.set_defaults(f=cmd_year)
    x = sub.add_parser("log-paper", help="log minutes read on paper")
    x.add_argument("minutes", type=int)
    x.add_argument("--pages", type=int, default=0, help="pages read, for a page goal")
    g = x.add_mutually_exclusive_group()
    g.add_argument("--date"); g.add_argument("--yesterday", action="store_true"); g.add_argument("--shabbat", action="store_true")
    x.add_argument("--note")
    x.set_defaults(f=cmd_log_paper)
    x = sub.add_parser("set-password"); x.add_argument("--random", action="store_true"); x.add_argument("--user", help="change the username too")
    x.set_defaults(f=cmd_set_password)
    x = sub.add_parser("kindle-token"); x.add_argument("name"); x.set_defaults(f=cmd_kindle_token)
    x = sub.add_parser("review", help="today's highlights"); x.add_argument("--json", action="store_true"); x.set_defaults(f=cmd_review)
    x = sub.add_parser("morning", help="the morning highlight"); x.add_argument("--send", action="store_true"); x.set_defaults(f=cmd_morning)
    x = sub.add_parser("note", help="file a note"); x.add_argument("text"); x.set_defaults(f=cmd_note)
    x = sub.add_parser("voice-note", help="transcribe and file a voice note"); x.add_argument("file"); x.set_defaults(f=cmd_voice_note)
    x = sub.add_parser("nightstand", help="show or set the nightstand"); x.add_argument("ids", nargs="*"); x.set_defaults(f=cmd_nightstand)
    x = sub.add_parser("paper-page", help="a photo of a marked paper page -> highlights")
    x.add_argument("photo"); x.add_argument("--caption", default=""); x.set_defaults(f=cmd_paper_page)
    x = sub.add_parser("clip", help="transcribe a podcast clip"); x.add_argument("text"); x.set_defaults(f=cmd_clip)
    x = sub.add_parser("jobs", help="transcripts and clips"); x.set_defaults(f=cmd_jobs)
    x = sub.add_parser("vault-backfill", help="rewrite Daf's article notes in the vault with the full text")
    x.add_argument("--dry-run", metavar="DIR", help="write copies there instead; the vault stays as it is"); x.set_defaults(f=cmd_vault_backfill)
    a = p.parse_args(argv)
    return a.f(a)


if __name__ == "__main__":
    sys.exit(main())
