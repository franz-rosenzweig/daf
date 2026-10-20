# Daf for macOS and Android: the brief

For the Claude session on Nathan's Mac that builds native shells. It built Dvarim's and
Moshe's (`franz-rosenzweig/dvarim`, `franz-rosenzweig/moshe`, both private, both Nathan's),
and this round should reuse what worked there. Written on morten, where Daf runs.
Replaces the two small briefs that were in `mac/NEXT.md` and `android/NEXT.md`; their specs
(the menu-bar minutes, the home-screen widget) are folded in below.

## What Daf is, and how it differs from Dvarim and Moshe

Daf is Nathan's reading app for "Year 30": an hour of reading a day, from 2026-10-09 to
2027-10-08. Readwise Reader is the model for the look and the reading
experience. It brings together:

- Kindle reading time and highlights (KOReader, with a Daf plugin);
- audiobooks (Audiobookshelf);
- Calibre books, read in Daf's own EPUB reader (foliate-js);
- articles, videos and tweets (Karakeep), and the Feed (FreshRSS);
- paper books (minutes logged by hand, photos of marked pages turned into highlights);
- a Torah shelf, a daily highlight review, stats, and an Obsidian vault it writes into.

**The big difference: Daf is server-first.** Dvarim and Moshe are "file over app": the engine
runs in the page, and the shell hands it a folder. Daf has no folder and no engine to bundle.
It's a FastAPI app with SQLite on morten that reads all those sources, so:

- **The shells load the live site.** They don't bundle the page and don't need the folder
  bridge (`BRIDGE.md` in the other two repos). What they add is a proper window, the things
  a web page can't do, and small always-visible surfaces (menu bar, widget).
- **Base URL `https://daf.tiresia.xyz`** (Cloudflare tunnel; username + password sign-in).
  The tailnet address `http://100.91.202.11:8440` also works, but it needs an ATS exception
  on the Mac and cleartext permission on Android. Make the base URL a setting, with the
  https one as the default.

## The web app the shells wrap

Everything is in this repo (`franz-rosenzweig/daf`):

- `daf/`: the Python server.
- `web/`: vanilla JS, **no build step**: `app.js`, `hl.js`, `reader.js`, `book.js` (an ES
  module, foliate-js in `web/vendor`), `paper.js`, `torah.js`, `stats.js`, `style.css`, `sw.js`.
- `docs/OPERATIONS.md`: how it runs. `PLAN.md`: the phases and decisions.

**Routes are hash routes,** so the history works and native Back can call `history.back()`:
`#today`, `#review`, `#stats`, `#library`, `#feed`, `#read/<doc>`, `#ebook/<book>`,
`#highlights`, `#books`, `#book/<id>`, `#torah`, `#paper`, `#prefs`. `#…/hl:<id>` opens a
highlight at its exact spot.

**Sign-in in the WebView** is the page's own form. It sets a cookie named `daf` (Secure on
https). Keep the default website data store so the cookie survives restarts.

**Native surfaces use device tokens,** never the cookie: `Authorization: Bearer <token>`. Nathan
makes one in Preferences → Phone → Make a token, or on morten with
`/srv/dev/daf/bin/daf kindle-token <name>` (printed once). Keep it in the Keychain on the Mac
and in EncryptedSharedPreferences on Android.

| Endpoint (device token) | What it gives |
| --- | --- |
| `GET /api/phone/widget` | `{date, minutes, goal, year_day, year_hours, highlight: {text, title}, nightstand: [{id, title, progress}]}`. Private books never appear by name. |
| `POST /api/save` `{url, title?, text?}` | Saves a link to the Library (through Karakeep on the next sync). |
| `GET /api/phone/nudge?app_name=<pkg>` | Asks whether to nudge right now. The server decides: at most one every 25 minutes, none once the hour is done. Answers `{show, title, text, url, minutes_left}`. |

Web-only (cookie): `POST /share` (multipart: `url`/`title`/`text`, or `photo` files that become
paper pages). It's the PWA's share target, and fine to reuse from a WebView.

**Things the page does that a WebView needs help with:**

