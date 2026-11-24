"""The Edition's second look (daf/edition.py): pieces earlier editions showed you that you never opened come
back once, ranked by today's taste, and a paper you didn't open at all that day doesn't count against its pieces.

Run: .venv/bin/python -m unittest discover tests
"""
import json
import os
import sqlite3
import sys
import time
import unittest
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))

from daf import db, edition  # noqa: E402

TODAY = date(2026, 3, 18)
NOW = time.mktime((2026, 3, 18, 4, 0, 0, 0, 0, -1))
BODY = json.dumps([{"t": "p", "x": "word " * 400}])
PROF = {"sources": {}, "mult": {}, "words": {}, "rising": [], "facts": {}}


def fresh_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA)
    for table, col, decl in db.MIGRATIONS:
        if col not in {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    return conn


def add_doc(conn, i, title, source, opened=None):
    conn.execute("INSERT INTO docs (id, kind, where_, status, title, source, url, published, added, summary, opened) "
                 "VALUES (?, 'article', 'feed', 'seen', ?, ?, ?, ?, ?, '', ?)",
                 (i, title, source, "https://example.org/" + i, NOW - 10 * 86400, NOW - 10 * 86400, opened))
    conn.execute("INSERT INTO doc_content (id, blocks, fetched) VALUES (?, ?, ?)", (i, BODY, int(NOW)))


def add_edition(conn, days_ago, items):
    d = TODAY - timedelta(days=days_ago)
    conn.execute("INSERT INTO editions (day, made, items, how) VALUES (?, ?, ?, 'rules')",
                 (d.isoformat(), int(NOW - days_ago * 86400), json.dumps(items)))


def item(i, source, section="Ideas", why="You've opened 3 from " , **kw):
    return dict({"id": i, "kind": "article", "section": section, "why": why + source, "title": "Title " + i, "source": source,
                 "minutes": 8, "thumb": "", "url": "", "summary": ""}, **kw)


class SecondLook(unittest.TestCase):
    def setUp(self):
        self.conn = c = fresh_db()
        self.e = dict(edition.DEFAULTS, desks=[edition._desk({"key": "home", "name": "Lisbon", "words": ["lisbon"]})])
        # five days ago: a paper you never opened at all
        for i, src in (("a1", "Aeon"), ("a2", "Nautilus"), ("a3", "Mosaic")):
            add_doc(c, i, "Title " + i, src)
        add_edition(c, 5, [item("a1", "Aeon", section="Lead"), item("a2", "Nautilus"), item("a3", "Mosaic", section="Torah")])
        # three days ago: you read one, passed by the others
        for i, src in (("b1", "Aeon"), ("b2", "Granta"), ("b3", "Daily Lisbon")):
            add_doc(c, i, "Title " + i, src)
        add_doc(c, "b4", "Title b4", "Psyche", opened=NOW - 3 * 86400)
        add_edition(c, 3, [item("b4", "Psyche", section="Lead"), item("b1", "Aeon"), item("b2", "Granta"),
                           item("b3", "Daily Lisbon", section="Lisbon")])
        # yesterday's is too fresh to call back, and one from long ago is too old
        add_doc(c, "y1", "Title y1", "Quanta")
        add_edition(c, 1, [item("y1", "Quanta")])
        add_doc(c, "o1", "Title o1", "Quanta")
        add_edition(c, 40, [item("o1", "Quanta")])

    def tearDown(self):
        self.conn.close()

    def ids(self, cb):
        return [x["id"] for x in cb]

    def test_what_comes_back(self):
        cb = edition.callbacks(self.conn, self.e, PROF, NOW, TODAY)
        got = self.ids(cb)
        # the Torah column and the news desk are for their own day; yesterday's and last month's aren't asked
        self.assertEqual(set(got), {"a1", "a2", "b1", "b2"})
        # never seen (a paper you didn't open) and the lead come first
        self.assertEqual(got[0], "a1")
        self.assertTrue(next(x for x in cb if x["id"] == "a2")["missed"])
        self.assertFalse(next(x for x in cb if x["id"] == "b2")["missed"])

    def test_opened_thumbed_or_read_elsewhere_stays_out(self):
        self.conn.execute("INSERT INTO edition_votes (id, vote, at) VALUES ('a2', -1, ?)", (int(NOW),))
        self.conn.execute("INSERT INTO sessions (id, source, origin, item, title, start, seconds, day) "
                          "VALUES ('k1', 'article', 'kindle', 'b2', 'Title b2', ?, 300, '2026-03-16')", (int(NOW - 2 * 86400),))
        add_doc(self.conn, "dup", "Title b1", "Aeon (mirror)", opened=NOW - 86400)    # the same story, read in another feed's copy
        self.assertEqual(self.ids(edition.callbacks(self.conn, self.e, PROF, NOW, TODAY)), ["a1"])

    def test_once_only(self):
        add_edition(self.conn, 2, [item("a1", "Aeon", section=edition.CALLBACK, callback="2026-03-13")])
        self.assertNotIn("a1", self.ids(edition.callbacks(self.conn, self.e, PROF, NOW, TODAY)))
        # but making today's again doesn't count today's own second look
        add_edition(self.conn, 0, [item("a2", "Nautilus", section=edition.CALLBACK, callback="2026-03-13")])
        self.assertIn("a2", self.ids(edition.callbacks(self.conn, self.e, PROF, NOW, TODAY)))

    def test_take_keeps_the_source_caps(self):
        cb = edition.callbacks(self.conn, self.e, PROF, NOW, TODAY)
        chosen = [{"id": "x", "title": "Something else", "source": "Granta"}, {"id": "y", "title": "And more", "source": "Granta"}]
        got = edition.take_callbacks(cb, chosen, 3, TODAY)
        self.assertEqual([x["source"] for x in got], ["Aeon", "Nautilus"])           # one Aeon only; Granta's full already
        self.assertTrue(all(x["section"] == edition.CALLBACK for x in got))
        self.assertEqual(got[0]["why"], "Missed on Friday · You've opened 3 from Aeon")

    def test_the_line(self):
        c = {"from": "2026-03-01", "missed": False, "why_then": ""}
        self.assertEqual(edition.callback_line(c, TODAY), "Skipped on 1 March")
        c = {"from": "2026-03-15", "missed": True, "why_then": "x" * 70}
        self.assertEqual(edition.callback_line(c, TODAY), "Missed on Sunday")

    def test_a_paper_you_never_opened_doesnt_count_against_it(self):
        sk = edition.skipped(self.conn, NOW)
        srcs = {s for _, _, s, _ in sk}
        self.assertIn("Granta", srcs)           # passed by on a day you read the paper
        self.assertNotIn("Nautilus", srcs)      # the paper you didn't open that day


if __name__ == "__main__":
    unittest.main()
