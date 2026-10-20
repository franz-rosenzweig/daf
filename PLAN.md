# Daf — build plan

*Written 2026-10-09.*

**Status (2026-10-09 evening):** Phases 0–4 built and running; the Kindle plugin is installed and
reporting. HTTPS (for installing the app and the share menu) waits on one sudo command. Phase 2's "done when" (seven mornings of review in a row) starts with the first
05:32 message. Operating notes are in [docs/OPERATIONS.md](docs/OPERATIONS.md).


## What Daf is for

One goal: **read at least an hour a day in Year 30** (2026-10-09 → 2027-10-08).
Year 29 was 65 hours on 185 days; twelve days reached the hour.

Daf is a personal Readwise. It gathers reading from the apps Nathan already uses, counts the
time, brings old highlights back each morning, and writes highlights and notes into the
Obsidian vault. It reads articles, feeds and video transcripts itself. Books stay on the
Kindle, audiobooks in Audiobookshelf, podcasts in AntennaPod.

## Decisions already made

| Decision | Detail |
|---|---|
| Look | "Shelf × Reader": Readwise Reader's three-column layout in Things-style lists, teal accent, yellow highlights. The demo is the spec. |
| Counts toward the hour | Kindle books, audiobooks, articles read in Daf, paper books. **Not** podcasts. Videos off by default. |
| Readers stay where they are | KOReader on the Kindle for books, Audiobookshelf for audiobooks, AntennaPod for podcasts. Daf reads articles, feeds and videos. |
| Feed vs Library | Feed = FreshRSS (passes by). Library = what you keep: Karakeep for articles, videos, tweets and PDFs; Calibre for books. |
| Ask | Stays. Claude on the subscription, answering from the document and Nathan's highlights. |
| File over app | The vault holds every highlight, note and hand-logged minute. Daf's database is an index plus review state, rebuildable from the sources and the vault. |
| Sources stay in charge | Daf never deletes anything in FreshRSS, Karakeep, Calibre, Audiobookshelf or the vault. |
| Hardcover | `hardcover-sync.py` stays the only writer to Hardcover. Daf never touches `rating`, `status`, `read`, `consuming` or `progress`. |
| Privacy | Books on the private list are never named on the Kindle sleep screen, the phone widget or the morning message. |

## What already exists and gets reused

| Piece | Where | Daf uses it for |
|---|---|---|
| KOReader → vault highlights | `.claude/scripts/koreader-sync.sh`, `koreader-parse.py`, `koreader-merge.py` (cron, every 10 min) | Book highlights. Keeps running; Daf reads them, never rewrites that region. |
| KoInsight | `/srv/docker/koinsight/prod.sqlite3` (`page_stat`, `annotation`) | Year 29 history and early reading time, read-only. |
| Calibre libraries | `/srv/docker/cwa-library/metadata.db` (245), `cwa-libros` (181) | Book metadata and covers, read-only. |
| Audiobookshelf | `/srv/docker/audiobookshelf/config/absdatabase.sqlite` | Listening time, progress, bookmarks, read-only (same way `audiobookshelf-sync.py` reads it). |
| FreshRSS | `freshrss` container, Google Reader API enabled | The Feed: items, folders, read state. |
| Karakeep | `docker-web-1`, keep.tiresia.xyz, REST API + Meilisearch | The Library: saving, archived text, highlights, search. |
| Vault helpers | `.claude/scripts/vault_notes.py`, `MEDIA-SYNC.md` | Note walking, frontmatter surgery, the one-writer-per-field rules. |
| Reading CLI | `/srv/office/bin/read-cli.py` (feeds, saved, books, highlights) | Starting point for the source adapters. |
| Transcription | `/srv/office/bin/transcribe` (faster-whisper small, CPU) | Podcast and video transcripts, voice notes. |
| Claude runner | `/srv/office` runner used by `office-bot.py` | Ask. |
| Ezer | `.claude/scripts/signal-bot.py` (cron, every minute; calls CLIs) | "read 40 paper", voice notes, the morning highlight. |
| Kokoro | `kokoro-tts` on network `openreader_default`, port 8880 | Read-aloud. |
| Desk | `/srv/docker/desk` collectors | A Reading card fed by `daf today --json`. |
| Tasker on the S24 | Already reports app use to ActivityWatch | The evening "read instead?" nudge. |
| Deploy pattern | Dvarim and Moshe: compose service, `tools/autodeploy.sh`, worktree | Same setup for Daf. |

