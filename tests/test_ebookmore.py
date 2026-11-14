"""Edit book's other tools (daf/ebookmore.py): where a split goes, what Split, Merge and Beautify hand
Calibre and how they checkpoint, the character map, and the link check's rule for the web. Calibre
itself isn't run here (TOOLS_SCRIPT is only compiled); the working copy is a made-up book."""
import socket
import tempfile
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from daf import ebookedit as E, ebookmore as T
from tests.test_ebookedit import make_book

BODY = """<html xmlns="http://www.w3.org/1999/xhtml"><head><title>T</title><style>p{}</style></head>
<body class="x"><h1 id="a">One</h1><!-- <p>not this</p> --><p class='q' title="a > b">First</p>
<p>Second <i>part</i></p></body></html>"""


class SplitPoint(unittest.TestCase):
    """split_point gives the place just after the start tag's name, where the mark goes."""
    def at(self, cursor):
        return T.split_point(BODY, cursor)

    def test_the_tag_the_cursor_is_in_or_the_next(self):
        first, second = BODY.index("<p class=") + 2, BODY.index("<p>Second") + 2
        self.assertEqual(self.at(BODY.index("<p class=") + 4), first)       # inside its start tag: that one
        self.assertEqual(self.at(BODY.index("<p class=")), first)           # just before it
        self.assertEqual(self.at(BODY.index("First")), second)              # in its text: the next one
        self.assertIsNone(self.at(BODY.index("part")))                      # nothing after it but closing tags

    def test_skips_what_isnt_an_element_in_the_body(self):
        self.assertEqual(self.at(0), BODY.index("<h1") + 3)                 # before <body>: its first element
        self.assertEqual(self.at(BODY.index("<!--")), BODY.index("<p class=") + 2)   # a comment is no place
        self.assertEqual(self.at(BODY.index("</h1>")), BODY.index("<p class=") + 2)  # nor a closing tag
        self.assertIsNone(T.split_point("<p>no body</p>", 0))

    def test_quoted_greater_than(self):
        self.assertEqual(self.at(BODY.index("a > b") + 3), BODY.index("<p class=") + 2)   # the > in quotes doesn't end the tag: still in it


