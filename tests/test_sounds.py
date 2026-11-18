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


class SceneMusic(unittest.TestCase):
    """With a music catalogue (daf/music.py) the model is asked what music suits each scene, in the
    catalogue's own tag words; without one it isn't asked, and nothing about music is kept."""

    def setUp(self):
        self.said, self.words = [], ["sad", "rain", "tender", "battle"]

        def answer(text, timeout=0):
            self.said.append(text)
            return json.dumps([
                {"from": 1, "scene": "Rain", "sounds": {"rain": 0.4}, "music": {"tags": ["Sad", "rain", "made-up", "tender", "battle", "sad"], "energy": 1}},
                {"from": 2, "scene": "Still rain", "sounds": {"rain": 0.4}, "music": {"tags": ["battle"], "energy": 7}},
                {"from": 3, "scene": "Rain again", "sounds": {"rain": 0.4}, "music": {"tags": ["battle"], "energy": None}}])

        for p in (mock.patch.object(ai, "run", answer), mock.patch.object(ai, "model", lambda: "test"),
                  mock.patch.object(soundscape.music, "vocabulary", lambda: self.words)):
            p.start()
            self.addCleanup(p.stop)

    def ask(self):
        return soundscape._ask({"title": "A book"}, {"start": 0, "end": 30}, [(0, "Rain fell."), (10, "It went on."), (20, "And on.")])

    def test_music_is_asked_in_the_catalogues_words(self):
        scenes = self.ask()
        self.assertIn("sad, rain, tender, battle", self.said[0])
        self.assertIn('"music": {"tags"', self.said[0])
        self.assertEqual(scenes[0]["music"], {"tags": ["sad", "rain", "tender", "battle"], "energy": 1})   # its words only, each once, four at most
        self.assertEqual(scenes[1]["music"], {"tags": ["battle"], "energy": None})                          # a new scene for the music alone
        self.assertEqual(len(scenes), 2)                                                                     # the same sounds and music: one scene

    def test_without_music_nothing_is_asked(self):
        self.words = []
        scenes = self.ask()
        self.assertNotIn("music", self.said[0].split("Answer with JSON")[0].split("Nothing fits")[1])
        self.assertNotIn('"music"', self.said[0])
        self.assertEqual(len(scenes), 1)
        self.assertNotIn("music", scenes[0])

    def test_a_scenes_music_sounds_are_named(self):
        self.assertEqual(soundscape._tunes({"rain": 0.4, "piano": 0.5, "calm": 0.3}), ["piano", "calm"])


class Vocabulary(unittest.TestCase):
    def test_the_most_used_tags_first(self):
        from daf import music
        tracks = {"a": {"moods": ["x"], "tags": ["sad", "rain"]}, "b": {"moods": ["x"], "tags": ["sad"]},
                  "c": {"tags": ["unsorted"]}, "d": {"moods": ["x"], "tags": ["off"], "off": True}}
        with tempfile.TemporaryDirectory() as d, mock.patch.object(music, "ROOT", d), mock.patch.object(music, "load", lambda: {"moods": [], "tracks": tracks}):
            self.assertEqual(music.vocabulary(), ["sad", "rain"])
        with mock.patch.object(music, "ROOT", ""):
            self.assertEqual(music.vocabulary(), [])


if __name__ == "__main__":
    unittest.main()
