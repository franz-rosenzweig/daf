"""Pull every source into the index. Safe to run any time; the server runs it every five minutes."""
import logging
import threading
import time

from . import config, db
from . import library, vaultnotes
from . import gpodder, media, reader
from .sources import audiobookshelf, freshrss, highlights, karakeep, kindle, paper

log = logging.getLogger("daf.sync")
_lock = threading.Lock()


def _status(conn, name, ok, detail, last=None):
    conn.execute(
        "INSERT INTO source_status (name, ok, checked, last_data, detail) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(name) DO UPDATE SET ok = excluded.ok, checked = excluded.checked, "
        "last_data = COALESCE(excluded.last_data, last_data), detail = excluded.detail",
        (name, int(ok), int(time.time()), last, detail))


class _Retired(Exception):
    pass


def run():
    """Returns a short report: {source: detail}."""
    report = {}
    with _lock, db.session() as conn:
        conn.commit()      # each source in its own transaction: the write lock isn't held through the next one's network calls
        try:
            if config.load_settings().get("koinsight") == "off":
                raise _Retired()
            n, newest = kindle.import_koinsight(conn)
            _status(conn, "koinsight", True, f"{n} page turns", newest)
            report["koinsight"] = f"{n} page turns"
        except _Retired:
            pass                # KoInsight is retired: the Daf plugin sends the Kindle's pages itself
        except Exception as e:  # noqa: BLE001 - one dead source must not stop the others
            _status(conn, "koinsight", False, str(e))
            report["koinsight"] = f"failed: {e}"
            log.exception("koinsight")
        settings = config.load_settings()
        conn.commit()      # each source in its own transaction: the write lock isn't held through the next one's network calls
        try:
            from . import kindlesend
            kindlesend.scan(conn)
        except Exception:  # noqa: BLE001
            log.exception("kindle epubs")
        conn.commit()      # each source in its own transaction: the write lock isn't held through the next one's network calls
        try:
            n = library.rebuild(conn, settings)
            report["library"] = f"{n} books"
        except Exception as e:  # noqa: BLE001
            report["library"] = f"failed: {e}"
            log.exception("library")
        conn.commit()      # each source in its own transaction: the write lock isn't held through the next one's network calls
        try:
            n = kindle.rebuild_sessions(conn)
            report["kindle"] = f"{n} sittings"
        except Exception as e:  # noqa: BLE001
            report["kindle"] = f"failed: {e}"
            log.exception("kindle sessions")
        conn.commit()      # each source in its own transaction: the write lock isn't held through the next one's network calls
        try:
            n, newest = audiobookshelf.import_sessions(conn)
            _status(conn, "audiobookshelf", True, f"{n} sessions", newest)
            report["audiobookshelf"] = f"{n} sessions"
        except Exception as e:  # noqa: BLE001
            _status(conn, "audiobookshelf", False, str(e))
            report["audiobookshelf"] = f"failed: {e}"
            log.exception("audiobookshelf")
        conn.commit()      # each source in its own transaction: the write lock isn't held through the next one's network calls
        try:
            n = paper.import_entries(conn, __import__("daf.today", fromlist=["tz_of"]).tz_of(settings))
            _status(conn, "paper", True, f"{n} entries")
            report["paper"] = f"{n} entries"
        except Exception as e:  # noqa: BLE001
            _status(conn, "paper", False, str(e))
            report["paper"] = f"failed: {e}"
            log.exception("paper")
        conn.commit()      # each source in its own transaction: the write lock isn't held through the next one's network calls
        try:
            n = highlights.import_all(conn, settings)
            _status(conn, "highlights", True, f"{n} highlights")
            report["highlights"] = f"{n} highlights"
        except Exception as e:  # noqa: BLE001
            _status(conn, "highlights", False, str(e))
            report["highlights"] = f"failed: {e}"
            log.exception("highlights")
        conn.commit()      # each source in its own transaction: the write lock isn't held through the next one's network calls
        try:
            new, total = freshrss.sync(conn, settings)
            reader.apply_edits(conn)
            _status(conn, "freshrss", True, f"{new} new, {total} unread", int(time.time()))
            report["feed"] = f"{new} new, {total} unread in FreshRSS"
        except Exception as e:  # noqa: BLE001
            _status(conn, "freshrss", False, str(e))
            report["feed"] = f"failed: {e}"
            log.exception("freshrss")
        conn.commit()      # each source in its own transaction: the write lock isn't held through the next one's network calls
        try:
            from . import torah
            ids = torah.ensure_week(conn)
            _status(conn, "sefaria", True, f"{len(ids)} readings this week", int(time.time()))
        except Exception as e:  # noqa: BLE001
            _status(conn, "sefaria", False, str(e))
            log.exception("sefaria")
        # Newsletters from Proton (read-only), every quarter hour, for the senders you chose.
        conn.commit()      # each source in its own transaction: the write lock isn't held through the next one's network calls
        try:
            if settings.get("newsletters"):
                last = conn.execute("SELECT v FROM kv WHERE k = 'nl_ran'").fetchone()
                if not last or time.time() - float(last[0]) > 14 * 60:
                    conn.execute("INSERT INTO kv (k, v) VALUES ('nl_ran', ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", (str(time.time()),))
                    from .sources import newsletters
                    report["newsletters"] = f"{newsletters.sync(conn, settings)} new"
        except Exception as e:  # noqa: BLE001
            report["newsletters"] = f"failed: {e}"
            log.exception("newsletters")
        # Hardcover: every half hour, like the vault's own sync. Progress from Daf's reader goes up.
        conn.commit()      # each source in its own transaction: the write lock isn't held through the next one's network calls
        try:
            from . import hardcover
            last = conn.execute("SELECT v FROM kv WHERE k = 'hc_ran'").fetchone()
            if hardcover._key() and (not last or time.time() - float(last[0]) > 29 * 60):
                conn.execute("INSERT INTO kv (k, v) VALUES ('hc_ran', ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", (str(time.time()),))
                hardcover.build_map(conn)
                hardcover.fetch(conn, force=True)
                pushed = hardcover.push_progress(conn, settings)
                hardcover.sync_lists(conn)
                report["hardcover"] = f"{len(pushed)} sent" if pushed else "up to date"
        except Exception as e:  # noqa: BLE001
            report["hardcover"] = f"failed: {e}"
            log.exception("hardcover")
        conn.commit()      # each source in its own transaction: the write lock isn't held through the next one's network calls
        try:
            reader.push_inbox(conn)
            reader.purge_deleted(conn)
            n = karakeep.sync(conn)
            reader.apply_edits(conn)
            reader.queue_summaries(conn, settings)
            _status(conn, "karakeep", True, f"{n} saved", int(time.time()))
            report["library"] = report.get("library", "") + f" · {n} in Karakeep"
        except Exception as e:  # noqa: BLE001
            _status(conn, "karakeep", False, str(e))
            report["karakeep"] = f"failed: {e}"
            log.exception("karakeep")
        conn.commit()      # each source in its own transaction: the write lock isn't held through the next one's network calls
        try:
            for (did,) in conn.execute("SELECT id FROM docs WHERE kind = 'video' AND where_ = 'library' AND status != 'deleted' AND id NOT IN "
                                       "(SELECT id FROM doc_content) AND id NOT IN (SELECT ref FROM jobs WHERE kind = 'captions')").fetchall():
                media.queue(conn, "captions", did)
            media.queue_bookmarks(conn)
            media.prune(conn)
            from . import manga
            manga.prune()
            gpodder.refresh_feeds(conn)
        except Exception as e:  # noqa: BLE001
            report["media"] = f"failed: {e}"
            log.exception("media")
        conn.commit()      # each source in its own transaction: the write lock isn't held through the next one's network calls
        try:
            n = paper.log_reading(conn, settings)
            if n:
                report["reading log"] = f"{n} days of Daf reading written to the vault"
            reader.prune_tts()
        except Exception as e:  # noqa: BLE001
            report["reading log"] = f"failed: {e}"
            log.exception("reading log")
        conn.execute("DELETE FROM ops WHERE at < ?", (int(time.time()) - 30 * 86400,))   # the offline queues' answers, kept a month
        conn.commit()      # each source in its own transaction: the write lock isn't held through the next one's network calls
        try:
            res = vaultnotes.write_all(conn, settings)
            report["vault"] = ", ".join(f"{v}" for v in sorted(set(res.values()))) or "nothing to write"
        except Exception as e:  # noqa: BLE001
            report["vault"] = f"failed: {e}"
            log.exception("vault notes")
    return report


def manga_index():
    """Outside run(): the first pass hashes the whole manga library, and that mustn't hold the
    sync's transaction open."""
    try:
        from . import manga
        manga.refresh_index()
    except Exception:  # noqa: BLE001
        log.exception("manga index")


def full_articles():
    """Outside run() too: the feeds set to "always load the full article" fetch pages, which can
    take a while, and no transaction may wait on the network (fulltext.backfill keeps each write short)."""
    try:
        from . import fulltext
        fulltext.backfill(config.load_settings())
    except Exception:  # noqa: BLE001
        log.exception("fulltext")


def loop(stop):
    while not stop.is_set():
        try:
            run()
        except Exception:  # noqa: BLE001
            log.exception("sync")
        manga_index()
        full_articles()
        extras()
        stop.wait(config.SYNC_EVERY_SECONDS)


def extras():
    """After each sync, outside its transaction: the morning email when it's time, feedback that
    couldn't reach GitHub, and an import a restart interrupted."""
    from . import digest, feedback, imports
    for f in (digest.maybe_send, feedback.retry, imports.resume):
        try:
            f()
        except Exception:  # noqa: BLE001
            log.exception(f.__module__)
