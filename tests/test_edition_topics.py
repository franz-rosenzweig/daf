"""The Edition's topics (daf/edition.py): adding one of your own, removing one, and "Name them again"
keeping yours and leaving the removed ones out. The model is a stand-in; the settings go to a scratch folder.

Run: .venv/bin/python -m unittest discover tests
"""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))

from daf import ai, config, edition  # noqa: E402

PROFILE = {"topics": [], "sources": {}, "words": {}, "rising": [], "named": [], "recent": [], "down": []}
NAMED = {"topics": [{"name": "AI & tools", "words": ["model", "agents", "llm"]},
                    {"name": "Torah & Jewish thought", "words": ["parasha", "talmud", "midrash"]},
                    {"name": "Writing craft", "words": ["essay", "editing", "prose"]}]}


def names():
    return [t["name"] for t in edition.settings()["topics"]]


def topic(name):
    return next(t for t in edition.settings()["topics"] if t["name"] == name)


class Topics(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        state = Path(self.tmp.name)
        self.said = []                      # what the model was asked

        def answer(text, timeout=0, s=None):
            self.said.append(text)
            if self.model is None:
                raise RuntimeError("no model here")
            return "Here you go:\n" + json.dumps(self.model)

        self.model = NAMED
        for p in (mock.patch.object(config, "STATE", state), mock.patch.object(config, "SETTINGS_PATH", state / "settings.json"),
                  mock.patch.object(ai, "run", answer), mock.patch.object(edition, "taste", lambda conn, *a: PROFILE)):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def name_them(self):
        return edition.seed_topics(conn=object())

    def test_add_with_my_words(self):
        edition.add_topic("  Woodworking ", "Lathe, chisels; Dovetail joints, lathe")
        self.assertEqual(topic("Woodworking"), {"name": "Woodworking", "words": ["lathe", "chisel", "dovetail", "joint"], "adj": "more", "mine": True})
        self.assertEqual(self.said, [])     # words were given: the model isn't asked

    def test_add_asks_the_model_once(self):
        self.model = {"words": ["joinery", "Lathe", "workbench", "planes"]}
        edition.add_topic("woodworking")                    # typed small: it gets its capital
        self.assertEqual(topic("Woodworking")["words"], ["woodworking", "joinery", "lathe", "workbench", "plane"])
        self.assertEqual(len(self.said), 1)
        self.assertIn('"Woodworking"', self.said[0])

    def test_add_without_the_model(self):
        self.model = None
        with self.assertLogs("daf.edition", "WARNING"):
            edition.add_topic("Bread baking")
        self.assertEqual(topic("Bread baking")["words"], ["bread", "baking"])
        with self.assertLogs("daf.edition", "WARNING"), self.assertRaises(ValueError):      # nothing in the name to go by, and nobody to ask
            edition.add_topic("AI")
        self.assertEqual(names(), ["Bread baking"])

    def test_what_is_kept(self):
        with self.assertRaises(ValueError):
            edition.add_topic("   ")
        edition.add_topic("X" * 60, ["w%02d%s" % (i, "ord") for i in range(50)])
        t = edition.settings()["topics"][0]
        self.assertEqual((len(t["name"]), len(t["words"])), (40, 30))

    def test_mine_is_used_like_any_topic(self):
        self.name_them()
        edition.add_topic("Woodworking", "lathe chisel dovetail")
        e = edition.settings()
        self.assertEqual(edition.topic_of(set(edition.words("A new lathe and a dovetail jig")), e["topics"])["name"], "Woodworking")
        now = time.time()
        w = {t["name"]: t for t in edition.topic_weights([(now, 1.0, "Shop Notes", "Sharpening a chisel", "opened"),
                                                        (now, 1.0, "Blog", "Editing an essay", "opened")], e, now)}
        self.assertGreater(w["Woodworking"]["weight"], 0)
        self.assertEqual((w["Woodworking"]["adj"], w["Woodworking"]["mine"], w["Writing craft"]["mine"]), ("more", True, False))

    def test_remove_sticks(self):
        self.name_them()
        edition.remove_topic("writing CRAFT")
        self.assertEqual(names(), ["AI & tools", "Torah & Jewish thought"])
        self.assertEqual(edition.settings()["topics_removed"], ["Writing craft"])
        self.name_them()
        self.assertEqual(names(), ["AI & tools", "Torah & Jewish thought"])
        self.assertIn("removed these topics", self.said[-1])
        self.assertIn("Writing craft", self.said[-1])
        edition.remove_topic("Not on the list")
        self.assertEqual(edition.settings()["topics_removed"], ["Writing craft"])

    def test_name_them_again_keeps_mine(self):
        self.name_them()
        edition.add_topic("Woodworking", "lathe chisel")
        edition.save({"topics": [dict(t, adj="less") if t["name"] in ("Woodworking", "AI & tools") else t for t in edition.settings()["topics"]]})
        self.model = {"topics": [{"name": "AI & tools", "words": ["model", "prompt"]}, {"name": "woodworking", "words": ["saw"]},
                                 {"name": "History", "words": ["empire", "medieval"]}]}
        self.name_them()
        self.assertEqual(names(), ["AI & tools", "History", "Woodworking"])        # the model's, then mine; its "woodworking" isn't a second one
        self.assertEqual(topic("Woodworking"), {"name": "Woodworking", "words": ["lathe", "chisel"], "adj": "less", "mine": True})
        self.assertEqual(topic("AI & tools"), {"name": "AI & tools", "words": ["model", "prompt"], "adj": "less"})
        self.assertIn("topics of their own", self.said[-1])
        edition.remove_topic("Woodworking")                                         # mine can go too, and stays gone
        self.name_them()
        self.assertEqual(names(), ["AI & tools", "History"])

    def test_adding_one_that_is_there_or_was_removed(self):
        self.name_them()
        edition.add_topic("writing craft")                  # the model's becomes mine: no second one, its words kept
        self.assertEqual(names().count("Writing craft"), 1)
        self.assertEqual(topic("Writing craft"), {"name": "Writing craft", "words": ["editing", "essay", "prose"], "adj": "", "mine": True})
        edition.remove_topic("AI & tools")
        edition.add_topic("AI & tools", "llm agents")       # changed my mind: it's back and no longer on the removed list
        self.assertEqual(edition.settings()["topics_removed"], [])
        self.assertTrue(topic("AI & tools")["mine"])

    def test_not_plain_settings(self):
        self.assertIn("topics_removed", edition.OWN)        # the page can't overwrite the list as an ordinary setting
        self.assertNotIn("topics_removed", {k for k in edition.settings() if k not in edition.OWN})


if __name__ == "__main__":
    unittest.main()
