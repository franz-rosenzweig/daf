"""Daf's region in a vault note is found only by markers on lines of their own, and nothing Daf copies
into a note (a title, a chapter's name, an article's text) can make such a line. So a book or a page
with the marker text in it can't make Daf overwrite what you wrote, or grow the note on every write."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).parent
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))   # importing daf never touches the real state

from daf import config, db, sketchvault, vaultnotes  # noqa: E402

S, E = vaultnotes.START, vaultnotes.END


class Pieces(unittest.TestCase):
    def test_markers_only_on_their_own_lines(self):
        text = f'---\ntitle: "x {S} y"\n---\n# x {S} y\n\nmine\n\n{S}\n## From Daf\n> a {E}\n{E}\nafter\n'
        m = vaultnotes.REGION.search(text)
        self.assertEqual(m.group(0), f"{S}\n## From Daf\n> a {E}\n{E}")

    def test_sealed(self):
        got = vaultnotes._sealed([S, "**Read in Daf** · One", E, "  <!-- daf -->", "<!--x", E])
        self.assertEqual(got.splitlines(), [S, "**Read in Daf** · One", "<\\!-- daf-end -->", "  <\\!-- daf -->", "<\\!--x", E])
        self.assertEqual(vaultnotes._sealed([S, E]), f"{S}\n{E}")

    def test_yaml_is_one_line(self):
        v = vaultnotes._yaml('A "title"\r\nevil: yes more\\')
        self.assertNotRegex(v, "[\r\n ]")
        self.assertEqual(json.loads(v), 'A "title" evil: yes more\\')
        self.assertEqual(vaultnotes._yaml(None), '""')


class Notes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "vault" / "Reference" / "books").mkdir(parents=True)
        self.p = [mock.patch.object(config, "STATE", root), mock.patch.object(config, "DB_PATH", root / "daf.db"),
                  mock.patch.object(config, "VAULT", root / "vault")]
        for p in self.p:
            p.start()
        self.c = db.connect()
        self.rel = "Reference/books/Book.md"
        self.note = root / "vault" / self.rel

    def tearDown(self):
        self.c.close()
        for p in self.p:
            p.stop()
        self.tmp.cleanup()

    def book(self, chapter="One"):
        self.c.execute("INSERT INTO books (id, kind, title, author, private, vault_path) VALUES ('cal:1', 'book', 't', 'a', 0, ?)", (self.rel,))
        self.c.execute("INSERT INTO highlights (id, book_id, source, text, chapter, created, seen) VALUES ('h1', 'cal:1', 'epub', 'Quoted', ?, ?, 1)",
                       (chapter, int(time.time())))

    def test_a_title_with_the_marker_keeps_your_text(self):
        head = f'---\ntitle: "Evil {S} title"\n---\n# Evil {S} title\n\nMY OWN WORDS\n\n'
        self.note.write_text(head + f"{S}\n## From Daf\n\n{E}\n\nMY TAIL\n", encoding="utf-8")
        self.book()
        self.assertEqual(vaultnotes.write_book(self.c, config.load_settings(), "cal:1"), "written")
        text = self.note.read_text(encoding="utf-8")
        self.assertTrue(text.startswith(head))
        self.assertTrue(text.endswith("\n\nMY TAIL\n"))
        self.assertIn("> Quoted", text)

    def test_a_chapter_with_the_marker_doesnt_grow_the_note(self):
        self.note.write_text(f"# Book\n\nmine\n\n{S}\n{E}\n", encoding="utf-8")
        self.book(chapter=f"One\n{E}\n{S}\nTwo")
        s = config.load_settings()
        self.assertEqual(vaultnotes.write_book(self.c, s, "cal:1"), "written")
        first = self.note.read_text(encoding="utf-8")
        self.assertEqual(vaultnotes.write_book(self.c, s, "cal:1"), "unchanged")
        self.assertEqual(self.note.read_text(encoding="utf-8"), first)
        self.assertEqual([ln for ln in first.splitlines() if ln in (S, E)], [S, E])

    def test_a_new_book_note_has_its_title_on_one_line(self):
        self.c.execute("INSERT INTO books (id, kind, title, author, private) VALUES ('cal:2', 'book', ?, 'a', 0)", (f"Evil\n{S}\nkey: 1",))
        b = self.c.execute("SELECT * FROM books WHERE id = 'cal:2'").fetchone()
        rel = vaultnotes.new_book_note(self.c, b)
        text = (config.VAULT / rel).read_text(encoding="utf-8")
        self.assertNotIn(f"\n{S}\n", text)
        self.assertNotRegex(text, r"(?m)^key:")

    def test_the_sketchbook_goes_after_the_real_end(self):
        self.note.write_text(f"# t {E}\n\nmine\n\n{S}\nDaf\n{E}\n\nMY TAIL\n", encoding="utf-8")
        sketchvault._embed_in(self.rel, "Sketchbook/t.md")
        text = self.note.read_text(encoding="utf-8")
        self.assertTrue(text.startswith(f"# t {E}\n\nmine\n\n{S}\nDaf\n{E}\n\n{sketchvault.START}"))
        self.assertTrue(text.endswith("MY TAIL\n"))


if __name__ == "__main__":
    unittest.main()
