"""Learn's areas (daf/areas.py), on a database of made-up books, articles and feeds; the model and the
network are stood in for."""
import sqlite3
import unittest

from daf import areas, db


def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(db.SCHEMA)
    for table, col, decl in db.MIGRATIONS:
        if col not in {r[1] for r in c.execute(f"PRAGMA table_info({table})")}:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    c.execute("INSERT INTO books (id, kind, title, author, status, progress) VALUES ('cal:1', 'book', 'A Field Guide', 'A. Writer', 'reading', 40)")
    c.execute("INSERT INTO books (id, kind, title, author, status, progress) VALUES ('cal:2', 'book', 'Done Already', 'B. Writer', 'read', 100)")
    c.execute("INSERT INTO books (id, kind, title, author, private) VALUES ('cal:3', 'book', 'Secret', 'C', 1)")
    c.execute("INSERT INTO docs (id, kind, where_, status, title, source, url, words, progress) VALUES "
              "('kk:1', 'article', 'library', 'inbox', 'How to Begin', 'A Blog', 'https://example.org/begin', 2300, 0)")
    c.execute("INSERT INTO docs (id, kind, where_, status, title, source, url, duration, progress) VALUES "
              "('kk:2', 'video', 'library', 'later', 'A Talk', 'A Channel', 'https://video.example/watch', 840, 50)")
    c.execute("INSERT INTO feeds (id, url, title, site) VALUES ('feed/1', 'https://example.org/rss', 'A Blog', 'https://example.org')")
    c.execute("INSERT INTO docs (id, kind, where_, status, title, feed) VALUES ('rss:1', 'article', 'feed', 'unseen', 'New post', 'feed/1')")
    c.commit()
    return c


class Areas(unittest.TestCase):
    def setUp(self):
        self.c = conn()
        self.a = areas.create(self.c, "Birdwatching", "Know the garden birds", "#2f5d46", suggest=False)

    def test_create_needs_a_name_and_a_good_colour(self):
        with self.assertRaises(ValueError):
            areas.create(self.c, "  ")
        b = areas.create(self.c, "Knots", color="red")
        self.assertEqual(self.c.execute("SELECT color FROM areas WHERE id = ?", (b,)).fetchone()[0], areas.COLORS[0])

    def test_what_is_in_an_area(self):
        for ref in ("book:cal:1", "book:cal:2", "doc:kk:1", "doc:kk:2", "feed:feed/1", "want:Another Book|D. Writer"):
            areas.add(self.c, self.a, ref)
        p = areas.page(self.c, self.a)
        st = {x["title"]: x["st"] for x in p["items"]}
        self.assertEqual(st, {"A Field Guide": "40%", "Done Already": "Done", "How to Begin": "New", "A Talk": "50%", "Another Book": "Wanted"})
        self.assertEqual([x["title"] for x in p["next"]], ["A Field Guide", "How to Begin", "A Talk", "Another Book"])
        self.assertEqual(p["feeds"][0]["st"], "1 new")
        s = p["area"]
        self.assertEqual(s["counts"], "3 books · 1 article · 1 video · 1 feed")
        self.assertEqual((s["n"], s["done"]), (5, 1))         # the feed is followed, not counted

    def test_a_private_book_never_shows(self):
        areas.add(self.c, self.a, "book:cal:3")
        self.assertEqual(areas.page(self.c, self.a)["items"], [])

    def test_nothing_that_isnt_there(self):
        with self.assertRaises(ValueError):
            areas.add(self.c, self.a, "book:cal:404")
        with self.assertRaises(KeyError):
            areas.add(self.c, "nope", "book:cal:1")

    def test_a_link_saved_while_the_library_was_away_becomes_its_doc(self):
        areas.add(self.c, self.a, "url:https://example.org/begin")
        self.assertEqual(areas.page(self.c, self.a)["items"][0]["title"], "How to Begin")

    def test_order_and_remove(self):
        for ref in ("doc:kk:1", "doc:kk:2"):
            areas.add(self.c, self.a, ref)
        areas.order_items(self.c, self.a, ["doc:kk:2", "doc:kk:1"])
        self.assertEqual([x["title"] for x in areas.page(self.c, self.a)["items"]], ["A Talk", "How to Begin"])
        areas.remove(self.c, self.a, "doc:kk:2")
        self.assertEqual(len(areas.page(self.c, self.a)["items"]), 1)

    def test_deleting_an_area_keeps_its_things(self):
        areas.add(self.c, self.a, "doc:kk:1")
        areas.delete(self.c, self.a)
        self.assertEqual(areas.list_areas(self.c), [])
        self.assertTrue(self.c.execute("SELECT 1 FROM docs WHERE id = 'kk:1'").fetchone())

    def test_update(self):
        areas.update(self.c, self.a, {"name": "Birds", "color": "#4b3a78", "suggest": True})
        a = areas.list_areas(self.c)[0]
        self.assertEqual((a["name"], a["color"], a["suggest"], a["goal"]), ("Birds", "#4b3a78", True, "Know the garden birds"))
        with self.assertRaises(ValueError):
            areas.update(self.c, self.a, {"name": ""})


