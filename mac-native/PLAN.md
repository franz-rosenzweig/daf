# The Mac app: catching up with the new Daf

Between November 10 and 14 the web app changed more than in any week before it. It got the new look (Today's card in the colour of the book I'm reading, colours taken from covers, Rooms, Preferences one page at a time), the Study reader with Margin and Side by side, one Notebook instead of two, Learn with its areas, and an almost complete copy of Calibre's main window and book editor in All Books. The Mac app stopped at 0.6.5 on November 10, so all of that is missing there. This page is the plan for bringing it back level, one phase at a time, each phase its own pull request and its own release.

The rule stays the same as always: every tool the web app has is in the Mac app too, the pens excepted, and it's fine for the Mac to do things the Mac way. [PARITY.md](PARITY.md) is the list of what's there and what isn't yet; this page is the order I'm doing it in.

## What's decided

The Mac app stays NATIVE all the way through, All Books and Edit book included, unless the mockups change my mind. Putting the web page for those two inside the Mac window would be quicker and would keep up with the web by itself, but a real Mac table and a real Mac editor are what I'm leaning towards, even though it means building every later Calibre change twice.

Before building, I'm looking at mockups of the Mac app in the new look (Today, the reader, All Books, Edit book and Preferences, kept privately), so I can see how it would look and feel after everything that changed. Phase 0 doesn't depend on them, so it goes ahead now.

Getting around is a sidebar, decided November 16. It has the web's tabs as its headings, in the same order (Today, Books, Library, Feed, Learn, Listen), with each tab's pages listed underneath. So it's the same map as the web, just turned on its side. Every page is one click away with its count beside it, the feed folders, pins and shelves keep their place in it, and when Daf only has half the screen the sidebar simply hides. The web's tabs across the top suit the tablet, but on the Mac a sidebar is what every app does.

Left out on purpose: pen ink (tablet only), and Shelfmark.

## Still open

- **What should work differently on the Mac,** beyond catching up. That list goes into the phases below once I have it.
- **Where Music goes in the order.** It can come right after the sidebar, or wait until the rest of phase 1 is done.

## The phases

**0. Clear the decks.** The 0.6.6 work from November 10 (the Tags, Authors and Series sheet, Find Details for many books at once, and Write Details into Every File) was never pushed. It's rebased onto today's master now. Its self-test crashed twice at the step that switches the sidebar between full, mini and hidden. The cause was the mini sidebar's names shrinking to fit: text that scales with the width changed the rows' height, which changed the width again, round and round until the window gave up. The names keep their size now, the self-test passes, and it ships as 0.6.6.

**1. The frame and the new look.** Everything else sits inside this, so it comes first. It goes out in four parts:
- *1a, the sidebar:* the web's tabs as its headings with their pages under them, Recents under Today, and Listen's pages named for themselves. The self-test's pictures of the window leave the sidebar's rows out now that the sidebar is glass, so the test takes the sidebar's own pictures two other ways, and it has a short run of just the frame.
- *1b, the toolbar:* Back and Forward, Search, Add, the ⋯ menu for each screen and the minutes ring.
- *1c, the look:* Today's card in the current book's cover colour with the lines where I left off (`GET /api/books/{id}/excerpt`), the cover colours on a book's page, on Books and on the player, and the themes and Rooms with the new look's colours.
- *1d, Preferences:* one page at a time, the way the Mac's own Settings are, with Devices & extension as a page of its own.

**Music.** The web got Music on November 17: whole tracks from my own music folder, played quietly under the page. On the Mac it's six things, built in this order: the player (two players taking turns, so one track fades into the next), Music in the Sound menu, the playing track's page, Auto (the scene picks what plays), Today's Music row, and the Music page. Radio stations and a Music button in the article and PDF readers come after, once the web has them. Track, album and artist names are my own listening, so they never go into the repo, a pull request, the docs, a test or a picture that leaves my machines.

**2. Reading.** The Study reader: Margin (the page to the left and a line for each highlight beside it) and Side by side (a second book on the right half). The one Notebook, with its Pages and List, as the first tab of the reader's panel beside Info and Ask. Page turns (None, Slide, Curl). MOBI, AZW3 and FB2 read natively instead of in the web reader. A book's Details card, Add a book → Public domain, and videos picking up where I left them.

**3. All Books and Calibre, built for the Mac.** The biggest phase, so it goes out in three parts:
- *3a, the library:* the Tag browser with its menu on a name, Book details beside the table, the cover grid, Quickview, Similar books, marks, editing a cell in the table and Calibre's keys, sorting on several columns, my own columns and columns made from other columns, Highlight beside the search, dragging books onto the Tag browser, and Jobs in the status bar.
- *3b, the books' tools:* what Edit details is still missing (half stars, the sort fields, the description with bold, italic and lists, one at a time with Previous and Next, generate, trim and remove a cover, set details from a file), Edit N books' find and replace, the Convert sheet, Polish books and Restore the originals, EpubMerge, Send to Kindle, Save to disk, Add from ISBN, Import list, Check library, Count pages, the Metadata download settings, and Open with.
- *3c, Edit book:* its own window with the book's files, a code editor with colours, the live preview, find and replace, Contents, Check book, Spelling, Reports, Split and Merge, Beautify, special characters and the outside-links check.

**4. Listen.** Add a podcast, a show's downloads and each episode's, Audiobooks by series, authors, narrators and collections, an audiobook's own page (chapters, bookmarks, details, speed, sleep timer), and reading along with the audiobook.

**5. Learn and the rest.** Areas and an area's pages (Overview, Everything, Plan, Ask), Ask across all areas, moving things around and taking them out, and Add to an area from anywhere. Then the Edition's own topics and Calibre's highlights in the Highlights filter.

## How each phase ships

Each phase is built on a branch from master in its own worktree, compiled on the Mac, and checked with `selftest.sh`, which takes over the Mac's screen for about nine minutes (or about one for just the frame), so it only runs after a heads-up. The self-test uses its own copy of Daf's data, and anything that would write to Calibre is a stand-in there, so it never touches the real library. Then a pull request, which gets merged when I say so, and the release, which I usually run myself.
