# Daf Native (the Mac trial)

This is Daf for the Mac made the way a Mac app is made: SwiftUI and AppKit, with the system's own window, sidebar, toolbar, search, inspector and Settings, instead of the web page in a window. It sits beside the regular Daf app (`mac/`) as its own app, **Daf Native** (`xyz.tiresia.daf.native`), so I can use both for a while and decide.

It talks to Daf the same way the page does, through Daf's own API, so nothing changes on the server and everything I do in it shows up everywhere else.

## What's native

- **The window.** The sidebar has Today and Review; the Library's Inbox, Later, Shortlist and Archive; the Feed, with its folders opening onto their feeds, each with what's unseen in it; Books, Manga, Torah, Podcasts, Highlights and Stats; and Sources. Search sits at the top of the sidebar. The Go menu has them all (⌘1 to ⌘8 for the main ones).
- **Today.** The minutes ring with the main goal, Year 30 so far, the week as a chart against the goal, today's reading, and what to keep reading.
- **Lists.** The Library and the Feed, with pictures, minutes and progress. Right-click (or the toolbar) for Archive, Read Later, Mark Seen, Save to Library, Open the Original and Delete. Delete has Undo, in the little note at the bottom and in Edit › Undo (⌘Z).
- **The Feed's sources.** Right-click a feed to rename it, move it to another folder, turn on "Always load the full article" or "Tell me about new posts", copy its address or unfollow it. Mark All Seen (⌥⌘K) works on the whole Feed, a folder or one feed, with Undo. Check for New Posts (⇧⌘R) asks FreshRSS now, and Feed › Follow a Site… adds one.
- **The article reader.** Native text in a column, the way Apple Books lays it out: headings, lists, quotes, pictures and captions, my highlights in their colours. Select and press **H** (or right-click → Highlight) to highlight. Right-click a highlight to give it a note or another colour, or to remove it; a highlight with a note is underlined with dots, and the note shows when I hold the pointer over it. It keeps my place in Daf and counts my reading time exactly as the page does (15 seconds at a time, while I'm actually reading).
- **The inspector** (⌥⌘I) has the article's details, my note on it, its tags (Article › Tags…, ⌥⌘T, with the tags Daf already knows as suggestions), the summary and the highlights. PDFs and videos have the note and the tags too.
- **Read aloud.** **P** listens or pauses (⌥⌘P from the menu), **L** or right-click → Read Aloud from Here starts at a paragraph. It's Kokoro on Daf, a paragraph at a time, the next one made while this one plays; the paragraph being read is marked and kept in view, and the player at the bottom has the paragraph before and after, the speed and Stop. The keyboard's play and skip keys work too. Listening counts as reading. The voice is in Settings.
- **Review.** Today's highlights one at a time, with Keep, Less, Never, a note and Favorite, and the flashcards that are due, as in the page (K, L, N and F, the arrow keys, Space, and 1 to 4 for a card).
- **Highlights.** Every book and article with highlights; each one's highlights with their notes, colours and tags. Open at Its Spot opens the article in a window of its own at that highlight.
- **Stats.** The numbers, the last two weeks against the goal, where the minutes come from, highlights a week, the hours and the days of the week, in Apple's charts.
- **Books.** A book's own page: its cover, where I am, the nightstand, my reading of it (time, sittings, pace, when I'd finish) and its highlights. Read opens it in a window of its own.
- **Manga.** A series' volumes as covers. A volume opens in a native reader: one page or two side by side when the window is wide enough, right to left unless the series says otherwise, ←/→, Space or a click on either side to turn. It keeps my place and my reading time as the page does, and offers the next volume at the end.
- **Torah, Podcasts and Sources.** This week's parasha and haftarah with the readings, which open in the reader; what I've listened to lately and what I follow; whether each place Daf reads from is answering, with Sync Now.
- **PDFs** open in Apple's own PDF view.
- **Settings** (⌘,) has the address and sign-in, today's minutes in the menu bar (off unless I turn it on), and Daf's reading preferences: highlights and flashcards a day, how long unseen Feed items stay, the voice and the speed for reading aloud.
- **File menu.** Add a Link… (⌘L) and Log Paper Minutes… (⇧⌘P).

## What's still the page

The book reader, videos and podcast episodes open as Daf's own pages (without the page's sidebar). They count reading time and keep their place themselves, as in a browser.

## Not yet

Offline, Save to Daf in the share menu, the Safari extension and new-post notifications (the regular app still has all of those), shelves, and the rest of Daf's preferences, which open as the page from Settings.

## Building it

On the Mac:

    cd mac-native && ./build.sh

That makes `build/Daf Native.app`, signed ad hoc. `./selftest.sh BASE COOKIE` runs the app against a sandbox Daf (never the real one) and writes `build/selftest/log.txt` with a picture of each step. A tailnet sandbox needs macOS's local-network permission for the app; an SSH tunnel to the Mac's own 127.0.0.1 avoids that. Reading aloud plays silently in the self-test.