class Helper(unittest.TestCase):
    def setUp(self):
        self.c = conn()
        self.a = areas.create(self.c, "Birdwatching", suggest=True)
        areas.add(self.c, self.a, "doc:kk:1")

    def ask(self, name, goal, have, skipped):
        self.asked = (name, have, skipped)
        return [{"kind": "book", "title": "Birds of the Garden", "by": "E. Author", "url": ""},
                {"kind": "article", "title": "How to Begin", "by": "A Blog", "url": "https://example.org/begin"},   # already there
                {"kind": "article", "title": "Binoculars", "by": "A Shop", "url": "https://example.org/bins"},
                {"kind": "video", "title": "A Broken One", "by": "X", "url": "https://nowhere.invalid/x"},
                {"kind": "feed", "title": "Bird Blog", "by": "Bird Blog", "url": "https://birds.example/feed"}]

    def check(self, s):
        return None if "invalid" in s["url"] else s

    def test_suggestions_skip_what_is_there_and_links_that_dont_open(self):
        got = areas.suggest_now(self.c, self.a, ask=self.ask, check=self.check)
        self.assertEqual([s["title"] for s in got], ["Birds of the Garden", "Binoculars", "Bird Blog"])
        self.assertIn("How to Begin", self.asked[1])
        self.assertEqual(len(areas.suggestions(self.c, self.a)), 3)
        # asked again: nothing it already suggested
        self.assertEqual(areas.suggest_now(self.c, self.a, ask=self.ask, check=self.check), [])

    def test_add_and_set_aside(self):
        areas.suggest_now(self.c, self.a, ask=self.ask, check=self.check)
        s = {x["title"]: x["id"] for x in areas.suggestions(self.c, self.a)}
        self.assertEqual(areas.take(self.c, s["Birds of the Garden"]), "want:Birds of the Garden|E. Author")
        self.assertEqual(areas.take(self.c, s["Binoculars"], save_link=lambda c, u, t: "kk:2"), "doc:kk:2")
        self.assertEqual(areas.take(self.c, s["Bird Blog"], follow=lambda c, u: "feed/1"), "feed:feed/1")
        self.assertEqual(areas.suggestions(self.c, self.a), [])
        titles = {x["title"] for x in areas.page(self.c, self.a)["items"]} | {x["title"] for x in areas.page(self.c, self.a)["feeds"]}
        self.assertEqual(titles, {"How to Begin", "Birds of the Garden", "A Talk", "A Blog"})

    def test_set_aside_is_told_to_the_model_next_time(self):
        areas.suggest_now(self.c, self.a, ask=self.ask, check=self.check)
        areas.skip(self.c, areas.suggestions(self.c, self.a)[0]["id"])
        areas.suggest_now(self.c, self.a, ask=self.ask, check=self.check)
        self.assertEqual(self.asked[2], ["Birds of the Garden"])


if __name__ == "__main__":
    unittest.main()