class Tools(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        p = mock.patch.object(E, "EDIT_DIR", self.root)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)
        self.book = make_book(self.root)
        self.ch1 = self.book / "OEBPS/Text/chapter1.xhtml"

    def test_split_marks_then_asks_calibre(self):
        seen = {}

        def run(cid, job, timeout=600, script=None):
            seen.update(job=job, script=script, text=self.ch1.read_text())
            return {"ok": True, "bottom": "OEBPS/Text/chapter1_split1.xhtml"}
        text = self.ch1.read_text()
        with mock.patch.object(E, "_run", side_effect=run):
            out = T.split(7, "OEBPS/Text/chapter1.xhtml", text.index("Who that"))
        self.assertEqual(out["bottom"], "OEBPS/Text/chapter1_split1.xhtml")
        self.assertIs(seen["script"], T.TOOLS_SCRIPT)
        self.assertEqual(seen["job"], {"op": "split", "name": "OEBPS/Text/chapter1.xhtml"})
        self.assertIn('<p data-daf-split="">Miss Brooke', seen["text"])          # the paragraph after the cursor
        self.assertEqual(E.checkpoints(7)[0]["label"], "Split chapter1.xhtml")
        self.assertEqual(out["checkpoint"], E.checkpoints(7)[0]["n"])
        self.assertTrue(E.meta(7)["changed"])

    def test_a_failed_split_leaves_the_file_and_no_checkpoint(self):
        before = self.ch1.read_bytes()
        with mock.patch.object(E, "_run", side_effect=E.EditError("Cannot split inside tables")), self.assertRaises(E.EditError):
            T.split(7, "OEBPS/Text/chapter1.xhtml", 0)
        self.assertEqual(self.ch1.read_bytes(), before)
        self.assertEqual(E.checkpoints(7), [])
        with self.assertRaises(E.EditError):
            T.split(7, "OEBPS/Text/chapter1.xhtml", len(before))          # after the last element
        self.assertEqual(E.checkpoints(7), [])
        for bad in (-1, "3", True, None):
            with self.assertRaises(E.EditError):
                T.split(7, "OEBPS/Text/chapter1.xhtml", bad)
        with self.assertRaises(E.EditError):
            T.split(7, "../../etc/passwd", 0)

    def test_merge(self):
        calls = []
        with mock.patch.object(E, "_run", side_effect=lambda cid, job, timeout=600, script=None: calls.append(job) or {"ok": True, "master": job["master"]}):
            T.merge(7, "text", ["OEBPS/Text/notes.xhtml", "OEBPS/Text/chapter1.xhtml", "OEBPS/Text/notes.xhtml"], "OEBPS/Text/notes.xhtml")
        self.assertEqual(calls[0], {"op": "merge", "category": "text", "names": ["OEBPS/Text/chapter1.xhtml", "OEBPS/Text/notes.xhtml"],
                                    "master": "OEBPS/Text/notes.xhtml"})                   # in the book's order, each once
        self.assertEqual(E.checkpoints(7)[0]["label"], "Merge into notes.xhtml")
        for args in (("images", ["a", "b"], "a"), ("text", ["OEBPS/Text/chapter1.xhtml"], "OEBPS/Text/chapter1.xhtml"),
                     ("text", ["OEBPS/Text/chapter1.xhtml", "OEBPS/Text/notes.xhtml"], "OEBPS/Text/x.xhtml"),
                     ("styles", ["OEBPS/Styles/style.css", "OEBPS/Text/notes.xhtml"], "OEBPS/Styles/style.css")):
            with self.assertRaises(E.EditError):
                T.merge(7, *args)

    def test_beautify(self):
        calls = []
        with mock.patch.object(E, "_run", side_effect=lambda cid, job, timeout=600, script=None: calls.append(job) or {"ok": True}):
            T.beautify(7, "OEBPS/Styles/style.css")
            T.beautify(7)
        self.assertEqual(calls, [{"op": "pretty", "name": "OEBPS/Styles/style.css"}, {"op": "pretty", "name": None}])
        self.assertEqual([c["label"] for c in E.checkpoints(7)], ["Beautify all files", "Beautify style.css"])
        with self.assertRaises(E.EditError):
            T.beautify(7, "OEBPS/nope.css")

    def test_runner_takes_another_script(self):
        done = SimpleNamespace(stdout='DAFRESULT {"ok": true, "links": []}', stderr="")
        with mock.patch("subprocess.run", return_value=done) as run:
            self.assertEqual(T._run(7, {"op": "links"}), {"ok": True, "links": []})
        self.assertIn(T.TOOLS_SCRIPT, run.call_args.args[0])

    def test_script(self):
        compile(T.TOOLS_SCRIPT, "calibre-script", "exec")
        for s in ('split(c, name, "//*[@data-daf-split]")', "merge(c, job[\"category\"], job[\"names\"], job[\"master\"])", "pretty_all(c)", "c.iterlinks(name)"):
            self.assertIn(s, T.TOOLS_SCRIPT)


class CharMap(unittest.TestCase):
    def test_categories_and_favorites(self):
        r = T.chars()
        self.assertEqual(len(r["categories"]), 21)
        self.assertEqual(r["categories"][0][0], "European scripts")
        self.assertEqual(r["favorites"][0], [0xA0, "NO-BREAK SPACE"])
        self.assertIn([0x2014, "EM DASH"], r["favorites"])

    def test_search(self):
        found = T.chars("em dash")["chars"]
        self.assertIn([0x2014, "EM DASH"], found)
        self.assertNotIn(0x2013, [c for c, _n in found])
        self.assertEqual(T.chars("U+05D0")["chars"][0], [0x5D0, "HEBREW LETTER ALEF"])
        self.assertIn(0x5D0, [c for c, _n in T.chars("hebrew alef")["chars"]])
        self.assertEqual(T.chars("   ")["chars"], [])
        self.assertLessEqual(len(T.chars("a")["chars"]), T.MAX_CHARS)

    def test_a_category(self):
        r = T.chars(first=0x2010, last=0x2015)["chars"]
        self.assertEqual([c for c, _n in r], list(range(0x2010, 0x2016)))
        self.assertEqual(len(T.chars(first=0x4E00, last=0x9FFF)["chars"]), T.MAX_CHARS)
        self.assertEqual(T.chars(first=10, last=5)["chars"], [])


def addr(ip):
    return [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 80))]


