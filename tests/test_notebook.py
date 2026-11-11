"""The Notebook's pages (daf/sketchbook.py): a block written under a highlight's card keeps the
highlight it's under (hl) and where that was (hat), through an edit and a move; a stroke never takes
one; and the list's call gives every page in reading order, its blocks without their strokes.

Run: .venv/bin/python -m unittest discover -s tests
"""
import os
import sqlite3
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))

from daf import db, sketchbook as SB  # noqa: E402

ITEM = "book:cal:1"


def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(db.SCHEMA)
    return c


def stroke(sid, blk):
    return {"id": sid, "kind": "stroke", "blk": blk, "tool": "pen", "color": "ink", "size": 6, "pts": [[10, 20, 0.5], [40, 30, 0.5]], "hl": "e123456789"}


class Anchors(unittest.TestCase):
    def setUp(self):
        self.c = conn()

    def blocks(self, tab="c:ch1"):
        return {b["id"]: b for b in SB.blocks(SB.marks(self.c, ITEM, tab))}

    def test_kept_under_its_card(self):
        SB.change(self.c, ITEM, "c:ch1", [
            {"id": "bwriting01", "kind": "ink", "type": "writing", "ord": 1, "hl": "e1a2b3c4d5e6f7a8b", "hat": 0.4321},
            stroke("kstroke001", "bwriting01"),
            {"id": "ttyped0001", "kind": "text", "text": "Reread this.", "ord": 2, "hl": "e1a2b3c4d5e6f7a8b", "hat": 0.4321},
            {"id": "ttop000001", "kind": "text", "text": "Above the cards.", "ord": 0},
        ], title="Chapter One", pos=0.4)
        b = self.blocks()
        self.assertEqual(b["bwriting01"]["hl"], "e1a2b3c4d5e6f7a8b")
        self.assertEqual(b["bwriting01"]["hat"], 0.4321)
        self.assertEqual(b["ttyped0001"]["hl"], "e1a2b3c4d5e6f7a8b")
        self.assertNotIn("hl", b["ttop000001"])
        st = b["bwriting01"]["strokes"][0]
        self.assertNotIn("hl", st)                       # a stroke is in its block, not under a card

    def test_edit_and_move_keep_or_change_it(self):
        SB.change(self.c, ITEM, "c:ch1", [{"id": "ttyped0001", "kind": "text", "text": "One", "ord": 1, "hl": "eaaaaaaaa", "hat": 0.2}])
        old = self.blocks()["ttyped0001"]
        # typed again (the page sends the block whole, as the vault's merge does)
        SB.change(self.c, ITEM, "c:ch1", [{k: v for k, v in old.items() if k not in ("strokes", "updated")} | {"text": "One, again", "ord": 3}])
        b = self.blocks()["ttyped0001"]
        self.assertEqual((b["text"], b["hl"], b["hat"], b["ord"]), ("One, again", "eaaaaaaaa", 0.2, 3))
        # moved up over its card: above the cards now
        SB.change(self.c, ITEM, "c:ch1", [{"id": "ttyped0001", "kind": "text", "text": "One, again", "ord": 3}])
        self.assertNotIn("hl", self.blocks()["ttyped0001"])

    def test_bad_anchor_left_out(self):
        SB.change(self.c, ITEM, "", [{"id": "tbadanchor", "kind": "text", "text": "x", "ord": 1, "hl": "not an id!", "hat": 0.5}])
        b = self.blocks("")["tbadanchor"]
        self.assertNotIn("hl", b)
        self.assertNotIn("hat", b)

    def test_kindle_text_unchanged(self):
        SB.change(self.c, ITEM, "c:ch1", [{"id": "ttyped0001", "kind": "text", "text": "Words", "ord": 1, "hl": "eaaaaaaaa", "hat": 0.2}])
        self.assertEqual(SB.plain(SB.marks(self.c, ITEM, "c:ch1")), "Words")


class Everything(unittest.TestCase):
    def test_every_page_in_order_without_strokes(self):
        c = conn()
        SB.change(c, ITEM, "c:ch2", [{"id": "tlater0001", "kind": "text", "text": "Later on", "ord": 1}], title="Chapter Two", pos=0.6)
        SB.change(c, ITEM, "c:ch1", [{"id": "bwriting01", "kind": "ink", "type": "writing", "ord": 1, "transcript": "who am I meeting today?", "hl": "eaaaaaaaa", "hat": 0.3},
                                     stroke("kstroke001", "bwriting01"), stroke("kstroke002", "bwriting01")], title="Chapter One", pos=0.2)
        SB.change(c, ITEM, "", [{"id": "tgeneral01", "kind": "text", "text": "Why this book now", "ord": 1}])
        SB.change(c, "book:cal:2", "", [{"id": "tother0001", "kind": "text", "text": "Another book", "ord": 1}])
        out = SB.everything(c, ITEM)
        self.assertEqual([t["tab"] for t in out], ["", "c:ch1", "c:ch2"])
        self.assertEqual(out[1]["title"], "Chapter One")
        ink = out[1]["blocks"][0]
        self.assertEqual((ink["n"], ink["transcript"], ink["hl"]), (2, "who am I meeting today?", "eaaaaaaaa"))
        self.assertNotIn("strokes", ink)
        self.assertEqual([b["kind"] for t in out for b in t["blocks"]], ["text", "ink", "text"])     # no strokes


if __name__ == "__main__":
    unittest.main()
