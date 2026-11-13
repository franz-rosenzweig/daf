"""Shelfmark in Add a book: covers, metadata and the server-held release download payloads."""
import base64
import unittest
from unittest.mock import patch

from daf import shelfmark


class ShelfmarkTests(unittest.TestCase):
    def setUp(self):
        shelfmark._KEPT.clear()

    def tearDown(self):
        shelfmark._KEPT.clear()

    def test_cover_unwraps_shelfmarks_cache(self):
        original = "https://images.example/cover.jpg?size=large"
        encoded = base64.urlsafe_b64encode(original.encode()).decode().rstrip("=")
        self.assertEqual(shelfmark._cover("/api/covers/hardcover_42?url=" + encoded), original)
        self.assertEqual(shelfmark._cover("https://images.example/direct.jpg"), "https://images.example/direct.jpg")
        self.assertIsNone(shelfmark._cover("/api/covers/nope"))
        self.assertIsNone(shelfmark._cover("file:///etc/passwd"))

    @patch("daf.shelfmark._mode", return_value="universal")
    @patch("daf.shelfmark.freebooks._mark_have", side_effect=lambda hits: hits[0].update(have="cal:7"))
    @patch("daf.shelfmark._request")
    def test_search_is_shelfmarks_metadata_search(self, request, mark, mode):
        request.return_value = {"books": [{"provider": "hardcover", "provider_id": 42, "title": "Meditations",
                                           "authors": ["Marcus Aurelius"], "publish_year": 180,
                                           "cover_url": "https://images.example/meditations.jpg"}]}
        result = shelfmark.search("  Meditations  ")
        hits = result["hits"]
        self.assertEqual(request.call_args.args[0], "/api/metadata/search")
        self.assertEqual(request.call_args.args[1]["query"], "Meditations")
        self.assertEqual(request.call_args.args[1]["content_type"], "ebook")
        self.assertEqual(hits[0]["id"], "42")
        self.assertEqual(hits[0]["author"], "Marcus Aurelius")
        self.assertEqual(hits[0]["have"], "cal:7")
        mark.assert_called_once()
        self.assertEqual(shelfmark.search("   "), {"mode": "universal", "hits": []})

    @patch("daf.shelfmark._mode", return_value="direct")
    @patch("daf.shelfmark.freebooks._mark_have", side_effect=lambda hits: None)
    @patch("daf.shelfmark._request")
    def test_direct_results_are_ready_to_download(self, request, mark, mode):
        release = {"source": "direct_download", "source_id": "abc", "title": "Meditations EPUB", "format": "epub",
                   "size": "1 MB", "download_url": "https://source.example/private", "language": "en",
                   "extra": {"author": "Marcus Aurelius", "year": 180, "downloads": 12,
                             "preview": "https://images.example/meditations.jpg"}}
        request.side_effect = [{"releases": [release]}, {"status": "queued"}]
        result = shelfmark.search("Meditations")
        item = result["hits"][0]
        self.assertEqual(result["mode"], "direct")
        self.assertEqual(request.call_args.args[0], "/api/releases")
        self.assertEqual(request.call_args.args[1]["source"], "direct_download")
        self.assertNotIn("download_url", item)
        self.assertEqual(item["downloads"], 12)
        self.assertEqual(shelfmark.download(item["release_id"])["status"], "queued")
        body = request.call_args.kwargs["body"]
        self.assertEqual(body["search_mode"], "direct")
        self.assertEqual(body["source_id"], "abc")
        self.assertEqual(body["content_type"], "ebook")
        self.assertNotIn("download_url", body)

    @patch("daf.shelfmark._request")
    def test_releases_hide_source_urls_and_download_reuses_the_payload(self, request):
        release = {"source": "direct_download", "source_id": "abc", "title": "An EPUB", "format": "epub",
                   "size": "1 MB", "download_url": "https://source.example/private?token=secret",
                   "language": "en", "content_type": "ebook", "extra": {"downloads": 12}}
        request.side_effect = [{"book": {"title": "Meditations", "authors": ["Marcus Aurelius"],
                                         "cover_url": "https://images.example/meditations.jpg"}, "releases": [release]},
                               {"status": "queued", "priority": 0}]
        result = shelfmark.releases("hardcover", "42", "Meditations", "Marcus Aurelius")
        item = result["releases"][0]
        self.assertNotIn("download_url", item)
        self.assertNotIn("source.example", str(result))
        self.assertEqual(item["downloads"], 12)
        answer = shelfmark.download(item["id"])
        self.assertEqual(answer["status"], "queued")
        body = request.call_args.kwargs["body"]
        self.assertEqual(body["title"], "Meditations")
        self.assertEqual(body["author"], "Marcus Aurelius")
        self.assertEqual(body["download_url"], release["download_url"])
        self.assertEqual(body["content_type"], "ebook")
        self.assertEqual(request.call_args.args[0], "/api/releases/download")

    def test_unknown_or_old_release_cannot_be_downloaded(self):
        with self.assertRaises(KeyError):
            shelfmark.download("made-up")


if __name__ == "__main__":
    unittest.main()
