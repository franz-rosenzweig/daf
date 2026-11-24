"""The Edition's Kindle front page (daf/frontpage.py, kindlesend.make_epub with a Paper): which picture
counts as a photograph, the first page's links, the cover, and the book that comes out.

Run: .venv/bin/python -m unittest discover tests
"""
import io
import json
import os
import random
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))

from PIL import Image, ImageDraw  # noqa: E402

from daf import frontpage, kindlequeue, kindlesend, reader  # noqa: E402

DAY = date(2026, 3, 17)


def photo(w=640, h=400, seed=1):
    """Something with a photograph's spread of greys."""
    rng = random.Random(seed)
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            v = (x * 255 // w + y * 255 // h) // 2 + rng.randint(-40, 40)
            px[x, y] = (max(0, min(255, v)), max(0, min(255, v - 20)), max(0, min(255, v + 20)))
    out = io.BytesIO()
    im.save(out, "JPEG")
    return out.getvalue()


def logo(w=640, h=400):
    """A wordmark on white: two colours."""
    im = Image.new("RGB", (w, h), "white")
    ImageDraw.Draw(im).rectangle((100, 150, 540, 250), fill=(200, 20, 20))
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


FACE = photo(seed=9)
ITEMS = [
    {"id": "a", "kind": "article", "section": "Lead", "title": "The long essay about rivers", "source": "Aeon", "publication": "Aeon",
     "minutes": 12, "why": "You've opened 9 from Aeon", "summary": "Rivers keep their own time."},
    {"id": "b", "kind": "article", "section": "Lisbon", "title": "A tram line for Sintra", "source": "Lisbon Daily", "publication": "Lisbon Daily",
     "minutes": 4, "why": "Sintra news", "summary": ""},
    {"id": "c", "kind": "video", "section": "Watch", "title": "No transcript yet", "source": "A channel", "minutes": 20, "why": "", "summary": ""},
    {"id": "d", "kind": "article", "section": "Torah", "title": "פרשת השבוע: על הדרך", "source": "Torah Musings", "minutes": 6, "why": "", "summary": ""},
]


class Pictures(unittest.TestCase):
    def test_photo_or_not(self):
        self.assertGreaterEqual(frontpage.photo_score(photo()), frontpage.PHOTO)
        self.assertLess(frontpage.photo_score(logo()), frontpage.PHOTO)
        self.assertEqual(frontpage.photo_score(photo(1200, 200)), 0)       # a banner
        self.assertEqual(frontpage.photo_score(photo(200, 150)), 0)        # too small
        self.assertEqual(frontpage.photo_score(b"not an image"), 0)

    def test_first_photograph_in_the_papers_order(self):
        got = frontpage.pick_picture(ITEMS, {"a": [("u1", logo())], "b": [("u2", photo())], "d": [("u3", photo(seed=2))]})
        self.assertEqual((got[0], got[2]), ("b", "u2"))
        self.assertIsNone(frontpage.pick_picture(ITEMS, {"a": [("u1", logo())]}))

    def test_a_face_is_passed_over(self):
        saved = frontpage.big_face
        frontpage.big_face = lambda data: data == FACE
        try:
            got = frontpage.pick_picture(ITEMS, {"a": [("u1", FACE)], "b": [("u2", photo())]})
            self.assertEqual(got[0], "b")                                    # the lead's portrait is passed over
            self.assertIsNone(frontpage.pick_picture(ITEMS, {"a": [("u1", FACE)]}))   # and the page goes without
        finally:
            frontpage.big_face = saved

    def test_an_opencv_without_cascades_turns_the_check_off(self):
        import types
        saved = sys.modules.get("cv2")
        sys.modules["cv2"] = types.ModuleType("cv2")          # like OpenCV 5: no CascadeClassifier
        frontpage._faces.cache_clear()
        try:
            self.assertIsNone(frontpage._faces())
            self.assertFalse(frontpage.big_face(photo()))
        finally:
            if saved is None:
                sys.modules.pop("cv2", None)
            else:
                sys.modules["cv2"] = saved
            frontpage._faces.cache_clear()

    def test_a_photograph_without_a_face(self):
        if frontpage._faces() is None:
            self.skipTest("no OpenCV")
        self.assertFalse(frontpage.big_face(photo()))
        self.assertFalse(frontpage.big_face(b"not an image"))

    def test_no_opencv_no_check(self):
        if frontpage._faces() is not None:
            self.skipTest("OpenCV is installed")
        self.assertFalse(frontpage.big_face(photo()))

    def test_wide(self):
        im = Image.open(io.BytesIO(frontpage.wide(photo())))
        self.assertEqual((im.size, im.mode), ((1200, 600), "L"))
        self.assertIsNone(frontpage.wide(b"nope"))


class Page(unittest.TestCase):
    def test_links_and_order(self):
        html = frontpage.page(ITEMS, DAY, 7, "17 Adar 5786", {"a": "c2.xhtml", "b": "c3.xhtml", "d": "c4.xhtml"}, "images/img2.jpg", "b")
        self.assertIn('<p class="dl">No. 7 · Tuesday, 17 March 2026 · 17 Adar 5786</p>', html)
        self.assertIn('<a href="c2.xhtml">The long essay about rivers</a>', html)
        self.assertIn('<p class="t">No transcript yet</p>', html)            # not in the book: no link
        self.assertIn('<p class="k">Watch · video</p>', html)
        self.assertNotIn(">Lead<", html)                                      # the lead goes without a label
        self.assertIn('<p class="dek">Rivers keep their own time.</p>', html)
        self.assertIn('<div class="st" dir="rtl">', html)
        # the picture stands over its own piece
        self.assertLess(html.index("A tram line") - html.index('src="images/img2.jpg"'), 200)
        self.assertGreater(html.index('src="images/img2.jpg"'), html.index("The long essay"))


class Cover(unittest.TestCase):
    def test_draws(self):
        for items, pic in ((ITEMS, ("b", photo(), "u2")), (ITEMS[:1], None), ([], None)):
            im = Image.open(io.BytesIO(frontpage.cover(items, DAY, 7, "י״ז בַּאֲדָר תשפ״ו", pic)))
            self.assertEqual((im.size, im.mode), ((1264, 1680), "L"))

    def test_wrap_cuts_with_an_ellipsis(self):
        im = Image.new("L", (100, 100))
        d = ImageDraw.Draw(im)
        face = frontpage.Face("literata-latin-wght-normal.woff2", 30, 400)
        lines = frontpage.wrap(d, face, "word " * 80, 400, 2)
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[-1].endswith("…"))
        self.assertTrue(all(face.width(d, ln) <= 400 for ln in lines))


