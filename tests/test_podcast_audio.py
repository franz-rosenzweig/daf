"""The plain-http podcast pass-through (/api/podcasts/audio): whatever type the podcast's server claims,
the answer is sound and can't run anything, so a feed can't put a page on Daf's address."""
import os
import sqlite3
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

HERE = Path(__file__).parent
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))   # importing daf never touches the real state

from daf import app  # noqa: E402

URL = "http://podcast.example/ep1.mp3"


class Upstream:
    def __init__(self, kind, body=b"x" * 10, status=200):
        self.status, self.body = status, body
        self.headers = _Headers(kind, body)

    def read(self, n):
        b, self.body = self.body, b""
        return b

    def close(self):
        pass


class _Headers(dict):
    def __init__(self, kind, body):
        super().__init__({"Content-Length": str(len(body))})
        self.kind = kind

    def get_content_type(self):
        return self.kind


def db():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE gp_episodes (url TEXT)")
    c.execute("CREATE TABLE docs (enclosure TEXT)")
    c.execute("INSERT INTO gp_episodes VALUES (?)", (URL,))
    return c


class Audio(unittest.TestCase):
    def ask(self, kind, rng=None):
        req = SimpleNamespace(headers={"range": rng} if rng else {})
        with mock.patch("daf.outbound.open_public", return_value=Upstream(kind)):
            return app.get_podcast_audio(URL, req, db())

    def test_page_types_become_audio(self):
        for kind in ("text/html", "image/svg+xml", "application/xhtml+xml", "text/plain", "application/xml"):
            r = self.ask(kind)
            self.assertEqual(r.media_type, "audio/mpeg", kind)
            self.assertIn("sandbox", r.headers["content-security-policy"])

    def test_sound_types_kept(self):
        for kind in ("audio/mpeg", "audio/mp4", "video/mp4", "application/ogg"):
            self.assertEqual(self.ask(kind, "bytes=0-").media_type, kind)

    def test_unknown_address_refused(self):
        req = SimpleNamespace(headers={})
        with self.assertRaises(app.HTTPException):
            app.get_podcast_audio("http://elsewhere.example/x.mp3", req, db())


if __name__ == "__main__":
    unittest.main()