class Links(unittest.TestCase):
    def test_public_only(self):
        for ip in ("127.0.0.1", "10.0.0.5", "192.168.1.2", "100.91.202.11", "169.254.1.1", "::1", "fd00::1", "0.0.0.0", "224.0.0.1"):
            with mock.patch("socket.getaddrinfo", return_value=addr(ip)), self.assertRaises(T.NotWeb, msg=ip):
                T.public("http://somewhere.example/")
        with mock.patch("socket.getaddrinfo", return_value=addr("93.184.215.14")):
            T.public("https://example.com/page")
        for u in ("ftp://example.com/", "file:///etc/passwd", "http:///nohost", "javascript:alert(1)"):
            with self.assertRaises(T.NotWeb):
                T.public(u)

    def test_a_redirect_into_the_house_is_refused(self):
        h = T._Hops()
        with mock.patch("socket.getaddrinfo", return_value=addr("127.0.0.1")), self.assertRaises(T.NotWeb):
            h.redirect_request(None, None, 302, "Found", {}, "http://localhost:8440/api/settings")
        self.assertEqual(h.hops, [])

    def test_check_url(self):
        ok = mock.MagicMock()
        ok.__enter__.return_value = SimpleNamespace(status=200, headers={"Content-Type": "text/html"}, read=lambda n: b'<p id="here">x</p>')
        with mock.patch("socket.getaddrinfo", return_value=addr("93.184.215.14")), mock.patch("urllib.request.OpenerDirector.open", return_value=ok) as op:
            self.assertEqual(T.check_url("https://example.com/")["status"], "ok")
            self.assertEqual(op.call_args.args[0].get_method(), "HEAD")
            self.assertEqual(T.check_url("https://example.com/#here")["status"], "ok")
            self.assertEqual(op.call_args.args[0].get_method(), "GET")          # an anchor needs the page
            r = T.check_url("https://example.com/#gone")
            self.assertEqual((r["status"], r["error"]), ("broken", "HTML anchor gone not found on the page"))
        err = urllib.error.HTTPError("https://example.com/x", 404, "Not Found", {}, None)
        with mock.patch("socket.getaddrinfo", return_value=addr("93.184.215.14")), mock.patch("urllib.request.OpenerDirector.open", side_effect=err) as op:
            r = T.check_url("https://example.com/x")
        self.assertEqual((r["status"], r["code"]), ("broken", 404))
        self.assertEqual([c.args[0].get_method() for c in op.call_args_list], ["HEAD", "GET"])     # HEAD refused: GET too
        dead = urllib.error.URLError(socket.timeout("timed out"))
        with mock.patch("socket.getaddrinfo", return_value=addr("93.184.215.14")), mock.patch("urllib.request.OpenerDirector.open", side_effect=dead) as op:
            self.assertEqual(T.check_url("https://example.com/slow"), {"status": "broken", "error": "No answer", "url": None})
        self.assertEqual(len(op.call_args_list), 1)                              # no answer: not asked twice
        with mock.patch("socket.getaddrinfo", return_value=addr("10.1.1.1")):
            self.assertEqual(T.check_url("http://nas.example/")["status"], "skipped")

    def test_external_links_sorted_and_capped(self):
        found = [{"href": "https://a.example/%d" % i, "at": [["OEBPS/Text/chapter1.xhtml", i, 0]]} for i in range(T.MAX_LINKS + 5)]
        status = lambda h: {"status": "broken" if h.endswith("/7") else "ok"}
        with mock.patch.object(E, "_need"), mock.patch.object(T, "_run", return_value={"links": found}), mock.patch.object(T, "check_url", side_effect=status):
            r = T.external_links(7)
        self.assertEqual(r["more"], 5)
        self.assertEqual(len(r["links"]), T.MAX_LINKS)
        self.assertEqual(r["links"][0]["href"], "https://a.example/7")
        self.assertEqual(r["links"][0]["at"], [["OEBPS/Text/chapter1.xhtml", 7, 0]])


class Endpoints(unittest.TestCase):
    def setUp(self):
        from daf import app
        self.app = app

    def test_split_needs_where(self):
        from fastapi import HTTPException
        with mock.patch.object(E, "_need"):
            for body in ({}, {"name": "a.xhtml"}, {"name": "a.xhtml", "at": "3"}, {"name": "a.xhtml", "at": True}, None):
                with self.assertRaises(HTTPException):
                    self.app.post_ebookedit_split(7, body)
            with mock.patch("daf.calibrewrite.start_job", return_value="j") as sj:
                self.assertEqual(self.app.post_ebookedit_split(7, {"name": "a.xhtml", "at": 12}), {"job": "j"})
                self.assertEqual(self.app.post_ebookedit_beautify(7, {}), {"job": "j"})
                self.assertEqual(self.app.post_ebookedit_merge(7, {"category": "text", "names": ["a", "b"], "master": "a"}), {"job": "j"})
                self.assertEqual(self.app.post_ebookedit_extlinks(7), {"job": "j"})
            self.assertEqual(sj.call_count, 4)

    def test_charmap(self):
        self.assertIn([0x2014, "EM DASH"], self.app.get_charmap(q="em dash")["chars"])
        self.assertEqual(len(self.app.get_charmap()["categories"]), 21)


if __name__ == "__main__":
    unittest.main()