## Architecture

```
 Kindle (KOReader)          Phone (S24)                 Mac / desk browser
  daf.koplugin               PWA + widget + Tasker       PWA
  sleep screen patch              │                          │
        │ Tailscale               └──────────┬───────────────┘
        ▼                                    ▼
 ┌──────────────────────── daf (container, :8440) ─────────────────────────┐
 │  API + web app · source adapters · review scheduler · vault writer      │
 │  SQLite index /srv/docker/daf/daf.db (rebuildable)                      │
 └───────┬──────────────┬───────────────┬───────────────┬──────────────────┘
         │              │               │               │
   FreshRSS API   Karakeep API   read-only SQLite:    vault (rw, owned
   Kokoro TTS     gpodder API    Calibre, ABS,        regions only)
                  (for AntennaPod) KoInsight
         │
 daf-worker (container): yt-dlp captions, faster-whisper, tesseract eng+heb
 daf-ask (host, user systemd unit): Claude through the /srv/office runner
 daf CLI (host): what Ezer and the desk call
```

**Stack (as built).** Python 3.12 + FastAPI + SQLite, running directly on morten as the
systemd user service `daf.service`, not in a container: everything Daf talks to is on the
host (the Kindle stats, Audiobookshelf's database, the transcriber, Claude, signal-cli, the
vault), and a container would only add mounts and read-only-SQLite problems. The web app is
plain JavaScript and CSS served by the same process, with no build step (the clickable demo
was written the same way). Heavier tools come in as containers only if a later phase needs
something the host can't install without sudo (tesseract for Phase 7).

**Where things live:**

| | |
|---|---|
| `/srv/dev/daf` | the code, run in place (`.venv` inside) |
| `/srv/docker/daf` | `daf.db` (rebuildable index), `auth.json`, `settings.json`, `kindle-token` |
| `~/.config/systemd/user/daf.service` | the service (copy in `systemd/`) |
| Port | 8440 on 127.0.0.1 and on the Tailscale IP (both bind at boot: `ip_nonlocal_bind=1`) |
| Repo | `franz-rosenzweig/daf`, public under GPL-3.0 since 2026-10-20; the history before that is in the private `franz-rosenzweig/old-daf` |

## The vault contract

Same three rules as `MEDIA-SYNC.md`: own a named set of fields, never lower anything, find
notes by frontmatter `type:` and never by a fixed path.

| Note | Where | What Daf owns |
|---|---|---|
| Book notes | `Reference/books/📚 Title (Author - date).md` | Only the region between `<!-- daf-highlights -->` and `<!-- daf-end -->`, for highlights that don't come from KOReader (audiobook bookmarks, paper pages, voice notes). The `<!-- koreader-highlights -->` region stays `koreader-merge.py`'s. |
| Articles | `Reference/clippings/` | New notes in the format already there (frontmatter `tags: [clippings]`, `datasource: clippings`; `## Data`, `**Notes:**`, `## Highlights`), so Readwise-era clippings and Daf ones look alike. |
| Videos | `Reference/youtube/` | New notes in the Web Clipper format already used there, plus `## Highlights` with timestamps. |
| Reading log | `Reference/reading/2026.md` (new) | One line per hand-logged session (paper, Shabbat). These minutes exist nowhere else, so they live in the vault. |

Each highlight carries a block id (`^daf-7f3a`). When Nathan edits a note's text in Obsidian,
the vault wins: Daf reads the region back before writing and keeps his text.

## Phases

Each phase ships something usable on its own. A phase is "done" when it has been in daily
use for a week, and the next one starts after that.

### Phase 0 — Groundwork (1 evening) · DONE 2026-10-09
- Service, port, state folder, auth (one password, signed cookie; device tokens for the Kindle).
- FreshRSS API password and Karakeep API key wait for the phases that use them; Kokoro answers
  from the host on its container IP.
- Source adapters that only read, with a `daf doctor` command that shows each source and
  its last answer.
- Book identity: one book = one Calibre id, even when the Kindle holds two copies or
  editions. Progress comes from the newest session in the copy being read. *(Moved to
  Phase 2, where highlights and the nightstand need it; Phase 1 only counts minutes.)*