- Downloads: `<a download>` links (highlight exports at `/api/highlights/export?fmt=md|csv|json…`,
  `/api/ebooks/<id>/file`) and blob URLs. On the Mac, `WKDownloadDelegate` with a save panel;
  on Android, a `DownloadListener` and the create-document screen.
- Share as image: `hl.js` makes a PNG on a canvas, then tries `navigator.share({files})` and
  `ClipboardItem`. Neither is dependable in a WebView, so give the page a native share (below).
- Listen: Kokoro read-aloud via `new Audio(blob)`. The Mac is fine. On Android it stops when
  the screen goes off, so it needs native playback (round 3).
- Reading time counts only while the page is visible and active, by `document.visibilityState`
  and input. Make sure a minimized or hidden window reports `hidden`, or Daf counts minutes
  nobody read.
- Service worker: the page registers `/sw.js` for offline. Check it behaves in WKWebView and
  Android WebView. If it doesn't, skip it in shells (see `web/shell.js` below).
- The book reader puts foliate-js in iframes with blob URLs, and fonts come from Google Fonts.
  Test a long EPUB early in WebKit; Daf was built and tested in Chromium.

## The contract, and who touches what

Write `docs/SHELL.md` first: the contract between page and shell, the way `BRIDGE.md` is for
Dvarim and Moshe. Keep it short. It should cover:

- **User agent:** append `Daf/<version> (macOS shell)` or `Daf/<version> (Android shell)`.
- **`window.dafShell` (the page calls it):** `share({text?, url?, png?})`,
  `download(url | {name, mime, base64})`, `openExternal(url)`, `notify({title, text, route})`.
  A capability list, so the page falls back to web behavior when an op is missing.
- **`window.dafCommand(name)` (the shell calls it):** for the menus. Names like `go:today`,
  `go:review`, `search`, `toc`, `panel`, `aa`, `listen`, `highlight`, `bookmark`, `back`.
  Plus `window.dafState()` → `{route, title, minutes, goal, canHighlight, …}`, so menus can be
  ticked and greyed.
- **`window.dafBack()`:** true if the page went back (it closed a sheet or popover, or moved
  back in history); false when there's nowhere to go.

**Page-side code goes in a new file, `web/shell.js`,** loaded by `index.html` and doing nothing
unless the shell user agent is present. That way the shells' work doesn't collide with mine.
The morten session is changing `app.js`, `hl.js`, `reader.js`, `book.js` and `style.css`
right now. If something has to change in one of those, keep it small, say so in the PR,
and give Nathan a heads-up to pass on. Native code lives in `mac/` and `android/`. One
branch and one PR per piece.

**Deploying:** daf.service on morten serves `web/` straight from `/srv/dev/daf`, so a merged
change to `web/` is live once morten pulls master. Python changes also need
`systemctl --user restart daf`. There's no autodeploy for Daf yet, so tell Nathan when
something merges and the morten session will pull it.

## Round 1: Daf for macOS

Start from Moshe's `mac/` (SwiftUI with an AppKit window, `project.yml` for XcodeGen,
`build.sh`, `selftest.sh`), renamed to `xyz.tiresia.daf`. macOS 13+.

- **The window:** a WKWebView on the base URL, styled like Readwise Reader's Mac app.
  - The page runs to the top edge under a transparent title bar, and the traffic lights sit
    in the sidebar's top-left. The page leaves room for them when it sees the macOS shell
    user agent: a `shell-mac` class from `web/shell.js`.
  - Dragging an empty part of the top bar moves the window.
  - The frame is remembered; minimum 900 × 600.
  - Only Daf loads in the window. Any other address opens in the browser.
