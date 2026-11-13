"""Import list (daf/importlist.py): reading a list (text, CSV, a web page) and matching it to a made-up library."""
import base64
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from daf import config, importlist as il


def titles(rows):
    return [(r["title"], r["authors"]) for r in rows]


class Tidying(unittest.TestCase):
    def test_authors(self):
        self.assertEqual(il.split_authors("Eliot, George"), ["George Eliot"])
        self.assertEqual(il.split_authors("Le Guin, Ursula K."), ["Ursula K. Le Guin"])
        self.assertEqual(il.split_authors("Tolkien, J. R. R."), ["J. R. R. Tolkien"])
        self.assertEqual(il.split_authors("Wren Halloway, Ada Pemberton"), ["Wren Halloway", "Ada Pemberton"])
        self.assertEqual(il.split_authors("by Wren Halloway & Ada Pemberton"), ["Wren Halloway", "Ada Pemberton"])
        self.assertEqual(il.split_authors("Wren Halloway and Ada Pemberton; Tom Quill"), ["Wren Halloway", "Ada Pemberton", "Tom Quill"])
        self.assertEqual(il.split_authors("Ada Pemberton (Editor)"), ["Ada Pemberton"])
        self.assertEqual(il.split_authors("Quill, Jr."), ["Quill, Jr."])

    def test_titles(self):
        self.assertEqual(il.tidy_title('3. "Middlemarch".'), "Middlemarch")
        self.assertEqual(il.tidy_title("THE MILL ON THE FLOSS"), "The Mill on the Floss")
        self.assertEqual(il.tidy_title("HENRY V: PART II"), "Henry V: Part II")
        self.assertEqual(il.tidy_title("1984"), "1984")
        self.assertEqual(il.split_series("The Lantern Keeper (Coastal Fictions, #2)"), ("The Lantern Keeper", "Coastal Fictions", 2.0))
        self.assertEqual(il.split_series("The Lantern Keeper (Coastal Fictions #2.5)"), ("The Lantern Keeper", "Coastal Fictions", 2.5))
        self.assertEqual(il.split_series("Persuasion (Penguin Classics)"), ("Persuasion (Penguin Classics)", None, None))

    def test_dates_and_isbns(self):
        self.assertEqual(il.tidy_date("1871"), "1871-01-01")
        self.assertEqual(il.tidy_date("(1999)"), "1999-01-01")
        self.assertEqual(il.tidy_date("1999/04/03"), "1999-04-03")
        self.assertEqual(il.tidy_date("4/3/1999"), "1999-04-03")
        self.assertEqual(il.tidy_date("April 3, 1999"), "1999-04-03")
        self.assertEqual(il.tidy_date("3 April 1999"), "1999-04-03")
        self.assertIsNone(il.tidy_date("someday"))
        self.assertEqual(il.isbn13("0-14-143954-8"), "9780141439549")
        self.assertEqual(il.isbn13("978-0-14-143954-9"), "9780141439549")
        self.assertTrue(il.valid_isbn("0141439548"))
        self.assertFalse(il.valid_isbn("0141439549"))


