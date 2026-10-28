<p align="center"><img src="../design/icon/final/web/icon-512.png" width="72" alt=""></p>
<h1 align="center">Daf docs</h1>
<p align="center">My reading app for Year 30: an hour a day, counted from everywhere I read.</p>

These pages explain Daf the way I'd explain it to a friend sitting next to me: what each screen is for, what the buttons do, and how it all fits into a day. If you're new, read "What is Daf?" first and then "A day with Daf", which is the quickest way to see how the pieces fit together. The pages under "Under the hood" are the working notes I keep for running and building it, and you only need them if you're changing Daf itself.

### Getting started
- [What is Daf?](what-is-daf.md) — what it does, what works where, and what it connects to
- [A day with Daf](how-i-use-it.md) — how the pieces fit together, from the morning highlight to Shabbat
- [Install](install.md) — the web app, the Mac, Windows and Android apps, the Kindle plugin and the extension

### Using Daf
- [Today and goals](today-and-goals.md) — the ring, the sittings, the year grid, and the goals behind them
- [Where the minutes come from](reading-time.md) — the Kindle, audiobooks, paper and Daf, and what counts
- [Paper books](paper-books.md) — logging minutes, Shabbat, and photos of marked pages
- [The reader](reader.md) — books, articles and PDFs, themes and typefaces, writing with a pen, focus mode, Listen, lookup, Ask, and the keys
- [The Feed and the Library](feed-and-library.md) — FreshRSS, the Library and its tags, imports, the morning email, newsletters, Home, search and Send to Kindle
- [Videos and podcasts](videos-and-podcasts.md) — transcripts, clips, and AntennaPod
- [Highlights and review](highlights-and-review.md) — colors, tags, the daily review, flashcards and export
- [Books and shelves](books-and-shelves.md) — the nightstand, shelves, Hardcover and a book's page
- [The Torah shelf](torah.md) — the parasha, the haftarah, divrei Torah and the dictionaries
- [Recovery](recovery.md) — the Big Book by its chapters, the Step 10 and 11 readings, prayers
- [Stats](stats.md) — streaks, totals and the books that are waiting
- [Manga](manga.md) — reading Komga's manga in Daf

### Devices
- [The Kindle](kindle.md) — the KOReader plugin: Home, Shelves, the Daf tab and the sleep screen
- [The Mac app](mac.md) — the window, the menus, the menu bar and Safari
- [The Windows app](windows.md) — the window, the menus, today by the clock and no connection
- [The Android app](android.md) — phone and tablet, the widget, Listen and books on the phone
- [The browser extension](browser-extension.md) — highlighting on any web page
- [Sharing, messages and the widget](phone-shortcuts.md) — "Save to Daf", Signal messages, the morning highlight

### Tips and what's new
The first time you reach something you haven't used yet, like the search, a book's Aa or the read-aloud voice, a small note points at it, one at a time. It goes for good once you press the thing or **Got it**. **What's new** in the sidebar (or in ⌘K) lists what changed lately and shows a count until you've looked; on the phone the More button gets a dot. **Preferences → Tips** turns the notes off or brings them all back. What you've seen is kept on the server, so the Mac and the phone agree.

### Something wrong, or missing?
**Send feedback**, in ⌘K or at the bottom of Preferences, takes a note about it, with where Daf is, the device and what went wrong lately, and files it as an issue on Daf's GitHub repo, where the next working session picks it up. A private title never goes along.

### Running your own server
- [Your own server](server.md) — the service, the state folder and the `daf` command line

### Under the hood
- [How Daf runs](OPERATIONS.md) — the operating notes for my server, every detail
- [The plan](../PLAN.md) — the phases and the decisions behind them
- [The native apps brief](NATIVE.md) — what the Mac and Android apps were built to do
- [The shell contract](SHELL.md) — how the page and the native apps talk to each other
- [Daf for macOS](../mac/README.md) — building and testing the Mac app
- [Daf for Android](../android/README.md) — building and testing the Android app
- [Daf for Windows](../windows/README.md) — building and testing the Windows app
- [The extension's notes](../extension/README.md) — building, signing and connecting the extension