- **Done when:** `daf doctor` is green for all sources.

### Phase 1 — The hour (2–3 evenings) · BUILT 2026-10-09
- Reading time from the Kindle, Audiobookshelf and paper, stored as sessions in UTC.
- Kindle: a small KOReader plugin sends new reading sessions to Daf when the Kindle goes to
  sleep, and queues them while offline. Until it exists, KoInsight's database is the
  fallback.
- **Kindle sleep screen:** a KOReader user patch shows today's minutes from the Kindle's own
  stats database (works offline), plus Daf's total for the day when it last had Wi-Fi.
- Today page: the ring, the per-source breakdown, Year 30 (365 days) with Year 29 behind it.
- Ezer: "read 40 paper" and "shabbat 60" log minutes to the right day and the vault reading
  log.
- Desk: Reading card from `daf today --json`.
- **Done when:** a Kindle session shows on Today and on the sleep screen with nothing
  touched by hand.

### Phase 2 — Highlights and review (3 evenings) · BUILT 2026-10-09
- One highlight index across KOReader, Karakeep and Audiobookshelf bookmarks.
- Daily review: five highlights a day, spaced repetition (kept ones come back less often),
  Keep / Note / Less.
- Morning message: Ezer sends the first highlight with the 05:30 reading, Sunday to Friday.
  A reply becomes a note.
- **Voice notes while reading:** a voice note to Ezer is transcribed and filed under the
  book open on the Kindle, at the current page.
- The vault writer and its owned region.
- Nightstand: three books. Starting a fourth asks which one steps off.
- **Done when:** the morning review has run seven days in a row.

### Phase 3 — The phone (2 evenings) · BUILT 2026-10-09 (server side; widget brief in `android/NEXT.md`; HTTPS waits on `sudo tailscale set --operator=lander`)
- PWA installed on the S24: Today, Review, Nightstand.
- Tasker nudge: opening Instagram, Reddit, X or Discord after 21:00 shows one highlight and
  the minutes left today. It doesn't block anything. On by default, easy to turn off.