class Text(unittest.TestCase):
    def test_each_line_on_its_own(self):
        text = "\n".join([
            "Middlemarch by George Eliot",
            "Death by Black Hole by Neil Tyson",
            "George Eliot - Felix Holt, the Radical",
            "Romola - George Eliot",
            "The Mill on the Floss / George Eliot",
            "Adam Bede (George Eliot)",
            "Daniel Deronda\tGeorge Eliot",
            "  12. The Lantern Keeper (Coastal Fictions, #2) by Halloway, Wren",
            "9. ISBN 978-0-14-143954-9",
            "Scenes of Clerical Life",
            "",
        ])
        rows = il.parse_text(text)["rows"]
        self.assertEqual(titles(rows), [
            ("Middlemarch", ["George Eliot"]), ("Death by Black Hole", ["Neil Tyson"]), ("Felix Holt, the Radical", ["George Eliot"]),
            ("Romola", ["George Eliot"]), ("The Mill on the Floss", ["George Eliot"]), ("Adam Bede", ["George Eliot"]),
            ("Daniel Deronda", ["George Eliot"]), ("The Lantern Keeper", ["Wren Halloway"]), ("", []), ("Scenes of Clerical Life", [])])
        self.assertEqual((rows[7]["series"], rows[7]["series_index"]), ("Coastal Fictions", 2.0))
        self.assertEqual(rows[8]["isbn"], "9780141439549")

    def test_an_isbn_beside_the_title(self):
        r = il.parse_text("Middlemarch by George Eliot 0141439548")["rows"][0]
        self.assertEqual((r["title"], r["authors"], r["isbn"]), ("Middlemarch", ["George Eliot"], "9780141439549"))

    def test_unsure_dashes_follow_the_others(self):
        text = "George Eliot - Middlemarch\nCharlotte Bronte - Villette\nAnne Bronte - Agnes Grey"
        rows = il.parse_text(text)["rows"]
        self.assertEqual(titles(rows), [("Middlemarch", ["George Eliot"]), ("Villette", ["Charlotte Bronte"]), ("Agnes Grey", ["Anne Bronte"])])
        self.assertTrue(rows[2].get("alt"))                 # both sides look like names: the matcher may still turn it round
        self.assertEqual(titles(il.parse_text("Agnes Grey - Anne Bronte")["rows"]), [("Agnes Grey", ["Anne Bronte"])])

    def test_one_form_for_every_line(self):
        self.assertEqual(titles(il.parse_text("Brave Ships - Wren Halloway", "author-title")["rows"]), [("Wren Halloway", ["Brave Ships"])])
        self.assertEqual(titles(il.parse_text("Wren Halloway - Brave Ships", "title-author")["rows"]), [("Wren Halloway", ["Brave Ships"])])
        self.assertEqual(titles(il.parse_text("Stand By Me by Wren Halloway", "by")["rows"]), [("Stand By Me", ["Wren Halloway"])])

    def test_a_pattern(self):
        rows = il.parse_text("Middlemarch|Eliot, George|1871\nRomola|George Eliot|1863",
                             "pattern", r"(?P<title>[^|]+)\|(?P<author>[^|]+)\|(?P<published>\d+)")["rows"]
        self.assertEqual(titles(rows), [("Middlemarch", ["George Eliot"]), ("Romola", ["George Eliot"])])
        self.assertEqual(rows[1]["published"], "1863-01-01")
        with self.assertRaises(il.ListError):
            il.parse_text("x", "pattern", "(?P<title>")
        with self.assertRaises(il.ListError):
            il.parse_text("x", "pattern", "(?P<name>.*)")

    def test_columns_pasted_go_as_a_table(self):
        r = il.read({"source": "text", "text": "Title\tAuthor\nMiddlemarch\tGeorge Eliot\nRomola\tGeorge Eliot"})
        self.assertEqual((r["table"]["delimiter"], r["table"]["headings"], r["table"]["count"]), ("\t", True, 3))
        rows = il.read({"source": "table", "text": "Title\tAuthor\nMiddlemarch\tGeorge Eliot\nRomola\tGeorge Eliot",
                        "columns": r["table"]["columns"], "headings": True})["rows"]
        self.assertEqual(titles(rows), [("Middlemarch", ["George Eliot"]), ("Romola", ["George Eliot"])])


