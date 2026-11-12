"""Learn's areas (daf/areas.py), on a database of made-up books, articles and feeds; the model and the
network are stood in for."""
import sqlite3
import unittest

import json

from daf import areaagent, areas, db


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

    def feed_item(self, did="rss:2", url="https://example.org/feeders/"):
        self.c.execute("INSERT INTO docs (id, kind, where_, status, title, source, url, feed) VALUES (?, 'article', 'feed', 'unseen', 'Feeders', 'A Blog', ?, 'feed/1')",
                       (did, url))
        self.saved = []

        def save(c, d):
            self.saved.append(d)
            c.execute("INSERT INTO docs (id, kind, where_, status, title, url, added) VALUES ('kk:9', 'article', 'library', 'inbox', 'Feeders', ?, 1)", (url,))
            return "kk:9"
        return save

    def test_a_feed_item_is_saved_to_the_library_and_kept_as_that(self):
        save = self.feed_item()
        self.assertEqual(areas.add(self.c, self.a, "doc:rss:2", save=save), "doc:kk:9")
        self.assertEqual(self.saved, ["rss:2"])
        self.assertEqual([x["ref"] for x in areas.page(self.c, self.a)["items"]], ["doc:kk:9"])
        # asked about from the Feed's copy: it's in the area, and adding it again saves nothing more
        self.assertEqual(areas.areas_of(self.c, "doc:rss:2"), [self.a])
        self.assertEqual(areas.add(self.c, self.a, "doc:rss:2", save=save), "doc:kk:9")
        self.assertEqual(self.saved, ["rss:2"])
        # and taken out from there too
        areas.remove(self.c, self.a, "doc:rss:2")
        self.assertEqual(areas.page(self.c, self.a)["items"], [])

    def test_a_feed_item_already_in_the_library_is_not_saved_again(self):
        save = self.feed_item(url="https://example.org/begin/")       # How to Begin, kk:1 (the same address, but for its slash)
        self.assertEqual(areas.add(self.c, self.a, "doc:rss:2", save=save), "doc:kk:1")
        self.assertEqual(self.saved, [])

    def test_library_things_books_and_feeds_are_kept_as_they_are(self):
        for ref in ("doc:kk:1", "book:cal:1", "feed:feed/1", "doc:rss:1"):          # (rss:1 has no address to save)
            self.assertEqual(areas.add(self.c, self.a, ref, save=lambda c, d: self.fail("saved")), ref)

    def test_the_areas_several_things_are_all_in(self):
        b = areas.create(self.c, "Knots", suggest=False)
        for aid in (self.a, b):
            areas.add(self.c, aid, "doc:kk:1")
        areas.add(self.c, self.a, "book:cal:1")
        self.assertEqual(areas.areas_of(self.c, ["doc:kk:1"]), sorted([self.a, b]))
        self.assertEqual(areas.areas_of(self.c, ["doc:kk:1", "book:cal:1"]), [self.a])
        self.assertEqual(areas.areas_of(self.c, ["doc:kk:2"]), [])
        self.assertEqual(areas.areas_of(self.c, []), [])

    def test_not_a_good_source_is_set_aside_for_the_helper(self):
        for ref in ("doc:kk:1", "feed:feed/1", "want:Bad Book|X"):
            areas.add(self.c, self.a, ref)
        self.assertIsNone(areas.remove(self.c, self.a, "doc:kk:1"))                  # just taken out
        sids = [areas.remove(self.c, self.a, r, bad=True) for r in ("feed:feed/1", "want:Bad Book|X")]
        self.assertEqual(areas.page(self.c, self.a)["items"], [])
        rows = self.c.execute("SELECT kind, title, url, state FROM area_suggest ORDER BY rowid").fetchall()
        self.assertEqual([tuple(r) for r in rows], [("feed", "A Blog", "https://example.org/rss", "skipped"), ("book", "Bad Book", "", "skipped")])
        seen = {}
        areas.suggest_now(self.c, self.a, ask=lambda n, g, have, skipped: seen.setdefault("skipped", skipped) and [])
        self.assertEqual(seen["skipped"], ["A Blog", "Bad Book"])                   # told to the model, never suggested again
        areas.unskip(self.c, sids[1])                                                 # Undo
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM area_suggest").fetchone()[0], 1)

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


