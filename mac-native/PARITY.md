# Everything Daf's page does, on the Mac

Every tool the web app has belongs in the Mac app too, the Mac's way. This is the list, kept as the
rounds go: **here** means the Mac app has it, **not yet** means it's still to come.

## Manga

- here: the shelf (keep reading, every series), a series' page (volumes, keep reading, a file Komga can't open)
- here: right to left, left to right, vertical, long strip and strip with gaps
- here: page layout (auto, one, two), shift pairs by one, split wide pages, the cover alone, wide pages alone
- here: scale (fit screen, width, height, original), stretch small pages, crop borders
- here: settings kept per series by Daf (/api/manga/prefs), "use for every series"
- here: the start card (the volume before) and the end card (finished, next, back to the series); back past the first page into the previous volume, on past the last into the next
- here: the trackpad's swipe, the wheel, pinch and double-click zoom; tap zones (Mihon's layouts, inverted), shown when they change
- here: background (black, gray, white, from the page) and the filters (brightness, contrast, saturation, sepia, grayscale, invert)
- here: the page number and the progress line; the page slider and the volumes on either side; the quick settings
- here: every page as thumbnails; full screen; save this page; auto scroll; the keys ([ ] m t s r d c b a f, Home, End, Esc)
- here: the place and the reading time as the page keeps them; the screen stays awake while reading

## Books

