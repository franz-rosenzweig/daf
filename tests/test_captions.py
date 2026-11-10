"""YouTube's captions into a transcript (daf/media.py `_parse_vtt`).

The fixtures are short stretches of real YouTube auto-caption files, as yt-dlp downloads them:
- iw9SZgyahqg: a talk with punctuation, where every line used to come out three times.
- plly_ewBSDE: an interview, with ">>" for another voice, "[clears throat]", and real stutters.
- tpI0XWjIsqI: older captions with no punctuation, and one-word lines YouTube doesn't time.

Run: .venv/bin/python -m unittest discover tests
"""
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))   # importing daf never touches the real state

from daf import media  # noqa: E402


def fixture(name):
    return (HERE / "fixtures" / name).read_text(encoding="utf-8")


def said(lines):
    return " ".join(l["x"] for l in lines)


def doubled(text, shortest=3):
    """Every run of words (3 to 20 of them) that comes twice in a row."""
    w = text.split()
    return [" ".join(w[i:i + n]) for n in range(shortest, 21) for i in range(len(w) - 2 * n + 1)
            if w[i:i + n] == w[i + n:i + 2 * n]]


def rolling(*spoken):
    """A caption file in YouTube's rolling shape: each line typed out word by word under the one before,
    a 10 ms cue showing the line just finished, and the next cue opening with it."""
    cues, prev, t = [], " ", 0.0

    def ts(s):
        return f"00:00:{int(s):02d}.{int(s * 1000) % 1000:03d}"
    for line in spoken:
        first, *rest = line.split(" ")
        timed = first + "".join(f"<{ts(t + 0.2 * (i + 1))}><c> {w}</c>" for i, w in enumerate(rest))
        cues.append(f"{ts(t)} --> {ts(t + 2)} align:start position:0%\n{prev}\n{timed}")
        cues.append(f"{ts(t + 2)} --> {ts(t + 2.01)} align:start position:0%\n{line}\n ")
        prev, t = line, t + 2.01
    return "WEBVTT\nKind: captions\nLanguage: en\n\n" + "\n\n".join(cues) + "\n"


class RollingCaptions(unittest.TestCase):
    def test_each_line_comes_once(self):
        text = said(media._parse_vtt(fixture("youtube-auto-iw9SZgyahqg.vtt")))
        self.assertIn("It's the original NP-complete problem, which means if you could solve it fast, "
                      "you could solve every other NP problem fast.", text)
        self.assertEqual(text.count("NP-complete problem"), 1)
        self.assertEqual(doubled(text), [])

    def test_every_word_said_is_kept_in_order(self):
        vtt = fixture("youtube-auto-iw9SZgyahqg.vtt")
        timed = " ".join(x for _, cue in media._vtt_cues(vtt) for x, t in cue if t)
        self.assertTrue(said(media._parse_vtt(vtt)).endswith(timed))

    def test_paragraphs_break_at_sentences(self):
        lines = media._parse_vtt(fixture("youtube-auto-iw9SZgyahqg.vtt"))
        self.assertGreater(len(lines), 3)
        self.assertTrue(all(len(l["x"]) < 400 for l in lines))
        np = next(l for l in lines if "NP-complete" in l["x"])
        self.assertEqual(np["ts"], 98)
        self.assertTrue(np["x"].startswith("And your job is to find a setting of variables"))
        self.assertTrue(np["x"].endswith("every other NP problem fast."))

    def test_voices_noise_and_real_stutters(self):
        lines = media._parse_vtt(fixture("youtube-auto-plly_ewBSDE.vtt"))
        text = said(lines)
        self.assertNotIn(">>", text)
        self.assertNotIn("clears throat", text)
        self.assertIn("this much much larger global chessboard.", text)       # said twice, kept twice
        self.assertIn("It's it's in a sense two wars", text)
        self.assertEqual(doubled(text, 4), [])
        self.assertEqual([l["ts"] for l in lines if l["x"].startswith("This war is taking place")], [812])

    def test_unpunctuated_and_untimed_one_word_lines(self):
        text = said(media._parse_vtt(fixture("youtube-auto-tpI0XWjIsqI.vtt")))
        self.assertTrue(text.endswith("let us know in the comments you"))
        self.assertEqual(text.count("comments"), 1)
        self.assertEqual(doubled(text), [])

    def test_a_line_said_twice_stays_twice(self):
        text = said(media._parse_vtt(rolling("I told him no.", "I told him no.", "And I meant it every time.")))
        self.assertEqual(text, "I told him no. I told him no. And I meant it every time.")

    def test_one_word_said_twice_on_its_own_lines(self):
        text = said(media._parse_vtt(rolling("Wait.", "Wait.", "Listen to this.")))
        self.assertEqual(text, "Wait. Wait. Listen to this.")


