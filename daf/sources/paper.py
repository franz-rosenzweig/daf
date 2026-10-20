"""Paper reading, kept in the vault.

Minutes read on paper exist nowhere else, so the vault holds them: one note per
year, `type: reading-log`, one line per entry. Daf rereads the notes on every
sync, so editing or deleting a line in Obsidian changes the count.

    - 2026-10-10 · paper · 60 min · Shabbat
"""
import re
from datetime import date

from .. import config

PAGES = re.compile(r"^(\d{1,4})\s*pages?\b\s*(?:[·|-]\s*)?", re.I)
LINE = re.compile(r"^-\s*(\d{4}-\d{2}-\d{2})\s*[·|-]\s*(\w+)\s*[·|-]\s*(\d{1,4})\s*min\w*\s*(?:[·|-]\s*(.*?))?\s*$")
TYPE = re.compile(r"^type:\s*reading-log\s*$", re.M)


def _frontmatter(text):
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    return text[3:end] if end > 0 else ""


def log_notes():
    """Every reading-log note in the vault, found by its type, not its path."""
    found = []
    root = config.VAULT / "Reference"
    for p in root.rglob("*.md"):
        if ".sync-conflict-" in p.name:
            continue
        try:
            head = p.read_text(encoding="utf-8")[:600]
        except (OSError, UnicodeDecodeError):
            continue
        if TYPE.search(_frontmatter(head)):
            found.append(p)
    return sorted(found)


def parse(text):
    out = []
    for line in text.splitlines():
        m = LINE.match(line.strip())
        if m:
            day, kind, mins, note = m.groups()
            try:
                date.fromisoformat(day)
            except ValueError:
                continue
            note = note or ""
            pg = PAGES.match(note)              # "- 2026-10-10 · paper · 40 min · 32 pages · Shabbat"
            pages = int(pg.group(1)) if pg else None
            if pg:
                note = note[pg.end():].strip()
            out.append({"day": day, "kind": kind.lower(), "minutes": int(mins), "pages": pages, "note": note})
    return out


def import_entries(conn, tz=None):
    """Paper lines are a source. Article and video lines are the vault's record of minutes
    read in Daf; they only become sessions for days the index has lost (a rebuilt daf.db)."""
    conn.execute("DELETE FROM sessions WHERE origin = 'vault-log'")
    have = set()
    if tz is not None:
        from datetime import datetime
        for (start,) in conn.execute("SELECT start FROM sessions WHERE origin = 'daf-read'"):
            have.add(datetime.fromtimestamp(start, tz).date().isoformat())
    rows, seen = [], {}
    for p in log_notes():
        for e in parse(p.read_text(encoding="utf-8")):
            kind = e["kind"] if e["kind"] in ("paper", "article", "video", "ebook") else "paper"
            if kind != "paper" and (tz is None or e["day"] in have):
                continue
            n = seen.get((e["day"], kind), 0)
            seen[(e["day"], kind)] = n + 1
            rows.append((f"{kind}:{e['day']}:{n}", kind, "vault-log", None,
                         "Paper" if kind == "paper" else (e["note"] or kind.title()), None, None,
                         e["minutes"] * 60, e["day"], 0, e["note"] or None if kind == "paper" else None,
                         e["pages"] if kind == "paper" else None))
    conn.executemany(
        "INSERT INTO sessions (id, source, origin, item, title, author, start, seconds, day, private, note, pages) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    return len(rows)


def _new_note(year):
    return (
        "---\n"
        "type: reading-log\n"
        f"year: {year}\n"
        "tags:\n"
        "  - reading-logs\n"
        "---\n"
        "#ai-assisted-note\n"
        f"# Reading Log {year}\n\n"
        "Minutes read on paper, logged through Daf or Ezer, and minutes read in Daf itself "
        "(articles, videos), written once each day is over. Kindle and audiobook time isn't listed here; "
        "Daf counts those from their own records. Edit or delete paper lines freely: Daf rereads this note.\n\n"
    )


def log_reading(conn, settings):
    """Write finished days' article and video minutes into the reading log, once."""
    import json
    from datetime import datetime
    from .. import today as T
    tz = T.tz_of(settings)
    today = T.today(settings)
    done = set(json.loads((conn.execute("SELECT v FROM kv WHERE k = 'logged_reading'").fetchone() or ["[]"])[0]))
    wrote = 0
    for r in conn.execute("SELECT id, source, title, start, seconds FROM sessions WHERE origin = 'daf-read' ORDER BY start").fetchall():
        day = datetime.fromtimestamp(r["start"], tz).date()
        if day >= today or r["id"] in done or r["seconds"] < 60:
            continue
        append(day, round(r["seconds"] / 60), (r["title"] or "")[:120], kind=r["source"])
        done.add(r["id"])
        wrote += 1
    conn.execute("INSERT OR REPLACE INTO kv (k, v) VALUES ('logged_reading', ?)", (json.dumps(sorted(done)),))
    return wrote


def append(day, minutes, note="", kind="paper", pages=0):
    """Add one line to that year's log note, creating the note if needed. Returns its path."""
    year = day.year
    target = None
    for p in log_notes():
        head = _frontmatter(p.read_text(encoding="utf-8")[:600])
        if re.search(rf"^year:\s*{year}\s*$", head, re.M):
            target = p
            break
    if target is None:
        config.READING_LOG_DIR.mkdir(parents=True, exist_ok=True)
        target = config.READING_LOG_DIR / f"Reading Log {year}.md"
        text = target.read_text(encoding="utf-8") if target.exists() else _new_note(year)
    else:
        text = target.read_text(encoding="utf-8")
    note = re.sub(r"\s+", " ", (note or "").replace("·", "-")).strip()
    line = f"- {day.isoformat()} · {kind} · {int(minutes)} min" + (f" · {int(pages)} pages" if pages else "") + (f" · {note}" if note else "")
    if not text.endswith("\n"):
        text += "\n"
    text += line + "\n"
    tmp = target.with_name(f".{target.name}.daf-tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(target)
    return target