class Tables(unittest.TestCase):
    GOODREADS = ('\ufeffBook Id,Title,Author,Author l-f,Additional Authors,ISBN,ISBN13,My Rating,Year Published,Exclusive Shelf\n'
                 '19089,Middlemarch,George Eliot,"Eliot, George",,"=""0141439548""","=""9780141439549""",0,1871,to-read\n'
                 '12345,"The Lantern Keeper (Coastal Fictions, #2)",Wren Halloway,"Halloway, Wren",,"=""""","=""""",0,1999,read\n')

    def test_a_goodreads_export(self):
        t = il.read_table(self.GOODREADS.encode("utf-8"))
        self.assertEqual(t["delimiter"], ",")
        self.assertTrue(t["headings"])
        self.assertEqual({k: v for k, v in t["columns"].items() if v is not None},
                         {"title": 1, "authors": 2, "isbn": 6, "published": 8, "goodreads": 0})
        rows = il.table_rows(t["rows"], t["columns"])
        self.assertEqual(titles(rows), [("Middlemarch", ["George Eliot"]), ("The Lantern Keeper", ["Wren Halloway"])])
        self.assertEqual((rows[0]["isbn"], rows[0]["published"], rows[0]["ids"]), ("9780141439549", "1871-01-01", {"goodreads": "19089"}))
        self.assertEqual((rows[1]["isbn"], rows[1]["series"], rows[1]["series_index"]), (None, "Coastal Fictions", 2.0))

    def test_columns_chosen_by_hand_semicolons_no_headings(self):
        data = "Eliot, George;Middlemarch;Scenes;3\nHalloway, Wren;Brave Ships;;\n".encode("cp1252")
        t = il.read_table(data)
        self.assertEqual(t["delimiter"], ";")
        self.assertFalse(t["headings"])
        rows = il.table_rows(t["rows"], {"title": 1, "authors": 0, "series": 2, "series_index": 3}, headings=False)
        self.assertEqual(titles(rows), [("Middlemarch", ["George Eliot"]), ("Brave Ships", ["Wren Halloway"])])
        self.assertEqual((rows[0]["series"], rows[0]["series_index"], rows[1]["series"]), ("Scenes", 3.0, None))
        with self.assertRaises(il.ListError):
            il.table_rows(t["rows"], {"authors": 0})

    def test_a_file_through_read(self):
        data = base64.b64encode("Title\tAuthors\tISBN\nRomola\tGeorge Eliot\t\n".encode("utf-16")).decode()
        first = il.read({"source": "table", "data": data})
        self.assertEqual(first["table"]["count"], 2)
        rows = il.read({"source": "table", "data": data, "columns": first["table"]["columns"], "headings": True})["rows"]
        self.assertEqual(titles(rows), [("Romola", ["George Eliot"])])


PAGE = """<html><body><table class="tableList">
<tr><td>1</td><td><a class="bookTitle" href="/book/show/19089.Middlemarch"><span>Middlemarch (Paperback)</span></a>
  <span><div><a class="authorName"><span>George Eliot</span></a></div></span></td></tr>
<tr><td>2</td><td><a class="bookTitle" href="/book/show/777.Lantern"><span>The Lantern Keeper (Coastal Fictions, #2)</span></a>
  <span><div><a class="authorName"><span>Wren Halloway</span></a>, <a class="authorName"><span>Ada Pemberton</span></a></div></span></td></tr>
</table></body></html>"""


class Web(unittest.TestCase):
    def test_a_goodreads_list(self):
        rows = il.extract(PAGE, il.CONFIGS["Goodreads"])
        self.assertEqual(titles(rows), [("Middlemarch", ["George Eliot"]), ("The Lantern Keeper", ["Wren Halloway", "Ada Pemberton"])])
        self.assertEqual(rows[0]["ids"], {"goodreads": "19089"})
        self.assertEqual(rows[1]["series"], "Coastal Fictions")

    def test_xpaths_of_my_own(self):
        cfg = il.custom_config({"rows": "//tr", "title": ".//a[@class='bookTitle']/span/text()", "authors": ".//a[@class='authorName']//text()"})
        self.assertEqual([r["title"] for r in il.extract(PAGE, cfg)], ["Middlemarch (Paperback)", "The Lantern Keeper"])
        with self.assertRaises(il.ListError):
            il.custom_config({"rows": "//tr"})
        with self.assertRaises(il.ListError):
            il.extract(PAGE, {"rows": "//tr[", "title": (".", None, True)})

    def test_addresses(self):
        self.assertEqual(il.page_urls("https://example.org/list?page={2-4}"), [f"https://example.org/list?page={n}" for n in (2, 3, 4)])
        self.assertEqual(len(il.page_urls("https://example.org/list?page={1-50}")), 10)
        with self.assertRaises(il.ListError) as e:
            il.read_web("http://127.0.0.1:8440/")
        self.assertIn("Not an address on the web", str(e.exception))
        self.assertEqual(il.config_for("https://www.goodreads.com/shelf/show/fantasy"), "Goodreads Shelf")
        self.assertEqual(il.config_for("https://www.goodreads.com/list/show/1.Best"), "Goodreads")
        self.assertEqual(il.config_for("https://www.amazon.co.uk/gp/new-releases/books/72/"), "Amazon")
        self.assertIsNone(il.config_for("https://example.org/"))
        for s in il.sites():
            self.assertIn(s["config"], il.CONFIGS)
        with self.assertRaises(il.ListError):
            il.fetch("file:///etc/passwd")
        with self.assertRaises(il.ListError):
            il.fetch("http://127.0.0.1:8440/")