class PlainCaptions(unittest.TestCase):
    def test_hand_made_captions_read_as_before(self):
        vtt = ("WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nShe walked in.\n\n"
               "00:00:03.000 --> 00:00:05.000\nNobody looked up.\n\n"
               "00:00:09.000 --> 00:00:11.000\n[Music]\n\n"
               "00:00:11.000 --> 00:00:13.000\n- [Ana] Then the lights\nwent out.\n")
        lines = media._parse_vtt(vtt)
        self.assertEqual([(l["ts"], l["spk"], l["x"]) for l in lines],
                         [(1, None, "She walked in. Nobody looked up."), (11, "Ana", "Then the lights went out.")])


def tracks(*langs):
    return {lang: [{"ext": "vtt", "url": "https://example.invalid/" + lang}] for lang in langs}


class TrackChoice(unittest.TestCase):
    """media.caption_track, on the track lists yt-dlp's info.json gives (subtitles = made by a person)."""

    def test_made_by_a_person_under_another_code(self):            # tpI0XWjIsqI: a punctuated en-US track
        info = {"subtitles": tracks("en-US"), "automatic_captions": tracks("en", "en-orig", "en-US", "fr", "he")}
        self.assertEqual(media.caption_track(info), "en-US")

    def test_automatic_only_reads_plain_en_as_before(self):       # iw9SZgyahqg
        info = {"subtitles": {}, "automatic_captions": tracks("en-orig", "en", "he", "de")}
        self.assertEqual(media.caption_track(info), "en")

    def test_english_before_hebrew_and_plain_before_regional(self):
        self.assertEqual(media.caption_track({"subtitles": tracks("he", "en-GB", "en")}), "en")
        self.assertEqual(media.caption_track({"subtitles": tracks("he", "en-GB")}), "en-GB")

    def test_hebrew_by_a_person_before_automatic_english(self):
        info = {"subtitles": tracks("iw"), "automatic_captions": tracks("en", "iw-orig")}
        self.assertEqual(media.caption_track(info), "iw")

    def test_other_languages_and_live_chat_dont_count(self):
        self.assertEqual(media.caption_track({"subtitles": tracks("fr", "live_chat"), "automatic_captions": tracks("en")}), "en")
        self.assertIsNone(media.caption_track({"subtitles": tracks("fr"), "automatic_captions": tracks("de")}))
        self.assertIsNone(media.caption_track({}))


class Rebuild(unittest.TestCase):
    def test_old_transcripts_are_found_and_new_ones_are_not(self):
        vtt = fixture("youtube-auto-iw9SZgyahqg.vtt")
        new = media._blocks_from_lines(media._parse_vtt(vtt), [])
        old = [{"t": "cue", "x": "It's the original NP-complete problem, which means if you NP-complete problem, which "
                                 "means if you NP-complete problem, which means if you could solve it fast, you could "
                                 "solve could solve it fast, you could solve could solve it fast, you could solve"}]
        self.assertGreaterEqual(media.doubled_runs(old), 3)
        self.assertEqual(media.doubled_runs(new), 0)


if __name__ == "__main__":
    unittest.main()
