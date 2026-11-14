"""The Convert sheet's settings (convertopts.py): what Daf takes and how it checks it, ebook-convert's
flags (one argument each, never a shell string), a book's own settings as Calibre keeps them, and the
endpoints handing the options on to calibrewrite."""
import json
import os
import pickle
import sqlite3
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException

HERE = Path(__file__).parent
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))   # importing daf never touches the real state

from daf import calibrewrite, config, convertopts as co  # noqa: E402


def calibre_blob(d, short=False):
    """A conversion_options row's data the way Calibre 9 writes it (pickle_binary_string of "json:…")."""
    raw = b"json:" + json.dumps(d, indent=2).encode()
    if short:
        return b"\x80\x02U" + struct.pack("<B", len(raw)) + raw + b"."
    return b"\x80\x02T" + struct.pack("<I", len(raw)) + raw + b"."


class Clean(unittest.TestCase):
    def test_unknown_keys_dropped(self):
        out = co.clean({"margin_top": 10, "debug_pipeline": "/tmp/x", "read_metadata_from_opf": "/etc/passwd",
                        "search_replace": "x", "__proto__": 1, "transform_css_rules": "[]", "sr1_search": "a"}, "EPUB")
        self.assertEqual(out, {"margin_top": 10.0})

    def test_numbers_clamped_and_typed(self):
        out = co.clean({"margin_top": "12.5", "margin_left": -40, "base_font_size": 1e9, "toc_threshold": 3.6,
                        "max_toc_links": "7", "html_unwrap_factor": 5, "minimum_line_height": 0}, "EPUB")
        self.assertEqual(out["margin_top"], 12.5)
        self.assertEqual(out["margin_left"], -1.0)          # below zero is Calibre's "leave the book's margin"
        self.assertEqual(out["base_font_size"], 100.0)
        self.assertIsInstance(out["base_font_size"], float)
        self.assertEqual(out["toc_threshold"], 4)
        self.assertIsInstance(out["toc_threshold"], int)
        self.assertEqual(out["max_toc_links"], 7)
        self.assertEqual(out["html_unwrap_factor"], 1.0)
        self.assertEqual(out["minimum_line_height"], 0.0)

    def test_bad_numbers_dropped(self):
        out = co.clean({"margin_top": "ten", "margin_bottom": float("nan"), "margin_left": float("inf"),
                        "margin_right": True, "line_height": None, "flow_size": [3]}, "EPUB")
        self.assertEqual(out, {})

    def test_enums(self):
        out = co.clean({"output_profile": "kindle_pw", "input_profile": "nope", "epub_version": 3,
                        "change_justification": "justify", "chapter_mark": "pagebreak; rm -rf /"}, "EPUB")
        self.assertEqual(out, {"output_profile": "kindle_pw", "epub_version": "3", "change_justification": "justify"})
        self.assertEqual(co.clean({"paper_size": "a4"}, "PDF"), {"paper_size": "a4"})
        self.assertEqual(co.clean({"paper_size": "A4 "}, "PDF"), {})
        self.assertEqual(co.clean({"output_profile": True}, "EPUB"), {})

    def test_text_one_line_and_capped(self):
        out = co.clean({"toc_title": "Contents\n--output-profile=kindle", "chapter": "x" * 5000, "level1_toc": "  ",
                        "embed_font_family": 12}, "EPUB")
        self.assertEqual(out["toc_title"], "Contents --output-profile=kindle")
        self.assertEqual(len(out["chapter"]), 1000)
        self.assertIsNone(out["level1_toc"])                # empty: Calibre's own
        self.assertNotIn("embed_font_family", out)          # not text

    def test_extra_css_capped(self):
        out = co.clean({"extra_css": "p { margin: 0 }\n" * 5000}, "EPUB")
        self.assertEqual(len(out["extra_css"]), 20000)
        self.assertIn("\n", out["extra_css"])               # CSS keeps its lines
        self.assertIsNone(co.clean({"extra_css": "  \n "}, "EPUB")["extra_css"])

    def test_filter_and_font_key(self):
        self.assertEqual(co.clean({"filter_css": "font-family, Margin-Left,font-family"}, "EPUB")["filter_css"], "font-family,margin-left")
        self.assertNotIn("filter_css", co.clean({"filter_css": "color;}body{x"}, "EPUB"))
        self.assertEqual(co.clean({"font_size_mapping": "12, 12,14,16"}, "EPUB")["font_size_mapping"], "12,12,14,16")
        self.assertNotIn("font_size_mapping", co.clean({"font_size_mapping": "big"}, "EPUB"))

    def test_booleans(self):
        out = co.clean({"smarten_punctuation": True, "remove_fake_margins": 0, "linearize_tables": "yes", "insert_metadata": 2}, "EPUB")
        self.assertEqual(out, {"smarten_punctuation": True, "remove_fake_margins": False})

    def test_output_options_belong_to_their_format(self):
        opts = {"epub_version": "3", "no_inline_toc": True, "kepub_prefer_justification": True, "pdf_page_numbers": True}
        self.assertEqual(co.clean(opts, "EPUB"), {"epub_version": "3"})
        self.assertEqual(co.clean(opts, "AZW3"), {"no_inline_toc": True})
        self.assertEqual(co.clean(opts, "KEPUB"), {"kepub_prefer_justification": True})
        self.assertEqual(co.clean(opts, "PDF"), {"pdf_page_numbers": True})
        self.assertEqual(co.clean(opts), opts)              # Daf's defaults keep every format's

    def test_not_a_dict(self):
        self.assertEqual(co.clean(None, "EPUB"), {})
        self.assertEqual(co.clean([("margin_top", 3)], "EPUB"), {})