- **Menus:** File (Save a link…, Log paper minutes…, Export highlights…),
  View (Today ⌘1, Review ⌘2, Library ⌘3, Feed ⌘4, Highlights ⌘5, Books ⌘6, Stats ⌘7,
  Contents, Side panel, Typography), Go (Back ⌘[, Search ⌘K), Reader (Highlight, Note,
  Bookmark, Listen). Each item calls `window.dafCommand`. The page hears keys first, the
  way Moshe does it.
- **Menu-bar extra** (`MenuBarExtra`):
  - The title is today's minutes: `38′`, or `60′ ✓` once the hour is done.
  - The menu shows the ring with "38 of 60 minutes today · Year 30, day N", then the day's
    highlight (serif, 4 lines) with its book, then Open Daf, Review, and Settings… (base URL
    and token).
  - Data from `/api/phone/widget`: poll every 5 minutes while awake and on wake, and keep the
    last answer when offline.
- **Share extension:** "Save to Daf" for links in the macOS share menu, through `POST /api/save`.
- **Notifications:** none in round 1. The morning highlight already comes through Signal (Ezer).
- **Done when:**
  - Nathan reads a whole evening in the Mac app: an article, a book chapter with highlights,
    and the review.
  - The minutes sit in the menu bar.
  - One link is saved from Safari's share menu.

## Round 2: Daf for Android

Start from Dvarim's `android/shell` and Moshe's `android/` (WebView, `release.sh`, keystore),
renamed to `xyz.tiresia.daf`. Test on his S24+.

- **The app:** a WebView on the base URL.
  - Back goes through `window.dafBack()` first.
  - The keyboard resizes the window (`adjustResize` plus insets).
  - Only Daf loads in the window.
  - In the book reader (`#ebook/…`), the **volume keys turn pages**: call the page's
    `dafCommand('next')`/`('prev')`. Nobody gets this from a browser.
- **Share into Daf:**
  - Links go to `POST /api/save`.
  - Photos go to `POST /share` as `photo`; they become paper pages for OCR.
  - Plain text with a URL in it counts as a link.
- **Home-screen widget** (the point of the app: the hour in sight on the first screen, where
  Instagram and Reddit are now):
  - 2×2: a ring (`minutes` of `goal`) with the number in the middle and "Year 30 · day N"
    under it.
  - 4×2: the ring on the left. On the right, the highlight in a serif face (3 lines) and the
    book title, or "That's the hour." once `minutes >= goal`.
  - Material You colors, following the system theme.
  - Refresh with WorkManager every 30 minutes, and on `ACTION_USER_PRESENT` at most every
    10 minutes. On failure keep the last numbers and dim them.
  - Tapping the ring opens `#today`; tapping the highlight opens `#review`.
- **The evening nudge, natively:** this replaces the Tasker setup that's still sitting in
  Preferences → Phone.
  - With Usage Access granted, watch for Instagram, Reddit, X or Discord coming to the
    front between 21:00 and 03:00.
  - Ask `GET /api/phone/nudge?app_name=<package>` and, if `show`, post a notification
    (`title`, `text`) that opens `url`.
  - The server keeps the rules and counts what was shown and followed.
  - Make it a switch in the app's settings, off until Nathan turns it on.
- **App shortcuts** (long-press the icon): Review, Continue reading (the first nightstand
  book, `#ebook/<id>`), Log paper.
- **Done when:**
  - The 4×2 widget sits on the S24's first screen and refreshes on its own.
  - A link and a photo were shared in.
  - The volume keys turn pages.
  - Build steps are in `android/README.md`, the way Dvarim's are.

## Round 3, after Nathan has used both for a week

- Listen with the screen off on Android: a media session and a foreground service playing
  Daf's Kokoro paragraphs. The page hands over the paragraph texts, or the shell asks
  `/api/tts/text` itself.
- Offline reading for books on the phone (cache the EPUB and the position).
- Anything Nathan asks for after living with it.

## Rules carried over from Dvarim and Moshe

- **Interface copy:**
  - Plain labels in the web app's voice: sentence case, no emoji, no exclamation marks.
  - Say what it is: "Counting toward today", "That's the hour.", "Save to Daf".
  - Never mention Claude or prompts in the UI.
- **Data:**
  - Private books stay private: the server already reduces them to "Private reading".
    Never show a title the server didn't send.
  - Don't put Nathan's email anywhere.
- **Look:** Readwise Reader. Nathan's screenshots are in his Nextcloud,
  `Documents/0_BIN/Readwise Clone`.
- **Ask Nathan before** anything that costs money, publishes to a store, or changes his phone's
  system settings beyond the permissions the app asks for.
