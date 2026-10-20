"""A sandbox Daf whose outside writes go nowhere: Karakeep, FreshRSS, Hardcover, Komga progress, the
morning email and GitHub get stand-ins that print what they were asked. Reads still go out (Komga
pages, Hardcover search, Kokoro). No sync loop runs; "Sync now" still would, so leave it alone.

    PYTHONPATH=<checkout> DAF_STATE=<a copy of the state> DAF_VAULT=<a scratch vault> \\
      DAF_KINDLE_DIR=<scratch> DAF_CWA_INGEST=<scratch> DAF_FRESHRSS_URL=http://127.0.0.1:9 \\
      python tools/sandbox.py [host] [port]

The email's HTML and a feedback issue's text land in DAF_STATE as sandbox-mail.html and
sandbox-issue.md."""
import hashlib
import os
import sys

import uvicorn

from daf import config, digest, feedback, hardcover, manga
from daf.sources import freshrss, karakeep

OUT = config.STATE


def said(what, *args):
    print(what + " (stand-in):", *args, flush=True)


karakeep.save = lambda url, title=None: said("KARAKEEP SAVE", url) or {"id": "sbx" + hashlib.sha1(url.encode()).hexdigest()[:10]}
karakeep.attach_tags = karakeep.detach_tags = lambda *a, **k: said("KARAKEEP TAGS", *a)
karakeep.set_archived = lambda *a, **k: said("KARAKEEP ARCHIVE", *a)
karakeep.set_favourited = lambda *a, **k: said("KARAKEEP FAVOURITE", *a)
karakeep.upload_pdf = lambda name, data, title=None: said("KARAKEEP PDF", name) or {"id": "sbxpdf"}
karakeep.delete = lambda bid: said("KARAKEEP DELETE", bid) or {}
freshrss.mark_read = lambda ids, read=True: said("FRESHRSS MARK", ids, read)
freshrss.subscribe = lambda url, folder=None: said("FRESHRSS SUBSCRIBE", url, folder) or url
freshrss.subscriptions = lambda: [{"id": "feed/1", "title": "xkcd", "folder": "", "url": "https://xkcd.com/atom.xml", "site": "", "icon": ""}]


def _mail(subject, body_html, body_text):
    (OUT / "sandbox-mail.html").write_text(body_html)
    said("EMAIL", subject)


def _issue(title, body):
    (OUT / "sandbox-issue.md").write_text(title + "\n\n" + body)
    said("GITHUB ISSUE", title)
    return "https://github.com/franz-rosenzweig/old-daf/issues/999"


digest.send_mail = _mail
feedback.file_issue = _issue
_gql = hardcover.gql


def _hardcover(q, v=None):          # reads go to Hardcover; writes never leave the sandbox
    if q.lstrip().startswith("mutation"):
        said("HARDCOVER WRITE", q.split("{")[1].split("(")[0], v)
        return {"insert_list_book": {"id": 1}, "delete_list_book": {"id": 1}, "update_list": {"id": 1}, "update_user_book": {"id": 1}, "insert_user_book": {"id": 1}}
    return _gql(q, v)


hardcover.gql = _hardcover
manga.set_progress = lambda bid, page, completed=False, at=None: said("KOMGA PROGRESS", bid, page, completed)

if __name__ == "__main__":
    if "/srv/docker/daf" in str(config.STATE):
        sys.exit("DAF_STATE points at the real state: give the sandbox a copy")
    host = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DAF_SANDBOX_HOST", "127.0.0.1")
    port = int(sys.argv[2]) if len(sys.argv) > 2 else int(os.environ.get("DAF_SANDBOX_PORT", "8443"))
    uvicorn.run("daf.app:app", host=host, port=port, log_level="warning")