class More(unittest.TestCase):
    """Search & replace, page breaks, start reading at, PDF templates and size, image size limits."""
    def test_search_replace(self):
        sr = lambda v: co.clean({"search_replace": v}, "EPUB").get("search_replace", "DROPPED")
        self.assertEqual(json.loads(sr([["colou?r", "color"], ["Page \\d+", ""]])), [["colou?r", "color"], ["Page \\d+", ""]])
        self.assertEqual(json.loads(sr('[["a", "b"]]')), [["a", "b"]])          # Calibre's own JSON text
        self.assertEqual(json.loads(sr([["(unclosed", "x"], ["ok", "fine"]])), [["ok", "fine"]])
        self.assertEqual(json.loads(sr([["a\nb", "x"], ["c", "d\re"], ["  ", "x"], ["a", 3], ["a"], "ab", ["x" * 1001, ""]])), [])
        self.assertEqual(len(json.loads(sr([["a%d" % i, ""] for i in range(80)]))), co.SR_MAX)
        self.assertEqual(sr("not json"), "DROPPED")
        self.assertEqual(sr({"a": "b"}), "DROPPED")
        self.assertEqual(sr([]), "[]")

    def test_bad_regex(self):
        self.assertEqual(co.bad_regex({"search_replace": [["ok", ""], ["(", "x"]]}), "(")
        self.assertEqual(co.bad_regex({"search_replace": '[["\\\\p{Lu}", "x"]]'}), "\\p{Lu}")   # Calibre checks with Python's re too
        self.assertIsNone(co.bad_regex({"search_replace": [["ok", ""]]}))
        self.assertIsNone(co.bad_regex({}))
        self.assertIsNone(co.bad_regex(None))

    def test_files_not_flags(self):
        opts = co.clean({"search_replace": [["--output-profile=kindle", "x"]], "extra_css": "p{}"}, "EPUB")
        self.assertEqual(co.flags(opts, "EPUB"), [])
        self.assertEqual(co.files(opts), {"css": "p{}", "sr": [["--output-profile=kindle", "x"]]})
        self.assertEqual(co.files({}), {"css": None, "sr": None})
        self.assertEqual(co.files(co.clean({"search_replace": []}, "EPUB")), {"css": None, "sr": None})

    def test_structure_xpaths(self):
        opts = co.clean({"page_breaks_before": "//*[name()='h2']", "start_reading_at": "//*[@id='start']\n"}, "EPUB")
        self.assertEqual(co.flags(opts, "EPUB"), ["--page-breaks-before=//*[name()='h2']", "--start-reading-at=//*[@id='start']"])
        self.assertEqual(co.defaults("EPUB")["page_breaks_before"], "/")

    def test_pdf_size_and_templates(self):
        opts = co.clean({"custom_size": " 100 × 150.5 ", "unit": "millimeter", "pdf_header_template": "<p>\n_TITLE_ \x00_PAGENUM_</p>",
                         "pdf_footer_template": "x" * 9000}, "PDF")
        self.assertEqual(opts["custom_size"], "100x150.5")
        self.assertEqual(opts["pdf_header_template"], "<p>\n_TITLE_ _PAGENUM_</p>")
        self.assertEqual(len(opts["pdf_footer_template"]), 5000)
        f = co.flags(opts, "PDF")
        self.assertIn("--custom-size=100x150.5", f)
        self.assertIn("--unit=millimeter", f)
        self.assertIn("--pdf-header-template=<p>\n_TITLE_ _PAGENUM_</p>", f)      # one argument, lines and all
        for bad in ("0x10", "10x", "abc", "1e3x5", "-5x5", 7):
            self.assertNotIn("custom_size", co.clean({"custom_size": bad}, "PDF"), bad)
        self.assertIsNone(co.clean({"custom_size": "", "pdf_header_template": "  "}, "PDF")["custom_size"])
        self.assertNotIn("unit", co.clean({"unit": "furlong"}, "PDF"))
        self.assertEqual(co.clean({"custom_size": "1x1", "pdf_header_template": "x"}, "EPUB"), {})   # PDF's own

    def test_image_size(self):
        for fmt, k in (("EPUB", "epub_max_image_size"), ("KEPUB", "kepub_max_image_size")):
            self.assertEqual(co.clean({k: "400 x 300"}, fmt), {k: "400x300"})
            self.assertEqual(co.clean({k: "profile"}, fmt), {k: "profile"})
            self.assertEqual(co.clean({k: "none"}, fmt), {k: "none"})
            for bad in ("400x", "0x300", "-4x3", "big", "4.5x3", None):
                self.assertNotIn(k, co.clean({k: bad}, fmt) if bad is not None else {}, bad)
            self.assertEqual(co.flags(co.clean({k: "400x300"}, fmt), fmt), ["--%s=400x300" % k.replace("_", "-")])
        self.assertEqual(co.clean({"epub_max_image_size": "400x300"}, "KEPUB"), {})


