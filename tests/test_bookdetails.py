"""A book's description as its page shows it (catalog.clean_html)."""
import unittest

from daf import catalog


class CleanHtml(unittest.TestCase):
    def test_keeps_the_shape_drops_the_rest(self):
        h = catalog.clean_html('<div><h3>A Title</h3><p class="x" style="color:red">One <b>bold</b> and <a href="javascript:x()">a link</a>'
                               '<script>bad()</script></p><ul><li>one</li></ul><img src="x.png" onerror="bad()"></div>')
        self.assertEqual(h, '<p><b>A Title</b></p><p>One <b>bold</b> and a link</p><ul><li>one</li></ul>')

    def test_divs_are_paragraphs(self):
        self.assertEqual(catalog.clean_html('<div>One</div><div>Two</div>'), '<p>One</p><p>Two</p>')
        self.assertEqual(catalog.clean_html('<div><p>One</p><p>Two</p></div>'), '<p>One</p><p>Two</p>')

    def test_plain_text_and_entities(self):
        self.assertEqual(catalog.clean_html('Fish &amp; chips <i>&lt;tasty&gt;</i>'), '<p>Fish &amp; chips <i>&lt;tasty&gt;</i></p>')
        self.assertEqual(catalog.clean_html(''), '')


class EditFields(unittest.TestCase):
    def test_sorts_halves_and_the_description(self):
        from daf import app
        f = app._edit_fields({"title_sort": "Handbook, The", "author_sort": "  ", "rating": 4.5,
                              "comments_html": '<p>One <b>bold</b></p><img src=x onerror="bad()">'}, set())
        self.assertEqual(f, {"sort": "Handbook, The", "rating": 4.5, "comments": "<p>One <b>bold</b></p>"})


if __name__ == "__main__":
    unittest.main()
