"""The Edition's news desks and the Kindle's morning wake (daf/edition.py): which desk a piece is on, the
paper's order, the rules' pick keeping the desks, and when the Kindle should wake for the edition.

Run: .venv/bin/python -m unittest discover tests
"""
import os
import sqlite3
import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))

from daf import edition  # noqa: E402

TZ = ZoneInfo("Europe/Lisbon")
# Two made-up desks, as settings "edition.desks" would have them
DESKS = [edition._desk({"key": "far", "name": "Norway", "folders": ["Nordics"], "any": False, "sources": ["NRK"],
                        "words": ["norway", "norwegian", "oslo", "bergen", "storting"], "lean": ["oslo"]}),
         edition._desk({"key": "home", "name": "Lisbon", "folders": ["Portugal"], "any": True,
                        "words": ["lisbon", "portugal", "sintra", "cascais", "porto"], "lean": ["lisbon"], "at_least": 1})]


def piece(title, source="Somewhere", folder="", summary="", score=1.0, **kw):
    c = {"id": title, "kind": "article", "title": title, "source": source, "folder": folder, "summary": summary,
         "score": score, "minutes": 6, "torah": False, "parasha": False, "familiar": True}
    c.update(kw)
    return c


class Desks(unittest.TestCase):
    def desk(self, c):
        d = edition.desk_of(c, DESKS)
        return d["name"] if d else ""

    def test_by_source_folder_and_title(self):
        self.assertEqual(self.desk(piece("Snø i fjellet", source="NRK")), "Norway")
        self.assertEqual(self.desk(piece("City council votes on rent", folder="Portugal")), "Lisbon")
        # a folder for the whole region: only what names the place is on its desk
        self.assertEqual(self.desk(piece("Sweden's new budget", folder="Nordics")), "")
        self.assertEqual(self.desk(piece("Sweden's new budget", folder="Nordics", summary="What it means for Norway")), "Norway")
        self.assertEqual(self.desk(piece("A new tram line for Sintra")), "Lisbon")
        self.assertEqual(self.desk(piece("Portobello's markets")), "")             # "porto" only as a word

    def test_paper_order(self):
        e = {"desks": DESKS}
        chosen = [piece("lead", section="Lead"), piece("w", section="Wildcard"), piece("ideas 1", section="Ideas"),
                  piece("t", section="Torah"), piece("lis", section="Lisbon"), piece("science", section="Science"),
                  piece("nor", section="Norway"), piece("ideas 2", section="Ideas")]
        got = [c["title"] for c in edition.paper_order(chosen, e)]
        self.assertEqual(got, ["lead", "nor", "lis", "ideas 1", "ideas 2", "science", "t", "w"])

    def test_rules_keep_torah_to_its_column(self):
        e = dict(edition.DEFAULTS, desks=[], pieces=6, wildcard=0, torah=1)
        short = [piece(f"Dvar Torah {i}", source=f"Torah {i}", score=3.0 - i / 10, torah=True) for i in range(4)]
        short += [piece(f"Essay {i}", source=f"Mag {i}", score=1.0 - i / 10) for i in range(6)]
        got = edition.pick_local(short, e)
        self.assertEqual(sum(1 for c in got if c["torah"]), 1)
        self.assertEqual(len(got), 6)
        got = edition.pick_local(short, dict(e, torah=2))
        self.assertEqual(sum(1 for c in got if c["torah"]), 2)

    def test_rules_keep_the_desks(self):
        e = dict(edition.DEFAULTS, desks=DESKS, pieces=5, wildcard=0, torah=0)
        short = [piece(f"Essay {i}", source=f"Mag {i}", score=2.0 - i / 10) for i in range(8)]
        short += [piece("Oslo opens a new library", source="NRK", score=0.4, desk="Norway", lean="oslo", desk_rank=0.9),
                  piece("Lisbon heat record", source="Público", score=0.3, desk="Lisbon", lean="lisbon", desk_rank=0.8)]
        sections = [c["section"] for c in edition.pick_local(short, e)]
        self.assertIn("Norway", sections)
        self.assertIn("Lisbon", sections)
        self.assertEqual(len(sections), 5)


class Wake(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE kindle_queue (id TEXT, kind TEXT, ref TEXT, name TEXT, shelf TEXT, path TEXT, size INTEGER,"
                          " requested INTEGER, delivered INTEGER, error TEXT)")
        self.s = {"home_tz": "Europe/Lisbon", "edition": {"on": True, "kindle": True, "hour": 5}}

    def wake(self, *when):
        w = edition.kindle_wake(self.conn, self.s, datetime(*when, tzinfo=TZ))
        return datetime.fromtimestamp(w, TZ).strftime("%a %H:%M") if w else None

    def test_next_morning_skips_a_day_off(self):
        self.assertEqual(self.wake(2026, 11, 20, 21, 0), "Sun 05:15")       # Friday night
        self.assertEqual(self.wake(2026, 11, 21, 12, 0), "Sun 05:15")       # Saturday: no edition
        self.assertEqual(self.wake(2026, 11, 22, 4, 0), "Sun 05:15")

    def test_again_until_it_came(self):
        self.assertEqual(self.wake(2026, 11, 22, 5, 20), "Sun 05:50")
        self.conn.execute("INSERT INTO kindle_queue (name, delivered) VALUES (?, ?)",
                          (edition.kindle_file(datetime(2026, 11, 22).date()), 1))
        self.assertEqual(self.wake(2026, 11, 22, 5, 20), "Mon 05:15")
        self.assertEqual(self.wake(2026, 11, 23, 9, 30), "Tue 05:15")        # past the morning: tomorrow

    def test_off(self):
        self.s["edition"]["kindle"] = False
        self.assertIsNone(self.wake(2026, 11, 22, 4, 0))


if __name__ == "__main__":
    unittest.main()
