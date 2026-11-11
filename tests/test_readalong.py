"""The whole audiobook matched to the book (daf/readalong.py), with no recording and no real book.

The book is made up: sentences of nonsense words, the same every run, zipped into a small EPUB. "What
whisper heard" is made from those sentences, one thing said per sentence at a narrator's pace, with a
word dropped or misheard now and then, as whisper does. So every test knows where each thing said
really is in the text, and can ask for exactly that:
- every sentence read gets its point, at its first character, in order;
- credits, and a stretch of another text in the middle, leave no points, and the matching goes on;
- an abridged recording (a third of the book skipped) is found again where it goes on;
- heard ten minutes at a time, with a restart in between, it comes to the same points;
- a recording of another text is told apart before any of the long work;
- the job itself stops and goes on, and what the reader gets counts words the way the book does.

Run: .venv/bin/python -m unittest discover tests
"""
import json
import os
import random
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))   # importing daf never touches the real state

from daf import audiomap, config, db, readalong  # noqa: E402

SYL = "ba ne lo ri tu sha mi ko ve dan el or fin gal hu ist jo kal lem mor nu pra quo ras sil tor um val wen yo zar bri cle dro".split()


def words(seed, n=700):
    r = random.Random(seed)
    out = set()
    while len(out) < n:
        out.add("".join(r.choice(SYL) for _ in range(r.randint(1, 3))))
    return sorted(out)


def prose(seed, sentences, vocab):
    """[sentence, ...]: 5 to 16 words each, a capital first and a full stop last."""
    r = random.Random(seed)
    out = []
    for _ in range(sentences):
        ws = [r.choice(vocab) for _ in range(r.randint(5, 16))]
        out.append(" ".join(ws).capitalize() + ".")
    return out


VOCAB = words(1)
BOOK = [prose(10 + ch, 120, VOCAB) for ch in range(5)]          # five chapters of 120 sentences
OTHER = prose(99, 400, words(2))                                # another text altogether


def epub(path):
    """The made-up book as an EPUB: a title page, then a file a chapter, five sentences a paragraph."""
    page = '<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>t</title></head><body>%s</body></html>'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                   '<rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        items = ['<item id="t" href="title.xhtml" media-type="application/xhtml+xml"/>'] + [f'<item id="c{i}" href="c{i}.xhtml" media-type="application/xhtml+xml"/>' for i in range(len(BOOK))]
        refs = ['<itemref idref="t"/>'] + [f'<itemref idref="c{i}"/>' for i in range(len(BOOK))]
        z.writestr("content.opf", '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0"><metadata/>'
                   f'<manifest>{"".join(items)}</manifest><spine>{"".join(refs)}</spine></package>')
        z.writestr("title.xhtml", page % "<h1>A Made-Up Book</h1><p>Nobody wrote it.</p>")
        for i, ch in enumerate(BOOK):
            paras = "".join("<p>" + " ".join(ch[k:k + 5]) + "</p>" for k in range(0, len(ch), 5))
            z.writestr(f"c{i}.xhtml", page % (f"<h2>Chapter {i + 1}</h2>" + paras))


def said(sentences, t=0.0, seed=5, noise=0.06):
    """Sentences as whisper would give them back: [(start, end, text)], 2.6 words a second and a breath
    between, a word in sixteen dropped or misheard, no capitals it didn't feel like."""
    r = random.Random(seed)
    out = []
    for s in sentences:
        ws = s.rstrip(".").split()
        heard = []
        for w in ws:
            x = r.random()
            if x < noise / 2:
                continue
            heard.append(w + "sh" if x < noise else w)
        dur = len(ws) / 2.6
        out.append((round(t, 2), round(t + dur, 2), " ".join(heard) + "."))
        t += dur + 0.4
    return out


