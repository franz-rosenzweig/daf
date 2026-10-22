"""The index database. Rebuildable: nothing here is the only copy of anything,
except Kindle page turns the plugin sent that KoInsight never saw."""
import sqlite3
from contextlib import contextmanager

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (          -- Kindle page turns, from KoInsight and the Daf plugin
  md5 TEXT NOT NULL,
  start INTEGER NOT NULL,                   -- epoch seconds (UTC)
  duration INTEGER NOT NULL,
  page INTEGER,
  total INTEGER,
  origin TEXT NOT NULL,
  PRIMARY KEY (md5, start)
);
CREATE TABLE IF NOT EXISTS kindle_books (
  md5 TEXT PRIMARY KEY,
  title TEXT,
  authors TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,                     -- kindle | audio | article | paper | podcast | video
  origin TEXT NOT NULL,                     -- which adapter wrote it
  item TEXT,
  title TEXT,
  author TEXT,
  start INTEGER,                            -- epoch seconds, NULL for day-only entries
  seconds INTEGER NOT NULL,
  day TEXT,                                 -- YYYY-MM-DD when only the day is known (paper)
  private INTEGER NOT NULL DEFAULT 0,
  note TEXT
);
CREATE INDEX IF NOT EXISTS sessions_start ON sessions (start);
CREATE INDEX IF NOT EXISTS sessions_day ON sessions (day);
CREATE TABLE IF NOT EXISTS source_status (
  name TEXT PRIMARY KEY,
  ok INTEGER NOT NULL,
  checked INTEGER NOT NULL,
  last_data INTEGER,
  detail TEXT
);
CREATE TABLE IF NOT EXISTS books (           -- one row per work: every Kindle copy, the audiobook and the vault note
  id TEXT PRIMARY KEY,                      -- cal:<calibre id> | vault:<slug> | md5:<md5> | abs:<item> | kk:<bookmark>
  kind TEXT NOT NULL,                       -- book | article
  title TEXT NOT NULL,
  author TEXT,
  calibre_id INTEGER,
  calibre_path TEXT,
  vault_path TEXT,
  status TEXT,
  progress REAL,
  progress_note TEXT,
  last_read INTEGER,
  audio_pct REAL,
  audio_note TEXT,
  url TEXT,
  private INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS book_keys (key TEXT PRIMARY KEY, book_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS highlights (
  id TEXT PRIMARY KEY,
  book_id TEXT,
  source TEXT NOT NULL,                     -- kindle | karakeep
  text TEXT,
  note TEXT,                                -- the note typed where the highlight was made
  chapter TEXT,
  page INTEGER,
  created INTEGER,
  pos TEXT,
  seen INTEGER NOT NULL,
  deleted INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS highlights_book ON highlights (book_id);
CREATE TABLE IF NOT EXISTS review_state (    -- Daf's own data: spaced repetition and notes added in Daf
  hl_id TEXT PRIMARY KEY,
  status TEXT NOT NULL,                     -- kept | less
  interval INTEGER NOT NULL DEFAULT 0,
  due TEXT,
  reviews INTEGER NOT NULL DEFAULT 0,
  last TEXT,
  user_note TEXT,
  note_updated INTEGER,
  vault_hash TEXT
);
CREATE TABLE IF NOT EXISTS shelves (        -- your own shelves of books, like BookOrbit's collections
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS shelf_books (
  shelf_id TEXT NOT NULL,
  book_id TEXT NOT NULL,
  added INTEGER NOT NULL,
  PRIMARY KEY (shelf_id, book_id)
);
CREATE TABLE IF NOT EXISTS kindle_sidecars (  -- each book's KOReader notes file, as the Daf plugin sent it (highlights, title)
  md5 TEXT PRIMARY KEY, file TEXT, data TEXT NOT NULL, received INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS kindle_sent (    -- documents sent to the Kindle as EPUBs (kindlesend.py)
  doc_id TEXT PRIMARY KEY,
  file TEXT NOT NULL,
  at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS kindle_epubs (   -- each EPUB Send to Kindle wrote, by KOReader's md5 of the file (refilled from the files)
  md5 TEXT PRIMARY KEY,
  file TEXT NOT NULL,
  parts TEXT NOT NULL                       -- JSON [[doc id, length], …]: chapter n is the nth article
);
CREATE TABLE IF NOT EXISTS manga_files (    -- KOReader's md5 of each file in the manga library (manga.refresh_index)
  path TEXT PRIMARY KEY,                    -- relative to the manga root: <series folder>/<file>
  size INTEGER NOT NULL,
  mtime INTEGER NOT NULL,
  md5 TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS manga_files_md5 ON manga_files (md5);
CREATE TABLE IF NOT EXISTS manga_books (    -- Daf book rows that are manga volumes (read on the Kindle), and their Komga book
  book_id TEXT PRIMARY KEY,
  komga_book TEXT,
  series TEXT,
  series_name TEXT
);
CREATE TABLE IF NOT EXISTS ops (            -- writes sent with X-Daf-Op: a repeat (an offline queue sending again) gets the first answer
  id TEXT PRIMARY KEY,
  at INTEGER NOT NULL,
  status INTEGER NOT NULL,
  ctype TEXT,
  body BLOB
);
CREATE TABLE IF NOT EXISTS imports (        -- an export file from another app (imports.py), worked through in the background
  id TEXT PRIMARY KEY,
  service TEXT NOT NULL,                    -- instapaper | pocket | omnivore | readwise | raindrop | goodlinks | wallabag | bookmarks | csv | opml
  name TEXT,                                -- the file's name
  created INTEGER NOT NULL,
  items TEXT NOT NULL,                      -- JSON: what the file holds, in Daf's shape
  opts TEXT,                                -- JSON: {archived: bool}
  state TEXT NOT NULL,                      -- ready | running | done | stopped
  pos INTEGER NOT NULL DEFAULT 0,           -- the next item
  added INTEGER NOT NULL DEFAULT 0, had INTEGER NOT NULL DEFAULT 0, skipped INTEGER NOT NULL DEFAULT 0,
  failed INTEGER NOT NULL DEFAULT 0, highlights INTEGER NOT NULL DEFAULT 0,
  errors TEXT,                              -- JSON: the last few [{url, error}]
  finished INTEGER
);
CREATE TABLE IF NOT EXISTS feedback (       -- Send feedback: kept here, and filed as an issue on GitHub (feedback.py)
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at INTEGER NOT NULL,
  text TEXT NOT NULL,
  ctx TEXT,                                 -- JSON: where Daf was and what it said
  issue TEXT,                               -- the issue's address, once filed
  error TEXT
);
CREATE TABLE IF NOT EXISTS book_review (    -- how often a book's highlights come up in the daily review
  book_id TEXT PRIMARY KEY,
  freq TEXT NOT NULL                        -- more | less | never (no row: as usual)
);
CREATE TABLE IF NOT EXISTS ebook_pages (    -- pages shown in Daf's book reader, once a day each (for page goals)
  book_id TEXT NOT NULL,
  day TEXT NOT NULL,
  page TEXT NOT NULL,
  PRIMARY KEY (book_id, day, page)
);
CREATE TABLE IF NOT EXISTS review_days (day TEXT PRIMARY KEY, ids TEXT NOT NULL, done TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS reading_notes (   -- voice and text notes filed under a book
  id TEXT PRIMARY KEY,
  book_id TEXT,
  page INTEGER,
  total INTEGER,
  text TEXT NOT NULL,
  created INTEGER NOT NULL,
  source TEXT NOT NULL,
  vault_hash TEXT
);
CREATE TABLE IF NOT EXISTS audio_bookmarks (id TEXT PRIMARY KEY, book_id TEXT, title TEXT, at REAL, created INTEGER);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS kindle_pushed (   -- Daf highlights the Kindle plugin has added to KOReader
  hl_id TEXT PRIMARY KEY, device TEXT, at INTEGER);
CREATE TABLE IF NOT EXISTS cards (           -- flashcards made from highlights (cards.py)
  id TEXT PRIMARY KEY, hl_id TEXT NOT NULL, kind TEXT NOT NULL, front TEXT NOT NULL, back TEXT, created INTEGER,
  due TEXT, interval INTEGER, ease REAL, reps INTEGER, lapses INTEGER, last TEXT, first_seen TEXT, suspended INTEGER);
CREATE TABLE IF NOT EXISTS hc_links (        -- Daf books linked to Hardcover by hand (no hardcoverBookId in a vault note)
  book_id TEXT PRIMARY KEY, hc_book_id INTEGER NOT NULL, linked INTEGER);
CREATE TABLE IF NOT EXISTS doc_edits (       -- titles and authors you corrected; reapplied after every sync
  id TEXT PRIMARY KEY, title TEXT, author TEXT, updated INTEGER);
CREATE TABLE IF NOT EXISTS book_marks (      -- bookmarks in books read in Daf
  id TEXT PRIMARY KEY, book_id TEXT NOT NULL, cfi TEXT NOT NULL, fraction REAL, chapter TEXT, excerpt TEXT, created INTEGER);
CREATE TABLE IF NOT EXISTS book_positions (  -- where you are in a book read in Daf (EPUB CFI)
  book_id TEXT PRIMARY KEY, cfi TEXT, fraction REAL, chapter TEXT, updated INTEGER);
CREATE TABLE IF NOT EXISTS paper_pages (     -- photos of marked paper pages (Phase 7)
  id TEXT PRIMARY KEY, created INTEGER NOT NULL, photo TEXT NOT NULL, caption TEXT,
  book_id TEXT, page INTEGER, lang TEXT, header TEXT,
  lines TEXT, margin TEXT, chosen TEXT,       -- JSON: [{text, marked}], [{line, text}], [indices]
  status TEXT NOT NULL, error TEXT);          -- new | read | saved | error
CREATE TABLE IF NOT EXISTS docs (           -- the Feed (FreshRSS) and the Library (Karakeep)
  id TEXT PRIMARY KEY,                      -- fr:<freshrss item> | kk:<karakeep bookmark>
  kind TEXT NOT NULL,                       -- article | video | tweet | pdf | podcast
  where_ TEXT NOT NULL,                     -- feed | library
  status TEXT NOT NULL,                     -- feed: unseen | seen; library: inbox | later | archive; either: deleted
  title TEXT, author TEXT, source TEXT, category TEXT, url TEXT,
  published INTEGER, added INTEGER, words INTEGER, summary TEXT, thumb TEXT, enclosure TEXT,
  ext_id TEXT,
  progress REAL NOT NULL DEFAULT 0,
  note TEXT,
  opened INTEGER
);
CREATE INDEX IF NOT EXISTS docs_where ON docs (where_, status, published);
CREATE TABLE IF NOT EXISTS doc_content (id TEXT PRIMARY KEY, blocks TEXT NOT NULL, fetched INTEGER NOT NULL);
-- Full-text search over saved articles, emails and feed items: kept in step with doc_content by triggers.
CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(id UNINDEXED, title, body, tokenize = 'unicode61 remove_diacritics 2');
CREATE TRIGGER IF NOT EXISTS doc_content_fts_ins AFTER INSERT ON doc_content BEGIN
  DELETE FROM docs_fts WHERE id = NEW.id;
  INSERT INTO docs_fts (id, title, body) VALUES (NEW.id, COALESCE((SELECT title FROM docs WHERE id = NEW.id), ''),
    COALESCE((SELECT group_concat(json_extract(value, '$.x'), ' ') FROM json_each(NEW.blocks)), ''));
END;
CREATE TRIGGER IF NOT EXISTS doc_content_fts_upd AFTER UPDATE ON doc_content BEGIN
  DELETE FROM docs_fts WHERE id = NEW.id;
  INSERT INTO docs_fts (id, title, body) VALUES (NEW.id, COALESCE((SELECT title FROM docs WHERE id = NEW.id), ''),
    COALESCE((SELECT group_concat(json_extract(value, '$.x'), ' ') FROM json_each(NEW.blocks)), ''));
END;
CREATE TRIGGER IF NOT EXISTS doc_content_fts_del AFTER DELETE ON doc_content BEGIN
  DELETE FROM docs_fts WHERE id = OLD.id;
END;
CREATE TABLE IF NOT EXISTS asks (id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id TEXT, q TEXT, quote TEXT, a TEXT, at INTEGER);
CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, ref TEXT NOT NULL, status TEXT NOT NULL,
  detail TEXT, error TEXT, created INTEGER, started INTEGER, finished INTEGER);
CREATE TABLE IF NOT EXISTS gp_subs (url TEXT PRIMARY KEY, title TEXT, added INTEGER, removed INTEGER, checked INTEGER);
CREATE TABLE IF NOT EXISTS gp_actions (id INTEGER PRIMARY KEY AUTOINCREMENT, podcast TEXT, episode TEXT, action TEXT, position INTEGER,
  started INTEGER, total INTEGER, timestamp INTEGER, device TEXT, guid TEXT, received INTEGER);
CREATE TABLE IF NOT EXISTS gp_episodes (url TEXT PRIMARY KEY, link TEXT, title TEXT, podcast TEXT, podcast_title TEXT, published INTEGER);
CREATE TABLE IF NOT EXISTS nudges (at INTEGER NOT NULL, app TEXT, shown INTEGER NOT NULL, reason TEXT, minutes_left INTEGER);
CREATE TABLE IF NOT EXISTS inbox (           -- links shared to Daf from the phone, until Karakeep has them
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url TEXT, title TEXT, text TEXT,
  created INTEGER NOT NULL,
  status TEXT NOT NULL                      -- new | saved | failed
);
CREATE TABLE IF NOT EXISTS devices (
  token_hash TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created INTEGER NOT NULL,
  last_seen INTEGER
);
"""


def connect():
    config.STATE.mkdir(parents=True, exist_ok=True)
    # One connection per request; FastAPI may open it on one thread and use it on another.
    conn = sqlite3.connect(config.DB_PATH, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    conn.executescript(SCHEMA)
    for table, col, decl in MIGRATIONS:
        if col not in {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
            except sqlite3.OperationalError as e:      # another connection added it a moment ago
                if "duplicate column" not in str(e):
                    raise
    if not conn.execute("SELECT 1 FROM kv WHERE k = 'fts_v1'").fetchone():
        # Once: index what was saved before full-text search existed.
        conn.execute("DELETE FROM docs_fts")
        conn.execute("INSERT INTO docs_fts (id, title, body) SELECT c.id, COALESCE(d.title, ''), "
                     "COALESCE((SELECT group_concat(json_extract(value, '$.x'), ' ') FROM json_each(c.blocks)), '') "
                     "FROM doc_content c LEFT JOIN docs d ON d.id = c.id WHERE json_valid(c.blocks)")
        conn.execute("INSERT INTO kv (k, v) VALUES ('fts_v1', '1') ON CONFLICT(k) DO NOTHING")
        conn.commit()
    return conn


MIGRATIONS = [("docs", "duration", "INTEGER"), ("audio_bookmarks", "transcribed", "INTEGER"), ("highlights", "color", "TEXT"), ("review_state", "tags", "TEXT"), ("review_state", "fav", "INTEGER"),
              ("docs", "tags", "TEXT"), ("docs", "ai_summary", "TEXT"),
              ("docs", "starred", "INTEGER"), ("sessions", "pages", "INTEGER"),
              ("docs", "feed", "TEXT"), ("shelves", "hc_list", "INTEGER"), ("docs", "full", "INTEGER"),
              ("docs", "deleted", "INTEGER")]


@contextmanager
def session():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def read_only(path):
    """Open someone else's SQLite file without any chance of writing to it."""
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