class Agent(unittest.TestCase):
    """The area's agent (daf/areaagent.py): the model stood in for by what it might say."""

    def setUp(self):
        self.c = conn()
        c = self.c
        c.execute("INSERT INTO doc_content (id, blocks, fetched) VALUES ('kk:1', ?, 1)", (json.dumps(
            [{"t": "h2", "x": "Begin"}, {"t": "p", "x": "Look up at dawn."}, {"t": "img", "x": ""}, {"t": "p", "x": "Keep a notebook."}]),))
        c.execute("INSERT INTO doc_content (id, blocks, fetched) VALUES ('kk:2', ?, 1)", (json.dumps(
            [{"t": "cue", "ts": 0, "x": "Hello."}, {"t": "cue", "ts": 95, "x": "The wren sings loudest."}]),))
        c.execute("INSERT INTO highlights (id, book_id, source, text, note, created, deleted, seen) VALUES ('h1', 'cal:1', 'daf', 'Robins sing first.', 'true here', 1, 0, 0)")
        c.execute("INSERT INTO highlights (id, book_id, source, text, created, deleted, seen) VALUES ('h2', 'kk:1', 'daf', 'Keep a notebook.', 2, 0, 0)")
        c.execute("INSERT INTO books (id, kind, title, private) VALUES ('kk:3', 'article', 'Diary', 1)")
        c.execute("INSERT INTO docs (id, kind, where_, status, title, url) VALUES ('kk:3', 'article', 'library', 'inbox', 'Diary', 'https://example.org/d')")
        c.commit()
        self.a = areas.create(c, "Birdwatching", "Know the garden birds", suggest=False)
        for ref in ("book:cal:1", "doc:kk:1", "doc:kk:2", "doc:kk:3", "feed:feed/1"):
            areas.add(c, self.a, ref)

    def test_what_the_model_reads(self):
        srcs = areaagent.sources(self.c, self.a)
        self.assertEqual([s["title"] for s in srcs], ["A Field Guide", "How to Begin", "A Talk"])     # no feed, nothing private
        self.assertEqual(srcs[1]["paras"], {0: 1, 1: 2, 3: 3})
        self.assertIn("(t:95) The wren sings loudest.", srcs[2]["lines"])
        block = areaagent._block(srcs[0])
        self.assertIn('(h:h1) "Robins sing first." (their note: true here)', block)
        self.assertIn("40% through", block)

    def test_an_answer_says_where_each_part_came_from(self):
        said = {"paras": [{"text": "Robins first.", "from": [{"n": 1, "at": "h:h1"}, {"n": 1, "at": "h:nope"}]},
                          {"text": "Write it down.", "from": [{"n": 2, "at": "p:3"}]},
                          {"text": "Listen for the wren.", "from": [{"n": 3, "at": "t:95"}, {"n": 9}]},
                          {"text": "From what I know.", "from": []}]}
        cid = self.ask(said, anywhere=False)
        x = areaagent.chats(self.c, self.a)[0]
        self.assertEqual((x["id"], x["state"]), (cid, "done"))
        self.assertEqual([[ch["go"] for ch in p["from"]] for p in x["paras"]],
                         [["book/cal%3A1/hl:h1"], ["read/kk%3A1/p:3"], ["read/kk%3A2/t:95"], []])     # one each, where it was first cited
        self.assertEqual(x["paras"][1]["from"][0]["label"], "How to Begin · ¶ 3")
        self.assertEqual(x["paras"][2]["from"][0]["label"], "A Talk · 1:35")
        self.assertEqual(x["n"], 3)
        self.assertNotIn("Diary", self.prompt)                    # a private article never goes to the model
        self.assertIn("Answer from these sources.", self.prompt)

    def test_from_anywhere_it_offers_things_that_open(self):
        said = {"paras": [{"text": "Try this.", "from": []}],
                "outside": [{"kind": "article", "title": "Good", "by": "A", "url": "https://example.org/good"},
                            {"kind": "article", "title": "Broken", "by": "B", "url": "https://nowhere.invalid/x"},
                            {"kind": "podcast", "title": "Odd"}]}
        self.ask(said, anywhere=True)
        self.assertEqual([o["title"] for o in areaagent.chats(self.c, self.a)[0]["outside"]], ["Good"])
        self.assertIn("from what you know beyond them", self.prompt)

    def test_words_that_arent_json_still_show(self):
        self.ask("The robin sings first.", anywhere=False)
        self.assertEqual(areaagent.chats(self.c, self.a)[0]["paras"][0]["text"], "The robin sings first.")

    def test_a_failed_answer_says_so_and_can_be_forgotten(self):
        def boom(text, timeout=0):
            raise RuntimeError("The model didn't answer: busy")
        cid = self.row("Why?")
        areaagent.ask_now(self.c, cid, run=boom)
        x = areaagent.chats(self.c, self.a)[0]
        self.assertEqual((x["state"], x["error"]), ("error", "The model didn't answer: busy"))
        areaagent.forget(self.c, self.a, cid)
        self.assertEqual(areaagent.chats(self.c, self.a), [])

    def row(self, q, anywhere=False):
        cid = "q" + q.encode().hex()[:8]
        self.c.execute("INSERT INTO area_chat (id, area_id, q, anywhere, state, made) VALUES (?, ?, ?, ?, 'asking', 1)", (cid, self.a, q, int(anywhere)))
        return cid

    def ask(self, said, anywhere):
        cid = self.row("How do I start?", anywhere)

        def run(text, timeout=0):
            self.prompt = text
            return said if isinstance(said, str) else "Here: " + json.dumps(said)
        areaagent.ask_now(self.c, cid, run=run, check=lambda o: None if "invalid" in o["url"] else o)
        return cid

    def test_a_plan_from_the_areas_things(self):
        said = {"title": "Two weeks to the garden", "weeks": [
            {"name": "Sounds", "steps": [{"n": 1, "part": "ch. 1-2", "mins": 60}, {"n": 3, "mins": 14}, {"n": 42}]},
            {"name": "Out there", "steps": [{"do": "Sit outside at dawn", "mins": 30},
                                            {"add": {"kind": "article", "title": "Feeders", "by": "A", "url": "https://example.org/f"}, "mins": 10},
                                            {"add": {"kind": "article", "title": "Gone", "url": "https://nowhere.invalid/"}}]},
            {"name": "Empty", "steps": []}]}
        areaagent.plan_now(self.c, self.a, 30, 2, run=lambda t, timeout=0: json.dumps(said), check=lambda o: None if "invalid" in o["url"] else o)
        p = areas.page(self.c, self.a)
        x = areaagent.extra(self.c, self.a, p)
        self.assertIsNone(x["plan"])
        d = x["plan_draft"]
        self.assertEqual([w["name"] for w in d["weeks"]], ["Sounds", "Out there"])
        self.assertEqual([(s["title"], s.get("part", ""), s["mins"]) for s in d["weeks"][0]["steps"]], [("A Field Guide", "ch. 1-2", 60), ("A Talk", "", 14)])
        self.assertEqual([s["kind"] for s in d["weeks"][1]["steps"]], ["do", "article"])
        self.assertTrue(d["weeks"][1]["steps"][1]["add"])
        # kept, ticked off, and its outside thing added to the area
        ids = [[st["id"] for st in w["steps"]] for w in d["weeks"]]
        areaagent.plan_change(self.c, self.a, {"keep": True})
        areaagent.plan_change(self.c, self.a, {"tick": ids[0][0], "done": True})
        self.c.execute("INSERT INTO docs (id, kind, where_, status, title, url) VALUES ('kk:9', 'article', 'library', 'inbox', 'Feeders', 'https://example.org/f')")
        from unittest import mock
        with mock.patch.object(areas, "_save_link", lambda c, u, t=None: "kk:9"):
            areaagent.plan_change(self.c, self.a, {"add": ids[1][1]})
        self.c.execute("UPDATE docs SET status = 'archive' WHERE id = 'kk:2'")       # the video watched: its step is done
        p = areas.page(self.c, self.a)
        plan = areaagent.extra(self.c, self.a, p)["plan"]
        self.assertEqual([s["done"] for s in plan["weeks"][0]["steps"]], [True, True])
        self.assertEqual(plan["now"], 1)
        self.assertEqual(plan["weeks"][1]["steps"][1]["go"], "read/kk%3A9")
        self.assertIn("doc:kk:9", [x["ref"] for x in p["items"]])
        with self.assertRaises(ValueError):
            areaagent.plan_change(self.c, self.a, {"tick": "nope", "done": True})
        # moved (the "do" step into week 1, first), taken out and put back
        areaagent.plan_change(self.c, self.a, {"order": {"0": [ids[1][0], ids[0][1], ids[0][0]]}})
        view = lambda: areaagent.extra(self.c, self.a, areas.page(self.c, self.a))["plan"]
        self.assertEqual([[s["title"] for s in w["steps"]] for w in view()["weeks"]],
                         [["Sit outside at dawn", "A Talk", "A Field Guide"], ["Feeders"]])
        areaagent.plan_change(self.c, self.a, {"remove": ids[0][1]})
        self.assertEqual([s["title"] for s in view()["weeks"][0]["steps"]], ["Sit outside at dawn", "A Field Guide"])
        areaagent.plan_change(self.c, self.a, {"order": {"0": [ids[0][0], ids[1][0]]}})          # (a step taken out keeps its place behind)
        areaagent.plan_change(self.c, self.a, {"restore": ids[0][1]})
        self.assertEqual([s["title"] for s in view()["weeks"][0]["steps"]], ["A Field Guide", "Sit outside at dawn", "A Talk"])

    def test_a_layout_of_known_sections_only(self):
        said = {"sections": [{"kind": "continue", "title": "Go on"}, {"kind": "plan"}, {"kind": "widget"},
                             {"kind": "highlights", "title": "Songs", "wide": True, "groups": [{"name": "First", "hl": ["h1", "nope"]}, {"name": "None", "hl": ["x"]}]},
                             {"kind": "things", "title": "Watch", "items": [3, 99]}, {"kind": "things", "items": [99]},
                             {"kind": "suggestions"}, {"kind": "feeds"}]}
        got = areaagent.layout_now(self.c, self.a, "for spring", run=lambda t, timeout=0: json.dumps(said))
        self.assertEqual([s["kind"] for s in got], ["continue", "highlights", "things", "feeds"])      # no plan yet, suggestions off
        self.assertEqual(got[1]["groups"], [{"name": "First", "hl": ["h1"]}])
        self.assertEqual(got[2]["refs"], ["doc:kk:2"])
        p = areas.page(self.c, self.a)
        x = areaagent.extra(self.c, self.a, p)
        self.assertIsNone(x["layout"])
        self.assertEqual([s["kind"] for s in x["draft"]], ["continue", "highlights", "things", "feeds"])
        self.assertEqual(x["draft"][1]["groups"][0]["hls"][0]["go"], "book/cal%3A1/hl:h1")
        areaagent.layout_change(self.c, self.a, {"keep": True})
        x = areaagent.extra(self.c, self.a, areas.page(self.c, self.a))
        self.assertEqual((x["draft"], [s["kind"] for s in x["layout"]]), (None, ["continue", "highlights", "things", "feeds"]))
        # edited by hand, then back to the plain page
        areaagent.layout_change(self.c, self.a, {"sections": [{"kind": "feeds"}, {"kind": "next", "wide": True}]})
        self.assertEqual([s["kind"] for s in areaagent.extra(self.c, self.a, areas.page(self.c, self.a))["layout"]], ["feeds", "next"])
        areaagent.layout_change(self.c, self.a, {"plain": True})
        x = areaagent.extra(self.c, self.a, areas.page(self.c, self.a))
        self.assertIsNone(x["layout"])
        self.assertEqual([s["kind"] for s in x["sections"]], ["continue", "next", "highlights", "feeds"])   # the plain page: what there is

    def test_areas_home_asks_across_every_area(self):
        b = areas.create(self.c, "Knots", "Tie a bowline", suggest=False)
        areas.add(self.c, b, "doc:kk:1")                     # in both areas: read once, with both names
        areas.add(self.c, b, "book:cal:2")
        srcs = areaagent.sources_all(self.c)
        self.assertEqual([(s["title"], s["areas"]) for s in srcs],
                         [("A Field Guide", ["Birdwatching"]), ("How to Begin", ["Birdwatching", "Knots"]), ("A Talk", ["Birdwatching"]), ("Done Already", ["Knots"])])
        self.assertEqual([s["title"] for s in areaagent.sources_all(self.c, [b])], ["How to Begin", "Done Already"])
        cid = "qall1"
        self.c.execute("INSERT INTO area_chat (id, area_id, q, anywhere, refs, state, made) VALUES (?, ?, ?, 0, ?, 'asking', 1)",
                       (cid, areaagent.ALL, "I want to learn sailing", json.dumps([b])))
        said = {"paras": [{"text": "Knots first.", "from": [{"n": 1, "at": "p:3"}]}], "new_area": {"name": "Sailing", "goal": "Sail a dinghy"}}
        seen = {}

        def run(text, timeout=0):
            seen["text"] = text
            return json.dumps(said)
        areaagent.ask_now(self.c, cid, run=run)
        self.assertIn("- Knots: Tie a bowline", seen["text"])
        self.assertIn("[in Knots]", seen["text"])
        self.assertNotIn("A Field Guide", seen["text"])          # only the areas asked about
        x = areaagent.home(self.c)
        self.assertEqual([a["name"] for a in x["areas"]], ["Birdwatching", "Knots"])
        q = x["chat"][0]
        self.assertEqual((q["paras"][0]["from"][0]["go"], q["new_area"]), ("read/kk%3A1/p:3", {"name": "Sailing", "goal": "Sail a dinghy"}))
        self.assertEqual(areaagent.chats(self.c, self.a), [])     # (not in an area's own Ask)
        # an area that's already there is never offered again
        areas.create(self.c, "sailing", suggest=False)
        self.c.execute("UPDATE area_chat SET state = 'asking' WHERE id = ?", (cid,))
        areaagent.ask_now(self.c, cid, run=run)
        self.assertNotIn("new_area", areaagent.home(self.c)["chat"][0])
        areaagent.forget(self.c, areaagent.ALL, cid)
        self.assertEqual(areaagent.home(self.c)["chat"], [])

    def test_deleting_the_area_forgets_what_was_asked(self):
        self.row("Why?")
        areas.delete(self.c, self.a)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM area_chat").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
