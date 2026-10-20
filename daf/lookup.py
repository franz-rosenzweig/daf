"""Look up a word while reading: Hebrew in Sefaria's lexicons (BDB, Jastrow, Klein), English in
Wiktionary, and either one in context through Claude ("what does it mean here?").
Dictionary answers are cached in kv; Claude's are not (they depend on the sentence)."""
import html
import json
import re
import urllib.parse
import urllib.request


HEBREW = re.compile("[֐-׿]")
NIKUD = re.compile("[֑-ׇ]")


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Daf/1.0 (personal reader)"})
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read())


def _text(h):
    h = re.sub(r"<style.*?</style>", "", h or "", flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", h))).strip()


def _senses(senses, out, depth=0):
    for s in senses or []:
        if s.get("definition"):
            out.append(_text(s["definition"]))
        if s.get("senses") and depth < 2:
            _senses(s["senses"], out, depth + 1)


def hebrew(word):
    w = NIKUD.sub("", word).strip(" ,.;:!?\"'()[]־-")
    data = _get("https://www.sefaria.org/api/words/" + urllib.parse.quote(w) + "?never_split=1")
    entries, seen = [], set()
    rank = {"BDB Augmented Strong": 0, "Klein Dictionary": 1, "Jastrow Dictionary": 2}
    exact = lambda e: NIKUD.sub("", e.get("headword") or "").replace(" I", "").replace(" II", "").strip() != w
    for e in sorted(data if isinstance(data, list) else [], key=lambda e: (exact(e), rank.get(e.get("parent_lexicon"), 5))):
        c = e.get("content") or {}
        defs = []
        _senses(c.get("senses"), defs)
        defs = [d if len(d) < 320 else d[:300].rsplit(" ", 1)[0] + "…" for d in defs if d and d.lower() not in ("adj", "adv", "n-m", "n-f")][:4]
        key = (e.get("headword"), tuple(defs))
        if not defs or key in seen:
            continue
        seen.add(key)
        entries.append({"head": e.get("headword"), "pos": c.get("morphology") or "", "source": e.get("parent_lexicon"), "defs": defs})
        if len(entries) >= 6:
            break
    return {"word": w, "lang": "he", "entries": entries, "source": "Sefaria"}


def english(word):
    w = word.strip(" ,.;:!?\"'()[]—–").lower()
    try:
        data = _get("https://en.wiktionary.org/api/rest_v1/page/definition/" + urllib.parse.quote(w))
    except Exception:  # noqa: BLE001 - not found is a 404
        data = {}
    entries = []
    for e in data.get("en", [])[:4]:
        defs = [_text(d.get("definition")) for d in e.get("definitions", [])][:3]
        defs = [d for d in defs if d]
        if defs:
            entries.append({"head": w, "pos": e.get("partOfSpeech", ""), "source": "Wiktionary", "defs": defs})
    return {"word": w, "lang": "en", "entries": entries, "source": "Wiktionary"}


def lookup(conn, word):
    word = (word or "").strip()
    if not word or len(word) > 60:
        raise ValueError("One word or a short phrase")
    is_he = bool(HEBREW.search(word))
    key = "lookup:" + ("he:" + NIKUD.sub("", word) if is_he else "en:" + word.lower())
    row = conn.execute("SELECT v FROM kv WHERE k = ?", (key,)).fetchone()
    if row:
        return json.loads(row[0])
    res = hebrew(word) if is_he else english(word)
    conn.execute("INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)", (key, json.dumps(res, ensure_ascii=False)))
    return res


def in_context(word, sentence):
    """Claude, briefly: the meaning here, and a translation either way."""
    from . import ai
    is_he = bool(HEBREW.search(word + (sentence or "")))
    ask = ("Translate and explain the Hebrew" if is_he else "Explain the English") + f" «{word}» as it is used in this passage:\n\n{sentence}\n\n" + \
        ai.prompt("word_he" if is_he else "word_en")
    out = ai.run(ask, timeout=90)
    return {"word": word, "answer": out}
