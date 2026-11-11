"""The lines where you left off in a book: a sentence or two from your place, for the new look's Today.

The place is Daf's own (the reader's CFI) when the book was read here, else the Kindle's percent. EPUBs
only: the same text the audiobook map reads (audiomap.book, cached per file). Never for a private book.
"""
import re

from . import audiomap, ebooks

SENT_END = re.compile(r"[.!?…][\"”’)\]]*(?=\s)")


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
    out = re.sub(r"\s+", " ", text[start:start + n + 300]).strip()
    if len(out) <= n:
        return out or None
    # end with a sentence when one ends soon after n characters, else at a word
    m = SENT_END.search(out, n, n + 220)
    if m:
        return out[:m.end()]
    cut = out.rfind(" ", 0, n)
    return out[:cut if cut > 0 else n].rstrip(",;:—– ") + "…"
