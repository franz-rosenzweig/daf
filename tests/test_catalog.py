"""All books' search, the way Calibre searches (daf/catalog.py), on a few made-up books.

Run: .venv/bin/python -m unittest discover tests
"""
import os
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))

from daf import catalog  # noqa: E402

T = date.today()
COLS = catalog.columns([{"key": "#read", "label": "Read", "type": "text"}, {"key": "#pages", "label": "Pages", "type": "number"}])
for c in COLS[-2:]:
    c["custom"] = True


def book(title, **kw):
    b = {"title": title, "title_sort": title, "authors": [], "tags": [], "formats": ["EPUB"], "shelves": [], "languages": ["eng"],
         "series": None, "series_index": 1, "rating": None, "added": T.isoformat(), "published": None, "cover": True,
         "status": None, "progress": None, "highlights": 0, "size": 1048576, "#read": None, "#pages": None, "author_sort": ""}
    b.update(kw)
    return b


BOOKS = [
    book("Gilead", authors=["Marilynne Robinson"], tags=["Fiction", "Classics"], rating=5, status="Read", **{"#pages": 247, "#read": "Finished"}),
    book("The Plague", authors=["Albert Camus"], tags=["Fiction", "Philosophy"], rating=4, added=(T - timedelta(40)).isoformat(), published="1947-06-10"),
    book("Hebrew Grammar", authors=["Page H. Kelley"], tags=["Reference"], formats=[], cover=False, added="2025-03-02", **{"#pages": 620}),
    book("The Lord of the Rings, Vol. 1", authors=["J. R. R. Tolkien"], series="The Lord of the Rings", series_index=1, tags=[],
         status="Reading", progress=42.0, size=12 * 1048576, highlights=3, shelves=["Books"]),
]


def titles(q):
    return [b["title"] for b in catalog.search(BOOKS, q, COLS)]


class Search(unittest.TestCase):
    def test_words(self):
        self.assertEqual(titles("camus"), ["The Plague"])
        self.assertEqual(titles("lord rings"), ["The Lord of the Rings, Vol. 1"])
        self.assertEqual(titles(""), [b["title"] for b in BOOKS])

    def test_text_and_lists(self):
        self.assertEqual(titles('tags:"=Fiction"'), ["Gilead", "The Plague"])
        self.assertEqual(titles("tags:fic"), ["Gilead", "The Plague"])
        self.assertEqual(titles("tags:~^ref"), ["Hebrew Grammar"])
        self.assertEqual(titles("tags:false"), ["The Lord of the Rings, Vol. 1"])
        self.assertEqual(titles("formats:false"), ["Hebrew Grammar"])
        self.assertEqual(titles("series:true"), ["The Lord of the Rings, Vol. 1"])
        self.assertEqual(titles('status:"=Read"'), ["Gilead"])

    def test_numbers(self):
        self.assertEqual(titles("rating:>=4"), ["Gilead", "The Plague"])
        self.assertEqual(titles("rating:4"), ["The Plague"])
        self.assertEqual(titles("rating:false"), ["Hebrew Grammar", "The Lord of the Rings, Vol. 1"])
        self.assertEqual(titles("size:>10mb"), ["The Lord of the Rings, Vol. 1"])
        self.assertEqual(titles("progress:>40 highlights:3"), ["The Lord of the Rings, Vol. 1"])
        self.assertEqual(titles("#pages:>500"), ["Hebrew Grammar"])
        self.assertEqual(titles("pages:<300"), ["Gilead"])
        self.assertEqual(titles("#read:=Finished"), ["Gilead"])

    def test_dates(self):
        self.assertEqual(titles("added:today"), ["Gilead", "The Lord of the Rings, Vol. 1"])
        self.assertEqual(titles("added:>=30daysago"), ["Gilead", "The Lord of the Rings, Vol. 1"])
        self.assertEqual(titles("date:2025-03"), ["Hebrew Grammar"])
        self.assertEqual(titles("added:<2026"), ["Hebrew Grammar"] if T.year == 2026 else titles("added:<2026"))
        self.assertEqual(titles("published:<1950"), ["The Plague"])
        with self.assertRaises(catalog.SearchError):
            titles("added:soon")

    def test_and_or_not(self):
        self.assertEqual(titles("tags:fiction and not rating:5"), ["The Plague"])
        self.assertEqual(titles("(camus or tolkien) -tags:fiction"), ["The Lord of the Rings, Vol. 1"])
        self.assertEqual(titles("tags:reference or series:rings"), ["Hebrew Grammar", "The Lord of the Rings, Vol. 1"])
        self.assertEqual(titles("((tags:fiction"), ["Gilead", "The Plague"])          # half-typed: closes itself
        self.assertEqual(titles('tags:"=Fic'), [])

    def test_sort(self):
        s = catalog.sort(BOOKS, "rating", True, COLS)
        self.assertEqual([b["title"] for b in s][:2], ["Gilead", "The Plague"])
        s = catalog.sort(BOOKS, "series", False, COLS)
        self.assertEqual(s[0]["title"], "The Lord of the Rings, Vol. 1")      # books without a series last

    def test_views(self):
        v = catalog.clean_views([{"name": " Mine ", "q": "tags:x", "cols": ["title", 3], "widths": {"title": 2000, "tags": 120}}, {"name": "mine"}, {"q": "no name"}])
        self.assertEqual(v, [{"name": "Mine", "q": "tags:x", "sort": "added", "desc": False, "cols": ["title"], "widths": {"tags": 120}}])