class Flags(unittest.TestCase):
    def test_flags(self):
        opts = co.clean({"margin_top": 20, "output_profile": "kobo", "smarten_punctuation": True, "remove_fake_margins": False,
                         "dehyphenate": True, "linearize_tables": False, "epub_version": "3", "level1_toc": None,
                         "replace_scene_breaks": "", "extra_css": "p{color:red}"}, "EPUB")
        f = co.flags(opts, "EPUB")
        self.assertIn("--margin-top=20.0", f)
        self.assertIn("--output-profile=kobo", f)
        self.assertIn("--smarten-punctuation", f)
        self.assertIn("--disable-remove-fake-margins", f)   # on by default: off is --disable-…
        self.assertIn("--epub-version=3", f)
        self.assertFalse(any("dehyphenate" in x or "linearize" in x or "level1" in x or "scene" in x for x in f))
        self.assertFalse(any("extra-css" in x for x in f))  # a file, written in the container
        self.assertEqual(f, co.flags(opts, "EPUB"))         # a fixed order

    def test_no_injection(self):
        evil = '"; rm -rf / #\' $(touch /tmp/x) `id` --output-profile=kindle'
        opts = co.clean({"toc_title": evil, "chapter": "-//h1 --debug-pipeline=/tmp", "embed_font_family": "--verbose"}, "EPUB")
        f = co.flags(opts, "EPUB")
        self.assertTrue(all(isinstance(x, str) and x.startswith("--") for x in f))
        self.assertIn("--toc-title=" + evil, f)             # the whole value in its own argument
        self.assertIn("--chapter=-//h1 --debug-pipeline=/tmp", f)
        self.assertIn("--embed-font-family=--verbose", f)
        names = [x.split("=", 1)[0] for x in f]
        self.assertEqual(sorted(names), ["--chapter", "--embed-font-family", "--toc-title"])

    def test_whole_numbers_where_the_command_line_wants_them(self):
        f = co.flags(co.clean({"base_font_size": 12.6, "line_height": 14.2, "minimum_line_height": 130.5}, "EPUB"), "EPUB")
        self.assertEqual(f, ["--base-font-size=13", "--minimum-line-height=130.5", "--line-height=14"])

    def test_flags_only_from_the_allow_list(self):
        f = co.flags({"debug_pipeline": "/tmp", "margin_top": 3.0}, "EPUB")
        self.assertEqual(f, ["--margin-top=3.0"])

    def test_every_flag_is_a_real_ebook_convert_option(self):
        known = {"--" + k.replace("_", "-") for f in [None] + list(co.OUT) for k in co.specs(f)}
        known |= {"--disable-" + k.replace("_", "-") for k, s in co.specs().items() if s["t"] == "bool" and s["d"]}
        for fmt in co.OUT:
            everything = {k: (not s["d"]) if s["t"] == "bool" else s["d"] for k, s in co.specs(fmt).items()}
            for x in co.flags(everything, fmt):
                self.assertIn(x.split("=", 1)[0], known)

    def test_to_save(self):
        s = co.to_save({"margin_top": 9.0}, "KEPUB")
        self.assertEqual(s["margin_top"], 9.0)
        self.assertEqual(s["flow_size"], 512)               # KEPUB's own default, not EPUB's 260
        self.assertNotIn("epub_version", s)
        self.assertEqual(s["chapter"], co.CHAPTER)
        json.dumps(s)


