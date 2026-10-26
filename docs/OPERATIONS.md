*Moved here from the top-level README on 2026-10-11, word for word; the README is now the project's front page. This is the working log of how Daf runs on the server.*

# Daf

A personal Readwise for one reader's own stack. Goal: an hour of reading a day in Year 30
(2026-10-09 to 2027-10-08). The plan for the whole app is in [PLAN.md](../PLAN.md).

**Open it:** https://daf.tiresia.xyz (the cloudflared tunnel on the server → localhost:8440), or
http://<server>:8440 on the tailnet. Install it as an app from the phone's browser menu on the
https address; offline reading needs that address too (service workers want a secure origin).

**Sign-in:** username + password (`auth.json`; a new install's username is `reader` until changed). Change
both in Preferences → Account or with `daf set-password [--user NAME]`; a new password signs out
every other browser. Five wrong tries from one address lock it for 15 minutes, twenty from anywhere
in an hour pause sign-in for 15 minutes, and Ezer says so on Signal (at most every 6 hours). Behind
the tunnel the client address comes from `CF-Connecting-IP` (trusted only from loopback) and cookies
are `Secure`. Devices (Kindle, phone, AntennaPod, `/api/save`) use their own tokens. Links in
messages use settings `public_url` (now https://daf.tiresia.xyz). The Kindle keeps the tailnet URL.

## What runs where

| | |
|---|---|
| Code | `/srv/dev/daf` (Python package `daf/`, web app `web/`, Kindle plugin `kindle/`) |
| Service | systemd user unit `daf.service` (copy in `systemd/`): web app + API on :8440, sync every 5 min |
| State | `/srv/docker/daf`: `daf.db` (index, rebuildable), `auth.json`, `settings.json`, `kindle-token` |
| Vault | Daf writes `Reference/reading/Reading Log YYYY.md` (paper minutes), in book notes only the region between `<!-- daf -->` and `<!-- daf-end -->` (notes added in Daf, voice and text reading notes), and a note per highlighted article, video, podcast, tweet, PDF, reel or Torah reading in `Reference/clippings`, `youtube`, `podcasts`, `instagram` and `torah`, with the full text inside its region (see "Vault notes with the full text" below). Edits made in Obsidian inside a region win. |
| Logs | `journalctl --user -u daf -f` |

After changing code: `systemctl --user restart daf`. The web app has no build step.

## Command line (`bin/daf`)

    daf doctor                          every source, and how fresh it is
    daf sync                            pull every source now
    daf today [--json] [--date D]       today's minutes, by source and sitting
    daf year [30|29]                    the year so far
    daf log-paper 40 [--shabbat | --yesterday | --date D] [--note TEXT]
    daf set-password                    change the web password
    daf kindle-token NAME               new device token (printed once)
    daf review [--json]                 today's highlights
    daf morning [--send]                the morning highlight (a cron job sends it)
    daf note "n: text"                  file a note under the morning highlight or the current Kindle book
    daf voice-note FILE                 transcribe (faster-whisper) and file the same way
    daf nightstand [ID ...]             show or set the three nightstand books
    daf paper-page PHOTO [--caption "page 112 middlemarch"]   a marked paper page -> highlights
    daf clip "TEXT"                     a podcast link with a time: transcribe the minute before it
    daf jobs                            transcripts and clips, waiting or done
    daf vault-backfill [--dry-run DIR]  rewrite Daf's article notes the current way (DIR: copies there, the vault untouched)

Ezer (`.claude/scripts/signal-bot.py`, rules ahead of the router, no model call):
- `read 40 paper`, `paper 40`, `shabbat 60`: paper minutes.
- `n: …` / `note: …`: under this morning's highlight (if sent in the last 20 h and not yet noted),
  otherwise a reading note on the book last read on the Kindle, at that page.
- A voice note with no text: transcribed and filed under the book read on the Kindle in the
  last 3 hours (or if it starts with "note"); otherwise the transcript comes back unfiled.
- A photo captioned `page`, `p: 112` or `page 112 middlemarch`: `daf paper-page` (below).
- A link with a time that isn't YouTube or X (`#t=750`, AntennaPod's "Starting position: 00:12:30",
  or `clip <link> 12:30`): `daf clip`, the minute before that point, transcribed.

## Highlights and review (Phase 2)

- **Books** (`library.py`): one row per work. Kindle copies (by KOReader md5), the
  Audiobookshelf item and the vault note are matched to the Calibre id by normalized title,
  so two copies of one novel are one book.
- **Highlights** (`sources/highlights.py`): KOReader sidecars synced to `/srv/koreader/Libros`
  (parsed by `sources/lua.py`), KoInsight's annotation table as fallback, Karakeep highlights,
  and Audiobookshelf bookmarks whose title is a sentence. Ids are stable hashes of book + text.
- **Review** (`review.py`): one fixed set per day (5 by default): due first, then new ones
  weighted toward the nightstand and recent highlights; at most 2 per book; private books never.
  Keep: 4 days, then x2.5. Less: 120+ days.
- **Private books**: titles matching `private_titles` (defaults in `config.py`, more in
  `settings.json`, which is not in git) still count toward the hour but show as "Private
  reading" and never appear in review, the morning message, the nightstand or the Kindle.

## The reader (Phase 4)

- **Feed** = FreshRSS over its Google Reader API (`sources/freshrss.py`, credentials read in place by
  `secrets.py`: the homepage's FreshRSS API password). Newest unread items back to the expiry window
  (30 days by default, Preferences up to a year or never) become `docs` with cleaned text (`content.py`). Seen in Daf = read in FreshRSS;
  read elsewhere = seen here on the next sync. Older unread items count as seen in Daf; a button
  (Feed → Seen) marks them read in FreshRSS too, only when pressed.
- **Library** = Karakeep's REST API (`sources/karakeep.py`): list, archived text, save, archive.
  "Later" is Daf's own status. Links shared to Daf from the phone go to Karakeep on the next sync.
- **Reading view** (`web/reader.js`): highlight by selection or `h`, notes (`n`), Ask (Claude CLI,
  `secrets.claude_model()`), read-aloud through Kokoro (`/api/tts`, cached in `/srv/docker/daf/tts`),
  progress, Aa (theme, typeface, size, width), `[` `]` panels, ⌘K search. Highlights write a clipping
  note in `Reference/clippings` with Daf's region (the full text since 2026-10-25, below).
- **Reading time**: the open reading view sends a 15-second beat while you're active (or while
  read-aloud plays). Each article is one session per day; finished days go into the vault reading log.
  Beats made offline wait in localStorage (`daf.beatq`) and are sent with their own time (`at`).
- **Offline** (`web/sw.js`): network first, the cached copy when the network fails, for the shell,
  `/api/me`, Today, Review, Books, Highlights, Torah, lists and single docs. Opening the Library
  prefetches the text of up to 30 Inbox/Later articles and tweets (`?prefetch=1` doesn't mark them
  opened). Service workers only run on a secure origin, so this works once Daf has its HTTPS address
  (or on `localhost`); on `http://<server>:8440` the page simply needs the network.

## Watch and listen (Phase 5)

- **Jobs** (`media.py`): a queue in `jobs`, worked by one thread in the service (restarts requeue
  anything left running). `daf jobs` lists them.
- **Videos** (Karakeep video bookmarks): captions with yt-dlp first, faster-whisper when there are none
  (`tools/whisper_segments.py`, run with Daf's own Python; yt-dlp and faster-whisper are in its .venv from requirements.txt since the October 2026 OS upgrade to Python 3.14 left the host's copies behind). The transcript is cue blocks
  with timestamps, speakers and chapters. The player is YouTube's privacy-mode embed
  (`youtube-nocookie.com`); Invidious couldn't stream (its companion answers 500), so it's only a link.
  Click a line to seek, `c` or Clip 30s highlights the last 30 seconds, Follow along scrolls with it.
  Video time counts only if Preferences says so (off by default).
- **Podcasts**: Daf speaks the part of the gpodder.net v2 API AntennaPod uses (`gpodder.py`; login sets a
  `daf_gp` cookie, later calls use it). Password = Preferences → Podcasts → Make a password. Play actions
  become `podcast` sessions (shown, never counted). Feeds of subscriptions are read once a day for
  episode names. A share "with position" sent to Ezer becomes a `clip` highlight, written to
  `Reference/podcasts`. Clipping a minute takes about 30 seconds.
  - **From Nextcloud's GPodder Sync:** `daf podcasts-import` reads its two tables (through psql in the
    AIO database container, never writing) into Daf's: subscriptions, unsubscriptions and each
    episode's last play. Run again, it adds only what's new. Done once on 2026-10-11 (22 podcasts, 74
    episodes); then AntennaPod's sync moves from Nextcloud to Daf.
- **Audiobookshelf bookmarks**: the minute before each bookmark is transcribed (ffmpeg over the
  audiobook's files) into a highlight shown as "Audiobook, h:mm:ss" in the book note.

## Paper and Torah (Phase 7)

- **Paper pages** (`paper_pages.py`, web `#paper`): a photo of a marked page, from Ezer, the share
  target (Android: Share → Daf) or the Paper pages view. Claude (CLI, only the Read tool, `--add-dir`
  `/srv/docker/daf/pages`) transcribes it line by line in English or Hebrew, flags marked lines, and
  copies margin handwriting. Marked lines are kept at once; each run of adjacent lines is one `paper`
  highlight with the page, and a margin note beside it becomes its note. The book comes from the
  caption, then the running head, then the last paper page in the past two weeks; otherwise Daf asks.
  A paper book with no vault note gets a minimal one in `Reference/books` (type: book, format: paper).
  Photos stay in `/srv/docker/daf/pages`. About 15 seconds a page.
- **Torah shelf** (`torah.py`, web `#torah`): Sefaria's calendar (diaspora, home time zone) gives the
  week's parasha with aliyot and the haftarah; each becomes a doc (`where_ = 'torah'`) of verse blocks,
  Hebrew (nikud, no cantillation) beside the JPS English. Both / עברית / English toggle in the reader.
  The Ruach FreshRSS folder supplies the week's divrei Torah, those naming the parasha first.
  Highlights go to `Reference/torah`, each with its verse.
- **Lookup** (`lookup.py`): select one word → Define (Hebrew: Sefaria's BDB, Klein, Jastrow; English:
  Wiktionary; cached in kv). "In this sentence" and Translate (a Hebrew phrase) ask Claude, ~10 s.

## Books in Daf (the EPUB reader)

- **Engine:** foliate-js (MIT, the core of the Foliate e-reader), vendored as-is in
  `web/vendor/foliate-js` at commit 78914ae; `web/book.js` is Daf's reader around it, inside the same
  reading view as articles (contents and search left; Info / Notebook / Ask right; Aa menu shared).
- **Files:** every Calibre book (`library.rebuild` now includes all of them) with EPUB, KEPUB, AZW3,
  MOBI, FB2 or CBZ; served from `cwa-library` by `/api/ebooks/{id}/file`. Books → Your library lists
  them; a book page has "Read in Daf".
- **Reading:** Scroll or Pages (two columns on a wide screen without the panel), themes Auto / Light /
  Sepia / Dark, Source Serif, Literata, Frank Ruhl Libre (Hebrew), Atkinson Hyperlegible, Figtree or the
  book's own font, size / line spacing / width, justify. Footnotes open in a popover by the link.
  The footer has the chapter, minutes left in it and in the book, and the percent (tap it to jump).
  Keys: ← → (space in Pages), t contents, / search, l listen, h/n highlight/note a selection, b bookmark,
  ] panel, ? the list. The footer also shows the printed page when the EPUB has a page list.
  The screen stays awake while a book is open.
