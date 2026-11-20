"""Addresses someone else chose (a feed's files, a page's feed link, the Learn helper's suggestions) are
fetched only on public addresses, redirects included, so they can't point this server at itself or the
machines around it."""
import os
import tempfile
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

HERE = Path(__file__).parent
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))   # importing daf never touches the real state

from daf import areaagent, areas, episodes, kindlesend, outbound, pdfdoc  # noqa: E402
from daf.sources import rss  # noqa: E402

INSIDE = ["http://127.0.0.1/", "http://localhost:8440/api/me", "http://10.0.0.5/", "http://192.168.1.1/",
          "http://100.91.202.11:8440/", "http://172.17.0.1:2375/", "http://169.254.169.254/latest/", "http://[::1]/",
          "file:///etc/passwd", "ftp://example.com/x", "gopher://example.com/", "data:text/plain,hi", "", "http:///x"]


class Hits(BaseHTTPRequestHandler):
    hits = []

    def do_GET(self):  # noqa: N802
        Hits.hits.append(self.path)
        if self.path == "/page":
            port = self.server.server_address[1]
            body = (f'<html><head><link rel="alternate" type="application/rss+xml" href="http://localhost:{port}/feed">'
                    "</head></html>").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/away":
            self.send_response(302)
            self.send_header("Location", f"http://localhost:{self.server.server_address[1]}/inside")
            self.end_headers()
        else:
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

    def log_message(self, *a):
        pass


class Rule(unittest.TestCase):
    def test_inside_addresses_are_refused(self):
        for u in INSIDE:
            self.assertFalse(outbound.public_url(u), u)
            with self.assertRaises(outbound.NotPublic, msg=u):
                outbound.open_public(u)

    def test_public_ones_pass_the_check(self):
        with mock.patch.object(kindlesend, "_public", return_value=True):
            self.assertTrue(outbound.public_url("https://example.com/feed"))


class Server(unittest.TestCase):
    """A server on this machine that the tests call public by its number (127.0.0.1) and not by its
    name (localhost): a redirect or a link to "localhost" is the inside address."""

    def setUp(self):
        Hits.hits = []
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), Hits)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        p = mock.patch.object(kindlesend, "_public", side_effect=lambda h: h == "127.0.0.1")
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def test_a_redirect_inside_isnt_followed(self):
        with self.assertRaises(urllib.error.HTTPError):
            outbound.open_public(self.base + "/away")
        self.assertEqual(Hits.hits, ["/away"])

    def test_learn_links(self):
        self.assertTrue(areas._opens(self.base + "/fine"))
        self.assertFalse(areas._opens(self.base + "/away"))
        self.assertFalse(areas._opens("http://localhost:%d/inside" % self.srv.server_address[1]))
        self.assertEqual(Hits.hits, ["/fine", "/away"])

    def test_feed_reader(self):
        with self.assertRaises(rss.FeedError):
            rss._get("http://localhost:%d/feed" % self.srv.server_address[1])
        with self.assertRaises(ValueError):
            rss.discover(self.base + "/page")           # the page names a feed on an inside address
        with self.assertRaises(urllib.error.HTTPError):
            rss._get(self.base + "/away")
        self.assertEqual(Hits.hits, ["/page", "/away"])

    def test_podcast_files(self):
        for u in [u for u in INSIDE if "127.0.0.1" not in u] + ["http://localhost:%d/t.vtt" % self.srv.server_address[1]]:
            with self.assertRaises(ValueError, msg=u):          # NotPublic, or no address at all
                episodes._get(u)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(outbound.NotPublic):
                episodes._download("file:///etc/passwd", tmp)
            path = episodes._download(self.base + "/ep.mp3", tmp, head=1)
            self.assertEqual(Path(path).read_bytes(), b"ok")
        with self.assertRaises(outbound.NotPublic):
            pdfdoc._fetch("http://localhost:%d/x.pdf" % self.srv.server_address[1])
        self.assertEqual(Hits.hits, ["/ep.mp3"])


class Learn(unittest.TestCase):
    def test_three_at_most(self):
        got = [{"kind": "book", "title": f"Book {i}", "by": "Someone"} for i in range(8)]
        self.assertEqual(len(areaagent._outside(got, check=lambda o: o)), 3)


class Probe(unittest.TestCase):
    def test_ffprobe_reads_files_only(self):
        with mock.patch.object(episodes.shutil, "which", return_value="/usr/bin/ffprobe"), \
             mock.patch.object(episodes.subprocess, "run", return_value=mock.Mock(stdout="{}")) as run:
            episodes._chapters_probe("/state/tmp/x/audio")
        cmd = run.call_args[0][0]
        self.assertEqual(cmd[cmd.index("-protocol_whitelist") + 1], "file")
        self.assertEqual(cmd[-1], "/state/tmp/x/audio")


if __name__ == "__main__":
    unittest.main()
