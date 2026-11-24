"""The Edition read aloud (daf/edition_audio.py): the script's shape, what the voice is given, the episode's
chapters and file, the private feed, and a play in the podcast app counting as the pieces opened.

Run: .venv/bin/python -m unittest discover tests
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))

from daf import db, edition, edition_audio as EA  # noqa: E402

PS = [{"n": 1, "id": "a1", "section": "Lead", "title": "The harbour at night", "publication": "The Harbour Review",
       "kind": "article", "minutes": 8, "text": "First line of the lead. " * 60, "callback": None},
      {"n": 2, "id": "a2", "section": "Science", "title": "Moss on Mars?", "publication": "Field Notes",
       "kind": "article", "minutes": 4, "text": "Moss grows slowly. " * 40, "callback": None},
      {"n": 3, "id": "a3", "section": "Second look", "title": "An old map", "publication": "Atlas Weekly",
       "kind": "article", "minutes": 5, "text": "Maps lie a little. " * 40, "callback": "Missed on Tuesday"}]
FACTS = {"date": "Wednesday, 18 March", "hebrew": "28 Adar", "parasha": "Vayakhel"}


def fresh_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA)
    for table, col, decl in db.MIGRATIONS:
        if col not in {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    return conn


class Folder(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._dir, self._parts = EA.DIR, EA.PARTS
        EA.DIR, EA.PARTS = self.tmp / "edition-audio", self.tmp / "edition-audio" / "parts"
        EA.DIR.mkdir(parents=True)

    def tearDown(self):
        EA.DIR, EA.PARTS = self._dir, self._parts
        shutil.rmtree(self.tmp, ignore_errors=True)

    def episode(self, key="2026-03-18-1773820800", chapters=None):
        chapters = chapters or [
            {"start": 0, "end": 30, "title": "Headlines"},
            {"start": 31.6, "end": 200, "title": "The harbour at night", "id": "a1", "publication": "The Harbour Review",
             "url": "https://daf.example/#read/a1", "heard": [31.6, 200]},
            {"start": 201.6, "end": 300, "title": "Moss on Mars?", "id": "a2", "publication": "Field Notes",
             "url": "https://daf.example/#read/a2", "heard": [201.6, 290]}]
        m = {"key": key, "day": key[:10], "made": int(key[11:]), "title": "Wednesday, 18 March", "how": "model", "minutes": 20,
             "voice": "af_heart", "speed": 1.0, "seconds": 300.0, "bytes": 12345, "spoken": int(key[11:]) + 900, "took": 600,
             "chapters": chapters, "lines": [[0, 4.5, "Good morning."], [5, 30, "Here's what's in it."]], "parts": []}
        (EA.DIR / f"{key}.json").write_text(json.dumps(m))
        (EA.DIR / f"{key}.mp3").write_bytes(b"ID3" + b"\0" * 100)
        return m


class Script(unittest.TestCase):
    def test_prompt_has_every_piece_the_day_and_the_length(self):
        p = EA.prompt(PS, FACTS, 20)
        for x in ("The harbour at night", "Moss on Mars?", "An old map", "Missed on Tuesday", "Wednesday, 18 March",
                  "28 Adar", "Vayakhel", "about 3100 words", "no more than 3410", "=== intro ===", "=== end ==="):
            self.assertIn(x, p)

    def test_each_piece_gets_its_share_and_the_lead_the_most(self):
        b = EA.budgets(PS, 20)
        self.assertEqual(len(b), 3)
        self.assertEqual(max(b), b[0])
        self.assertAlmostEqual(sum(b), 20 * EA.WPM - sum(EA.FRAME), delta=30)
        self.assertIn(f"Length: about {b[1]} words", EA.prompt(PS, FACTS, 20))
        self.assertTrue(all(x >= 60 for x in EA.budgets(PS * 10, 5)))      # never nothing, however short

    def test_parse_keeps_the_papers_order_and_fills_a_missing_piece(self):
        out = ("=== intro ===\nWednesday. Three pieces.\n\nA harbour, moss, a map.\n"
               "=== 2 ===\nMoss, says Field Notes, grows on Mars. Maybe.\n"
               "=== 1: Lead ===\nThe harbour at night is quiet.\n"
               "=== end ===\nThat's the edition.\n")
        parts = EA.parse(out, PS)
        self.assertEqual([p["key"] for p in parts], ["intro", "1", "2", "3", "end"])
        self.assertEqual(parts[0]["text"], "Wednesday. Three pieces.\n\nA harbour, moss, a map.")
        self.assertEqual(parts[1]["text"], "The harbour at night is quiet.")
        self.assertTrue(parts[3]["text"].startswith("From Atlas Weekly: An old map."))      # the rules' lines for the one it skipped

    def test_parse_refuses_something_that_isnt_a_script(self):
        with self.assertRaises(ValueError):
            EA.parse("Sure! Here's a podcast script about your articles.", PS)
        with self.assertRaises(ValueError):
            EA.parse("=== intro ===\nHello.\n=== end ===\nBye.", PS)       # no pieces at all

    def test_the_voice_gets_no_links_brackets_or_markup(self):
        t = EA.speakable("**Big** news [see](https://x.example/a) at <b>noon</b>.\n\n- a list item\n\n\n# Heading")
        self.assertNotIn("http", t)
        for ch in "*[]()<>#/":
            if ch in "()":
                continue
            self.assertNotIn(ch, t)
        self.assertEqual(t.count("\n\n"), 2)
        self.assertIn("a list item", t)

    def test_rules_script_is_the_day_the_headlines_and_each_opening(self):
        parts = EA.script_rules(PS, FACTS, 3)
        self.assertEqual([p["key"] for p in parts], ["intro", "1", "2", "3", "end"])
        self.assertIn("Wednesday, 18 March", parts[0]["text"])
        self.assertIn("Moss on Mars?", parts[0]["text"])
        self.assertTrue(parts[1]["text"].startswith("From The Harbour Review: The harbour at night."))
        self.assertLess(len(parts[1]["text"].split()), 220)          # its share of three minutes, not the whole text

    def test_opening_ends_on_a_sentence(self):
        self.assertEqual(EA._opening("One two three. Four five six. Seven eight nine ten.", 7), "One two three. Four five six.")


class Voice(Folder):
    def test_parts_and_paragraphs_are_timed_with_the_gaps(self):
        sec = lambda s: b"\x01\x00" * int(EA.RATE * s)       # noqa: E731
        lengths = {"Hello.": 1.0, "Second paragraph.": 2.0, "A piece.": 3.0}
        orig = EA.speak
        EA.speak = lambda text, v, s: sec(lengths[text])
        try:
            pcm, times, lines = EA.voice([{"key": "intro", "text": "Hello.\n\nSecond paragraph."}, {"key": "1", "text": "A piece."}], "v", 1.0)
        finally:
            EA.speak = orig
        g = EA.GAP
        self.assertEqual(times[0], [0, round(1 + g["para"] + 2, 2)])
        self.assertEqual(times[1][0], round(1 + g["para"] + 2 + g["part"], 2))
        self.assertEqual(lines[1][0], round(1 + g["para"], 2))
        self.assertAlmostEqual(len(pcm) / 2 / EA.RATE, 1 + g["para"] + 2 + g["part"] + 3, places=3)

    def test_kokoro_restarting_midway_is_waited_for(self):
        calls = []

        def flaky(text, v, s):
            calls.append(text)
            if len(calls) == 1:
                raise ConnectionResetError("Remote end closed connection without response")
            return b"\x01\x00" * EA.RATE
        orig = EA._kokoro_pcm, EA._wait_for_kokoro
        EA._kokoro_pcm, EA._wait_for_kokoro = flaky, lambda: calls.append("waited")
        try:
            self.assertEqual(len(EA.speak("Hello.", "v", 1.0)), 2 * EA.RATE)
            self.assertEqual(calls, ["Hello.", "waited", "Hello."])
            EA.speak("Hello.", "v", 1.0)                       # kept: not asked again
            self.assertEqual(len(calls), 3)
        finally:
            EA._kokoro_pcm, EA._wait_for_kokoro = orig

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "needs ffmpeg")
    def test_the_mp3_has_its_chapters(self):
        out = EA.DIR / "t.mp3"
        EA.encode(b"\x10\x00\xf0\xff" * EA.RATE * 3, out, "Wednesday, 18 March",
                  [{"start": 0, "end": 2.5, "title": "Headlines"}, {"start": 2.5, "end": 6, "title": "Moss; on = Mars?"}])
        r = subprocess.run(["ffprobe", "-v", "error", "-show_chapters", "-show_format", "-of", "json", str(out)], capture_output=True, text=True)
        info = json.loads(r.stdout)
        self.assertEqual([c["tags"]["title"] for c in info["chapters"]], ["Headlines", "Moss; on = Mars?"])
        self.assertEqual(info["format"]["tags"]["title"], "Wednesday, 18 March")
        self.assertAlmostEqual(float(info["format"]["duration"]), 6, delta=0.3)


class Feed(Folder):
    def test_feed_lists_the_episodes_with_the_token_in_every_address(self):
        self.episode()
        x = EA.feed("tok123", {"public_url": "https://daf.example"})
        root = ET.fromstring(x)
        items = root.findall("./channel/item")
        self.assertEqual(len(items), 1)
        enc = items[0].find("enclosure").attrib
        self.assertEqual(enc["url"], "https://daf.example/api/edition/listen/tok123/2026-03-18-1773820800.mp3")
        self.assertEqual(enc["type"], "audio/mpeg")
        ns = {"podcast": "https://podcastindex.org/namespace/1.0", "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}
        self.assertTrue(items[0].find("podcast:chapters", ns).attrib["url"].endswith("/tok123/2026-03-18-1773820800.chapters.json"))
        self.assertEqual(items[0].find("itunes:duration", ns).text, "300")
        self.assertIn("1. The harbour at night (The Harbour Review)", items[0].find("description").text)

    def test_a_script_waiting_to_be_read_isnt_an_episode(self):
        self.episode()
        (EA.DIR / "2026-03-18-1773899999.script.json").write_text(json.dumps({"parts": [], "how": "model", "minutes": 20}))
        self.assertEqual([m["key"] for m in EA.episodes()], ["2026-03-18-1773820800"])
        self.assertEqual(EA.get(date(2026, 3, 18))["key"], "2026-03-18-1773820800")

    def test_an_episode_without_its_sound_isnt_listed(self):
        self.episode()
        (EA.DIR / "2026-03-18-1773820800.mp3").unlink()
        self.assertEqual(ET.fromstring(EA.feed("t", {"public_url": "https://daf.example"})).findall("./channel/item"), [])

    def test_files_are_only_the_episodes_own(self):
        self.episode()
        self.assertEqual(EA.file_for("2026-03-18-1773820800.mp3")[0], "mp3")
        kind, ch = EA.file_for("2026-03-18-1773820800.chapters.json")
        self.assertEqual(kind, "json")
        self.assertEqual(ch["chapters"][1], {"startTime": 31.6, "endTime": 200, "title": "The harbour at night", "url": "https://daf.example/#read/a1"})
        kind, tr = EA.file_for("2026-03-18-1773820800.transcript.json")
        self.assertEqual(tr["segments"][0], {"startTime": 0, "endTime": 4.5, "body": "Good morning."})
        for bad in ("../daf.db", "2026-03-18-1773820800.json", "x.mp3", "2026-03-18-1773820800.mp3/..", "2026-03-19-1.mp3"):
            self.assertEqual(EA.file_for(bad), (None, None), bad)

    def test_prune_drops_old_episodes(self):
        self.episode("2026-01-01-1767225600")
        self.episode()
        EA.prune(now=1773820800 + 3600)
        self.assertEqual(sorted(p.name for p in EA.DIR.glob("2026-*")), ["2026-03-18-1773820800.json", "2026-03-18-1773820800.mp3"])


class Heard(Folder):
    URL = "https://daf.example/api/edition/listen/tok/2026-03-18-1773820800.mp3"

    def setUp(self):
        super().setUp()
        self.conn = fresh_db()
        for i in ("a1", "a2"):
            self.conn.execute("INSERT INTO docs (id, kind, where_, status, title, source, url, added) VALUES (?, 'article', 'feed', 'seen', ?, 'X', ?, 0)",
                              (i, i, "https://x.example/" + i))
        self.episode()

    def opened(self):
        return {r[0]: r[1] for r in self.conn.execute("SELECT id, opened FROM docs")}

    def test_a_chapter_played_through_counts_as_opened(self):
        self.assertEqual(EA.heard(self.conn, self.URL, 0, 210, 1773830000), ["a1"])
        self.assertEqual(self.opened(), {"a1": 1773830000, "a2": None})

    def test_a_skipped_chapter_doesnt(self):
        self.assertEqual(EA.heard(self.conn, self.URL, 31, 60, 1773830000), [])
        self.assertEqual(EA.heard(self.conn, self.URL, 0, 300, 1773830000), ["a1", "a2"])
        self.assertEqual(EA.heard(self.conn, self.URL, 0, 300, 1773839999), ["a1", "a2"])
        self.assertEqual(self.opened()["a1"], 1773830000)                   # the first time it was opened stays

    def test_anything_else_is_left_alone(self):
        self.assertEqual(EA.heard(self.conn, "https://pods.example/ep1.mp3", 0, 999, 1), [])
        self.assertEqual(EA.heard(self.conn, self.URL.replace("1773820800", "1"), 0, 999, 1), [])

    def test_gpodder_play_names_the_episode_and_marks_the_pieces(self):
        from daf import gpodder
        gpodder.actions_upload(self.conn, [{"podcast": "https://daf.example/api/edition/listen/tok/feed.xml", "episode": self.URL,
                                            "action": "play", "started": 0, "position": 210, "total": 300, "timestamp": "2026-03-18T13:00:00"}])
        self.assertIsNotNone(self.opened()["a1"])
        ep = self.conn.execute("SELECT title, podcast_title, transcript_url, checked FROM gp_episodes WHERE url = ?", (self.URL,)).fetchone()
        self.assertEqual((ep["title"], ep["podcast_title"]), ("Wednesday, 18 March", "Daf Edition"))
        self.assertTrue(ep["transcript_url"].endswith("/tok/2026-03-18-1773820800.transcript.json") and ep["checked"])
        s = self.conn.execute("SELECT title, author, seconds FROM sessions WHERE origin = 'gpodder'").fetchone()
        self.assertEqual((s["title"], s["author"], s["seconds"]), ("Wednesday, 18 March", "Daf Edition", 210))


class Settings(unittest.TestCase):
    def test_off_unless_asked_and_the_length_kept_sensible(self):
        e = edition.settings({"edition": {}})
        self.assertIs(e["audio"], False)
        self.assertEqual(e["audio_minutes"], 20)
        self.assertEqual(edition.settings({"edition": {"audio": True, "audio_minutes": 500}})["audio_minutes"], 45)
        self.assertIs(edition.settings({"edition": {"audio": "yes"}})["audio"], False)
        a = EA.settings({"edition": {"on": True, "audio": True}, "tts_voice": "bf_emma", "tts_speed": 1.1})
        self.assertEqual((a["on"], a["voice"], a["speed"]), (True, "bf_emma", 1.1))
        self.assertFalse(EA.settings({"edition": {"on": False, "audio": True}})["on"])


if __name__ == "__main__":
    unittest.main()