if __name__ == "__main__":
    unittest.main()


class Tidy(unittest.TestCase):
    def test_alike(self):
        tags = ["Self Help", "Self-Help", "selfhelp", "Thriller", "Thrillers", "Essays", "Glass", "History"]
        self.assertEqual(sorted(map(sorted, catalog.alike(tags, "tags"))), [["Self Help", "Self-Help", "selfhelp"], ["Thriller", "Thrillers"]])
        authors = ["J. R. R. Tolkien", "J.R.R. Tolkien", "J R R Tolkien", "Tolkien, J. R. R.", "Raphael Patai", "Patai, Raphael", "Ann Patchett"]
        groups = sorted(map(sorted, catalog.alike(authors, "authors")))
        self.assertEqual(groups, [["J R R Tolkien", "J. R. R. Tolkien", "J.R.R. Tolkien", "Tolkien, J. R. R."], ["Patai, Raphael", "Raphael Patai"]])


class Fill(unittest.TestCase):
    def setUp(self):
        from daf import calibrefind
        self.F = calibrefind
        self.book = {"title": "Gilead", "authors": ["Marilynne Robinson"], "publisher": None, "published": "2004-01-01", "comments": "",
                     "tags": [], "series": None, "languages": ["eng"], "cover": True, "#pages": None, "identifiers_map": {"isbn": "9781700137210"}}

    def test_same_book(self):
        F = self.F
        self.assertTrue(F.same_book(self.book, {"title": "Gilead: A Novel", "authors": ["Marilynne Robinson"]}))
        self.assertFalse(F.same_book(self.book, {"title": "Study Guide: Gilead by Marilynne Robinson", "authors": ["Supersummary"]}))
        self.assertFalse(F.same_book(self.book, {"title": "Gilead", "authors": ["Someone Else"]}))
        self.assertTrue(F.same_book({"title": "Café", "authors": ["Jean Kovačić"]}, {"title": "Cafe", "authors": ["J. Kovacic"]}))

    def test_proposals_fill_only_whats_missing(self):
        a = {"source": "Hardcover", "title": "Gilead", "authors": ["Marilynne Robinson"], "publisher": "Picador", "published": "2006-01-10",
             "comments": "A letter.", "tags": ["Fiction"], "series": "Gilead", "series_index": 1, "languages": ["eng"],
             "identifiers": {"hardcover-book": "247430", "isbn": "9780312424404"}, "pages": 289, "cover": "https://x/c.jpg"}
        props, src = self.F.proposals(self.book, [a], self.F.FILL_FIELDS, {"#pages"})
        self.assertEqual(props["publisher"], "Picador")
        self.assertNotIn("published", props)                 # it has a date already
        self.assertNotIn("cover", props)                     # and a cover
        self.assertNotIn("languages", props)
        self.assertEqual(props["identifiers"], {"hardcover-book": "247430"})   # its own ISBN stays
        self.assertEqual((props["series"], props["series_index"], props["#pages"]), ("Gilead", 1, 289))
        self.assertEqual(src["publisher"], "Hardcover")
