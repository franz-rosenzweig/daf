"""A Karakeep bookmark whose page gave no text falls back to the page's own description. That text is
plain, so the block's 'h' (shown as html by the reader) carries it escaped; rows kept raw before are
escaped once when the database opens."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).parent
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))   # importing daf never touches the real state

from daf import config, db  # noqa: E402
from daf.sources import karakeep  # noqa: E402

DESC = '<img src=x onerror="alert(1)"> Tom & Jerry'


class Desc(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        state = Path(self.tmp.name)
        self.p = [mock.patch.object(config, "STATE", state), mock.patch.object(config, "DB_PATH", state / "daf.db")]
        for p in self.p:
            p.start()
        self.c = db.connect()

    def tearDown(self):
        self.c.close()
        for p in self.p:
            p.stop()
        self.tmp.cleanup()

    def test_fallback_is_escaped(self):
        self.c.execute("INSERT INTO docs (id, title, where_, kind, status) VALUES ('kk:1', 't', 'library', 'article', 'inbox')")
        answer = {"content": {"type": "link", "htmlContent": None, "description": DESC}}
        with mock.patch.object(karakeep, "_req", return_value=answer):
            bl = karakeep.fetch_content(self.c, "kk:1")
        self.assertEqual(bl[0]["x"], DESC)
        self.assertNotIn("<", bl[0]["h"])
        self.assertIn("&lt;img", bl[0]["h"])
        stored = json.loads(self.c.execute("SELECT blocks FROM doc_content WHERE id = 'kk:1'").fetchone()[0])
        self.assertEqual(stored, bl)

    def test_repair(self):
        rows = {"kk:raw": [{"t": "p", "h": DESC, "x": DESC}],
                "kk:clean": [{"t": "p", "h": "Tom &amp; Jerry", "x": "Tom & Jerry"}, {"t": "p", "h": "plain words", "x": "plain words"}],
                "dl:other": [{"t": "p", "h": DESC, "x": DESC}],                 # not a Karakeep row: left alone
                "kk:img": [{"t": "img", "h": "<b>", "x": "<b>", "src": "https://a.example/x.png"}]}
        for k, v in rows.items():
            self.c.execute("INSERT INTO doc_content (id, blocks, fetched) VALUES (?, ?, 0)", (k, json.dumps(v)))
        self.assertEqual(karakeep.repair_descriptions(self.c), 1)
        get = lambda k: json.loads(self.c.execute("SELECT blocks FROM doc_content WHERE id = ?", (k,)).fetchone()[0])
        self.assertNotIn("<", get("kk:raw")[0]["h"])
        self.assertEqual(get("kk:raw")[0]["x"], DESC)
        self.assertEqual(get("kk:clean"), rows["kk:clean"])
        self.assertEqual(get("dl:other"), rows["dl:other"])
        self.assertEqual(get("kk:img"), rows["kk:img"])
        self.assertEqual(karakeep.repair_descriptions(self.c), 0)       # once fixed, nothing more to do

    def test_connect_runs_it_once(self):
        self.assertIsNotNone(self.c.execute("SELECT v FROM kv WHERE k = 'kk_desc_escaped'").fetchone())


if __name__ == "__main__":
    unittest.main()