- **Position:** an EPUB CFI per book in `book_positions` (and localStorage), so phone and desktop agree;
  the newest wins on open ("Picked up at 45%"). If the Kindle is further along (KOReader page turns),
  Daf offers to go there by percent. A newer Daf position also wins on the Books page.
- **Highlights:** source `epub`, anchored by CFI, into review and the book note's Daf region
  ("**Read in Daf** · chapter"). The Notebook lists every highlight in the book (Daf's, the Kindle's,
  audiobook and paper ones) in reading order under chapter headings; a click goes to it.
- **Bookmarks** (`book_marks`): b or the ribbon in the top bar; listed at the top of Contents.
- **Listen:** Kokoro reads from the top of the screen a paragraph at a time (`POST /api/tts/text`),
  highlights it, follows it across pages and chapters; speed, sleep timer (15–60 min). Counts as reading.
- **Time:** beats every 15 s while active (2-minute idle cutoff) → `ebook` sessions, "Books in Daf",
  counted by default, written to the vault reading log like article minutes.
- **Series:** Info shows the Calibre series and the next book; near the end Daf offers to start it.
- **Kindle highlights in the book:** placed by KOReader's xpointer (`DocFragment[n]` is the section, the
  element path narrows it), then matched on their words (first 8 and last 6, whitespace and quotes squashed),
  falling back to the whole section and then a search; drawn like Daf's own, with "Kindle" in the toolbar.
- **Daf → the Kindle** (the Daf plugin, not kosync, which stays on Komga): when a book opens in KOReader the
  plugin asks `GET /api/kindle/book?md5=` and (1) if Daf's position is newer than the Kindle's last page
  turn in that book and more than 1% away, asks "You read further in Daf… Go there?" (GotoPercent; "Stay
  here" is remembered for that position); (2) adds Daf highlights (source `epub`) as KOReader annotations,
  found with `findAllText` on the first 10 and last 7 words (`findText` from the start finds nothing on
  2025.04), with the Daf note; each is acknowledged (`kindle_pushed`) and also remembered on the device.
  When those come back in the sidecar, the importer skips them as duplicates of the Daf highlight.
  Tools → Daf → "Get my place and highlights from Daf" does it by hand. Tested in the emulator.
- **Colors:** yellow, green, blue, pink, purple (KOReader on the Kindle draws them all gray).

## Highlights, everywhere (`web/hl.js`, `daf/jump.py`)

- **The look:** Readwise's: a soft fill with a firmer underline (`--hl-<color>` and `--hl-<color>-line`, for
  light, dark and sepia). In books, `HL.draw` draws on foliate's overlay from the text boxes only (an
  empty paragraph inside a highlight draws nothing), blended multiply in light themes and screen in dark.
  A dot at the end means a note. Articles use `<mark class="hl">` with the same tokens.
- **The toolbar** (`#selbar`, a pill): over a selection, Highlight / Note / Define or Translate / Ask /
  Copy; over a highlight, remove (the colored circle; Undo in the toast), note, tags, the five colors,
  and … (copy, ask, share as image, view in notebook, favorite, auto highlight). The reader in front
  supplies what only it can do (`HL.active`).
- **Auto highlight** (per device, on with a mouse, off on touch): selecting more than one word highlights
  it at once; Alt (⌥) selects without. Selections grow to whole words. A highlight over existing ones
  merges with them (`replaces`), carrying notes, tags, favorite and review history (`review.carry`).
  Article highlights can span paragraphs (`pos.be`, the end block). Karakeep's highlights, which come
  without a position, are found in the text by their words.
- **Open at the exact spot:** every highlight row carries `open` (`jump.py`): `#ebook/<book>/hl:<id>` when
  Calibre has a file (Daf's by CFI, the Kindle's by xpointer, audiobook and paper ones by searching their
  words), `#read/<doc>/hl:<id>`, or `#book/<id>/hl:<id>`. The spot flashes. Used by the Highlights page,
  book pages, the Notebook, review (o), On this day.
- **Highlights page:** search (text, notes, tags, titles), source chips, color, tag, favorites, order
  (newest, by book in reading order, oldest), export of what's showing as Markdown, CSV or JSON
  (`/api/highlights/export`). Book pages list highlights in reading order by chapter, with Export.
- **Tags and favorites** live in `review_state` (`tags` JSON, `fav`). Tags go into the vault note as
  `#tags` on the quote's last line; a Kindle highlight with tags gets an entry there. Favorites come up
  twice as often in review.
- **Share as image:** a 1080×1350 card (the quote beside its color, title, author), with Share, Copy and
  Download.

## Home, stats, the … menu

- **Library home** (`home.py`, `#library`): shelves of cards: Continue reading (books + articles in progress),
  Recently added, Quick reads (≤10 min), Long reads (≥30 min), Recently highlighted, New in the Feed.
  Configure hides shelves (localStorage `daf.homeHidden`).
- **Stats** (`stats.py`, `#stats`): streaks (days at the hour, days reading, best), two weeks of dots,
  totals and the Year 30 projection at the last 30 days' pace, minutes by hour and weekday (90 days),
  sources, highlights per week, books waiting (2–97%, untouched 14+ days), reading now, finished, and
  "On this day". Today shows the streak and On this day; the Kindle screen shows the streak.
