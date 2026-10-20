"""What Daf asks the model, and how: Preferences → AI (Readwise's Ghostreader settings).

Each prompt is the instruction part only. Daf adds what it's about (the document, the passage, the
word in its sentence) and keeps the parts that must stay as they are (the flashcard's JSON). An
empty one means Daf's own, below, so a better default reaches him too.

The model runs as the Claude CLI on Nathan's subscription; settings "ai" picks which one.
"""
import os
import re
import subprocess

from . import config, secrets

CLAUDE = config.CLAUDE

MODELS = [("", "Daf’s default"), ("claude-opus-5-5", "Opus 5.5 (deepest, slowest)"),
          ("claude-sonnet-5-5", "Sonnet 5.5"), ("claude-haiku-5-5", "Haiku 5.5 (quickest)")]

DEFAULTS = {
    "summary": "Summarize this for a reader deciding whether to read it, in two or three plain sentences: what it says, "
               "and the main point or argument. No preamble, no 'This article', no markdown. Write in the document's own "
               "language if it isn't English.",
    "ask": "Answer his question about the document below, from the document itself. Be direct and short (a few "
           "sentences, or a short list when he asks for one). If the document doesn't say, say so plainly. Plain text, "
           "no markdown headings.",
    "ask_book": "Answer briefly and plainly, in a few short paragraphs at most. Don't spoil what comes later in the book.",
    "word_en": "Answer in at most three short lines: what it means here, and, if it helps, a Hebrew equivalent.",
    "word_he": "Answer in at most three short lines: an English gloss of the word here, its root (shoresh) and form, "
               "and a natural English translation of the clause around it.",
    "card": "Make a flashcard from this highlight, so that remembering it means remembering the idea.",
    "tags": "Pick 2 to 4 tags for this saved page, so it can be found again by its subject. Use his own tags when one "
            "fits, spelled as he spells them; make a new one only when none does. Short, plain words, no hashtags.",
}
LABELS = {
    "summary": ("Summaries", "The two or three lines on every article in the Library, and Summarize."),
    "ask": ("Ask, in an article", "How Ask answers about an article, a PDF or an email."),
    "ask_book": ("Ask, in a book", "How Ask answers about where you are in a book."),
    "word_en": ("A word in its sentence (English)", "In this sentence, under Define."),
    "word_he": ("A word in its sentence (Hebrew)", "In this sentence, under Define, for Hebrew."),
    "card": ("Flashcards", "Suggest, when you make a flashcard from a highlight."),
    "tags": ("Tags", "The tags Daf gives what you save to the Library."),
}
QUESTIONS = ["Summarize this", "What’s the main argument?", "What should I remember from this?"]
BOOK_QUESTIONS = ["Who is this?", "What just happened?", "Remind me where we are"]


def clean(a):
    """settings "ai" as it may be saved: {auto_summary, auto_tags, model, prompts: {name: text}, questions, book_questions}."""
    a = a if isinstance(a, dict) else {}
    out = {"auto_summary": a.get("auto_summary") is not False, "auto_tags": a.get("auto_tags") is not False,
           "model": a.get("model") if a.get("model") in {m for m, _ in MODELS} else "",
           "prompts": {}, "questions": [], "book_questions": []}
    for k, v in (a.get("prompts") or {}).items():
        if k in DEFAULTS and isinstance(v, str) and v.strip() and v.strip() != DEFAULTS[k]:
            out["prompts"][k] = v.strip()[:4000]
    for key in ("questions", "book_questions"):
        qs = a.get(key)
        if isinstance(qs, list):
            out[key] = [" ".join(str(q).split())[:120] for q in qs if isinstance(q, str) and q.strip()][:8]
    return out


def settings(s=None):
    return clean((s or config.load_settings()).get("ai"))


def prompt(name, s=None):
    return settings(s)["prompts"].get(name) or DEFAULTS[name]


def model(s=None):
    return settings(s)["model"] or secrets.claude_model()


def questions(s=None, book=False):
    a = settings(s)
    return a["book_questions" if book else "questions"] or (BOOK_QUESTIONS if book else QUESTIONS)


def run(text, timeout=180, s=None):
    """The model's answer to text. Raises RuntimeError with what went wrong."""
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    r = subprocess.run([CLAUDE, "--print", "--model", model(s)], input=text, capture_output=True, text=True, timeout=timeout, env=env)
    out = (r.stdout or "").strip()
    if r.returncode != 0 or not out:
        raise RuntimeError(plain_error(r.stderr or r.stdout))
    return out


def plain_error(text):
    """The CLI's complaint as the app can show it: short, and in Daf's words (no product names)."""
    t = " ".join((text or "").split())[-300:]
    t = re.sub(r"(?i)\bclaude(\s+code)?\b", "the model", t)
    return ("The model didn't answer: " + t) if t else "No answer came back"


def public(s=None):
    """For Preferences → AI: the settings, Daf's own prompts and the choices."""
    return {"ai": settings(s), "defaults": DEFAULTS, "labels": LABELS, "questions": QUESTIONS, "book_questions": BOOK_QUESTIONS,
            "models": [{"id": m, "label": label} for m, label in MODELS], "default_model": secrets.claude_model()}
