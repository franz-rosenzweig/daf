"""Add from ISBN (isbnadd.py, /api/catalog/isbn/*): reading the ISBNs, what's added, and what's turned away."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))

from fastapi import HTTPException  # noqa: E402

from daf import isbnadd  # noqa: E402


class Parse(unittest.TestCase):
    def test_isbns(self):
        got = isbnadd.parse("978-0-14-143951-8, 0141439513\n(9780306406157) junk 12345 9780306406157")
        isbns = [g["isbn"] for g in got if g["isbn"]]
        self.assertEqual(isbns, ["9780141439518", "9780306406157"])          # the ten-digit one is the same book: once
        self.assertEqual([g["token"] for g in got if not g["isbn"]], ["12345"])

    def test_clean_book(self):
        b = isbnadd.clean_book({"title": " A Made Up Book ", "authors": ["Some One", " "], "isbn": "0-306-40615-2", "publisher": "A Press",
                                "published": "1999-04-01", "languages": ["eng", "not a code"], "tags": ["Fiction"], "comments": "<p>Hi<script>x</script></p>",
                                "identifiers": {"google": "abc", "bad key!": "x"}, "series": "Saga", "series_index": "2"}, tags=["From ISBN", "Fiction"])
        self.assertEqual(b["title"], "A Made Up Book")
        self.assertEqual(b["authors"], ["Some One"])
        self.assertEqual(b["identifiers"], {"google": "abc", "isbn": "9780306406157"})
        self.assertEqual(b["tags"], ["Fiction", "From ISBN"])
        self.assertEqual((b["series"], b["series_index"], b["pubdate"]), ("Saga", 2.0, "1999-04-01"))
        self.assertEqual(b["fields"]["languages"], ["eng"])
        self.assertNotIn("script", b["fields"]["comments"])
        with self.assertRaises(ValueError):
            isbnadd.clean_book({"title": " "})


class Endpoints(unittest.TestCase):
    def setUp(self):
        from daf import app
        self.app = app

    def test_lookup(self):
        with mock.patch.object(isbnadd, "lookup_start", return_value="j1") as st:
            self.assertEqual(self.app.post_isbn_lookup({"text": "9780306406157"}), {"job": "j1"})
            st.assert_called_once_with("9780306406157")
            with self.assertRaises(HTTPException):
                self.app.post_isbn_lookup({"text": "nothing here 123"})

    def test_lookup_job(self):
        with mock.patch.object(isbnadd, "in_library", return_value={"9780141439518": (5, "Had It")}), \
                mock.patch.object(isbnadd, "_found", side_effect=lambda i: {"title": "Found", "identifiers": {"isbn": i}} if i.endswith("57") else None):
            jid = isbnadd.lookup_start("9780141439518 9780306406157 9781234567897 x123")
            from daf import calibrewrite
            for _ in range(100):
                j = calibrewrite.job(jid)
                if j["state"] != "running":
                    break
                import time
                time.sleep(0.02)
        self.assertEqual([it["state"] for it in j["items"]], ["have", "found", "missing", "bad"])
        self.assertEqual((j["done"], j["total"]), (4, 4))

    def test_add(self):
        from daf import calibrewrite
        seen = []

        def run(ops, timeout=120):
            seen.append(ops[0])
            return {"added": [41, 42]} if ops[0]["op"] == "add_empty" else {}

        def start(fn):
            self.result = fn()
            return "j2"
        with mock.patch.object(calibrewrite, "run", side_effect=run), mock.patch.object(calibrewrite, "start_job", side_effect=start), \
                mock.patch.object(self.app, "_cover_data", return_value=b"\xff\xd8\xff fake jpeg"):
            out = self.app.post_isbn_add({"books": [{"title": "One", "isbn": "9780306406157", "cover": "https://example.org/c.jpg"},
                                                    {"title": "Two", "cover": "file:///etc/passwd"}], "tags": ["New"]})
        self.assertEqual(out, {"job": "j2"})
        self.assertEqual(self.result, [41, 42])
        self.assertEqual([o["op"] for o in seen], ["add_empty", "cover"])      # only an http(s) cover is fetched
        self.assertEqual(seen[0]["books"][0]["tags"], ["New"])
        with self.assertRaises(HTTPException):
            self.app.post_isbn_add({"books": [{"title": ""}]})
        with self.assertRaises(HTTPException):
            self.app.post_isbn_add({"books": []})


if __name__ == "__main__":
    unittest.main()