class BookSettings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "metadata.db"
        c = sqlite3.connect(self.db)
        c.execute("CREATE TABLE conversion_options (id INTEGER PRIMARY KEY, format TEXT NOT NULL COLLATE NOCASE, book INTEGER, data BLOB NOT NULL, UNIQUE(format, book))")
        c.execute("INSERT INTO conversion_options (format, book, data) VALUES ('PIPE', 7, ?)",
                  (calibre_blob({"margin_top": 15.0, "output_profile": "kindle", "gui_preferred_input_format": "pdf",
                                 "search_replace": "[]", "epub_version": "3", "base_font_size": 0.0}),))
        c.execute("INSERT INTO conversion_options (format, book, data) VALUES ('PIPE', 8, ?)", (b"not a pickle",))
        c.execute("INSERT INTO conversion_options (format, book, data) VALUES ('PIPE', 10, ?)",
                  (calibre_blob({"sr1_search": "colour", "sr1_replace": "color", "sr2_search": None, "sr3_search": "\\s+$", "sr3_replace": None}),))
        c.commit()
        c.close()
        p = mock.patch.object(config, "CALIBRE_DBS", [self.db])
        p.start()
        self.addCleanup(p.stop)

    def test_read_as_calibre_keeps_it(self):
        opts, src = co.book_opts(7)
        self.assertEqual(src, "PDF")
        self.assertEqual(opts, {"margin_top": 15.0, "output_profile": "kindle", "epub_version": "3", "base_font_size": 0.0, "search_replace": "[]"})

    def test_older_three_pairs(self):
        opts, _src = co.book_opts(10)
        self.assertEqual(json.loads(opts["search_replace"]), [["colour", "color"], ["\\s+$", ""]])

    def test_none_or_unreadable(self):
        self.assertEqual(co.book_opts(8), ({}, None))
        self.assertEqual(co.book_opts(9), ({}, None))

    def test_parse_formats(self):
        self.assertEqual(co.parse(calibre_blob({"a": 1}, short=True)), {"a": 1})
        old = repr({"margin_top": 4.0, "chapter_mark": "rule"}).encode()
        self.assertEqual(co.parse(b"\x80\x02T" + struct.pack("<I", len(old)) + old + b"."), {"margin_top": 4.0, "chapter_mark": "rule"})
        self.assertEqual(co.parse(None), {})
        self.assertEqual(co.parse(calibre_blob([1, 2])), {})

    def test_parse_never_unpickles(self):
        calls = []

        class Evil:
            def __reduce__(self):
                return (calls.append, ("ran",))
        self.assertEqual(co.parse(pickle.dumps(Evil(), protocol=2)), {})
        self.assertEqual(calls, [])


