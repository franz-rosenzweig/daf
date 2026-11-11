"""Sound's sounds (daf/soundscape.py, tools/sounds.py): Daf's own are only offered when their file is
here, a missing one is never fetched, and every one of them has a pick that makes it.

Run: .venv/bin/python -m unittest discover tests
"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))

from daf import ai, soundscape  # noqa: E402

spec = importlib.util.spec_from_file_location("daf_sounds_tool", HERE.parent / "tools" / "sounds.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

TEST = {"test-own": ("test-own-1", "a test sound: nowhere")}


class Picks(unittest.TestCase):
    def test_every_own_sound_has_its_pick(self):
        self.assertEqual(set(tool.PICKS), set(soundscape.OWN))
        for id, (file, about) in soundscape.OWN.items():
            p = tool.PICKS[id]
            self.assertEqual(p["file"], file, id)
            self.assertIsInstance(p["sound"], int, id)
            self.assertTrue(p.get("kind") in tool.LOUD or "lufs" in p, id)
            self.assertIsInstance(p["loop"], int, id)    # whole seconds: sound.js rounds the length
            self.assertGreaterEqual(p["loop"], 30, id)
            self.assertTrue(about and len(about) <= 100, id)

    def test_ids_and_files_are_unique(self):
        self.assertFalse(set(soundscape.BORROWED) & set(soundscape.OWN))
        files = [v[0] for v in soundscape.SOUNDS.values()]
        self.assertEqual(len(files), len(set(files)))
        self.assertEqual(soundscape.SOUNDS, {**soundscape.BORROWED, **soundscape.OWN})


class Offered(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.said = []

        def answer(text, timeout=0):
            self.said.append(text)
            return json.dumps([{"from": 1, "scene": "Nowhere", "sounds": {"test-own": 0.5, "rain": 0.4}}])

        def no_fetch(*a, **k):
            raise AssertionError("a sound was fetched")

        for p in (mock.patch.object(soundscape, "DIR", self.dir), mock.patch.dict(soundscape.SOUNDS, TEST),
                  mock.patch.object(ai, "run", answer), mock.patch.object(ai, "model", lambda: "test"),
                  mock.patch("urllib.request.urlopen", no_fetch)):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def ask(self):
        return soundscape._ask({"title": "A book"}, {"start": 0, "end": 10}, [(0, "Rain fell on nowhere.")])

    def test_own_sound_missing(self):
        self.assertNotIn("test-own", soundscape.offered())
        self.assertTrue(set(soundscape.BORROWED) <= set(soundscape.offered()))
        self.assertIsNone(soundscape.sound_file("test-own"))
        scenes = self.ask()
        self.assertNotIn("test-own:", self.said[0])
        self.assertIn("\nrain: ", self.said[0])
        self.assertEqual(scenes[0]["sounds"], {"rain": 0.4})

    def test_own_sound_here(self):
        (self.dir / "test-own-1.mp3").write_bytes(b"ID3" + b"\0" * 20000)
        self.assertIn("test-own", soundscape.offered())
        self.assertEqual(soundscape.sound_file("test-own"), self.dir / "test-own-1.mp3")
        scenes = self.ask()
        self.assertIn("test-own: a test sound: nowhere", self.said[0])
        self.assertEqual(scenes[0]["sounds"], {"test-own": 0.5, "rain": 0.4})

    def test_no_such_sound(self):
        self.assertIsNone(soundscape.sound_file("no-such-sound"))


if __name__ == "__main__":
    unittest.main()