LIBRARY = [
    {"calibre_id": 1, "title": "Middlemarch", "authors": ["George Eliot"], "identifiers": ["isbn:978-0-14-143954-9"], "formats": ["EPUB"]},
    {"calibre_id": 2, "title": "The Mill on the Floss", "authors": ["George Eliot"], "identifiers": [], "formats": ["EPUB"]},
    {"calibre_id": 3, "title": "Brave Ships: A Novel of the Sea", "authors": ["Wren Halloway"], "identifiers": ["hardcover-book:4242"], "formats": []},
    {"calibre_id": 4, "title": "The Hobbit", "authors": ["J.R.R. Tolkien"], "identifiers": [], "formats": ["EPUB"]},
    {"calibre_id": 5, "title": "Romola", "authors": ["George Eliot"], "identifiers": [], "formats": []},
    {"calibre_id": 6, "title": "Romola", "authors": ["George Eliot"], "identifiers": [], "formats": ["PDF"]},
    {"calibre_id": 7, "title": "Café Stories", "authors": ["Ada Pemberton"], "identifiers": ["goodreads:555"], "formats": []},
    {"calibre_id": 8, "title": "Silas Marner", "authors": ["George Eliot"], "identifiers": [], "formats": []},
]


class Matching(unittest.TestCase):
    def one(self, **row):
        r = il.match([il.make_row(**row) | {k: v for k, v in row.items() if k == "alt"}], LIBRARY)[0]
        return (r["match"] or {}).get("id"), r["how"]

    def test_identifiers_first(self):
        self.assertEqual(self.one(title="Something Else", authors="Nobody", isbn="0141439548"), (1, "isbn"))
        self.assertEqual(self.one(title="Brave Ships", ids={"hardcover-book": "4242"}), (3, "hardcover"))
        self.assertEqual(self.one(title="?", ids={"goodreads": "555"}), (7, "goodreads"))

    def test_from_strict_to_forgiving(self):
        self.assertEqual(self.one(title="Middlemarch", authors="George Eliot"), (1, "identical"))
        self.assertEqual(self.one(title="the mill on the floss", authors="george eliot"), (2, "identical"))
        self.assertEqual(self.one(title="The Mill on the Floss?", authors="George Eliot"), (2, "similar"))
        self.assertEqual(self.one(title="Mill on the Floss", authors="Eliot, George"), (2, "similar"))
        self.assertEqual(self.one(title="Cafe Stories", authors="Ada Pemberton"), (7, "similar"))
        self.assertEqual(self.one(title="The Hobbit", authors="J. R. R. Tolkien"), (4, "similar"))
        self.assertEqual(self.one(title="Brave Ships", authors="Wren Halloway"), (3, "fuzzy"))
        self.assertEqual(self.one(title="Middlemarch: A Study of Provincial Life", authors="George Eliot"), (1, "fuzzy"))

    def test_title_alone_and_nothing(self):
        self.assertEqual(self.one(title="Silas Marner"), (8, "title"))
        self.assertEqual(self.one(title="Middlemarch", authors="Someone Else"), (None, None))
        self.assertEqual(self.one(title="Daniel Deronda", authors="George Eliot"), (None, None))

    def test_several_the_one_with_a_file_first(self):
        r = il.match([il.make_row("Romola", "George Eliot")], LIBRARY)[0]
        self.assertEqual(r["match"]["id"], 6)
        self.assertEqual([c["id"] for c in r["choices"]], [6, 5])

    def test_an_unsure_dash_line_turns_round(self):
        r = il.match([il.make_row("George Eliot", "Silas Marner") | {"alt": True}], LIBRARY)[0]
        self.assertEqual((r["match"]["id"], r["title"], r["authors"]), (8, "Silas Marner", ["George Eliot"]))
        r = il.match([il.make_row("George Eliot", "Daniel Deronda") | {"alt": True}], LIBRARY)[0]     # no book: the known author decides
        self.assertEqual((r["match"], r["title"], r["authors"]), (None, "Daniel Deronda", ["George Eliot"]))

    def test_isbn_alone_looked_up(self):
        rows = [il.make_row(isbn="9780141439600"), il.make_row(isbn="0141439548")]
        got = {"9780141439600": il.make_row("Romola", "George Eliot", ids={"hardcover-book": "1"})}
        with mock.patch.object(il, "lookup_isbns", return_value=got) as look:
            out = il.prepare(rows, LIBRARY)
        look.assert_called_once_with(["9780141439600"])                     # the one the library has isn't asked about
        self.assertEqual((out[0]["title"], out[0]["match"]["id"]), ("Romola", 6))
        self.assertEqual(out[1]["match"]["id"], 1)

    def test_search_by_hand(self):
        self.assertEqual([b["id"] for b in il.search(LIBRARY, "eliot mill")], [2])
        self.assertEqual([b["id"] for b in il.search(LIBRARY, "cafe")], [7])