class Endpoints(unittest.TestCase):
    def setUp(self):
        from daf import app
        self.app = app
        self.formats = {1: ["EPUB", "PDF"], 2: ["AZW3"], 3: ["AZW3", "KFX"], 4: [], 5: ["DOCX", "TXT"]}
        p = mock.patch("daf.catalog.formats_of", side_effect=lambda cid: self.formats.get(cid, []))
        p.start()
        self.addCleanup(p.stop)

    def many(self, body):
        with mock.patch.object(calibrewrite, "start_convert_many", return_value="job1") as m:
            out = self.app.post_convert_many(body)
        return out, m

    def test_many_passes_clean_opts(self):
        out, m = self.many({"ids": [1, 2, "3", 4, 5, 1], "to": "azw3",
                            "opts": {"margin_top": 999, "no_inline_toc": True, "epub_version": "3", "evil": "x"}})
        self.assertEqual(out, {"job": "job1", "total": 2, "have": 2})
        todo, to, opts = m.call_args.args
        self.assertEqual(to, "AZW3")
        self.assertEqual(todo, [(1, "EPUB"), (5, "DOCX")])    # each once; 2 and 3 have it, 4 has no file
        self.assertEqual(opts, {"margin_top": 500.0, "no_inline_toc": True})

    def test_many_replace(self):
        out, m = self.many({"ids": [1, 2, 3], "to": "AZW3", "replace": True, "opts": {}})
        todo, _to, opts = m.call_args.args
        self.assertEqual(todo, [(1, "EPUB"), (3, "KFX")])    # 2 has only the AZW3
        self.assertEqual(opts, {})
        self.assertEqual(out["have"], 0)

    def test_many_without_opts_is_as_before(self):
        _out, m = self.many({"ids": [1], "to": "MOBI"})
        self.assertEqual(m.call_args.args, ([(1, "EPUB")], "MOBI", None))

    def test_many_turned_away(self):
        for body in ({"ids": [1], "to": "DOCX"}, {"ids": [], "to": "EPUB"}, {"ids": [1], "to": "EPUB", "opts": "margin_top=1"}, None):
            with self.assertRaises(HTTPException):
                self.many(body)

    def test_bad_regex_turned_away(self):
        body = {"ids": [1], "to": "AZW3", "opts": {"search_replace": [["([a-z]", "x"]]}}
        with self.assertRaises(HTTPException) as e:
            self.many(body)
        self.assertIn("([a-z]", e.exception.detail)
        with mock.patch("daf.catalog.book_file", return_value=Path("/x.epub")), self.assertRaises(HTTPException):
            self.app.convert_catalog_file(1, {"from": "EPUB", "to": "PDF", "opts": {"search_replace": '[["*", ""]]'}})
        with mock.patch.object(config, "load_settings", return_value={}), mock.patch.object(config, "save_settings") as save, \
                self.assertRaises(HTTPException):
            self.app.put_convert_opts({"opts": {"search_replace": [["?", ""]]}})
        save.assert_not_called()

    def test_one_book(self):
        with mock.patch("daf.catalog.book_file", return_value=Path("/x.epub")), \
                mock.patch.object(calibrewrite, "start_convert", return_value="job2") as m:
            out = self.app.convert_catalog_file(1, {"from": "epub", "to": "kepub", "opts": {"kepub_disable_hyphenation": True, "flow_size": "40", "no_inline_toc": True}})
            self.assertEqual(out, {"job": "job2"})
            self.assertEqual(m.call_args.args, (1, "EPUB", "KEPUB", {"kepub_disable_hyphenation": True, "flow_size": 40}))
            self.app.convert_catalog_file(1, {"from": "EPUB", "to": "PDF"})
            self.assertEqual(m.call_args.args, (1, "EPUB", "PDF", None))
            with self.assertRaises(HTTPException):
                self.app.convert_catalog_file(1, {"from": "EPUB", "to": "PDF", "opts": [1]})

    def test_defaults_saved_clean(self):
        saved = {}
        with mock.patch.object(config, "load_settings", return_value={"home_tz": "UTC"}), \
                mock.patch.object(config, "save_settings", side_effect=lambda s: saved.update(s)):
            out = self.app.put_convert_opts({"opts": {"margin_top": "8", "epub_version": "3", "nope": 1, "pdf_page_numbers": True}})
            self.assertEqual(out["saved"], {"margin_top": 8.0, "epub_version": "3", "pdf_page_numbers": True})
            self.assertEqual(saved["convert_opts"], out["saved"])
            self.assertEqual(saved["home_tz"], "UTC")
            with self.assertRaises(HTTPException):
                self.app.put_convert_opts({"opts": "x"})
        with mock.patch.object(config, "load_settings", return_value={"convert_opts": {"margin_top": 8.0, "bad": 1}}):
            got = self.app.get_convert_opts()
        self.assertEqual(got["saved"], {"margin_top": 8.0})
        self.assertEqual(got["calibre"]["pipe"]["margin_top"], 5.0)
        self.assertEqual(got["calibre"]["out"]["KEPUB"]["flow_size"], 512)
        self.assertEqual(got["formats"], self.app.CONVERT_TO)
        self.assertIn(["kindle_pw", "Kindle PaperWhite"], [list(x) for x in got["choices"]["output_profile"]])
        json.dumps(got)

    def test_settings_keep_the_defaults(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(config, "SETTINGS_PATH", Path(d) / "settings.json"), \
                mock.patch.object(config, "STATE", Path(d)):
            s = config.load_settings()
            s["convert_opts"] = {"margin_top": 8.0}
            config.save_settings(s)
            self.assertEqual(config.load_settings()["convert_opts"], {"margin_top": 8.0})


class Op(unittest.TestCase):
    def test_convert_op(self):
        self.assertEqual(calibrewrite.convert_op(3, "EPUB", "AZW3"), {"op": "convert", "id": 3, "from": "EPUB", "to": "AZW3"})
        op = calibrewrite.convert_op(3, "EPUB", "AZW3", co.clean({"margin_top": 12, "extra_css": "p{x:y}", "no_inline_toc": True}, "AZW3"))
        self.assertEqual(op["flags"], ["--margin-top=12.0", "--no-inline-toc"])
        self.assertEqual(op["css"], "p{x:y}")
        self.assertIsNone(op["sr"])
        self.assertEqual(op["save"]["margin_top"], 12.0)
        self.assertEqual(op["save"]["extra_css"], "p{x:y}")  # the book keeps its CSS in Calibre, as Calibre does
        self.assertTrue(op["save"]["no_inline_toc"])
        op = calibrewrite.convert_op(3, "EPUB", "PDF", co.clean({"search_replace": [["a", "b"]], "custom_size": "5x8", "unit": "inch"}, "PDF"))
        self.assertEqual(op["sr"], [["a", "b"]])
        self.assertEqual(op["flags"], ["--custom-size=5x8", "--unit=inch"])
        self.assertEqual(json.loads(op["save"]["search_replace"]), [["a", "b"]])     # kept the way Calibre's dialog keeps it
        json.dumps(op)

    def test_many_is_one_op_a_book(self):
        opts = co.clean({"margin_top": 12}, "MOBI")
        with mock.patch.object(calibrewrite, "start_each", return_value="j") as m:
            self.assertEqual(calibrewrite.start_convert_many([(1, "EPUB"), (2, "AZW3")], "MOBI", opts), "j")
        ops, timeout = m.call_args.args
        self.assertEqual(m.call_args.kwargs, {"to": "MOBI"})
        self.assertEqual([(o["id"], o["from"], o["flags"]) for o in ops], [(1, "EPUB", ["--margin-top=12.0"]), (2, "AZW3", ["--margin-top=12.0"])])
        self.assertTrue(all(o["save"]["margin_top"] == 12.0 for o in ops))
        with mock.patch.object(calibrewrite, "start_each", return_value="j") as m:
            calibrewrite.start_convert_many([(1, "EPUB")], "MOBI")
        self.assertEqual(m.call_args.args[0], [{"op": "convert", "id": 1, "from": "EPUB", "to": "MOBI"}])

    def test_script(self):
        compile(calibrewrite.SCRIPT, "calibre-script", "exec")
        self.assertIn("save_specifics(ldb, ids[0], recs)", calibrewrite.SCRIPT)
        self.assertIn('cmd.append("--extra-css=" + css)', calibrewrite.SCRIPT)
        self.assertIn('cmd.append("--search-replace=" + srf)', calibrewrite.SCRIPT)


if __name__ == "__main__":
    unittest.main()
