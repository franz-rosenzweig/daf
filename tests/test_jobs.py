"""The Jobs list (GET /api/catalog/jobs, POST /api/catalog/jobs/{id}/stop): names, states, order, Stop."""
import time
import unittest
from unittest import mock

from fastapi import HTTPException


class Now:                                              # a job's thread, run right here
    def __init__(self, target, daemon):
        self.target = target

    def start(self):
        self.target()


class Held:                                             # a job's thread, started by hand later
    def __call__(self, target, daemon):
        self.target = target
        return self

    def start(self):
        pass

    def go(self):
        self.target()


class Base(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        from daf import calibrewrite, config
        self.W = calibrewrite
        saved = dict(calibrewrite._jobs)
        calibrewrite._jobs.clear()
        self.addCleanup(lambda: (calibrewrite._jobs.clear(), calibrewrite._jobs.update(saved)))
        # the kept rows go to a database of the test's own, never Daf's
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        was = (config.STATE, config.DB_PATH, calibrewrite._stored)
        config.STATE, config.DB_PATH, calibrewrite._stored = Path(tmp.name), Path(tmp.name) / "daf.db", None
        self.addCleanup(lambda: setattr(calibrewrite, "_stored", was[2]))
        self.addCleanup(lambda: (setattr(config, "STATE", was[0]), setattr(config, "DB_PATH", was[1])))

    def put(self, jid, **j):
        self.W._jobs[jid] = dict({"started": time.time()}, **j)
        return jid


class Names(Base):
    def test_one_book_by_its_title_many_by_count(self):
        W = self.W
        W.name(self.put("a", running=True), "polish", "Polish {}", "Polish {} books", [7])
        W.name(self.put("b", running=True), "polish", "Polish {}", "Polish {} books", [7, 8, 9])
        W.name(self.put("c", running=True), "convert", "Convert {} to AZW3", "", [5])          # no title known
        W.name(self.put("d", state="running", kind="isbn"), "other", "Look up an ISBN", "Look up {} ISBNs", n=4)
        self.put("e", running=True)                                                              # not named: not listed
        rows = {r["id"]: r for r in W.jobs_list(lambda ids: {7: "A Made-Up Book"} if 7 in ids else {})}
        self.assertEqual(rows["a"]["label"], "Polish “A Made-Up Book”")
        self.assertEqual(rows["b"]["label"], "Polish 3 books")
        self.assertEqual(rows["c"]["label"], "Convert a book to AZW3")
        self.assertEqual(rows["d"]["label"], "Look up 4 ISBNs")
        self.assertEqual(rows["d"]["kind"], "isbn")                                             # a job's own kind stays
        self.assertEqual(rows["a"]["kind"], "polish")
        self.assertNotIn("e", rows)

    def test_name_of_nothing(self):
        self.assertIsNone(self.W.name(None, "convert", "x", "y", []))                           # convert-many with nothing to do
        self.assertEqual(self.W.name("gone", "convert", "x", "y", [1]), "gone")


class States(Base):
    def named(self, jid, **j):
        self.put(jid, **j)
        self.W.name(jid, "k", "One {}", "{} books", [1, 2])
        return jid

    def test_states_from_both_shapes(self):
        now = time.time()
        self.named("run", running=True, done=1, total=2, failed=[], stoppable=True)
        self.named("ok", running=False, done=2, total=2, failed=[{"id": 1, "error": "bad file"}], ended=now - 5)
        self.named("allbad", running=False, done=2, total=2, failed=[{"id": 1, "error": "x"}, {"id": 2, "error": "y"}], ended=now - 4)
        self.named("err", running=False, error="Calibre said no", ended=now - 3)
        self.named("st", state="done", ended=now - 2)
        self.named("stf", state="failed", error="nope", ended=now - 1)
        self.named("stopped", running=False, stopped=True, done=1, total=2, failed=[], ended=now)
        self.named("result", running=False, done=[41, 42])                                    # start_job: done is what came back
        rows = {r["id"]: r for r in self.W.jobs_list(lambda ids: {1: "Book One"})}
        self.assertEqual({k: r["state"] for k, r in rows.items()},
                         {"run": "running", "ok": "done", "allbad": "failed", "err": "failed", "st": "done", "stf": "failed", "stopped": "stopped", "result": "done"})
        self.assertEqual((rows["run"]["done"], rows["run"]["total"], rows["run"]["stoppable"]), (1, 2, True))
        self.assertEqual(rows["ok"]["failed"], 1)
        self.assertEqual(rows["ok"]["errors"], [{"id": 1, "error": "bad file", "title": "Book One"}])
        self.assertEqual(rows["allbad"]["error"], "x")
        self.assertEqual(rows["stf"]["error"], "nope")
        self.assertIsNone(rows["result"]["done"])
        self.assertFalse(rows["ok"]["stoppable"])
        self.assertIsNotNone(rows["result"]["ended"])                                         # stamped when first seen finished

    def test_order_and_how_many(self):
        now = time.time()
        for n in range(40):
            self.named("f%d" % n, running=False, ended=now - 1000 + n)
        self.named("old", running=False, ended=now - 2 * 86400)                               # finished over a day ago: gone
        self.put("r1", running=True, started=now - 50)
        self.W.name("r1", "k", "x", "Run one {}", [1, 2])
        self.put("r2", running=True, started=now - 10)
        self.W.name("r2", "k", "x", "Run two {}", [1, 2])
        ids = [r["id"] for r in self.W.jobs_list()]
        self.assertEqual(ids[:2], ["r2", "r1"])                                                # running first, newest first
        self.assertEqual(ids[2:5], ["f39", "f38", "f37"])                                      # then the latest finished
        self.assertEqual(len(ids), 32)
        self.assertNotIn("old", self.W._jobs)

    def test_titles_failing_is_still_a_list(self):
        self.named("a", running=True)
        rows = self.W.jobs_list(mock.Mock(side_effect=OSError("no db")))
        self.assertEqual(rows[0]["label"], "2 books")


class Stop(Base):
    def test_stops_between_books(self):
        W, calls = self.W, []

        def run(ops, timeout):
            calls.append(ops[0]["id"])
            if len(calls) == 1:                                     # Stop pressed while the first book goes
                for k, j in list(W._jobs.items()):
                    if j.get("running"):
                        self.assertTrue(W.stop(k))
                        self.assertFalse(W.stop("nope"))
            return {}
        with mock.patch.object(W, "run", side_effect=run), mock.patch.object(W.threading, "Thread", Now):
            jid = W.start_restore_many([1, 2, 3])
        j = W.job(jid)
        self.assertEqual(calls, [1])                                # the book going on finished, the rest were left
        self.assertEqual((j["running"], j["stopped"], j["done"], j["total"]), (False, True, 1, 3))
        self.assertFalse(W.stop(jid))                               # done now
        W.name(jid, "restore", "x", "Restore {} books", [1, 2, 3])
        self.assertEqual(W.jobs_list()[0]["state"], "stopped")

    def test_a_job_that_isnt_a_book_at_a_time(self):
        W = self.W
        self.put("one", running=True)                               # start_job's
        self.put("conv", state="running")                           # start_convert's
        self.assertFalse(W.stop("one"))
        self.assertFalse(W.stop("conv"))
        self.put("each", running=True, stoppable=True)
        self.assertTrue(W.stop("each"))
        W.name("each", "k", "x", "{} books", [1, 2])
        row = W.jobs_list()[0]
        self.assertTrue(row["stopping"])
        self.assertFalse(row["stoppable"])                          # asked once is enough


class Endpoints(Base):
    def setUp(self):
        super().setUp()
        from daf import app
        self.app = app

    def test_list(self):
        self.put("a", running=True, done=0, total=1, failed=[])
        self.W.name("a", "polish", "Polish {}", "Polish {} books", [3])
        with mock.patch("daf.catalog.calibre_rows", return_value=({3: {"title": "A Made-Up Book"}}, [])):
            out = self.app.get_catalog_jobs()
        self.assertEqual(out["running"], 1)
        self.assertEqual(out["jobs"][0]["label"], "Polish “A Made-Up Book”")

    def test_stop(self):
        self.put("each", running=True, stoppable=True)
        self.put("one", running=True)
        self.assertEqual(self.app.post_catalog_job_stop("each"), {"ok": True})
        with self.assertRaises(HTTPException) as e:
            self.app.post_catalog_job_stop("one")
        self.assertEqual(e.exception.status_code, 400)
        with self.assertRaises(HTTPException) as e:
            self.app.post_catalog_job_stop("nope")
        self.assertEqual(e.exception.status_code, 404)

    def test_endpoints_name_their_jobs(self):
        W = self.W
        formats = {1: ["EPUB", "ORIGINAL_EPUB"], 2: ["AZW3"]}
        self.put("p", running=True)
        self.put("r", running=True)
        self.put("c", running=True)
        with mock.patch("daf.catalog.formats_of", side_effect=lambda cid: formats.get(cid, [])), \
                mock.patch.object(W, "start_polish_many", return_value="p"), mock.patch.object(W, "start_restore_many", return_value="r"), \
                mock.patch.object(W, "start_convert_many", return_value="c"):
            self.app.post_polish({"ids": [1, 2], "opts": {"embed": True}})
            self.app.post_restore_original({"ids": [1, 2]})
            self.app.post_convert_many({"ids": [1, 2], "to": "MOBI"})
        rows = {r["id"]: r for r in W.jobs_list(lambda ids: {1: "One"})}
        self.assertEqual(rows["p"]["label"], "Polish 2 books")
        self.assertEqual(rows["r"]["label"], "Restore the originals of “One”")
        self.assertEqual(rows["c"]["label"], "Convert 2 books to MOBI")
        self.assertEqual((rows["p"]["kind"], rows["r"]["kind"], rows["c"]["kind"]), ("polish", "restore", "convert"))


class KeptRows(Base):
    """The named jobs' rows in Daf's database (kv calibre_jobs), read back after a restart."""
    def restart(self):
        self.W._jobs.clear()
        self.W._stored = None                                       # a new process: nothing read yet

    def test_after_a_restart(self):
        W, now = self.W, time.time()
        W.name(self.put("done1", running=False, done=2, total=2, failed=[{"id": 4, "error": "bad file"}], ended=now - 60), "polish", "x", "Polish {} books", [4, 5])
        W.name(self.put("run1", running=True, done=1, total=3, failed=[], stoppable=True), "convert", "x", "Convert {} books to MOBI", [1, 2, 3])
        W.name(self.put("old", running=False, ended=now - 2 * 86400, started=now - 2 * 86400), "save", "x", "Save {} books to disk", [1, 2])
        self.put("unnamed", running=False, ended=now)
        W.finished("unnamed")
        self.restart()
        rows = {r["id"]: r for r in W.jobs_list(lambda ids: {4: "Book Four"})}
        self.assertEqual(set(rows), {"done1", "run1"})                # the old one dropped, the unnamed never kept
        self.assertEqual(rows["done1"]["state"], "done")
        self.assertEqual(rows["done1"]["label"], "Polish 2 books")
        self.assertEqual(rows["done1"]["errors"], [{"id": 4, "error": "bad file", "title": "Book Four"}])
        self.assertEqual(rows["run1"]["state"], "interrupted")       # running when Daf stopped
        self.assertEqual((rows["run1"]["done"], rows["run1"]["total"]), (1, 3))
        self.assertFalse(rows["run1"]["stoppable"])

    def test_a_job_kept_when_it_finishes(self):
        W = self.W
        with mock.patch.object(W.threading, "Thread", Now):
            jid = W.start_job(lambda: 7)
        W.name(jid, "pages", "x", "Count pages of {} books", [1, 2])     # named after it finished: kept as done
        later = Held()
        with mock.patch.object(W.threading, "Thread", later):
            jid2 = W.start_job(lambda: W.name(jid2, "pages", "x", "Count pages of {} books", [1, 2]) and 1)
        self.assertEqual(W.job(jid2)["running"], True)
        later.go()                                                       # named while it runs, then it finishes
        self.restart()
        self.assertEqual({r["id"]: r["state"] for r in W.jobs_list()}, {jid: "done", jid2: "done"})

    def test_a_broken_database_doesnt_stop_a_job(self):
        W = self.W
        with mock.patch.object(W, "_store_save", side_effect=OSError("disk full")):
            W.name(self.put("a", running=True), "polish", "x", "Polish {} books", [1, 2])
        self.assertEqual(W.jobs_list()[0]["id"], "a")


class StopMore(Base):
    def test_start_job_that_can_stop(self):
        W, seen, box = self.W, [], {}

        def fn(stop):
            for step in range(5):
                if step == 2:
                    self.assertTrue(W.stop(box["jid"]))          # Stop pressed before the third step
                if stop():
                    break
                seen.append(step)
            return seen
        later = Held()
        with mock.patch.object(W.threading, "Thread", later):
            box["jid"] = W.start_job(fn, stoppable=True)
        later.go()
        j = W.job(box["jid"])
        self.assertEqual(j["done"], [0, 1])
        self.assertTrue(j["stopped"])
        self.assertFalse(W.stop(box["jid"]))                      # done now
        with mock.patch.object(W.threading, "Thread", Now):
            self.assertFalse(W.job(W.start_job(lambda: 1)).get("stoppable"))   # a plain one can't

    def test_find_details_for_many(self):
        from daf import calibrefind
        W = self.W
        books = {i: {"title": "Book %d" % i, "authors": ["A Writer"], "identifiers_map": {}, "id": i} for i in (1, 2, 3, 4)}
        asked = []

        def sources(title, *a, **k):
            asked.append(title)
            if len(asked) == 2:                                     # Stop pressed while the second book is looked up
                self.assertTrue(W.stop(next(k for k, j in W._jobs.items() if j.get("kind") == "fill")))
            return [{"title": title}]

        class Serial:                                               # the four lookers, one after another
            def __init__(self, max_workers):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def map(self, fn, items):
                return [fn(x) for x in items]
        with mock.patch("daf.catalog.brief", return_value=(books, set())), mock.patch.object(calibrefind, "_tidy_found"), \
                mock.patch.object(calibrefind, "calibre_sources", side_effect=sources), mock.patch.object(calibrefind, "same_book", return_value=True), \
                mock.patch.object(calibrefind, "_hardcover_answer", return_value=None), \
                mock.patch.object(calibrefind, "proposals", side_effect=lambda b, ans, f, ck: ({"publisher": "P"}, {"publisher": "Calibre"})), \
                mock.patch("concurrent.futures.ThreadPoolExecutor", Serial), mock.patch.object(calibrefind.threading, "Thread", Now):
            jid = calibrefind.fill_start([1, 2, 3, 4], ["publisher"])
        j = W.job(jid)
        self.assertEqual(asked, ["Book 1", "Book 2"])
        self.assertEqual((j["state"], j["done"], j["total"], j["stopped"]), ("done", 2, 4, True))
        self.assertEqual([b["id"] for b in j["books"]], [1, 2])     # what was found so far, for the sheet
        W.name(jid, "fill", "x", "Find details for {} books", [1, 2, 3, 4])
        self.assertEqual(W.jobs_list()[0]["state"], "stopped")

    def test_import_list(self):
        from daf import app, calibrewrite as W, importlist
        rows = [{"title": "Made Up %d" % i, "authors": ["A Writer"]} for i in range(25)]
        runs, made = [], {}

        def run(ops, timeout):
            runs.append(ops[0])
            if ops[0]["op"] == "add_empty":
                n = len(runs) * 100
                ids = list(range(n, n + len(ops[0]["books"])))
                return {"added": ids, **{i: {"title": "t", "authors": ["a"]} for i in ids}}
            return {}

        def start(fn, stoppable=False):
            self.assertTrue(stoppable)
            presses = iter([False, True])                           # Stop pressed after the first ten
            made["done"] = fn(lambda: next(presses, True))
            return "job9"
        with mock.patch.object(W, "run", side_effect=run), mock.patch.object(W, "start_job", side_effect=start), \
                mock.patch.object(importlist, "clean_rows", side_effect=lambda r: list(r or [])), \
                mock.patch.object(importlist, "add_daf_rows") as rows_in, mock.patch.object(app, "_after_removal"), \
                mock.patch("daf.catalog.calibre_rows", return_value=({}, [])):
            out = app.post_importlist_apply({"add": rows, "add_tag": "Imported"}, None)
        self.assertEqual(out, {"job": "job9"})
        self.assertEqual([len(o["books"]) for o in runs], [10])                 # the first ten went in, the rest were left
        self.assertEqual(made["done"]["added"], list(range(100, 110)))
        self.assertEqual(sorted(rows_in.call_args[0][1]), list(range(100, 110)))  # and the ones added got their Daf rows


if __name__ == "__main__":
    unittest.main()
