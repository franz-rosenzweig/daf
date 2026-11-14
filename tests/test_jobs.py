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


class Base(unittest.TestCase):
    def setUp(self):
        from daf import calibrewrite
        self.W = calibrewrite
        saved = dict(calibrewrite._jobs)
        calibrewrite._jobs.clear()
        self.addCleanup(lambda: (calibrewrite._jobs.clear(), calibrewrite._jobs.update(saved)))

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


if __name__ == "__main__":
    unittest.main()
