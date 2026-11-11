"""The lines where you left off in a book: a sentence or two from your place, for the new look's Today.
A heading the place's sentence runs into is left out, and a place in the front matter (a copyright
page) gives nothing.

The place is Daf's own (the reader's CFI) when the book was read here, else the Kindle's percent. EPUBs
only: the same text the audiobook map reads (audiomap.book, cached per file). Never for a private book.
"""
import re

from . import audiomap, ebooks

SENT_END = re.compile(r"[.!?…][\"”’)\]]*(?=\s)")
# a copyright page, a title page's small print: never the lines to show
FRONT = re.compile(r"(?i)\bcopyright\b|©|\bisbn\b|all rights reserved|library of congress|first published|printed in the united")


def _heading_line(line):
    """A line that reads as a heading: short, and in capitals or mostly capitalised words, with no full stop."""
    words = [w for w in line.split() if any(ch.isalpha() for ch in w)]
    if not words or len(words) > 12 or SENT_END.search(line + " "):
        return False
    caps = sum(1 for w in words if w.lstrip("“\"‘'(").isupper() or w.lstrip("“\"‘'(")[:1].isupper())
    return line.strip().isupper() or caps / len(words) >= 0.7


def _drop_heading(raw):
    """The text without a heading the sentence seemed to begin with: a heading line on its own, or a run of
    words in capitals (the book's text joins a heading to its paragraph with only a space)."""
    m = re.match(r"\s*([^\n]{1,120})\n\s*(?=\S)", raw)
    if m and _heading_line(m.group(1)):
        raw = raw[m.end():]
    words = re.sub(r"\s+", " ", raw).strip().split(" ")
    i = 0
    while i < len(words) and any(ch.isalpha() for ch in words[i]) and words[i].strip("“\"‘'():,.-–—").isupper():
        i += 1
    if i >= 2 and i < len(words) and words[i][:1].isupper():
        words = words[i:]
    return " ".join(words)


def at(conn, book_id, n=300):
    """About n characters from the start of the sentence your place is in, or None."""
    row = conn.execute("SELECT private, progress FROM books WHERE id = ?", (book_id,)).fetchone()
    if not row or row[0]:
        return None
    path, fmt = ebooks.book_file(conn, book_id)
    if not path or fmt not in ("EPUB", "KEPUB"):
        return None
    B = audiomap.book(path)
    if not B.get("total"):
        return None
    pos = conn.execute("SELECT cfi, fraction FROM book_positions WHERE book_id = ?", (book_id,)).fetchone()
    if pos and (pos[0] or pos[1] is not None):
        c = audiomap.char_of(B, {"cfi": pos[0], "fraction": pos[1]})
    elif row[1]:
        c = int(B["total"] * min(1.0, max(0.0, float(row[1]) / 100)))
    else:
        return None
    text = B["text"]
    c = max(0, min(c, len(text) - 1))
    # back to where the sentence the place is in begins (at most a few hundred characters)
    a = max(0, c - 400)
    ends = list(SENT_END.finditer(text, a, c))
    start = ends[-1].end() if ends else c
    if FRONT.search(text[max(0, c - 1500):c + 1500]):       # the place is in the front matter: nothing worth showing yet
        return None
    out = _drop_heading(text[start:start + n + 300])
    if len(out) <= n:
        return out or None
    # end with a sentence when one ends soon after n characters, else at a word
    m = SENT_END.search(out, n, n + 220)
    if m:
        return out[:m.end()]
    cut = out.rfind(" ", 0, n)
    return out[:cut if cut > 0 else n].rstrip(",;:—– ") + "…"
