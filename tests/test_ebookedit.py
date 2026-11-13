"""Edit book's working copy (daf/ebookedit.py): the file list, reading and writing text, find and
replace, checkpoints, and when a copy stays or goes. Calibre itself isn't run here: these are the
parts Daf does on its own, on a made-up book in a temp folder."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from daf import ebookedit as E

CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""
OPF = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Middlemarch</dc:title></metadata>
  <manifest>
    <item id="c2" href="Text/chapter%202.xhtml" media-type="application/xhtml+xml"/>
    <item id="c1" href="Text/chapter1.xhtml" media-type="application/xhtml+xml"/>
    <item id="notes" href="Text/notes.xhtml" media-type="application/xhtml+xml"/>
    <item id="css" href="Styles/style.css" media-type="text/css"/>
    <item id="img" href="Images/cover.jpg" media-type="image/jpeg"/>
    <item id="font" href="Fonts/serif.otf" media-type="application/vnd.ms-opentype"/>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
  </manifest>
  <spine toc="ncx"><itemref idref="c1"/><itemref idref="c2"/></spine>
</package>"""
CH1 = """<html xmlns="http://www.w3.org/1999/xhtml"><head><title>One</title></head>
<body><h1 id="prelude">Prelude</h1>
<p>Who that cares much to know the history of man, and how the mysterious mixture behaves.</p>
<p>Miss Brooke had that kind of beauty which seems to be thrown into relief by poor dress.</p>
</body></html>"""
CH2 = """<html xmlns="http://www.w3.org/1999/xhtml"><body>
<h2 id='c2'>Chapter II</h2><p>"What is that, Dorothea?" said Celia. 😀 Then Dorothea smiled.</p>
</body></html>"""
CSS = "p { margin: 0; text-indent: 1.2em }\nh1, h2 { text-align: center }\n"


def make_book(root, cid=7):
    b = root / str(cid) / "book"
    for name, text in [("mimetype", "application/epub+zip"), ("META-INF/container.xml", CONTAINER), ("OEBPS/content.opf", OPF),
                       ("OEBPS/Text/chapter1.xhtml", CH1), ("OEBPS/Text/chapter 2.xhtml", CH2),
                       ("OEBPS/Text/notes.xhtml", "<html><body><p>Notes</p></body></html>"),
                       ("OEBPS/Styles/style.css", CSS), ("OEBPS/toc.ncx", "<ncx/>")]:
        p = b / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    (b / "OEBPS/Images").mkdir()
    (b / "OEBPS/Images/cover.jpg").write_bytes(b"\xff\xd8\xff\xe0 not really a jpeg")
    (b / "OEBPS/Fonts").mkdir()
    (b / "OEBPS/Fonts/serif.otf").write_bytes(b"OTTO")
    (root / str(cid) / "meta.json").write_text(json.dumps({"id": cid, "fmt": "EPUB", "title": "Middlemarch", "changed": False,
                                                           "src": {"size": 1, "mtime": 1}}))
    return b