- here: EPUBs as pages, contents, highlights, bookmarks, search, Ask, read aloud, the Kindle's highlights and place, the Aa panel, footnotes
- here: the Info tab (details, series and the next one, the Kindle's page, the vault path)
- here: go to a percent, go to the beginning, go to the Kindle's page, forget my place, download the file, export the highlights
- here: a highlight's tags, favorite, flashcards and share as an image; overlapping highlights merged; highlight when selecting; Define and Translate
- here: selection snapped to whole words
- here: line width and settings just for this book
- here: the Scroll layout (the chapter as one column), as the Aa panel's Layout
- here: the player's voice menu and sleep timer
- here: next in the series and the Hardcover "finished" question near the end
- here: the time left in the chapter and the book, the page and the percent
- not yet: other formats (MOBI, AZW3, FB2) natively: they open in Daf's own reader

- not yet: what's written on a book's pages with a pen (book.js ink, /api/ebooks/{id}/ink), drawn over the page

## Articles

- here: the native reader, highlights with notes and colours, the note, tags, Ask, read aloud, send to Kindle, delete with Undo, open at a highlight
- here: Shortlist (F), previous and next in the list (⇧J ⇧K, ⌥⌘↓ ⌥⌘↑), Undo on Archive, Later and Delete
- here: Summarize, Load the Full Article, Reset Reading Progress, Edit the Title and Author, Copy the Link, Open the Note in Obsidian
- here: Define and Translate (/api/lookup, and "in this sentence")
- here: a highlight's tags, favorite, flashcards (fill in the blank, question, suggest), share as an image; Remove with Undo; overlapping highlights merged; highlight when selecting (⌥ to just select)
- here: paragraph focus (j, k) and h or n on it; the page's article keys (h n j k p L e l s f t N d z o J K C R M)
- here: picture highlights (right-click a picture, or select it and press H), framed in their colour, shown as the picture everywhere
- here: videos natively (YouTube's private player above the transcript, follow along, a timestamp plays from there, Clip 30s, C), captions or a transcription when there's none
- here: reels (social.py): Daf's own copy in AVPlayer, standing up, or square and wide in their own shape; the transcript follows along, Clip 30s; on its way from Instagram, or why not, with the way to Instagram in Settings; Open on Instagram
- here: a podcast episode's page (episodes.py): its audio from where the last play anywhere stopped (and says where), −15 and +30 (← →), the speed (1× to 2×, 0.8×, kept), chapters, Clip 30s (the server transcribes it when there's no transcript yet), Follow Along, Transcribe and Try Again, P plays and pauses, the media keys and Now Playing; where it stops goes back in stretches (/api/podcasts/position); #read/<doc>/t:<sec>; Save to Library for an episode met only in AntennaPod
- here: highlights in the PDF view (as you select, H or N, right-click), the text view's found on the page, its zoom keys (− +), its reading time and the page read
- here: Torah's verses in Hebrew and English, or one of them (the toolbar, or Article › Torah)
- not yet: what's written on an article with a pen (ink.js, /api/docs/{id}/ink), shown over the text and in the margin, in the pens' kinds (pens.js)
- here: focus mode (Focus.swift, as focus.js): full screen, only what's open, the toolbar and menu bar hidden till the top; ⇧⌘F, [ ], F in a book, ⇧F in an article, Esc
- not needed: the pens (pens.js), the lasso and handwriting into text are the tablet's; a note on the passage made from handwriting shows here as any highlight's note

## The focused round (2026-10-30)

- here: the sidebar full, mini or hidden on this Mac (⌘\, the button at the top left, View › Sidebar, Settings › General); a hidden one back for a moment; none while an article is read
- here: Today, Review, Library (its kinds with Inbox, Later and Archive, and the saved views), Books, Feed (its folders), Highlights; Pinned (settings nav_pins, Settings › General); Search ⌘K, Stats, Preferences at the bottom
- here: the article bar: Aa, Listen, Save (Feed, AntennaPod-only episodes), Done, …, Notebook; Shortlist, Later, the original, Focus Mode and next/previous in the … menu; the time left under the text
- here: books the Apple Books way: two pages when wide (already), Pages by default (already), the title in the middle, Contents, Aa, Search, Bookmark, …; Listen, Notebook, About, Ask and Focus in …; contents and the panel slide over the pages; the footer fades after a page turn
- here: Themes & Settings (Aa) for articles and books: A A, Pages/Scroll, six looks, Auto/Light/Dark, the typeface, spacing, width, justify; All Themes; articles now have a typeface, a size, spacing and a width (they had none)
- not needed: the toolbar hiding as you scroll, and fading in a book (a Mac window keeps its toolbar; in full screen and Focus Mode it hides till the pointer goes to the top)

## Lists

- here: the Library and the Feed, kinds, tabs, order, filters (length, added, highlighted, not started, source, author, tag), saved views, several at once, Undo, the Feed's sources (rename, move, switches, unfollow, follow a site), Check for New Posts
- here: Mark Seen Older Than a day, three days, a week; Sync Now for the Library; "Mark them read in FreshRSS too"
- here: the Library's home (continue reading, recently added, quick reads, long reads, recently highlighted, new in the Feed), each shelf shown or hidden
- here: the list keys (j k e l s f t d z)
- here: a saved view's order and filters changed in place, with Update the View

## Pages

- here: Today (the ring, the week, the sittings, keep reading), Review (highlights and flashcards), Highlights, Stats, Books, a book's page, shelves, Torah, Podcasts, Sources, Paper pages, Log paper minutes
- here: Podcasts as the page has it: Listened lately (how far, a transcript), the clips (each opens its episode 30 seconds before), the shows, a show's episodes; each opens its episode's page
- here: Today's notices (Shabbat, the Kindle finished a book, a book read off the nightstand), the other goals' chips, minutes by source, the day's review, On this day, the nightstand (or the suggested three), Year 30's year, how fresh the sources are, a goal met or a milestone said once
- here: Today as a page across the window, with Year 29 under Year 30
- here: Review by a book or by whatever the Highlights filters show (a tag, favorites, a colour, a search), Review more, another round; a flashcard, tags and share as an image from the review
- here: Highlights: source, colour, tag, favorites and private filters, sort (newest, by book, oldest), export (Markdown, CSV, JSON, Anki), Review these
- here: a book's page: a note on the book, audiobook bookmarks, how often its highlights come back in review, export, review these, a fourth book on the nightstand asks which one steps off
- here: Books: the nightstand, Want to read (from Hardcover), Opened lately, the whole library, a search by title or author
- here: Hardcover (link a book, its status and rating, finished)
- here: Torah's essays from the vault (Reference/torah/<parasha>/), opened in the reader, the time counted and the highlights back in the same note

## Preferences

- here: Goals, what counts, review size, flashcards a day, the voice and speed, how long the Feed keeps items, the menu bar, alerts, offline, Daf for Safari, sign out
- here: after Archive or Later, open the next one; the home time zone; how long the Feed keeps what's unseen
- here: Account (username, password, sign out other browsers, connected devices, the browser extension's token)
- here: AI (summaries and tags of what I save, the model, the ready questions, what Daf asks for each)
- here: Library tags (rename, merge, remove, the tidy-up)
- here: Import (Instapaper, Readwise, Raindrop, Pocket, OPML…), dropped or chosen, followed as it goes
- here: Morning email, Newsletters, Hardcover, Phone, Podcasts (AntennaPod, and Transcribe episodes I play or open)
- here: Instagram (the sign-in, Sign In to Instagram in a window that keeps nothing, Keep Daf signed in from my browser, the reels waiting, Forget It) and AniList (the client, Connect, the last update)
- here: Send Feedback (Help menu)
- here: appearance: Daf's themes (a theme for light and one for dark, with the Mac or always one), kept in Daf for every device; books keep their own

## Everywhere

- here: search, the File menu's Add to Daf and Log Paper Minutes, offline with changes kept, Undo
- here: ⌘K: search everything (articles and the words in them, books, highlights, the vault), go anywhere, do something
- here: adding books and PDFs as files, dropping files and links on the window, pasting a link or copied files
- here: the shortcuts sheet (Help › Keyboard Shortcuts, ⌘/)