class Book(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = kindlesend.KINDLE_DIR, kindlequeue.queue_file, reader.get_doc, kindlesend._fetch_image
        kindlesend.KINDLE_DIR = Path(self.tmp.name)
        kindlequeue.queue_file = lambda *a, **k: None
        docs = {i["id"]: {"id": i["id"], "title": i["title"], "source": i["source"], "url": "https://example.org/" + i["id"],
                          "blocks": [{"t": "img", "src": "https://example.org/pic.jpg"}, {"t": "p", "x": "Some words. " * 40}]}
                for i in ITEMS if i["kind"] == "article"}
        reader.get_doc = lambda conn, i, prefetch=False: docs.get(i)
        kindlesend._fetch_image = lambda url: kindlesend._ready(photo())
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE kindle_sent (doc_id TEXT PRIMARY KEY, file TEXT, at INTEGER)")
        self.conn.execute("CREATE TABLE kindle_epubs (md5 TEXT PRIMARY KEY, file TEXT, parts TEXT)")

    def tearDown(self):
        kindlesend.KINDLE_DIR, kindlequeue.queue_file, reader.get_doc, kindlesend._fetch_image = self.saved
        self.conn.close()
        self.tmp.cleanup()

    def test_the_edition_book(self):
        paper = frontpage.Paper(ITEMS, DAY, 7, "17 Adar 5786", "י״ז אדר תשפ״ו", {"b": photo(seed=3)})
        res = kindlesend.make_epub(self.conn, [i["id"] for i in ITEMS], title="Daf, Tuesday", fname="Daf test (Edition).epub", front=paper)
        self.assertEqual((res["count"], res["skipped"]), (3, ["c"]))
        z = zipfile.ZipFile(Path(self.tmp.name) / "Daf test (Edition).epub")
        opf = z.read("OEBPS/content.opf").decode()
        self.assertIn('href="images/cover.jpg" media-type="image/jpeg" properties="cover-image"', opf)
        self.assertIn('<meta name="cover" content="cover"/>', opf)
        self.assertEqual(Image.open(io.BytesIO(z.read("OEBPS/images/cover.jpg"))).size, (1264, 1680))
        front = z.read("OEBPS/c1.xhtml").decode()
        self.assertIn('class="front"', front)
        for i, ch in (("The long essay about rivers", "c2"), ("A tram line for Sintra", "c3"), ("פרשת השבוע: על הדרך", "c4")):
            self.assertIn(f'<a href="{ch}.xhtml">{i}</a>', front)
        self.assertIn('<img src="images/img', front)                          # the lead's own photograph, cut wide
        for n in (2, 3, 4):
            self.assertIn('<p class="back"><a href="c1.xhtml">Front page</a></p>', z.read(f"OEBPS/c{n}.xhtml").decode())
        # the Kindle's reading still finds its pieces: the front page counts as no piece
        parts = json.loads(self.conn.execute("SELECT parts FROM kindle_epubs").fetchone()[0])
        self.assertEqual([p[0] for p in parts], ["", "a", "b", "d"])

    def test_a_plain_send_is_as_it_was(self):
        kindlesend.make_epub(self.conn, ["a"])
        z = zipfile.ZipFile(next(Path(self.tmp.name).glob("*.epub")))
        self.assertNotIn("cover", z.read("OEBPS/content.opf").decode())
        self.assertNotIn("Front page", z.read("OEBPS/c1.xhtml").decode())


if __name__ == "__main__":
    unittest.main()