class Matching(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name) / "book.epub"
        epub(cls.path)
        cls.B = audiomap.book(cls.path)
        cls.all = [s for ch in BOOK for s in ch]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def at(self, sentence):
        c = self.B["text"].find(sentence)
        self.assertGreaterEqual(c, 0, sentence)
        return c

    def test_every_sentence_gets_its_point(self):
        segs = said(self.all)
        pts = readalong.match(self.B, segs, readalong.fresh())
        by_t = dict(pts)
        off = [by_t[a] - self.at(s) for (a, _, _), s in zip(segs, self.all) if a in by_t]
        self.assertGreater(len(off), 0.96 * len(segs))         # the rest: five words, and one of them misheard
        self.assertGreater(off.count(0), 0.85 * len(segs))     # at its first character
        self.assertTrue(all(0 <= d < 25 for d in off))         # or a word on, when one of its first three was dropped
        self.assertEqual([c for _, c in pts], sorted(c for _, c in pts))
        self.assertEqual([t for t, _ in pts], sorted({t for t, _ in pts}))

    def test_credits_and_another_text_leave_no_points(self):
        credits = said(OTHER[:8])
        first = said(self.all[:150], t=credits[-1][1] + 2)
        other = said(OTHER[20:60], t=first[-1][1] + 1)          # a foreword the EPUB doesn't have, say
        rest = said(self.all[150:300], t=other[-1][1] + 1)
        st = readalong.fresh()
        pts = readalong.match(self.B, credits + first + other + rest, st)
        self.assertFalse([p for p in pts if p[0] < first[0][0]])
        self.assertFalse([p for p in pts if other[0][0] <= p[0] < rest[0][0]])
        # the book's first sentences are found once there are enough of them to ask the whole book with
        self.assertLess(min(t for t, _ in pts), first[12][0])
        after = [p for p in pts if p[0] >= rest[0][0]]
        self.assertGreater(len(after), 0.9 * len(rest))
        self.assertEqual(after[0][1], self.at(self.all[150]))
        self.assertLess(st["found"], st["said"])

    def test_an_abridged_recording_is_found_where_it_goes_on(self):
        a, b = self.all[:120], self.all[330:500]                # 210 sentences cut: far past where it looks first
        one = said(a)
        two = said(b, t=one[-1][1] + 0.6)
        pts = readalong.match(self.B, one + two, readalong.fresh())
        on = [p for p in pts if p[0] >= two[0][0]]
        self.assertGreaterEqual(on[0][1], self.at(b[0]))
        self.assertLess(on[0][0], two[10][0])                   # within the ten sentences it takes to be sure
        self.assertGreater(len(on), 0.9 * (len(two) - 10))
        self.assertFalse([p for p in pts if self.at(a[-1]) + len(a[-1]) < p[1] < self.at(b[0])])

    def test_a_stretch_at_a_time_comes_to_the_same(self):
        segs = said(self.all)
        whole = readalong.match(self.B, segs, readalong.fresh())
        st, parts = readalong.fresh(), []
        for k in range(0, len(segs), 70):
            parts += readalong.match(self.B, segs[k:k + 70], st)
            st = json.loads(json.dumps(st))                     # as it's kept between stretches, and after a restart
        self.assertEqual(parts, whole)

    def test_a_place_in_one_is_a_place_in_the_other(self):
        segs = said(self.all[:200], noise=0)
        pts = readalong.match(self.B, segs, readalong.fresh())
        p = ([t for t, _ in pts], [c for _, c in pts])
        k = 77
        c = self.at(self.all[k])
        self.assertAlmostEqual(readalong.time_at(p, c), segs[k][0], delta=0.05)
        self.assertEqual(readalong.char_at(p, segs[k][0]), c)
        mid = readalong.char_at(p, (segs[k][0] + segs[k][1]) / 2)        # halfway through it: inside the sentence
        self.assertTrue(c < mid < c + len(self.all[k]))
        self.assertIsNone(readalong.char_at(p, segs[-1][1] + 600))       # past the last point: not known
        self.assertIsNone(readalong.time_at(p, self.at(self.all[400])))

    def test_another_text_is_told_apart_first(self):
        files = [("one", 0.0, 3000.0), ("two", 3000.0, 3000.0)]
        mine = lambda path, local, dur, off: said(self.all[int(off + local) // 20:][:8], t=off + local)
        theirs = lambda path, local, dur, off: said(OTHER[int(off + local) // 20:][:8], t=off + local)
        quiet = lambda path, local, dur, off: []
        self.assertTrue(readalong.is_it(self.B, files, mine))
        self.assertFalse(readalong.is_it(self.B, files, theirs))
        self.assertTrue(readalong.is_it(self.B, files, quiet))          # nothing said there: the long work will say


class Job(unittest.TestCase):
    """build(): the points kept as it goes, a stop in the middle, and going on from there."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.was = (config.STATE, config.DB_PATH, readalong._pair)
        config.STATE = Path(self.tmp.name)
        config.DB_PATH = config.STATE / "daf.db"
        self.path = config.STATE / "book.epub"
        epub(self.path)
        readalong._pair = lambda conn, book_id: ("item-1", self.path)
        self.all = [s for ch in BOOK for s in ch]
        self.segs = said(self.all)
        self.files = [(str(self.path), 0.0, 1800.0), (str(self.path), 1800.0, round(self.segs[-1][1] - 1800.0 + 5, 2))]   # (any file that's there)
        self.heard = []

    def tearDown(self):
        config.STATE, config.DB_PATH, readalong._pair = self.was
        self.tmp.cleanup()

    def hear(self, path, local, dur, off):
        self.heard.append((path, local, dur))
        return [s for s in self.segs if off + local <= s[0] < off + local + dur]

    def test_it_stops_and_goes_on(self):
        calls = 0

        def breaks(path, local, dur, off):
            nonlocal calls
            if dur > 100:                                      # (the five short listens before the work don't count)
                calls += 1
                if calls == 3:
                    raise RuntimeError("the server went down")
            return self.hear(path, local, dur, off)

        with self.assertRaises(RuntimeError):
            readalong.build("b1", hear=breaks, files=self.files)
        with db.session() as conn:
            m = readalong.meta(conn, "b1")
            self.assertEqual((m["state"], m["done"]), ("going", 1200.0))
            self.assertIsNone(readalong.points(conn, "b1"))    # not for the reader until it's whole
        self.heard = []
        m = readalong.build("b1", hear=self.hear, files=self.files)
        self.assertEqual(m["state"], "ready")
        self.assertEqual(self.heard[0][1:], (1200.0, 600))     # from where it stopped, and nothing heard twice
        self.assertFalse([h for h in self.heard if h[2] == 40])
        with db.session() as conn:
            t, c = readalong.points(conn, "b1")
            self.assertEqual(readalong.status(conn, "b1"), {"state": "ready", "done": 1.0})
        whole = readalong.match(audiomap.book(self.path), self.segs, readalong.fresh())
        self.assertEqual(list(zip(t, c))[:len(whole)], whole)  # the same as heard in one go (and where the last one ended)
        self.assertGreater(len(t), 0.9 * len(self.segs))
        self.assertEqual(c, sorted(c))

    def test_the_job_has_its_own_worker(self):
        from daf import media
        was = (readalong._hear, readalong._files)
        readalong._hear, readalong._files = self.hear, lambda item: self.files
        try:
            with db.session() as conn:
                media.queue(conn, "bookmap", "b4")
                media.queue(conn, "bookmap", "b4")                 # pressed twice: one job
                self.assertEqual(conn.execute("SELECT count(*) FROM jobs").fetchone()[0], 1)
                self.assertEqual(readalong.status(conn, "b4"), {"state": "queued", "done": 0.0})
            self.assertFalse(media._run_one("main"))               # hours of whisper never hold up a reel or a page
            self.assertFalse(media._run_one("long"))               # nor a podcast's transcript
            self.assertTrue(media._run_one("book"))
        finally:
            readalong._hear, readalong._files = was
        with db.session() as conn:
            self.assertEqual(media.job_status(conn, "bookmap", "b4")["status"], "done")
            self.assertEqual(readalong.status(conn, "b4"), {"state": "ready", "done": 1.0})

    def test_what_the_reader_gets_counts_words(self):
        readalong.build("b2", hear=self.hear, files=self.files)
        with db.session() as conn:
            r = readalong.for_reader(conn, "b2")
        B = audiomap.book(self.path)
        self.assertEqual(len(r["secs"]), 1 + len(BOOK))
        self.assertEqual(sum(n for _, n in r["secs"]), len(B["words"]))
        # the 40th sentence of the third chapter: the word its point says, in that chapter's own count
        s = BOOK[2][40]
        k = self.all.index(s)
        i = r["t"].index(round(self.segs[k][0], 1))
        w0, n = r["secs"][3]
        local = r["w"][i] - w0
        self.assertTrue(0 <= local < n)
        chapter_words = audiomap._norm_words("Chapter 3 " + " ".join(BOOK[2]))
        self.assertEqual(chapter_words[local:local + 3], audiomap._norm_words(s)[:3])

    def test_a_recording_of_another_text(self):
        theirs = said(OTHER * 3)
        m = readalong.build("b3", hear=lambda path, local, dur, off: [s for s in theirs if off + local <= s[0] < off + local + dur], files=self.files)
        self.assertEqual(m["state"], "other")
        with db.session() as conn:
            self.assertEqual(readalong.status(conn, "b3")["state"], "other")
            self.assertIsNone(readalong.for_reader(conn, "b3"))


if __name__ == "__main__":
    unittest.main()