class Doing(unittest.TestCase):
    def test_empty_books(self):
        rows = [il.make_row("The Lantern Keeper (Coastal Fictions, #2)", "Halloway, Wren", isbn="0141439548", published="1999",
                            ids={"hardcover-book": "9", "goodreads": "7", "ibdb": "x"}), il.make_row(isbn="9780141439600")]
        b = il.empty_books(rows, ["Hugo"], {"#read": "Planning"})
        self.assertEqual(b[0], {"title": "The Lantern Keeper", "authors": ["Wren Halloway"], "series": "Coastal Fictions", "series_index": 2.0,
                                "pubdate": "1999-01-01", "identifiers": {"hardcover-book": "9", "goodreads": "7", "isbn": "9780141439549"},
                                "tags": ["Hugo"], "fields": {"#read": "Planning"}})
        self.assertEqual((b[1]["title"], b[1]["authors"]), ("Unknown", ["Unknown"]))
        self.assertEqual(il.tags_from(" Hugo , Award,, Hugo"), ["Hugo", "Award"])

    def test_rows_from_the_page_checked(self):
        rows = il.clean_rows([{"title": " Romola ", "authors": "George Eliot & Ada Pemberton", "isbn": "bad", "series_index": "x",
                               "published": "1863", "ids": {"Goodreads": 5}}, "junk"])
        self.assertEqual(rows, [{"title": "Romola", "authors": ["George Eliot", "Ada Pemberton"], "series": None, "series_index": None,
                                 "isbn": None, "published": "1863-01-01", "ids": {"goodreads": "5"}, "alt": False}])

    def test_daf_rows(self):
        c = sqlite3.connect(":memory:")
        c.execute("CREATE TABLE books (id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, author TEXT, calibre_id INTEGER, private INTEGER NOT NULL DEFAULT 0)")
        c.execute("INSERT INTO books VALUES ('cal:1', 'book', 'Middlemarch', 'George Eliot', 1, 0)")
        il.add_daf_rows(c, {1: ("Changed", []), 9: ("Romola", ["George Eliot"]), 10: ("A Private Diary", [])}, {"private_titles": ["private diary"]})
        got = c.execute("SELECT id, title, author, calibre_id, private FROM books ORDER BY calibre_id").fetchall()
        c.close()
        self.assertEqual(got[:2], [("cal:1", "Middlemarch", "George Eliot", 1, 0), ("cal:9", "Romola", "George Eliot", 9, 0)])
        self.assertEqual((got[2][0], got[2][4]), ("cal:10", 1))

    def test_read_column(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "metadata.db"
            c = sqlite3.connect(db)
            c.execute("CREATE TABLE custom_columns (id INTEGER, label TEXT, name TEXT, datatype TEXT, display TEXT, mark_for_delete BOOL DEFAULT 0)")
            c.execute("INSERT INTO custom_columns (id, label, name, datatype, display) VALUES (4, 'read', 'Read', 'enumeration', ?)",
                      (json.dumps({"enum_values": ["Reading", "Planning", "Finished"]}),))
            c.commit()
            c.close()
            with mock.patch.object(config, "CALIBRE_DBS", [db]):
                self.assertEqual(il.read_column({}), {"key": "#read", "label": "Read", "choice": "Planning"})
                self.assertIsNone(il.read_column({"calibre_read_column": "#status"}))


if __name__ == "__main__":
    unittest.main()