class WorkingCopy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.p = mock.patch.object(E, "EDIT_DIR", self.root)
        self.p.start()
        self.book = make_book(self.root)

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def names(self, group):
        return [f["name"] for f in E.files(7)["files"] if f["group"] == group]

    def test_files_grouped_like_calibre(self):
        r = E.files(7)
        self.assertEqual(r["opf"], "OEBPS/content.opf")
        # text in the spine's order, then the rest; the OPF and NCX first under Other; no mimetype
        self.assertEqual(self.names("text"), ["OEBPS/Text/chapter1.xhtml", "OEBPS/Text/chapter 2.xhtml", "OEBPS/Text/notes.xhtml"])
        self.assertEqual(self.names("styles"), ["OEBPS/Styles/style.css"])
        self.assertEqual(self.names("images"), ["OEBPS/Images/cover.jpg"])
        self.assertEqual(self.names("fonts"), ["OEBPS/Fonts/serif.otf"])
        self.assertEqual(self.names("other"), ["OEBPS/content.opf", "OEBPS/toc.ncx", "META-INF/container.xml"])
        by = {f["name"]: f for f in r["files"]}
        self.assertEqual(by["OEBPS/Text/chapter1.xhtml"]["syntax"], "html")
        self.assertEqual(by["OEBPS/Styles/style.css"]["syntax"], "css")
        self.assertEqual(by["OEBPS/content.opf"]["syntax"], "xml")
        self.assertFalse(by["OEBPS/Images/cover.jpg"]["editable"])
        self.assertEqual(by["OEBPS/Text/chapter 2.xhtml"]["spine"], 1)
        self.assertIsNone(by["OEBPS/Text/notes.xhtml"]["spine"])

    def test_read_and_write_text(self):
        name = "OEBPS/Styles/style.css"
        self.assertEqual(E.read_text(7, name), CSS)
        self.assertFalse(E.write_text(7, name, CSS))                # the same text: nothing changes
        self.assertFalse(E.meta(7)["changed"])
        self.assertTrue(E.write_text(7, name, "p { margin: 1em }\r\n"))
        self.assertEqual((self.book / name).read_bytes(), b"p { margin: 1em }\n")
        self.assertTrue(E.meta(7)["changed"])

    def test_encodings_are_kept(self):
        p = self.book / "OEBPS/Text/notes.xhtml"
        p.write_bytes(b"\xef\xbb\xbf<p>caf\xc3\xa9</p>\r\n")
        self.assertEqual(E.read_text(7, "OEBPS/Text/notes.xhtml"), "<p>café</p>\n")
        E.write_text(7, "OEBPS/Text/notes.xhtml", "<p>cafés</p>\n")
        self.assertEqual(p.read_bytes(), b"\xef\xbb\xbf<p>caf\xc3\xa9s</p>\n")
        p.write_bytes(b'<?xml version="1.0" encoding="windows-1252"?>\n<p>na\xefve \x93quoted\x94</p>')
        text = E.read_text(7, "OEBPS/Text/notes.xhtml")
        self.assertIn("naïve “quoted”", text)
        E.write_text(7, "OEBPS/Text/notes.xhtml", text.replace("naïve", "naïve ☃"))
        self.assertIn(b"na\xefve &#9731; \x93quoted\x94", p.read_bytes())

    def test_paths_stay_inside_the_book(self):
        for bad in ["../meta.json", "/etc/passwd", "OEBPS/../../meta.json", "", "a\\b"]:
            with self.assertRaises(E.EditError):
                E.read_text(7, bad)
        with self.assertRaises(E.EditError):
            E.write_text(7, "../meta.json", "{}")

    def test_not_open(self):
        with self.assertRaises(E.EditError):
            E.files(8)

    def test_find_in_a_file_and_everywhere(self):
        r = E.find(7, {"find": "dorothea", "where": "file", "name": "OEBPS/Text/chapter 2.xhtml"})
        self.assertEqual(r["total"], 2)
        r = E.find(7, {"find": "dorothea", "case": True, "where": "text"})
        self.assertEqual(r["total"], 0)
        r = E.find(7, {"find": "Dorothea", "case": True, "where": "text"})
        self.assertEqual(r["files"], {"OEBPS/Text/chapter 2.xhtml": 2})
        r = E.find(7, {"find": r"\bth(at|e)\b", "regex": True, "where": "text"})
        self.assertEqual(r["files"], {"OEBPS/Text/chapter1.xhtml": 4, "OEBPS/Text/chapter 2.xhtml": 1})
        self.assertEqual(E.find(7, {"find": "margin", "where": "styles"})["total"], 1)
        # normal mode looks for the characters themselves
        self.assertEqual(E.find(7, {"find": "h1, h2", "where": "styles"})["total"], 1)
        self.assertEqual(E.find(7, {"find": "1.2em", "where": "styles", "regex": False})["total"], 1)
        with self.assertRaises(E.EditError):
            E.find(7, {"find": "(unclosed", "regex": True, "where": "text"})
        with self.assertRaises(E.EditError):
            E.find(7, {"find": "", "where": "text"})

    def test_offsets_count_like_the_browser(self):
        # 😀 is two units in the browser's editor and one character in Python: matches after it move by one
        name = "OEBPS/Text/chapter 2.xhtml"
        r = E.find(7, {"find": "Dorothea", "case": True, "where": "file", "name": name})
        text = E.read_text(7, name)
        first, second = r["matches"]
        self.assertEqual(text[first["start"]:first["end"]], "Dorothea")
        self.assertEqual(first["line"], 2)
        u16 = text.encode("utf-16-le")
        self.assertEqual(u16[second["start"] * 2:second["end"] * 2].decode("utf-16-le"), "Dorothea")
        self.assertEqual(second["start"], text.index("Then Dorothea") + 5 + 1)

    def test_replace_all_with_groups_and_a_checkpoint(self):
        r = E.replace(7, {"find": r"(Miss|Mr\.) (\w+)", "replace": r"\2, \1", "regex": True, "where": "text"})
        self.assertEqual(r, {"total": 1, "files": {"OEBPS/Text/chapter1.xhtml": 1}})
        self.assertIn("Brooke, Miss had", E.read_text(7, "OEBPS/Text/chapter1.xhtml"))
        cps = E.checkpoints(7)
        self.assertEqual([c["label"] for c in cps], ["Replace all"])
        before = self.root / "7" / "checkpoints" / str(cps[0]["n"]) / "OEBPS/Text/chapter1.xhtml"
        self.assertIn("Miss Brooke had", before.read_text())
        # normal mode puts the words in as they are, backslashes and all
        E.replace(7, {"find": "Celia", "replace": r"C\1", "where": "file", "name": "OEBPS/Text/chapter 2.xhtml", "case": True})
        self.assertIn(r"said C\1.", E.read_text(7, "OEBPS/Text/chapter 2.xhtml"))
        with self.assertRaises(E.EditError):
            E.replace(7, {"find": "(Dorothea)", "replace": r"\3", "regex": True, "where": "text"})

    def test_replace_one_match(self):
        name = "OEBPS/Text/chapter 2.xhtml"
        second = E.find(7, {"find": "Dorothea", "where": "file", "name": name})["matches"][1]
        r = E.replace(7, {"find": "Dorothea", "replace": "Dodo", "where": "file", "name": name, "at": second["start"]})
        self.assertEqual(r["change"], {"from": second["start"], "to": second["end"], "insert": "Dodo"})
        text = E.read_text(7, name)
        self.assertIn('"What is that, Dorothea?"', text)
        self.assertIn("Then Dodo smiled", text)
        self.assertEqual(E.checkpoints(7), [])
        self.assertEqual(E.replace(7, {"find": "Dorothea", "replace": "x", "where": "file", "name": name, "at": 3})["total"], 0)

    def test_ids_for_the_contents(self):
        got = E.ids(7, "OEBPS/Text/chapter1.xhtml")
        self.assertEqual(got, [{"id": "prelude", "tag": "h1", "text": "Prelude Who that cares much to know the history of man, and how the mysterious…"}])
        self.assertEqual([x["id"] for x in E.ids(7, "OEBPS/Text/chapter 2.xhtml")], ["c2"])
        (self.book / "OEBPS/Text/notes.xhtml").write_text('<p id="n1">Fish &amp; chips</p>' + "<p>x</p>" * 60 + '<p id="n2">' + "word " * 70 + "<span class='long'>tail</span></p>")
        got = E.ids(7, "OEBPS/Text/notes.xhtml")
        self.assertEqual(got[0]["text"][:12], "Fish & chips")
        self.assertNotIn("<", got[0]["text"] + got[1]["text"])

    def test_checkpoints_restore_and_keep_ten(self):
        n = E.checkpoint(7, "Smarten punctuation")
        E.write_text(7, "OEBPS/Styles/style.css", "p {}\n")
        E.restore(7, n)
        self.assertEqual(E.read_text(7, "OEBPS/Styles/style.css"), CSS)
        self.assertEqual([c["n"] for c in E.checkpoints(7)], [n])
        for i in range(12):
            E.checkpoint(7, f"Tool {i}")
        cps = E.checkpoints(7)
        self.assertEqual(len(cps), E.KEEP_CHECKPOINTS)
        self.assertEqual(cps[0]["label"], "Tool 11")
        self.assertEqual(len(list((self.root / "7" / "checkpoints").iterdir())), E.KEEP_CHECKPOINTS)
        with self.assertRaises(E.EditError):
            E.restore(7, 999)

    def test_tools_are_checked_before_calibre(self):
        with mock.patch.object(E, "_run") as run:
            for op, args in [("format_disk", {}), ("polish", {"tool": "embed"}), ("remove", {"names": ["mimetype", "META-INF/container.xml"]}),
                             ("rename", {"map": {"META-INF/container.xml": "x.xml"}}), ("rename", {"map": {"OEBPS/toc.ncx": "../x.ncx"}})]:
                with self.assertRaises(E.EditError, msg=op):
                    E.tool(7, op, args)
            run.assert_not_called()

    def test_a_tool_that_changes_nothing_leaves_no_checkpoint(self):
        with mock.patch.object(E, "_run", return_value={"ok": True, "changed": False, "report": []}):
            E.tool(7, "polish", {"tool": "subset"})
        self.assertEqual(E.checkpoints(7), [])
        self.assertFalse(E.meta(7)["changed"])
        with mock.patch.object(E, "_run", return_value={"ok": True, "changed": True, "report": ["Smartened"]}):
            E.tool(7, "polish", {"tool": "smarten_punctuation"})
        self.assertEqual([c["label"] for c in E.checkpoints(7)], ["Smarten punctuation"])
        self.assertTrue(E.meta(7)["changed"])
        with mock.patch.object(E, "_run", side_effect=E.EditError("Calibre said no")):
            with self.assertRaises(E.EditError):
                E.tool(7, "remove", {"names": ["OEBPS/Text/notes.xhtml"]})
        self.assertEqual(len(E.checkpoints(7)), 1)

    def test_close_keeps_only_a_copy_with_changes(self):
        self.assertEqual(E.close(7), {"kept": False})
        self.assertFalse((self.root / "7").exists())
        make_book(self.root)
        E.write_text(7, "OEBPS/Styles/style.css", "p {}\n")
        self.assertEqual(E.close(7), {"kept": True})
        self.assertTrue((self.root / "7" / "book").is_dir())
        E.discard(7)
        self.assertFalse((self.root / "7").exists())

    def test_status_drops_a_stale_copy_without_changes(self):
        src = self.root / "calibre.epub"
        src.write_bytes(b"PK")
        with mock.patch.object(E, "_calibre_book", return_value=("Middlemarch", ["EPUB", "AZW3"])), \
                mock.patch.object(E, "_source", return_value=src):
            m = E.meta(7)
            m["src"] = E._stamp(src)
            E._put_meta(7, m)
            s = E.status(7)
            self.assertEqual((s["formats"], s["stale"], s["copy"]["fmt"]), (["EPUB", "AZW3"], False, "EPUB"))
            # Calibre's file changed: with my changes the copy stays and says so, without them it goes
            src.write_bytes(b"PK and more")
            E.write_text(7, "OEBPS/Styles/style.css", "p {}\n")
            self.assertTrue(E.status(7)["stale"])
            m = E.meta(7)
            m["changed"] = False
            E._put_meta(7, m)
            s = E.status(7)
            self.assertEqual((s["copy"], s["stale"]), (None, False))
            self.assertFalse((self.root / "7").exists())

    def test_inside_is_the_containers_path(self):
        with mock.patch.object(E, "EDIT_DIR_IN", "/config/.daf-edit"):
            self.assertEqual(E.inside(self.root / "7" / "out.epub"), "/config/.daf-edit/7/out.epub")

    def test_add_file_names(self):
        with mock.patch.object(E, "_run", return_value={"ok": True, "name": "OEBPS/Images/map.png"}) as run:
            r = E.add_file(7, "../../map.png", b"\x89PNG")
            self.assertEqual(r["name"], "OEBPS/Images/map.png")
            job = run.call_args[0][1]
            self.assertEqual((job["op"], job["name"]), ("add", "map.png"))
            self.assertFalse((self.root / "7" / "incoming" / "map.png").exists())
        with self.assertRaises(E.EditError):
            E.add_file(7, "noending", b"x")


if __name__ == "__main__":
    unittest.main()