- Android shell with a home-screen widget (today's ring, one highlight) and a share target
  ("Save to Daf" goes to Karakeep). The Mac session builds it from `android/NEXT.md`, like
  Dvarim's.
- **Done when:** the widget and nudge have been live for a week.

### Phase 4 — The reader (5–7 evenings) · BUILT 2026-10-09 (Daf keeps its own highlights on Karakeep items; pushing them into Karakeep's reader was dropped, since its offsets don't match; offline reading added in the polish pass, and it needs the HTTPS address, since service workers only run on secure origins)
- Feed from FreshRSS: folders, Unseen/Seen, read state synced back.
- **Feed expiry:** anything unseen for 14 days moves to Seen, so the 2,382 never becomes a
  pile.
- Library from Karakeep: Articles, Tweets, PDFs (list now, reader later), Inbox/Later/Archive.
- Reading view: contents, focus bar, highlight with selection or `h`, notes, tags, the Aa menu,
  keyboard shortcuts, progress.
- Save to Library (Feed → Karakeep). Highlights also go to Karakeep through its API.
- Read-aloud through Kokoro, following along by paragraph.
- Ask through `daf-ask` on the host.
- Article minutes count toward the hour.
- Offline reading on the phone for saved items.
- **Done when:** a week of feed reading happens in Daf instead of Read You.

### Phase 5 — Watch and listen (3 evenings) · BUILT 2026-10-09 (playback is YouTube's privacy-mode embed, since Invidious can't stream here; the AntennaPod share-position test on the S24 is Nathan's)
- Videos: captions with yt-dlp, faster-whisper when there are none. Transcript beside the
  player, chapters, timestamped highlights, Clip 30s. Playback through Invidious.
- AntennaPod: Daf speaks the small gpodder sync API, so subscriptions and positions arrive
  without new habits. A "share with position" from AntennaPod becomes a transcribed clip.
  (Test the old share-position bug, AntennaPod #2012, on the S24 first.) Podcasts never count
  toward the hour.
- Audiobookshelf bookmarks: the minute before each bookmark gets transcribed into a highlight.
- **Done when:** one clip from each source is in the vault.

### Phase 6 — Daf on the Kindle (2–3 evenings) · BUILT 2026-10-09 (installed; loads on the next KOReader restart)
- The KOReader plugin grows a screen: today's ring, the review with page-turn buttons,
  the nightstand, opening a book from it. Black and white, as on the canvas.
- Same safety rules as the existing patches: no edits to `settings.reader.lua` while
  KOReader runs; only user patches and the plugin.
- **Done when:** a morning review happens on the Kindle.

### Phase 7 — Paper and Torah (3 evenings) · BUILT 2026-10-09 (OCR through the Claude CLI, not a separate OCR engine; lookup is a selection-bar button, which is the long-press on the phone)
- **Paper pages:** after Shabbat, photograph a marked page (Signal to Ezer, or the share
  target), OCR it in English or Hebrew, choose the lines, and they become highlights in that
  book's note.
- **Torah shelf:** the week's parasha from the Ruach feeds, texts from Sefaria, highlights
  and notes on them like anything else.
- **Lookup:** long-press a word for a definition or Hebrew↔English.
- **Done when:** one Shabbat's paper pages are in the vault.

### Added 2026-10-09: books in Daf
An EPUB reader for the whole Calibre library (foliate-js), in the reading view, with Kindle hand-off,
highlights into review and the vault, footnote popovers, Kokoro read-aloud, and reading time counted.
Ideas taken from BookOrbit's reader (time left in the chapter, wake lock, resume toast, jump box, next in
series); its kosync/two-way KOReader sync, highlight colors and stats dashboard were left for later.

### Phase 8 — Later, when wanted · PARTLY BUILT 2026-10-09: PDFs (text reflowed from the file, "Pages" opens the original), tweet threads, vault search in ⌘K, the vault's Covenant & Conversation essays on the Torah shelf, `POST /api/save` for devices, and the Mac brief in `mac/NEXT.md`. Not built: newsletters (needs a "Newsletters" label in Proton first; Substack already arrives through FreshRSS) and BookOrbit (no trial yet)
- PDF reader (pdf.js) and tweet threads.
- Newsletters: a Proton label read through the bridge, shown in the Feed.
- Mac shell (quick save, menu-bar minutes).
- Search across the vault from ⌘K.
- BookOrbit, if the trial says yes (below).

## Traps already known

- **Two copies of one book.** The Kites has two copies on the Kindle. One 605-page copy
  read to its last page by 2026-07-21, then a 562-page copy opened at page 178, at page
  348 (62%) on Aug 29. Never compute progress across editions or copies.
- **Syncthing duplicates.** `.sdr` folders get duplicated and `sync-conflict` files appear.
  Ignore conflict files and trust the newest session.
- **KOReader rewrites its settings on exit.** Use user patches and the plugin, never live
  edits.
- **Hardcover's conflict detector.** A new writer on its fields reads as Nathan's edit and
  gets pushed up. Daf stays off those fields.
- **Redeploys need `up -d --build`.** Autodeploy refuses a dirty tree.
- **Tailscale-IP binds stay down after a reboot.** A plain `docker start` gives no ports;
  recreate (see the reboot memory).
- **Morten's IPv6 to Cloudflare is dead.** Test public hostnames with `curl -4`.
- **No Node and no sudo on the host.** Builds in `node:22`, tools in containers.
- **Which day a session belongs to.** Nathan lives between Phoenix and Jerusalem. Store
  sessions in UTC and count days in a "home time zone" setting. Shabbat minutes logged after
  havdalah belong to Saturday.
- **FreshRSS's database is www-data only.** Use the API, not the file.

## Questions for Nathan

1. **BookOrbit:** Daf doesn't need it. Its value would be two-way KOReader sync and a web
   EPUB reader. Recommendation: skip until Phase 4 is done, then decide.
2. **Hostname:** Tailscale only (recommended), or also `daf.tiresia.xyz` through cloudflared
   for use without Tailscale?
3. **Home time zone:** switch it by hand when traveling, or follow the phone?
4. **The morning message:** fold the highlight into the 05:30 reading, or send it separately?
5. **Pace:** keep the "a phase starts after a week of daily use" rule? An optional extra:
   each phase also waits for a reading milestone (Phase 2 after 10 hours read in Year 30,
   Phase 4 after 30, Phase 6 after 60).
