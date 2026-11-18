"""Music (daf/music.py, tools/music.py): the catalogue of a music folder, what plays for a mood, the
listening copies, and what scan and tag do to it. Every name here is made up.

Run: .venv/bin/python -m unittest discover tests
"""
import importlib.util
import math
import os
import random
import shutil
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))

from daf import music  # noqa: E402

spec = importlib.util.spec_from_file_location("daf_music_tool", HERE.parent / "tools" / "music.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def tone(path, secs=1.0, hz=220.0, level=0.2):
    """A short sine wave as a WAV file: something real for ffprobe and ffmpeg to read."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"".join(struct.pack("<h", int(32767 * level * math.sin(2 * math.pi * hz * k / 22050))) for k in range(int(22050 * secs))))


def track(path, album="Low Tide", by="The Harbour Lights", n=1, **more):
    return {"path": path, "title": Path(path).stem, "artist": by, "by": by, "album": album, "n": n, "secs": 200.0, **more}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="daf-music-test-"))
        self.root = self.tmp / "library"
        self.root.mkdir()
        self.patches = [mock.patch.object(music, "ROOT", str(self.root)),
                        mock.patch.object(music, "CATALOGUE", self.tmp / "state" / "music" / "catalogue.json"),
                        mock.patch.object(music, "COPIES", self.tmp / "state" / "cache" / "music")]
        for p in self.patches:
            p.start()
        music._cat.update(at=None, data=None)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        music._cat.update(at=None, data=None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def keep(self, *tracks, moods=()):
        music.save({"moods": list(moods), "tracks": {music.track_id(t["path"]): t for t in tracks}})
        return [music.track_id(t["path"]) for t in tracks]


class Catalogue(Base):
    def test_no_catalogue_is_no_music(self):
        self.assertEqual(music.summary(), {"on": False, "moods": [], "albums": []})
        self.assertFalse(music.on())
        self.assertEqual(music.queue(), [])

    def test_only_sorted_tracks_are_offered(self):
        a, b, c, d = self.keep(track("x/one.flac", moods=["still"]), track("x/two.flac"),
                               track("x/three.flac", moods=["still"], off=True), track("x/four.flac", moods=["still"], gone=True))
        self.assertEqual(set(music.offered()), {a})
        self.assertEqual([t["id"] for t in music.queue()], [a])

    def test_summary_counts_moods_tags_and_albums(self):
        self.keep(track("a/1.flac", moods=["piano", "still"], tags=["sad", "rain"]),
                  track("a/2.flac", moods=["piano"], tags=["sad"], n=2),
                  track("b/1.flac", album="High Water", moods=["story"], tags=["wonder"]),
                  moods=["still", "piano"])
        s = music.summary()
        self.assertTrue(s["on"])
        self.assertEqual([m["id"] for m in s["moods"]], ["still", "piano", "story"])     # the kept order, then the rest
        piano = s["moods"][1]
        self.assertEqual((piano["n"], piano["secs"]), (2, 400))
        self.assertEqual(piano["tags"], [{"id": "sad", "n": 2}, {"id": "rain", "n": 1}])
        self.assertEqual([(a["album"], a["n"], a["moods"]) for a in s["albums"]], [("High Water", 1, ["story"]), ("Low Tide", 2, ["piano", "still"])])

    def test_words_are_kept_plain(self):
        self.assertEqual(music.words(["  Sad ", "sad", "Late  Night", "ra/in!", ""]), ["sad", "late night", "ra in"])
        self.assertEqual(music.words("sad"), [])


class Queue(Base):
    def setUp(self):
        super().setUp()
        self.ids = self.keep(
            track("a/1.flac", moods=["piano"], tags=["sad"], energy=1),
            track("a/2.flac", moods=["piano"], tags=["bright"], energy=2, n=2),
            track("b/1.flac", album="High Water", moods=["story"], tags=["sad", "journey"], energy=2),
            track("b/2.flac", album="High Water", moods=["story", "epic"], tags=["battle"], energy=3, n=2),
            track("c/1.flac", album="Salt", moods=["still"], tags=["dark"], energy=1))

    def test_a_mood_and_its_tags_narrow_the_pool(self):
        a1, a2, b1, b2, c1 = self.ids
        q = lambda **k: {t["id"] for t in music.queue(**k)}
        self.assertEqual(q(), set(self.ids))
        self.assertEqual(q(moods=["piano"]), {a1, a2})
        self.assertEqual(q(moods=["piano", "epic"]), {a1, a2, b2})                      # a track between two moods is in both
        self.assertEqual(q(moods=["piano"], tags=["sad"]), {a1})
        self.assertEqual(q(tags=["sad", "dark"]), {a1, b1, c1})
        self.assertEqual(q(moods=["nothing"]), set())

    def test_an_album_plays_in_its_order(self):
        a1, a2, b1, b2, c1 = self.ids
        self.assertEqual([t["id"] for t in music.queue(album=music.album_id(music.load()["tracks"][b1]))], [b1, b2])

    def test_what_played_lately_comes_last(self):
        a1, a2, b1, b2, c1 = self.ids
        for seed in range(5):
            got = [t["id"] for t in music.queue(recent=[c1, a1], rng=random.Random(seed))]
            self.assertEqual(got[-2:], [c1, a1])
            self.assertEqual(set(got[:3]), {a2, b1, b2})

    def test_two_from_one_album_dont_follow_each_other(self):
        rows = [(str(k), {"album": "A" if k < 4 else "B", "by": "x"}) for k in range(6)]
        out = music._spread(rows, 6)
        self.assertEqual([t["album"] for _, t in out], ["A", "B", "A", "B", "A", "A"])

    def test_a_scene_gets_what_fits_it_best(self):
        a1, a2, b1, b2, c1 = self.ids
        self.assertEqual(music.queue(match={"tags": ["battle"], "energy": 3}, n=1, rng=random.Random(1))[0]["id"], b2)
        t = lambda i: music.load()["tracks"][i]
        self.assertGreater(music.fit(t(a1), {"tags": ["sad"], "energy": 1}), music.fit(t(b1), {"tags": ["sad"], "energy": 1}))
        self.assertGreater(music.fit(t(b1), {"tags": ["sad", "journey"]}), music.fit(t(a1), {"tags": ["sad", "journey"]}))
        # within the moods chosen, even when something outside them would fit better
        self.assertEqual({x["id"] for x in music.queue(moods=["piano"], match={"tags": ["battle"], "energy": 3})}, {a1, a2})


class Correct(Base):
    def test_what_you_say_is_kept(self):
        (a,) = self.keep(track("a/1.flac", moods=["piano"], tags=["sad"]), moods=["piano"])
        self.assertIsNone(music.correct("0" * 12, {"off": True}))
        got = music.correct(a, {"moods": ["Still", "Late Night"], "tags": ["Rain"], "energy": 9})
        self.assertEqual((got["moods"], got["tags"], got["energy"]), (["still", "late night"], ["rain"], 3))
        cat = music.load()
        self.assertEqual(cat["moods"], ["piano", "still", "late night"])                # a new mood joins the row
        self.assertTrue(cat["tracks"][a]["said"])
        self.assertTrue(music.correct(a, {"off": True})["off"])
        self.assertEqual(music.queue(), [])
        self.assertFalse(music.correct(a, {"off": False})["off"])
        self.assertEqual(len(music.queue()), 1)


class Albums(Base):
    """The Music page: every album, sorted or not, and saying something about a whole album at once."""

    def setUp(self):
        super().setUp()
        self.a1, self.a2, self.b1, self.b2, self.c1 = self.keep(
            track("a/1.flac", moods=["piano"], tags=["sad"], energy=1),
            track("a/2.flac", moods=["piano"], tags=["bright"], energy=1, n=2, off=True),
            track("b/1.flac", album="High Water"), track("b/2.flac", album="High Water", n=2),
            track("c/1.flac", album="Salt", moods=["still"], gone=True), moods=["piano"])
        self.low, self.high = (music.album_id(music.load()["tracks"][i]) for i in (self.a1, self.b1))

    def test_every_album_is_listed_with_how_far_its_sorted(self):
        got = {a["album"]: a for a in music.albums()}
        self.assertEqual(set(got), {"Low Tide", "High Water"})                         # not the one whose files are gone
        low, high = got["Low Tide"], got["High Water"]
        self.assertEqual((low["n"], low["sorted"], low["off"], low["energy"]), (2, 2, 1, 1))
        self.assertEqual(low["moods"], [{"id": "piano", "n": 2}])
        self.assertEqual(low["tags"], [{"id": "bright", "n": 1}, {"id": "sad", "n": 1}])
        self.assertEqual((high["n"], high["sorted"], high["moods"], high["energy"]), (2, 0, [], None))

    def test_an_album_gives_its_tracks_in_order(self):
        a = music.album(self.low)
        self.assertEqual([(t["id"], t["off"]) for t in a["tracks"]], [(self.a1, False), (self.a2, True)])
        self.assertIsNone(music.album("0" * 12))

    def test_a_whole_album_is_sorted_at_once(self):
        a = music.album_say(self.high, {"add": {"moods": ["Story", "late night"], "tags": ["Sea"]}, "energy": 2})
        self.assertEqual((a["sorted"], a["energy"]), (2, 2))
        self.assertEqual(a["moods"], [{"id": "late night", "n": 2}, {"id": "story", "n": 2}])
        cat = music.load()
        self.assertEqual(cat["moods"], ["piano", "story", "late night"])                # the new moods join the row
        self.assertTrue(all(cat["tracks"][i]["said"] for i in (self.b1, self.b2)))
        self.assertEqual({t["id"] for t in music.queue(moods=["story"])}, {self.b1, self.b2})

    def test_each_track_keeps_what_else_it_had(self):
        music.album_say(self.low, {"add": {"moods": ["still"], "tags": ["night"]}, "remove": {"tags": ["bright"]}})
        t = music.load()["tracks"]
        self.assertEqual((t[self.a1]["moods"], t[self.a1]["tags"]), (["piano", "still"], ["sad", "night"]))
        self.assertEqual((t[self.a2]["moods"], t[self.a2]["tags"], t[self.a2]["off"]), (["piano", "still"], ["night"], True))
        music.album_say(self.low, {"remove": {"moods": ["piano", "still"]}})            # no mood left: not offered any more
        self.assertEqual(music.album(self.low)["sorted"], 0)
        self.assertEqual(music.queue(), [])
        self.assertIsNone(music.album_say("0" * 12, {"add": {"moods": ["x"]}}))

    def test_an_unsorted_album_can_be_heard_whole(self):
        self.assertEqual(music.queue(album=self.high), [])
        self.assertEqual([t["id"] for t in music.queue(album=self.high, every=True)], [self.b1, self.b2])
        self.assertEqual([t["id"] for t in music.queue(album=self.low, every=True)], [self.a1, self.a2])   # the one turned off too
        self.assertEqual([t["id"] for t in music.queue(album=self.low)], [self.a1])


class Copies(Base):
    def test_a_path_cant_leave_the_folder(self):
        (self.tmp / "secret.flac").write_bytes(b"x")
        tone(self.root / "a" / "1.wav")
        self.assertIsNone(music.source({"path": "../secret.flac"}))
        self.assertIsNone(music.source({"path": str(self.tmp / "secret.flac")}))
        self.assertIsNone(music.source({"path": "a/missing.wav"}))
        self.assertEqual(music.source({"path": "a/1.wav"}), (self.root / "a" / "1.wav").resolve())

    def test_gain_evens_the_loudness_without_clipping(self):
        self.assertEqual(music.gain(-26.0, -9.0), 6.0)          # a quiet track comes up
        self.assertEqual(music.gain(-12.0, -0.5), -8.0)         # a loud one comes down
        self.assertEqual(music.gain(-30.0, -4.0), 3.0)          # not past its peaks
        self.assertEqual(music.gain(-50.0, -40.0), 12.0)        # nor by more than 12
        self.assertEqual(music.gain(None, None), 0.0)

    def test_the_oldest_copies_go_first(self):
        music.COPIES.mkdir(parents=True)
        for k, name in enumerate(["old", "mid", "new"]):
            f = music.COPIES / f"{name}.mp3"
            f.write_bytes(b"x" * 1000)
            os.utime(f, (1000 + k, 1000 + k))
        with mock.patch.object(music, "KEEP", 2500):
            music.prune()
        self.assertEqual(sorted(f.stem for f in music.COPIES.glob("*.mp3")), ["mid", "new"])

    @unittest.skipUnless(FFMPEG, "needs ffmpeg")
    def test_a_copy_is_made_once_and_measured(self):
        tone(self.root / "a" / "1.wav", secs=1.5)
        (a,) = self.keep(track("a/1.wav", moods=["still"]))
        p = music.copy_of(a)
        self.assertTrue(p and p.stat().st_size > 2000)
        self.assertEqual(p.read_bytes()[:3] in (b"ID3", b"\xff\xfb\x90"[:3]) or p.read_bytes()[0] == 0xFF, True)
        kept = music.load()["tracks"][a]
        self.assertTrue(-40 < kept["lufs"] < 0)
        with mock.patch.object(music.subprocess, "run", side_effect=AssertionError("made twice")):
            self.assertEqual(music.copy_of(a), p)
        self.assertIsNone(music.copy_of("0" * 12))

    @unittest.skipUnless(FFMPEG, "needs ffmpeg")
    def test_an_unsorted_track_can_be_heard_but_not_a_gone_one(self):
        tone(self.root / "a" / "1.wav")
        tone(self.root / "a" / "2.wav")
        a, b = self.keep(track("a/1.wav"), track("a/2.wav", moods=["still"], gone=True))
        self.assertTrue(music.copy_of(a))
        self.assertIsNone(music.copy_of(b))


class Tool(Base):
    @unittest.skipUnless(FFMPEG, "needs ffprobe")
    def test_scan_adds_keeps_and_follows_a_moved_file(self):
        tone(self.root / "The Harbour Lights" / "Low Tide" / "01 Slack Water.wav", secs=1.0)
        tone(self.root / "The Harbour Lights" / "Low Tide" / "02 Ebb.wav", secs=2.0)
        (self.root / "The Harbour Lights" / "Low Tide" / "cover.jpg").write_bytes(b"x")
        self.assertEqual(tool.scan(self.root, say=lambda *_: None), (2, 0, 0, 0))
        cat = music.load()
        one = music.track_id("The Harbour Lights/Low Tide/01 Slack Water.wav")
        self.assertEqual((cat["tracks"][one]["title"], cat["tracks"][one]["secs"]), ("01 Slack Water", 1.0))
        self.assertNotIn("moods", cat["tracks"][one])
        music.correct(one, {"moods": ["still"], "tags": ["sea"]})
        self.assertEqual(tool.scan(self.root, say=lambda *_: None), (0, 2, 0, 0))
        # the album folder is renamed: what was said about the track comes along
        (self.root / "The Harbour Lights" / "Low Tide").rename(self.root / "The Harbour Lights" / "Low Tide (2019)")
        self.assertEqual(tool.scan(self.root, say=lambda *_: None), (0, 0, 2, 0))
        cat = music.load()
        self.assertNotIn(one, cat["tracks"])
        new = cat["tracks"][music.track_id("The Harbour Lights/Low Tide (2019)/01 Slack Water.wav")]
        self.assertEqual((new["moods"], new["tags"]), (["still"], ["sea"]))

    @unittest.skipUnless(FFMPEG, "needs ffprobe")
    def test_a_sorted_track_whose_file_is_away_stays(self):
        tone(self.root / "a" / "1.wav")
        tone(self.root / "a" / "2.wav", secs=2.0)
        tool.scan(self.root, say=lambda *_: None)
        one, two = music.track_id("a/1.wav"), music.track_id("a/2.wav")
        music.correct(one, {"moods": ["still"]})
        (self.root / "a" / "1.wav").unlink()
        self.assertEqual(tool.scan(self.root, say=lambda *_: None), (0, 1, 0, 1))
        self.assertTrue(music.load()["tracks"][one]["gone"])
        self.assertEqual(music.queue(), [])
        tone(self.root / "a" / "1.wav")                                               # and comes back with it
        tool.scan(self.root, say=lambda *_: None)
        self.assertNotIn("gone", music.load()["tracks"][one])
        (self.root / "a" / "1.wav").unlink()
        tool.scan(self.root, forget=True, say=lambda *_: None)
        self.assertEqual(set(music.load()["tracks"]), {two})

    def test_scan_wont_forget_over_an_empty_folder(self):
        self.keep(track("a/1.flac", moods=["still"]))
        with self.assertRaises(SystemExit):
            tool.scan(self.root, say=lambda *_: None)
        self.assertEqual(len(music.load()["tracks"]), 1)

    def test_tag_goes_by_place_and_the_closer_place_wins(self):
        a1, a2, b1 = self.keep(track("Band/Low Tide/1.flac"), track("Band/Low Tide/2.flac", n=2), track("Band/High Water/1.flac", album="High Water"))
        rules = {"order": ["Still", "piano"], "places": {
            "Band/": {"moods": ["still"], "tags": ["calm"], "energy": 1},
            "Band/Low Tide/": {"moods": ["piano"]},
            "Band/Low Tide/2.flac": {"tags": ["sad", "rain"], "energy": 2, "off": True}}}
        self.assertEqual(tool.tag(rules, say=lambda *_: None), 3)
        cat = music.load()
        self.assertEqual(cat["moods"], ["still", "piano"])
        t = cat["tracks"]
        self.assertEqual((t[a1]["moods"], t[a1]["tags"], t[a1]["energy"]), (["piano"], ["calm"], 1))
        self.assertEqual((t[a2]["moods"], t[a2]["tags"], t[a2]["energy"], t[a2]["off"]), (["piano"], ["sad", "rain"], 2, True))
        self.assertEqual(t[b1]["moods"], ["still"])

    def test_tag_leaves_what_you_said_alone(self):
        (a,) = self.keep(track("Band/Low Tide/1.flac", moods=["piano"]))
        music.correct(a, {"moods": ["story"]})
        rules = {"places": {"Band/": {"moods": ["still"]}}}
        self.assertEqual(tool.tag(rules, say=lambda *_: None), 0)
        self.assertEqual(music.load()["tracks"][a]["moods"], ["story"])
        self.assertEqual(tool.tag(rules, over=True, say=lambda *_: None), 1)
        self.assertEqual(music.load()["tracks"][a]["moods"], ["still"])


if __name__ == "__main__":
    unittest.main()
