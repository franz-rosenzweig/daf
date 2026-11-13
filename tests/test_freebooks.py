"""Public-domain books (daf/freebooks.py): only the two sites' own files, named by source and id."""
import unittest

from daf import freebooks


class Urls(unittest.TestCase):
    def test_the_two_sites_only(self):
        self.assertEqual(freebooks._url("pg", "2680"), "https://www.gutenberg.org/ebooks/2680.epub3.images")
        self.assertEqual(freebooks._url("se", "marcus-aurelius/meditations/george-long"),
                         "https://standardebooks.org/ebooks/marcus-aurelius/meditations/george-long/downloads/"
                         "marcus-aurelius_meditations_george-long.epub?source=download")
        for source, book_id in [("pg", "../etc"), ("pg", "12a"), ("se", "https://evil.example/x"), ("se", "a/../b"), ("x", "1"), ("se", "one")]:
            with self.assertRaises(ValueError):
                freebooks._url(source, book_id)

    def test_same_book_key(self):
        self.assertEqual(freebooks._key("Meditations: A New Translation", "Marcus Aurelius"), freebooks._key("Meditations", "marcus aurelius"))


if __name__ == "__main__":
    unittest.main()