- **Summaries and tags:** Library documents with text get a two- or three-sentence summary by Claude
  (`reader.summarize`, job `summary`, six per sync, never private ones), shown in Info ("Summarized by
  Claude") and as the list snippet; Feed items have a "Summarize with Claude" button. Karakeep's tags
  (mostly its AI's) are kept in `docs.tags`, shown in Info, and the Library list filters by one.
- **Inline tags:** ".shame" or ".big-idea" in a note tags the highlight, as in Readwise: a Daf note when you
  finish typing it (focus leaves, or Save in review); a Kindle note when it's new or changed on import
  (`review.dot_tags`, `add_tags`, never removing).
- **Add to Daf** (the + by Library, a file dropped anywhere, or a link pasted outside a text field): links go
  to Karakeep at once (`/api/add/link`); EPUB, MOBI, AZW3, FB2 and CBZ to Calibre-Web-Automated's ingest
  folder `/srv/docker/cwa-ingest` (`DAF_CWA_INGEST`), then Books; PDFs to Karakeep as assets (`/api/add/file`).
- **Library and Feed lists:** order by newest, oldest, published, shortest, longest or started first (per
  list, on this device). The **Shortlist** (★, f) is Karakeep's favourites, two-way, until archived. In an
  article, ↑ ↓ in the top bar (Shift K / Shift J) open the previous or next item of the list it came from;
  Preferences → Reader → "After Done or Later, open the next one" (per device).
- **Never again:** in review (x) or a highlight's …, a highlight leaves review for good (status `never`);
  "Back into review" undoes it. **Follow in the Feed:** Add to Daf can subscribe FreshRSS to a site, in a folder.
- **Reading settings for one book:** Aa → "Just for this book" keeps that book's typeface, size, spacing,
  width, layout and justification (localStorage `bookType.<id>`); the theme stays the app's.
- **Hardcover** (`hardcover.py`, `web/hardcover.js`; key HARDCOVER_API_KEY from the vault's `.claude/.env`): the vault's
  own two-way sync (`.claude/scripts/hardcover-sync.py`, every 30 min) owns the book notes' status, rating, review and
  progress, so Daf never writes those keys; it talks to Hardcover, and that sync pulls the change into the note.
  Daf sends progress from its own reader (forward only, never to a finished book; every 30 min in the sync loop) and
  moves a Want-to-read book it sees you start to Reading; marks a book Read with a date and an optional rating when
  you say so (book page, the end of a book in Daf, or Today when the Kindle reaches 98%+). Books match by the vault
  note's `hardcoverBookId` (231 of them) or a link made on the book page (`hc_links`, search by Calibre ISBN, then
  title). Books shows the Want to read shelf. **Hardcover marks a book Read, dated today, the moment it's rated**, so
  Daf only rates Read books, and re-reads the book after a status change instead of adding a second read.
- **Flashcards** (Readwise's Mastery; `cards.py`, table `cards`): from a highlight's … (toolbar, row, or the review
  card's Flashcard), a fill-in-the-blank (tap the words to hide; stored as `{{…}}` in the text) or a question and
  answer; "Suggest with Claude" proposes both. Due cards follow the day's highlights in Review: space shows the answer,
  1 Again (once more today), 2 Hard, 3 Good, 4 Easy; new cards come back in a day (Easy: four), then the interval grows
  by the card's ease, Anki-style. Up to `cards_per_day` (5) new cards a day.
- **Newsletters** (`sources/newsletters.py`): Daf reads the Proton mailbox through Proton Mail Bridge (IMAP
  127.0.0.1:1143, the office agent's PROTON_* keys from `/srv/office/.env`), read-only (BODY.PEEK, readonly select of
  "All Mail"), and finds senders with List-Unsubscribe / List-Id. Preferences → Newsletters lists them (likely
  newsletters first, shops folded away, private ones never) and the ticked ones (`settings.newsletters`) come in as
  Library documents of kind `email` (ids `nl:<hash of Message-ID>`, last 30 days, every 15 min), cleaned of newsletter
  chrome (preheader padding, app buttons, icons, footer), with the web version as the original. Reading state is Daf's.
  Bridge puts the UID after the literal in FETCH replies.
- **Themed review:** `#review/tag/<tag>`, `#review/fav`, `#review/color/<c>` (`/api/review/themed`): up to
  ten of those highlights, shuffled, with the same keep / less / note; linked from the Highlights page.
- **Article … menu:** document note, read aloud, ask, move, reset progress, edit title and author
  (`doc_edits`, laid over Karakeep's and FreshRSS's after every sync), open/copy the original, open the
  vault note, keyboard shortcuts (m, ?, o, Shift L/N/R/C/M).

## Goals, books, search, and sending to the Kindle (2026-10-09, late)

- **Goals** (`goals.py`, `web/goals.js`, Preferences → Goals, `#prefs/goals`):
  - **The goals:** one per kind, each on or off: reading time (a day, week or month); pages
    (a day or week); books (in Year N, a calendar year, or by 35); days with reading a week; a
    streak at the goal; highlights a week; and days with the daily review a week. Presets:
    Gentle, Year 30, Deep.
  - **History:** each goal keeps a dated `history` in settings.json. A change counts from today,
    so earlier days, streaks and the year grids are judged by the goal they had (`T.grid`
    returns each day's `targets`).
  - **The main goal** drives the ring on Today. `/api/today` and `/api/phone/widget` add `main`
    and `goals[]`; `/api/kindle/*` adds `main`. `goal` stays the day's minutes target, because
    the Kindle adds its own minutes to it.
  - **Pages:**
    - Kindle page turns of 5 s or more, each page once a day;
    - `ebook_pages` from Daf's reader (pages shown for 5 s);
    - paper pages logged as `· 32 pages ·` in the reading-log line (`sessions.pages`).
  - **Books:** Hardcover read dates plus Daf's ≥97%. Manga volumes don't count unless the books
    goal's switch says so.
  - **Previews and milestones:** previews use your own pace (`goals.pace`). Year 30 milestones
    get a small celebration once per device.
- **A book's page:** reading stats from `bookstats.py`:
  - time across the Kindle, Daf and the audiobook;
  - sittings;
  - Kindle pages an hour;
  - the last 30 days;
  - time left and a finish date at the recent pace.

  "Review these" reviews that book's highlights (`#review/book/<id>`). How often the book comes
  up in the daily review is More / As usual / Less / Never (`book_review`; Less is ×0.35, More
  ×2.5, Never leaves it out).
- **Search inside saved text:** FTS5 over `doc_content`, kept up to date by triggers and filled
  once (`docs_fts`). ⌘K shows the title and a snippet; opening a result goes to
  `#read/<id>/q:<words>`, which scrolls to the first match and marks it.
- **Several at once:** in Library and Feed lists:
  - Cmd/Ctrl-click or the round checkbox picks a row, Shift-click picks a range, and x picks the
    current row. On a phone, Select turns tapping into picking.
  - The bar at the bottom archives, moves, marks seen, shortlists, saves or sends to the Kindle
    (`POST /api/docs/bulk`).
- **Send to Kindle** (`kindlesend.py`): from an article's … menu or the bulk bar.
  - Daf makes one EPUB 3 of the articles, right-to-left for Hebrew; several articles become a digest.
  - It goes to `/srv/koreader/Libros/Daf` (`DAF_KINDLE_DIR`), which Syncthing hands to KOReader.
    A sandbox must set `DAF_KINDLE_DIR` to a scratch folder.
  - **Back from the Kindle:** each EPUB is recorded by KOReader's partial md5 (table `kindle_epubs`,
    refilled from the files by `kindlesend.scan`, since every chapter carries `<meta name="daf-doc">`).
    - Highlights made in it belong to their articles: chapter n of the xpointer is the nth article, and
      the words place them in the article's text. They open at their spot, go to the article's clipping
      note with any note typed on the Kindle, and the daily review shows them under the article.
    - Deleting the EPUB on the Kindle (its sidecar goes too) keeps the highlights. Deleting one
      highlight on the Kindle removes it from Daf.
    - Page turns in it are article reading, split by each article's share of the text, and set each
      article's progress. A digest never shows up as a book.
- **Tags on documents:** "+ Tag" / Edit in the info panel opens the highlight tag editor. Karakeep
  items attach and detach their tags in Karakeep; feed items and emails keep them in Daf. Saving a
  feed item to the Library takes its tags along.
- **Saved views:** "Save view" on a list keeps its tab, tag and order in settings.json (`views`) and
  in the sidebar under Shortlist (`#view/<id>`).
- **Flashcards for Anki:** Highlights → Export → a tab-separated file Anki imports
  (`/api/cards/export`). Cloze cards become `{{c1::…}}`.
- **Highlights → Review these:** a themed review of whatever the filters show (`#review/filter/<query>`).
- **PDFs as printed** (`web/pdfview.js`, pdf.js 4.10.38 vendored in `web/vendor/pdfjs`, Apache 2.0):
  `#pdf/<doc>[/hl:<id>]`, opened by the text view's Pages button.
  - **Pages:** drawn as they scroll into view, with a text layer to select on; selections snap to whole
    words.
  - **Highlights:** drawn on the page in Daf's colours. A highlight made on a page keeps `pos.pdf`
    (`{pg, r}`, rects as fractions of the page) and, when its words are in the text view, its place
    there too. One made in the text view is found on the page by its words.
  - **Reading:** zoom with + and −. The page is remembered, progress is the page you're on, and the
    time counts as reading.
- **Shelves** (`web/shelves.js`, tables `shelves` and `shelf_books`): your own groups of books.
  - A Shelves row on Books, and `#shelf/<id>` with Rename and Delete.
  - Chips on a book's page to put it on or take it off a shelf.
  - **Hardcover lists are shelves** (`shelves.hc_list`, `hardcover.sync_lists`): every list made on Hardcover
    comes in with the half-hourly Hardcover sync, and a book put on or taken off it in Daf changes the list
    at once (`insert_list_book` / `delete_list_book`), as does a rename. Only books Daf knows on Hardcover
    take part, private books never go up, and Daf never makes a list (lists can be public). Deleting one
    is done on Hardcover; its shelf then stays in Daf as an ordinary one.
- **Readwise, the years before Daf** (`sources/readwise.py`): the Readwise exports in `Reference/clippings`
  (bullets ending in a "View Highlight" link, with "Note:" under them) are read on every sync and never
  written. Each highlight keeps its Readwise id; it hangs off the Library's copy of the page when there is
  one, otherwise a `rw:` article whose vault note is the Readwise note. They come up in the daily review,
  and Highlights has a Readwise filter.
- **A highlight on a Feed item saves it to the Library**, as in Readwise: the server saves it after the
  first highlight and the reading view moves to the Library copy (`saved_as`).
- **One-word highlights** from the browser extension (or Karakeep) are found as whole words in the reading
  view, the words before them choosing between the places they appear.
- **Filters on lists:** Filter in a Library or Feed list narrows it by source, author, length, date added,
  highlighted or not started. The filtering happens on the server (`/api/docs?source=&author=&minlen=&maxlen=&since=&hl=&fresh=`).
  The active filters show as chips. A saved view keeps its filters; "Save to the view" updates them.
- **Send to Kindle images:**
  - Fetched six at a time, shrunk to 1200 px wide, and kept to 20 MB at most.
  - Only public addresses are fetched, with redirects checked too. Tracking pixels and icons are left out.
  - Needs Pillow, which is in requirements.txt.
- **Read aloud follows the sentence:** `H.follow` in `web/hl.js` marks the sentence Kokoro is on with the
  CSS Custom Highlight API (`::highlight(daf-speaking)`, the `--speak-line` colour), timed by
  characters. It works in articles and in books. The page's DOM and the shells' `[data-tts]` and
  `[data-bt]` buttons don't change.

## Later additions (Phase 8)

- **PDFs** (`pdfdoc.py`): opening a PDF in the Library queues a `pdf` job: Daf downloads it
  (Karakeep's asset if any, else the URL; on a certificate error it tries the host with/without
  `www.`, never without verification), keeps it in `/srv/docker/daf/pdf`, and reads its text with
  pypdf into paragraphs with page markers. Running heads/feet repeated on 40% of pages are dropped.
  "Pages" in the reader opens the file itself (`/api/docs/{id}/pdf`).
- **Tweets:** X's '(2) Name on X: "…" / X' title becomes "Name on X" with the first tweet as the
  lead; repeated avatars are hidden; each tweet gets a thread rule.
- **Vault search** (`vaultsearch.py`): ⌘K adds vault notes (names first, then `grep -F` over the
  text, hidden folders and `.claude` skipped; more in settings `vault_search_exclude`). Results open
  in Obsidian (`obsidian://open`).
- **Torah essays:** `Reference/torah/<parasha>/*.md` (Covenant & Conversation) for the week show on
  the Torah shelf; they open in Daf as docs `ve:<hash>` (markdown → blocks, clipping furniture
  dropped) and highlights go back into the same note's Daf region.
- **Devices:** `POST /api/save {url, title}` with a device token saves a link (Mac, Shortcuts).
  Mac menu-bar brief: `mac/NEXT.md`. Android widget brief: `android/NEXT.md`.

## Sources (Phase 1)

- **Kindle:** KoInsight's database (history; current only when KoInsight syncs), and the
  Daf KOReader plugin once installed, which posts page turns on sleep, on closing a book,
  and when Wi-Fi connects. Turns are stored once per (book md5, start) whichever way
  they arrive. Sittings = turns less than 10 minutes apart.
- **Audiobookshelf:** `absdatabase.sqlite`, read-only. Audiobooks count; the podcast
  library is stored private, never named, never counted.
- **Paper:** the reading-log notes in the vault, found by `type: reading-log`.

## The Kindle

`tools/install-kindle.sh` copies `kindle/daf.koplugin` over SSH (Tailscale, :2222), creates
`settings/daf.lua` with the URL and a device token the first time, and checks the Lua on the
device. Restart KOReader afterwards. Menu: Tools → Daf (Open Daf, today's minutes, send now,
sleep screen on/off, open Daf on the first wake of the morning). Turning the sleep screen off
restores the previous screensaver message.

**The Daf tab** (`dafscreen.lua`, drawn with `canvas.lua` like Home since 2026-10-20): today's
minutes and bar, the day's review (Keep / Less often, ‹ › or swipe), and the nightstand (tap a
book to open it). It draws from the
last `/api/kindle/home` answer kept in `settings/daf.lua`, so it works with Wi-Fi off; taps made
offline wait in `pending_review` and go to `/api/kindle/review` on the next sync. Books are found
by KOReader's partial md5 over the reading history, then by title in the file name. A gesture can
open it: Gestures → pick one → General → "Daf: open the Daf screen".

Testing without the Kindle: the KOReader Linux build (v2025.04, same as the Kindle) runs under
`xvfb-run` with `EMULATE_READER_W=1236 EMULATE_READER_H=1648 EMULATE_READER_DPI=300`, the plugin
symlinked into its `plugins/`, and a user patch that calls `showScreen()` and `Screen:shot()`.
Point it at a copy of the state (`DAF_STATE=… uvicorn daf.app:app --port 8441`) so taps don't
touch the real review. JSON `null` arrives in Lua as a function; `denull()` strips them.

## Tools

- `tools/shot.py OUT.png [--path /#sources] [--mobile --width 390 --height 844] [--dark] [--full]`:
  signed-in screenshot through the headless Chrome container.

## Manga (`daf/manga.py`, `web/manga.js`)

Komga is the library and Daf is where it's read; nothing is copied out of Komga.

- **Pages:** `#manga` shows the series and the ones under way, `#manga/<series>` a series' volumes, and
  `#mread/<book>[/<page>]` is the reader, full screen.
  - Right to left by default, left to right, or one long strip for webtoons.
  - Two pages side by side when the screen is wider than tall, with wide spreads alone and "Shift pages"
    for pairs that start wrong.
  - Tap the sides, swipe, or use the arrows to turn pages; tap the middle for the bars; pinch or
    double-tap to zoom. The choices are kept per series.
- **Progress:** goes to Komga as the Kindle's account (`kindle@tiresia.xyz`), so the Kindle opens where Daf
  left off and `manga-track.py` takes a finished volume to AniList. Daf reads both accounts and shows the
  furthest, so progress from Kahon (Mihon's Komga tracker) shows up too.
- **Images:** pages are shrunk to the screen as WebP in four sizes and cached under
  `STATE/manga-cache` (3 GB at most, oldest dropped first).
- **Minutes:** time in the reader is source `manga` ("Manga in Daf", counted by default), one session per
  series a day.
- **Kindle volumes:** `manga.refresh_index` (after each sync, outside its transaction) keeps the KOReader md5
  of every file in `/srv/media/manga` (`manga_files`) and ties Daf's book rows to Komga (`manga_books`),
  by md5, by file name, or by `series-map.json` and the volume number. Those rows leave Books, their Kindle
  time is titled by series, and the books goal leaves them out unless manga counts.
- **Keys:** `/srv/docker/manga-import/komga.json` (mode 600, manga-track's), read in place.
- **AniList (`daf/anilist.py`, `web/anilist.js`, 2026-10-26):** `manga-track.py` (cron, :25 every hour) sets
  progress on AniList with the sign-in Daf keeps in `STATE/anilist/token.json` (mode 600; AniList's implicit
  grant, a year at a time: the client id is in settings, the redirect is `/anilist`, which `sw.js` lets
  through). The script leaves `{at, summary, error}` in `/srv/docker/manga-import/last-run.json` for the
  Preferences card and the Sources check. It used Suwayomi's tracker until Suwayomi was retired the same day;
  what Suwayomi's reader had marked read is kept in `suwayomi-snapshot.json` and still counts.

## Offline

What you do with no network is kept on the device and goes to the server when it's back; what you read
can be kept ahead of time.

- **The outbox** (`app.js` `OUTBOX`, `localStorage daf.outbox`): book places, highlights, bookmarks;
  article highlights, notes, tags, status, progress, star and title; reading time (articles, books,
  manga); the daily review and cards; paper minutes; reading notes. Each write carries `X-Daf-Op`
  (a random id); the server keeps the first answer to each op for a month (`ops` table) and gives it
  again for a repeat, so nothing counts twice. A write waits at most six seconds on a connection that
  doesn't answer, then goes to the outbox. While it waits, the page gets the answer it would have had
  (a highlight's id is the server's own hash). Time is kept with each write (`at`): an offline review
  counts on the day it was done, a highlight keeps when it was made, paper minutes their day.
- **Shown:** "Offline · N waiting" in the corner (tap: send now); Today counts the minutes still on
  the device. What needs the server (Ask, summaries, Send to Kindle, adding links) says so offline.
- **Kept ahead:** `GET /api/offline/plan` names what to keep (the pages' own requests, character for
  character: Today, the review for today and the next three days, the Library and Feed lists, Books,
  Highlights, manga; `docs` to keep with their pictures; `ebooks` files; covers). Daf for Android keeps
  it natively; in a browser or the Mac app the page fetches it through the service worker every six
  hours. `/api/review?day=` builds a coming day's review now, without repeating the days before it.
- **The service worker** keeps lists also by what they are (where, tab, kind), so a list opens offline
  whatever order this device shows it in.

## Themes and typefaces

- **Themes** (`web/themes.js`): `FAMILIES`, each a light and a dark palette of a few colours (bg, side,
  fg, accent, read, ok, bad, five highlight hues). `T.vars` makes every token style.css uses from them,
  set inline on `<html>` (they win over style.css's own `:root`, which stays as the no-script look).
  - `settings.appearance` = {mode: system|light|dark, light, dark} (`config.clean_appearance`), applied
    from `/api/today`'s settings on every load.
  - `localStorage daf.themeVars` holds both versions, so index.html's first script paints the right one
    before any CSS rule shows.
  - `html[data-mode]` says light or dark, and `meta[name=theme-color]` follows the sidebar.
  - A `daf-theme` event ({name, dark, bg, side, fg, accent}) goes out on every change, for the apps'
    own chrome.
  - The old Aa themes (light, sepia, dark, black) move over once: sepia becomes Paper, black becomes
    Black.
- **Typefaces** (`web/fonts`, made by `tools/fetch-fonts.py`): 24 OFL families from Fontsource, Latin,
  Latin Extended and Hebrew subsets only, about 4.4 MB, with their own `@font-face` rules and unicode
  ranges in `web/fonts/fonts.css`.
  - No Google Fonts request any more. index.html and the book's pages (book.js `fontCSS`) load Daf's
    copies.
  - `T.FACES` / `T.stack(id)` give the reading stack; Hebrew falls back to Frank Ruhl Libre (serif) or
    Heebo (sans).
- **Your own fonts:** `POST /api/fonts?name=<file>` (the raw file; TTF, OTF, WOFF or WOFF2 by magic
  bytes, up to 8 MB) saves to `STATE/fonts`.
  - The family and style come from the file name ("Bookerly-BoldItalic" → Bookerly, 700, italic).
  - `settings.fonts` lists them; `GET` and `DELETE /api/fonts/<file>`.
  - `T.userFontCSS` adds their `@font-face` rules to the page and the book.

## Backups

- **Borg** (a nightly Borg script, 03:30) takes all of `/srv/docker`,
  Daf's state included, and `/srv/dev`. It keeps 7 daily, 4 weekly and 6 monthly archives and mirrors
  them to old the server.
- **`daf backup`** (cron 03:00, before Borg) writes a consistent copy of `daf.db` to
  `STATE/backups/daf-<date>.db.gz` and keeps 14 (mode 600).
  - It uses SQLite's online backup, so it's safe while Daf writes in WAL mode, which a plain file copy
    isn't.
  - Each copy is integrity-checked; a failure goes to Signal through `notify.sh`.
  - Borg then carries the clean copy. Restore: `gunzip -c daf-<date>.db.gz > daf.db` with daf.service
    stopped.
- **Left out:** the manga page cache lives in `STATE/cache/manga`, which Borg's `*/cache/*` rule skips;
  Daf rebuilds it from Komga.
- **What only Daf has:** reading sessions and time, the Kindle page turns the plugin sent, review
  history and state, cards, settings, your fonts. Highlights and notes are in the vault as well.


## Delete, pictures, paywalls, keys, AI, the morning email, feedback, imports (2026-10-12)

Daf was held up to Readwise Reader's intro video, and this round built all of what was missing, plus
four things first set aside as not worth it.

- **Delete** is a status, `deleted`, for a doc in either place (`reader.set_status`; `docs.deleted`
  is when). Every list, count, search and summary job skips it. A Feed item is marked read in FreshRSS
  at once; a Karakeep one stays in Karakeep for `UNDO_SECONDS` (600) so Undo can bring it back, then
  `reader.purge_deleted` (each sync, before `karakeep.sync`) deletes the bookmark and the row. A doc
  with highlights stays as a quiet row (`deleted = 1`) so its highlights keep their title; saving the
  same page again moves them to the new bookmark (`pages.save_page`). Karakeep's sync keeps `deleted`
  as it is. The Feed's 30-day prune takes deleted items with the seen ones. Anything that isn't
  Karakeep's (emails, Torah, Feed items) keeps its row as `deleted = 1` for good, so the sync that
  brought it (which skips ids it has) doesn't bring it back.
- **Undo** (`reader.js` `pushUndo`/`undoLast`): every Done, Later, Shortlist and Delete, single or
  bulk, pushes its inverse; the toast's Undo and z pop the newest.
- **Pictures as highlights**: a highlight whose text is Markdown's picture, `![alt](address)`, with
  `pos.img` the address (`reader.add_highlight(img=...)`, http(s) only). The reader frames the figure
  (`figure.hlimg`); `H.quote` draws it everywhere a highlight shows; the vault gets the Markdown, which
  Obsidian shows. Articles only; books and PDFs' pages still highlight text.
- **The page as you see it**: the extension (0.3.0) sends the page's HTML (`snapshot()` in
  content.js: scripts out, pictures and links made absolute, its own marks unwrapped, up to 6 MB) with
  Save and with the first highlight on a page; the popup's "Give Daf this page's text" sends it for a
  page already saved. `pages.keep_text` finds the article with trafilatura (`content.article`, shared
  with fulltext.py) and keeps it when it has more words than Daf's copy, and clears `ai_summary` so the
  summary is made again from the whole thing. `/api/web/page` answers `where: "deleted"`.
  URL helpers moved from webapi.py to `daf/pages.py`.
- **The extension updates itself** (0.5.1 on, Firefox and Zen): the Firefox manifest has
  `gecko.update_url` = https://daf.tiresia.xyz/extension/updates.json, which they check about once a
  day. `GET /extension/updates.json` offers the newest file in `extension/signed/` (with its sha256),
  and `GET /extension/daf-<version>.xpi` serves it. Both are open, no sign-in: signed builds of the
  public extension code. To ship a change: bump `version` in extension/manifest.json, run
  `extension/sign.sh`, commit the new file in `extension/signed/`; no restart (read from disk). Chrome
  and Arc (unpacked) don't update themselves; Safari's comes with the Mac app.
- **Keys** (`web/keys.js`): one table of scope → action → default keys for lists, articles, books,
  the review and manga; settings `keys` holds your changes (`PUT /api/keys`), `/api/today` brings them,
  localStorage `daf.keys` keeps them for a cold start. Handlers call `DafCore.Keys.is(e, scope, action)`;
  a letter typed with another layout (Hebrew) matches by `e.code`. Every shortcut sheet is
  `Keys.sheet(scope)`. shell.js presses the bound key for the menus (docs/SHELL.md).
- **AI** (`daf/ai.py`): `DEFAULTS` holds the instruction part of each prompt (summary, ask, ask_book,
  word_en, word_he, card); settings `ai` keeps your changes, the model (`""` = `DAF_CLAUDE_MODEL`), the
  ready questions (`/api/docs/{id}` and `/api/ebooks/{id}` send `questions`) and `auto_summary`, which
  `queue_summaries` obeys. `ai.run` is the one place the CLI is called (paper_pages keeps its own,
  with its tools).
- **The morning email** (`daf/digest.py`): settings `digest` {on, hour, feed}; the sync loop's
  `extras()` sends it once a day at the hour in the home zone, only with something new (kv
  `digest_last`, three tries on a day it fails). SMTP through the Bridge (`PROTON_SMTP_PORT`, 1025),
  from daf@tiresia.xyz (`digest.SENDER`, or settings `digest.from`; tiresia.xyz is a custom domain on
  the owner's Proton account, so Proton signs it; changed 2026-10-13) to PROTON_USER. `/api/digest/preview`
  renders it; `POST /api/digest/send` sends one now.
  Private titles are left out.
- **Feedback** (`daf/feedback.py`): kept in table `feedback`, then `gh issue create -R
  franz-rosenzweig/old-daf --label feedback` (the private repo, never the public one; env
  DAF_FEEDBACK_REPO) as lander (the label is made on first use). It carries the
  route, device, window, theme and the page's last errors (`DafCore.errs`, app.js); a private title
  is replaced. Ones GitHub didn't take are tried again by `extras()` for a day. POST /api/feedback is
  in the outbox, so it waits offline.
- **Imports** (`daf/imports.py`): `detect` reads Instapaper, Pocket (CSV zip or ril_export.html),
  Omnivore (zip), Readwise Reader, Raindrop, GoodLinks, Wallabag, Netscape bookmarks, OPML and any
  CSV/JSON with a url column into one shape; table `imports` keeps the items, the options and the
  counts. `POST /api/import` only reads the file; `/start` runs a thread (`_work`: the items read
  once, one item at a time, 0.25 s apart, committing after the save so Karakeep's archive/star/tag
  calls run without the write lock) that `extras()` restarts after a restart. Links go through
  `pages.save_page` (keeps the saved date), then archive/star/tags in Karakeep; highlights are `daf`
  highlights placed by their words (`pos {q}`), never twice. Feeds go through `freshrss.subscribe`,
  skipping ones already followed.
- **Drag and drop** takes several files at once and a link dragged from another tab (`text/uri-list`);
  a drag that starts inside Daf isn't one.
- **Sandbox**: scratchpad `sbf.sh` starts sbfake.py with stand-ins for Karakeep (save, archive, star,
  tags, delete, PDF), FreshRSS (mark, subscribe, subscriptions), the email and GitHub; checks in
  apitest.py (31), imptest.py (15) and uitest.py (29).

## The audit round (2026-10-13)

Two read-only audit agents (server and web) went through Daf; these are the fixes, made on the
`audit-fixes` branch.

- **Nothing slow on the event loop.** The routes that wait on Karakeep, FreshRSS, Komga, GitHub, the
  Kindle send or the database are plain `def`s now (FastAPI runs them on worker threads), reading their
  JSON through the `json_body` dependency (webapi.py's `_body` is the same, as a dependency). The rest
  of the `async def` routes do only quick work. `/api/paper` no longer runs a whole sync: it appends
  the line and reads the paper log back (`paper.import_entries`).
- **The sync commits after each source** (`conn.commit()` before each block in `sync.run`), so the
  write lock isn't held through the next source's network calls.
- **X-Daf-Op is claimed before the write runs** (`_op_claim` puts a status-0 row in `ops`; a repeat
  that arrives meanwhile waits for the answer, up to 20 s, then gets 503 and stays queued; a 5xx or
  401 releases the claim). The middleware's database work runs in the thread pool, and nothing is
  replayed to a request without a cookie or a token.
- **Vault notes after a highlight changes** all go through `vaultnotes.write_for`: an id in `docs`
  gets its clipping note (`write_article`), anything else its book note. A note added in the review,
  over Signal ("n:"), a tag, a removal or a restore on an article's highlight no longer leaves only
  the noted highlights in its clipping note. `write_all` does the same.
- **Saving a Feed item that Karakeep already has** keeps the Library copy (place, Later, note, star,
  tags, summary, text) and only adds to it (`reader.save_to_library`); a page saved again after its
  purge takes the old row's highlights, sessions, books row (its vault note) and note
  (`pages.save_page`).
- **Reading after midnight counts for the new day** (`today.beat_start` keeps a session's start at
  or after that day's midnight), and the three beats (articles, books, manga) are one upsert each,
  so two first beats at once don't fail.
- **Summaries** skip items under 60 words and items that already had a job, so short tweets don't
  hold the queue; `pages.keep_text` drops the old job when a longer text arrives.
- **Private titles**: the phone widget and the Kindle home show "A private book" for one on the
  nightstand; picture highlights are said in words on the phone (`reader.plain`). Asking about a
  private book yourself still sends it to the model (Preferences → AI says so).
- **Feedback** is retried only after its first try failed and two minutes passed (no double issues),
  and one GitHub never took is said on Signal after a day. **The morning email** tries three times
  a day and then says so on Signal.
- **`GET /share`** from another site asks first (a form that posts); the share menu and Daf itself
  save at once (`Sec-Fetch-Site`).
- **Smaller:** `vault_search_exclude` is read from settings again; clipping file names stay under
  200 bytes; a bad date to `/api/paper` is a 400, not a 500 that would block the offline queue; bulk
  status checks the status once and lists per-document failures; the books goal and Hardcover use the
  home time zone; deleted docs leave the home shelf, the Torah page's Ruach list and the caption jobs;
  the model's errors reach the page in Daf's words (`ai.plain_error`).
- **Web:** the offline queue reads the stored queue afresh for each send and removes only what it
  sent (new writes made during a flush were lost), and sets aside one Daf keeps refusing after five
  tries (`daf.outbox.stuck`, included in Send feedback); queued tag edits keep their tags; a sheet in
  front takes the keys (and Esc closes only it); a Library tag doesn't follow into the Feed; a saved
  view's order can change and be saved; the manga reader doesn't open over a page you've gone to;
  the Notebook's Delete highlight removes it from the text too; picture highlights undo, list in
  Contents and jump to the figure; Forget my place forgets on the server (`DELETE
  /api/ebooks/{id}/position`); leaving an article opened straight from a link goes to its list;
  several dragged links are each saved; key hints and `/` follow Preferences → Keyboard; keys work by
  position with a Hebrew layout (Q no longer opens search; the brackets aren't mirrored); `?` answers
  on every page; the row hover bar is off on touch screens.

## Recovery (`daf/recovery.py`, `web/recovery.js`, 2026-10-13)

`#recovery`, under Library. `GET /api/recovery` builds it from Calibre:
- **The Big Book** is the book whose title matches `BIG_BOOK` (cal:17 now). Its EPUB's NCX contents,
  in spine order, are split into the first 164 pages (The Doctor's Opinion and chapters 1-11, with
  the Fourth Edition's first pages from `PAGES`; the file has no page markers), the stories (Part
  I-III) and the appendices.
- **How far:** each chapter's start is its place in the spine by size, and "read" comes from the
  furthest of Daf's place and the Kindle's progress.
- **Readings and prayers** open with `#ebook/<id>/q:<words>`: book.js `goToWords` finds the passage
  with the reader's search. Only public-domain texts (the Serenity Prayer, St. Francis) and the first
  words of each passage live in the code.
- **More to read** is A.A. literature by name (`OTHER`). Never widen it to general words like
  "recovery" or "addiction": they match books that don't belong on this page.

There's no check-in form and no date counter, on purpose.

## Speed (2026-10-13)

Daf answers in 5-35 ms; through daf.tiresia.xyz every request costs 250-450 ms (even from the server), so
a page that made several reads and revalidated ~40 files took seconds. Now (measured with 300 ms added
per request: Daf opens 2.0 s → 0.4 s, the Library list 418 → 65 ms, Books 339 → 11 ms, a book opened
before 3.5 → 0.8 s):

- **Fingerprinted files** (`daf/webcache.py`): `/` serves index.html with each script and style as
  `/name.js?v=<sha1[:10]>`; those go out `immutable` (the headers middleware), vendor files for an hour
  with a week of stale-while-revalidate, fonts for a month. `/sw.js` is served with `VERSION` (a hash
  over every file's size and mtime in web/) and `FILES` (the fingerprinted list) filled in.
- **The service worker** (web/sw.js): caches `daf-shell-<VERSION>` (the page answered from here at
  once and refreshed behind; every other file of the page device-first), `daf-data-v1` (API reads,
  network-first, as before), `daf-img-v1` (covers, manga thumbnails and pages, feed icons,
  device-first, 3000 kept) and `daf-books-v1` (book files, device-first, 60 kept; `cache: 'reload'`
  fetches again). A change anywhere in web/ is a new sw.js: the browser installs the new set on the
  next load and the one after runs it; old shell caches are dropped. In Daf for Android book files and
  manga pages pass through (the app keeps them itself, `Offline.intercept`).
- **Pages draw from the device first** (`DafCore.swr` in app.js): Today, the Library and Feed lists,
  Home, Books, Highlights, Manga, Stats, Torah and Recovery render the kept copy at once, then draw
  again in place (scroll kept) if the network brings something new, unless a menu, a sheet, a field
  or a tap since the page was drawn says you're busy. The sidebar's counts do the same.
- **Warm menus**: `warm()` in app.js reads the offline plan's URLs (not books or fonts) a few seconds
  after Daf opens and every ten minutes while it's in front.
- **Books**: book.js fetches the file beside the book's details, from the device when kept, and
  again only if its size differs from Calibre's (`d.size`).
- **Covers and manga thumbnails** go out for a week with a month of stale-while-revalidate.
- Test: scratchpad swtest.py (9 checks), swtime.py (timings) and swupdate.py (an update reaches a
  device), through a forwarder on localhost:18443 inside docker-chrome-1 (container daf-swproxy,
  scratchpad swp/proxy.py, with `/__count` and `/__delay?ms=`), because a service worker needs a
  secure origin and Chrome treats localhost as one.

## Phone fixes (2026-10-14)

- Each Android device has its own token now, named android-<model> (android-sm-s926u, android-sm-t580). Before, the phone and the tablet shared "android", and whichever connected last killed the other's token, which broke Save to Daf with "Daf doesn't know this phone's token". Making an android-* token deletes the old shared row.
- The page tells Daf for Android two things through the `reading` op (docs/SHELL.md): whether the volume keys turn pages, and whether Daf's bar owns text selection. The volume switch is per device, in localStorage `daf.volumeKeys`, and off by default.
- `tools/sandbox.py` runs a sandbox whose outside writes (Karakeep, FreshRSS, Hardcover, Komga progress, the email, GitHub) are stand-ins that print what they were asked. It refuses to start on the real state. Run straight from uvicorn, the sandbox has no sync loop, so shared links stay in its inbox.

## Tips, What's new, and pages that update themselves (2026-10-14)

- `web/tips.js` holds the tips (TIPS: a feature's view, its control's selector, the words) and What's new (NEWS, newest first). Add a NEWS line with each user-facing change. State is in settings.json `tips` {off, seen, news} through GET/POST /api/tips. In the console, `DafCore.Tips.why()` says why no tip shows.
- index.html carries `<meta name="daf-version">` (webcache), and /api/health returns the live version. A page that's older reloads at a calm moment: on the next move outside a reader, or on coming back after 30 s away, never while something plays. Before this, the apps could run an old page for days after an update.

## Daf keeps the Library (Karakeep read only) (2026-10-14)

- settings.json `library.karakeep`: "on" (Karakeep keeps the Library, the old way), "read" (Daf keeps it; Karakeep is only read, for bookmarks made there; nothing is written to it), "off" (Karakeep isn't asked). `daf karakeep-import` moves it from "on" to "read", once; `--again` fills in anything still missing.
- New saves are dl:<16 hex> rows. A "page" job (its own worker thread, `daf-pages`, so it never waits behind a transcript) reads the page: urllib with the public-address guard, then the headless Chrome in docker-chrome-1 (daf/browser.py, DevTools on :9222) for robot checks and script pages. Pictures are kept in STATE/thumbs (/api/thumb/<hash>.jpg, at most 960 px). Uploaded PDFs are kept in pdfdoc's folder.
- A "tags" job gives a new save 2 to 4 tags (ai prompt "tags", Preferences → AI switch), never a private one. A "tagtidy" job asks the model for a tidy-up of the doc tags (kv tag_tidy); Preferences → Library tags applies only the ticked changes.
- **When Karakeep goes for good** (with the owner's OK first): set library.karakeep to "off", `karakeep dump` into the borg backup, stop the web and meilisearch containers, and keep **docker-chrome-1**: browser.py needs it.
- The sandbox has no job workers: run pages.fetch / tagging.tag_doc by hand against its state (scratchpad libtest.py).

## Karakeep retired (2026-10-19)

- settings library.karakeep = "off": Daf asks Karakeep nothing (no sync, no check on Sources). Its containers (web, meilisearch) are stopped and sit behind the compose profile "karakeep" in /srv/docker/docker-compose.yml (backup .bak-20261019-karakeep), so a plain `docker compose up -d` leaves them off. Data stays in /srv/docker/karakeep-app and /srv/docker/meilisearch, in the nightly borg. To bring it back: `docker compose --profile karakeep up -d web meilisearch`, and library.karakeep "read".
- **docker-chrome-1 stays**: daf/browser.py reads robot-checked pages with it.
- What used Karakeep now uses Daf's API for local tools (/api/tools/library, /api/tools/save, /api/tools/docs/{id}; /api/thumb takes a device token), each with its own device token: the desk ("desk", DESK_DAF_TOKEN in /srv/docker/desk/.env: the Saved page, k-capture, save/archive/star, pictures) and the office agent ("office", DAF_TOKEN in /srv/office/.env: `read saved`). The homepage tile is Daf's (services.yaml backup .bak-20261019-karakeep).
- Left for a root moment: keep.tiresia.xyz in /etc/cloudflared/config.yml (and its DNS record) now leads nowhere. The vault script karakeep-sync.py was no longer scheduled; Reference/karakeep/ keeps its 30 notes.

## KoInsight retired; the Feed keeps a month (2026-10-20)

- settings koinsight = "off": no import, no Sources check. The KoInsight container is stopped and behind the compose profile "koinsight" (backup docker-compose.yml.bak-20261020-koinsight); its data stays in /srv/docker/koinsight (borg). Its old annotations still fill highlights (sources/highlights.py reads the file if it's there).
- The Kindle: plugins/koinsight.koplugin renamed .retired and settings/koinsight.lua sync_on_suspend false (backup .bak-20261020), so it doesn't try to sync at every sleep. To undo: rename it back, then restart KOReader.
- Kindle numbers for local tools: /api/tools/kindle?days=N (device token). The desk's Trends and reading card use it with DESK_DAF_TOKEN; the homepage tile "Kindle" uses /srv/docker/homepage/kindle-stats.sh (token "homepage" in kindle-stats.env, cron every 30 min; it replaced koinsight-stats.sh).
- Left for a root moment: koinsight.tiresia.xyz in /etc/cloudflared/config.yml.
- The Feed: feed_expire_days defaults to 30; Preferences offers a week up to a year or never (3650). A larger window makes the next sync fetch once back to its start (kv feed_window). FreshRSS's archiving keep_unreads is now true (config.php backup .bak-20261020), so unread articles stay as long as the window wants them.

## The Kindle: Home, and highlights through the plugin (2026-10-20)

- Syncthing is off on the Kindle (its plugin is disabled), so the Daf plugin now sends each book's notes file (highlights and notes) itself: POST /api/kindle/annotations, kept per md5 in kindle_sidecars, which library.sidecars() reads before any Syncthing copy. On the plugin side the settings keep notes_sent (file → mtime).
- Home (kindle/daf.koplugin/home.lua) draws itself at fixed places, designed at 1236 px. Covers are cached in <data>/cache/daf-home. /api/kindle/home now also gives hebrew_date (Hebcal, cached in kv), parasha (Sefaria calendar) and private_md5s. Settings home_on_start (default on).
- Later the same day: Home lost the review (it's on the Daf tab, now a canvas page too) and the shelves (on Shelves). Shelves got KOReader's own long-press dialog (fm.file_chooser:showFileDialog, after moving the browser underneath to the same folder), a "Move to shelf…" row added with fm:addFileDialogButtons("daf_move"), a Put-it-here bar after Cut/Copy, and Files ▾. canvas.lua C.watchFiles() wraps FileChooser.refreshPath, FileManager.cutFile/copyFile and onToggleSelectMode once, so a shelf redraws after KOReader's own file actions. Don't use KOReader's Menu widget for lists here: Project: Title patches Menu.init and a tap on a plain Menu crashed KOReader in the simulator; ButtonDialog with rows_per_page works.
- Project: Title lays the file browser out again after the plugins register, leaving a second FileManagerMenu with no plugins as fm.menu (the browser itself still opens the first). canvas.lua C.fileMenu() finds the one with the plugins and gives the empty one the same list, so the menu from Home is complete.
- readerprefs.lua puts the global settings KOReader only builds inside a book (status_bar, page_turns, follow_links, long_press, translation_settings, fulltext_search_settings) into the file browser's menu: each reader module's addToMainMenu runs on a stand-in for an open EPUB, with redraws as no-ops, and every callback is wrapped so an error shows a message. Placed by editing the cached ui/elements/filemanager_menu_order table once. Tested by walking every item and callback in the simulator (scratchpad walk.lua, ~1,600 calls, no errors).
- **Covers (2026-10-21), covers.lua.** Shelves used to make every missing cover by opening the book with FileManagerBookInfo:getCoverImage (crengine for EPUB, MuPDF for CBZ/PDF) on the main thread, one per tick, keyed by exact size, so Home, Lately and the shelf grid each opened a book again. Now a size that isn't cached is cut from, in order: a custom cover (DocSettings:findCustomCoverFile), the book's master (<md5>.jpg, ≤600 px tall at 1236 px wide), Project: Title's settings/PT_bookinfo_cache.sqlite3, then CoverBrowser's settings/bookinfo_cache.sqlite3 when its picture is at least 90% of the height asked for (its covers are mosaic-sized). Both databases are opened read only (`SQ3.open(path, "ro")`), looked up by directory + filename, then by filename alone when exactly one row has it (a book moved since it was indexed), and closed after 8 quiet seconds. Only when none of those has a cover is the book opened, and never in KOReader's own process: up to 8 at a time go to a child process (ffiutil.runInSubProcess, like Project: Title's own extraction, crengine cache in cache/daf-covers-cr3, purged after), which writes the sizes asked for and the master. The parent checks every 0.5 s and redraws the places waiting (Canvas:coverReady). A child stuck 90 s on a book is killed; a book that stopped a child leaves <md5>.try and gets <md5>.none next time. To make a book try again, delete its .none.
- The cache is cache/daf-home: gray JPEGs (turbojpeg TJPF_GRAY, quality 88) named <md5>_<w>x<h>.jpg, the masters, .none markers, and keys.lua (file → size, mtime, partial md5, so util.partialMD5 runs once per file version). The key is the file's partial md5, which follows a book to another shelf. The first run of this version (no .v2 file) empties the folder of the old PNGs. C.bookInfo now carries key (the md5 now) next to md5 (the one in the notes); C.isPrivate checks both, so a private book never opened on the Kindle is caught too.
- **The library pass:** Daf:coversAhead runs 3 s after Home shows. It walks the home folder (six deep) and makes each book's shelf-size cover (Shelf.usualCoverSize: the grid with no Cut/Copy bar) in 30 ms slices 0.2 s apart, sending books with no quick cover to the child. While a book is open it checks back every 20 s. It deletes any cached file whose md5 is on the private list, and never makes one for a private book (checked by the file's md5 and by the md5 in its notes). The log says `[Daf] covers: library pass over N books in S s: M made, K to open` and `[Daf] covers: opened N books in S s`. A shelf page makes its covers inside layout while it has under 300 ms spent (none on a partial redraw, since only that region refreshes), the rest one per tick after it's up, then the next page's through Covers.ahead.
- Measured on the Kindle (a standalone luajit over SSH, reading only): a Project: Title cover takes about 4 ms to query, 5 ms to unzstd and 12 ms to scale and crop; writing it as PNG took 62 ms and as JPEG 6.5 ms, which is why the cache is JPEG; util.partialMD5 is 4 to 5 ms a book. In the simulator, the time to fully draw a shelf page with an empty cache went from 1,363 ms (6 manga) and 850 ms (6 EPUBs), with the screen frozen for each, to 34 and 45 ms when Project: Title has the covers; books nothing has a cover for still take that long, but in the child, with the UI loop free (0 ms delay measured); a page already cached draws in 23 to 28 ms, and the next page is ready before the swipe. The Kindle is about 7 to 10 times slower than the simulator on these steps.
- Querying the Kindle's sqlite files by hand: /var (and /tmp) is a 64 MB tmpfs that's nearly full, so anything needing a temp b-tree (GROUP BY, ORDER BY on a blob table) fails with "database or disk is full" unless you run `PRAGMA temp_store=MEMORY` first.
- **The KOReader simulator** is /srv/dev/koreader-emu (README there): KOReader v2025.04 headless at the PW11's size. Its home/plugins/daf.koplugin links to the working copy in /srv/dev/daf-phone/kindle; point its settings/daf.lua at a sandbox. `./emu.sh start --night --ui pt --touch-only`, `shot`, `tap`, `hook 'event DafHome'`. Never at live Daf. Since the server's October OS upgrade, Mesa's llvmpipe threads made every forked child in the simulator (Project: Title's indexing, the covers and download children) hang at exit; emu.sh now sets `LP_NUM_THREADS=0 MESA_SHADER_CACHE_DISABLE=true`. The Kindle never had the problem.


## The taste on stuffs (2026-10-22)

- **What it is:** a public demo at stuffs.tiresia.xyz/daf/ (a static folder, no server): the real web app from `web/`, running in the browser on a sample library, with screenshots and links around it. Source in `taste/`: the page (`index.html`, `taste.css`, `taste.js`, `shots/`), the demo layer (`taste/app/`) and the sample library (`taste/data/`). Rebuild with `python3 -I tools/build_taste.py /srv/docker/stuffs/site/daf`; it replaces that folder (only one it made itself, marked `.daf-taste`). The cover is `/srv/docker/stuffs/site/covers/daf.webp`.
- **How it runs with no server:** `taste/app/demo.js` is loaded before the app's scripts and stands in front of `fetch`: every `api/` call is answered in the browser from `demo-seed.js` (made by the build) and what the visitor does, kept in localStorage `daftaste.v1` (plus the app's own `daf.*` keys). A made-up reader's year is generated per day from a fixed seed, so Today, the week, the Year 30 grid, Stats and the book pages look lived in on any date. Calls it doesn't know answer "That needs Daf's own server, so it isn't in this demo". demo.js also catches `window.DafCore` as app.js makes it, so the sidebar is filtered and the server-only places get their "Not in the demo" page from the very first drawing (a page can draw before reader.js and the later scripts have run; wrapping `navExtra` afterwards once let Recovery through for a moment). `demo-ui.js` (after the classic scripts) adds About this demo (with Reset) and makes exports and downloads from the demo's own data. `demo.css` hides the controls that need the server (Ask, Define, Listen, Hardcover, the account and service cards).
- **What the build changes in the copy (never in `web/`):** absolute paths become relative (`'/api/x'` → `'api/x'`, `/style.css` → `style.css`), covers get a `.jpg` ending (static files in `app/api/cover/`), book.js's pages load `fonts/fonts.css` from the folder, `sw.js`, `pdfview.js` (and pdf.js), `recovery.js`, the manifest and the Recovery line of What's new are left out, and the copy of foliate-js's paginator doesn't lay out a section that is still loading. That last one is a race the live app has too: a resize while a book's section loads (the Kindle notice appearing, the panel opening) runs `render()` before the new `<body>` exists and throws `Cannot destructure property 'style' of 'el' as it is null` (harmless; the load lays it out a moment later). Recovery never appears in the taste. If `index.html` or one of those lines changes shape, the build stops and says which; a new `/api/` call simply answers "not in this demo" until `demo.js` learns it.
- **The sample library:** four Project Gutenberg EPUBs kept as Gutenberg made them in `taste/data/books` (Meditations tr. Casaubon #2680, Walden #205, Pride and Prejudice #1342, The Odyssey tr. Butler #1727), covers made for the demo, three public-domain essays as Daf blocks in `articles.json` (Bacon, Lamb, Schopenhauer tr. Saunders), and made-up highlights, places and notes in `books.json`. The build checks every highlight against its book or essay and stops if one isn't found. Nothing from the real state, the vault or the library goes in, ever.
- **The docs' screenshots** (docs/images) are taken from the same sample library: `python3 -I tools/docs_shots.py [--only hero-light,feed,...]` makes a `--docs` build (it adds `taste/data/docs.json`, a made-up Feed, Torah shelf and Hardcover status, keeps the whole sidebar except Recovery and drops the demo's notes; the build refuses to put it on stuffs), serves it on 127.0.0.1, shoots each screen in Chrome for Testing and frames it like the old ones (same names, sizes, rounded window and shadow; the three phones in their frames). Today is shot in a time zone where it's evening, so it has three sittings (41 of 60 minutes). It fails on any page error, or if Recovery ever shows. appearance.png, torah.png and torah-dark.png aren't retaken there.
- **Checks:** load each screen in light, dark and at 390 px with no page errors, and confirm in the network log that nothing is asked outside `/daf/`. The landing page's screenshots (`taste/shots/`) are taken from the demo; Cloudflare keeps pictures a day, so a replaced one needs a new file name.

## Instagram reels (`daf/social.py`, `web/social.js`, 2026-10-25)

- **Saving:** an instagram.com `/reel/`, `/reels/`, `/p/` or `/tv/` link is a video doc (`karakeep.kind_of`), stored under its canonical address `https://www.instagram.com/reel/<code>/` (or `/p/<code>/`) so a re-share with `?igsh=` finds the same doc. `pages.save_page` queues the **reel** job instead of the page job. The web route ignores the extension's page snapshot for a reel. `POST /api/save` (phone shares) now runs `reader.push_inbox` straight away when Daf keeps the Library, so a shared reel starts at once instead of at the next sync.
- **The reel job** (`social.fetch`): yt-dlp with the kept cookies (a temp copy, since yt-dlp writes its jar back), the best ≤1280 px video merged to mp4 (needs ffmpeg), at most 400 MB, into `STATE/media/<id>.mp4`. Then the picture (`pages.keep_thumb`), the caption as paragraphs, `@account` as author, then faster-whisper on the file for a "Transcript" heading and cue blocks. It also queues tags. `video_transcript` on a reel runs the same job. The sync's auto-captions skip instagram.com. `media.prune` → `social.prune` removes videos whose doc is gone.
- **Playing:** `GET /api/media/<id>` (signed in or a device; FileResponse answers Range, so it seeks). `get_doc` adds `reel`, `media`, `preparing`, `content_error`. `web/reader.js` `reelHead`/`startReel` wrap the `<video>` in the YouTube player's four methods, so the transcript, Clip and the keys work unchanged. The frame stands up (`.vframe.tall`) and turns to the video's own shape for square or wide posts.
- **The sign-in:** cookies in `STATE/instagram/cookies.txt` (Netscape format, 600, directory 700), never logged, never in the repo. kv `instagram` = {hash (sha256[:16] of sessionid), user, by, updated, expired}.
  - Routes: `GET/PUT /api/instagram` (status; `from_browser`), `POST /api/instagram/cookies` (signed in or any device: `{cookies:[…]}` or `{cookie_header:"a=1; b=2"}`, for the apps' sign-in), `DELETE /api/instagram/cookies`. For the extension: `GET/POST /api/web/instagram`, and the POST is 403 unless `settings.instagram.from_browser`.
  - On arrival, every reel without content is queued again (`social.WAITING`, which doesn't depend on failed jobs surviving the 14-day prune).
- **Lapses:** yt-dlp's login-ish errors ("login required", "rate-limit", "not available", "Failed to parse JSON", HTTP 401/403/429) are checked with `session_ok()`: a GET of /accounts/edit/ with the cookies, where a signed-out session lands on /accounts/login.
  - If the session really lapsed, kv `expired` is set and the job fails with `LOGIN_ERROR`, which the reel page, Preferences → Instagram and the Sources check (`check_instagram`, shown once a reel exists) all show.
  - Otherwise it's "deleted, or a private account?".
  - The same lapsed session sent again is answered `same` and nothing is retried.
- **The extension (0.6.0, "cookies" permission):** `syncInstagram()` in background.js runs on install and startup, when instagram.com's `sessionid` cookie changes, and when a page on instagram.com loads (content.js). It asks `/api/web/instagram` and POSTs instagram.com's cookies only when `want` and the hash differs, or Daf's is expired.
- **The apps** (to come, the native session): a "Sign in to Instagram" web view that posts `cookie_header` to `/api/instagram/cookies` with the device token.

## Adding books, and the Kindle's downloads (2026-10-25)

- **Matching** (`library.py`):
  - Calibre's `hardcover-book` identifier (CWA fills it for most books), a note's `hardcoverBookId` and `book_adds` give each row `books.hc_id`. Matching is by that id first, then by title.
  - `norm()` keeps a non-Latin title's own letters (Hebrew titles all used to normalize to "" and matched each other).
  - `slug()` hashes such a title for its vault id.
  - `hardcover.build_map` starts from `books.hc_id`, so 60 more Calibre books have Hardcover sync.
  - **rekey:** when a book's id changes (hc: → vault: → cal:), `library.rekey` moves its rows in BOOK_REFS, its ebook/paper sessions, its kindle_queue row and its nightstand slot. It's found by hc_id, vault_path or calibre_id.
- **Add a book** (`hardcover.find_books`, `hardcover.add_book`, `web/addbook.js`):
  - `GET /api/books/find?q=`: ISBN through editions, else Hardcover search sorted by readers. Each hit is annotated with the Daf book, whether it has a file, and its Hardcover status (cached shelves up to 6 h old).
  - `POST /api/books/add {hc_book_id, status 1|2|0, kindle_shelf?}`: `insert_user_book` (privacy 3 for a private title; Reading also starts a read) unless it's already on a shelf, then a `book_adds` row. `rebuild` shows that as `hc:<id>` until a note or Calibre has the hc id. The cover comes from Hardcover through `pages.keep_thumb`, via `/api/cover/hc:<id>`.
  - hardcover-sync makes the note. Its cron runs WITHOUT `--no-create` again since 10-25. Two notes on old ids were re-pointed first (The Gay Science → 442702, Primary Greatness → 447079), after a dry run showed they'd otherwise duplicate. Backups are in that session's scratchpad.
- **A book's file** (`bookfiles.py`):
  - `POST /api/books/<id>/file` (multipart: file, kindle_shelf, force) refuses a book Calibre has (by hc id, ISBN or title: 409 with its id). It writes ISBN and `hardcover-book:<id>` identifiers into an EPUB's OPF (OPF2 `opf:scheme`, OPF3 `urn:isbn:` / `hardcover-book:`) and puts it in `CWA_INGEST` as "Title - Author.ext" (hidden `.part` first). The row goes in `book_files`.
  - `settle()` (before each rebuild) finds the Calibre book it became among those added since: by hc id, ISBN or title. It sets `cal_id`, writes `hc_links`, and `overrides()` makes the chosen hc id win over CWA's.
  - It notes a file in CWA's `processed_books/failed`, or one still not in Calibre after 6 h.
  - Calibre-Web's `metadata_provider_hierarchy` now starts with hardcover (cwa.db `cwa_settings`, backup taken 10-25). It's read fresh for each import.
- **The Kindle's downloads** (`kindlequeue.py`): Syncthing is off on the Kindle, so the plugin fetches its files itself.
  - Table `kindle_queue`. Device routes: `GET /api/kindle/inbox`, `GET /api/kindle/inbox/<id>/file`, `POST /api/kindle/inbox/<id>/done {error?}`, `POST /api/kindle/shelves {shelves}` (stored in kv `kindle_shelves`).
  - User routes: `GET /api/kindle/shelves`, `POST|DELETE /api/books/<id>/kindle {shelf}`. Books are named "Title - Author (<calibre id>).epub", like the Kindle's own.
  - A book waiting for its file keeps `kindle_shelf` on book_files/book_adds, and `follow_up()` (end of rebuild) queues it once Calibre has it.
  - Send to Kindle's EPUBs are queued too (shelf "Daf").
  - **The plugin side** is kindle/daf.koplugin/inbox.lua, called from Daf:send after the pages, highlights and /api/kindle/home, so on every Wi-Fi sync (Wi-Fi coming on, a book closing, Home's refresh, Send now) except the one in onSuspend (`send(true, true)`), which shouldn't wait for downloads. It posts the home folder's top-level folders (no dot folders, no .sdr) to /api/kindle/shelves, then reads the inbox. An item already at `<home_dir>/<shelf>/<name>` with the same size is only marked done. A different file by that name, a name with a kind KOReader doesn't list (C.BOOK_EXT), a size over 210 MB, or less than 50 MB left after it (`util.diskUsage`) is reported as an error and not downloaded. Names and shelves have `\/:*?"<>|` and control characters taken out, and a leading dot is refused. Ids are percent-encoded.
  - The downloads run in a child process (ffiutil.runInSubProcess), one after another. Each streams to `.<name>.daf-part` in the shelf folder (made with util.makePath), stops past the size Daf gave, is checked against it, renamed, and reported done or with the reason. The parent checks the child every second, kills it after an hour, and when it's over refreshes the file browser and any shown Home or shelf (C.refreshShown), starts the covers pass (so the new books get covers) and shows "Daf put N books on your Kindle." The log says `[Daf] inbox: N of M files came in S s`. An item reported with {error} leaves the inbox until it's sent again (server side, d955ab0), so a broken connection (the download stopped, a non-200 answer, a short file) isn't reported: the item comes again on the next sync, and only its third failure in a row is reported. Settings keep `inbox_tries` {id → failures in a row}, pruned to what's still waiting.
  - Tested in the simulator against a sandbox on a fresh state: `DAF_STATE=<scratch> python -m daf.cli kindle-token sim`, tools/sandbox.py on a spare port, rows put straight into kindle_queue, and the simulator's settings/daf.lua pointed at it (and put back after).

## Vault notes with the full text (`daf/vaultnotes.py`, `daf/vaultmd.py`, 2026-10-25)

What I highlight or write a note on outside a book now lands in the vault the way Readwise's Obsidian export does it, text and all.

- **Which notes:** `write_article` makes a note for any document in `docs` (Feed, Library, imports, tweets, PDFs, videos, podcasts, reels, Torah readings) and for a podcast clip's `pod:` books row, once it has a highlight (sources `daf`, `clip`, `kindle`, `karakeep`) or a document note. Folders: `Reference/clippings`, `youtube`, `podcasts`, `torah`, and `instagram` for reels.
- **The head** is written once, for a new note: frontmatter `title`, `author` (one `"[[Name]]"` per person, affiliations after a comma dropped, none for Torah), `url`, `daf` (`<public_url>/#read/<id>`, or `#book/<id>` for a clip), `source`, `category` (article, video, podcast, reel, tweet, pdf, torah), `published`, `saved`, `words`, `cover` (YouTube's, or a picture on the web), `categories` (`[[Clippings]]`, `[[Youtube Clippings]]`, `[[Podcast episodes]]` with `show`, which is what the vault's Bases filter on), `tags`, `datasource: daf`; then `#ai-assisted-note` and the title. Never `created`/`updated` (Obsidian adds those, the linter strips them) or the keys hardcover-sync and koreader-merge own (`NOT_DAFS`). After that only the `daf:` line changes, when a Feed item moves to the Library.
- **The region** (`<!-- daf -->` … `<!-- daf-end -->`): Source/Author/Published lines and an "In Daf" link (Source and Published left out when an older Daf's `## Data` head already says them), `## Notes` (the document note, ending `^daf-note`), `## Highlights` (quote, then `([[#^daf-b<block>|in the text]])` or the time or verse as the label, tags, the note, `^daf-h<id>`), and the text under `## Full text`, `## Transcript`, `## Show notes` (a podcast's), or `## Caption` + `## Transcript` (a reel's).
- **The text** (`vaultmd.Doc`): blocks → Markdown, h2/h3 → `###`/`####` (no bold inside), lists, quotes, pictures by address, PDF page marks, cues with `[m:ss](youtube…&t=Ns)` or `**m:ss**` and the speaker, verses as `**n** Hebrew` + English. Plain text is escaped so a `#`, `$`, `[[`, `==`, `^` or a leading `1.` in an article never becomes a tag, math, a link, a mark, a block id or a list. Highlights are placed by `pos` (b/s/e/be) when the words there still match (offsets counted without whitespace, since the reader counts over the page and the Kindle over the block's plain text), otherwise by their words (`pre` picks between repeats; long Kindle quotes by their ends). Marked words get `==…==` (trimmed off punctuation that would stop the mark closing), and each highlighted block gets `^daf-b<i>`. Past `FULL_TEXT_MAX` (150,000 characters), only highlighted blocks follow, with "…" between and a link to Daf.
- **Only Daf's own notes** (frontmatter `datasource: daf`) get the text. A Readwise note, a vault essay (`ve:`) or a karakeep-sync note (`Reference/karakeep`, linked by its `id:` for a `kk:` document that has no note yet) only gets highlights, without its `karakeep`-source ones and without a document note it already contains. A note Daf never wrote in doesn't get an empty region.
- **Vault wins**, as in book notes: an edited highlight note (`review_state.vault_hash`) or document note (kv `vault_note:<doc>`) is taken back into Daf before rewriting. Only the part above the text is read for that.
- **When:** every highlight change (`write_for`), a document note, an import (also a link's own note: Raindrop's `note`, a CSV's `note`/`notes`), `save_to_library` (the note follows, its `vault_path` carried over even when the Library copy had a books row), and after a `reel`, `captions`, `whisper`, `pdf` or `page` job (`vaultnotes.refresh`), so text that comes later fills the note in.
- **Backfill:** `daf vault-backfill --dry-run DIR` copies each affected note to DIR as it would be and rolls the database back; without it, it rewrites for real. It covers notes Daf made (`datasource: daf`), links Karakeep-era documents to their karakeep-sync note, and makes notes for documents that have highlights or a note and never got one. An older Daf's note keeps its head; the keys it lacks are added at the end of its frontmatter, and nothing already there changes.

