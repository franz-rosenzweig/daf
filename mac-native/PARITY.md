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
- not yet: what's drawn on a page with a pen (mink.js, /api/manga/books/<id>/ink), shown over it

## Books

- here: EPUBs as pages, contents, highlights, bookmarks, search, Ask, read aloud, the Kindle's highlights and place, the Aa panel, footnotes
- here: the Info tab (details, series and the next one, the Kindle's page, the vault path)
- here: go to a percent, go to the beginning, go to the Kindle's page, forget my place, download the file, export the highlights
- here: a highlight's tags, favorite, flashcards and share as an image; overlapping highlights merged; highlight when selecting; Define and Translate
- here: selection snapped to whole words
- here: line width and settings just for this book
- here: the Scroll layout (the chapter as one column), as the Aa panel's Layout
- here: the player's voice menu and sleep timer
- here: the status bar under the pages, as KOReader's (book.js drawStatus): the things picked in Themes & Settings › Status Bar (or its right-click), one at a time (a click goes on) or all at once, the line of the book with its chapters marked or of the chapter; the printed book's pages where the EPUB has them
- not yet: scanned books (scans.js): a book of pictures of its pages read as the printed book, two facing, up close
- not yet: page turns (pageturn.js: None, Slide, Curl, in Aa) and the rooms (themes.js: wood, rustic, gothic, cyber)
- not needed: underlining with the pen (underline.js) is the tablet's
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
- here: reels (social.py): Daf's own copy in AVPlayer, standing up, or square and wide in their own shape; the transcript follows along, Clip 30s, Open on Instagram; a reel Daf has no video of stays its link, with just Open on Instagram (Daf never fetches from Instagram)
- here: a podcast episode's page (episodes.py): its audio from where the last play anywhere stopped (and says where), −15 and +30 (← →), the speed (1× to 2×, 0.8×, kept), chapters, Clip 30s (the server transcribes it when there's no transcript yet), Follow Along, Transcribe and Try Again, P plays and pauses, the media keys and Now Playing; where it stops goes back in stretches (/api/podcasts/position); #read/<doc>/t:<sec>; Save to Library for an episode met only in AntennaPod
- here: highlights in the PDF view (as you select, H or N, right-click), the text view's found on the page, its zoom keys (− +), its reading time and the page read
- here: Torah's verses in Hebrew and English, or one of them (the toolbar, or Article › Torah)
- not yet: what's written on an article with a pen (ink.js, /api/docs/{id}/ink), shown over the text and in the margin, in the pens' kinds (pens.js)
- here: focus mode (Focus.swift, as focus.js): full screen, only what's open, the toolbar and menu bar hidden till the top; ⇧⌘F, [ ], F in a book, ⇧F in an article, Esc
- not needed: the pens (pens.js), the lasso and handwriting into text are the tablet's; a note on the passage made from handwriting shows here as any highlight's note

## The focused round (2026-10-30)

- here: the sidebar shown or hidden (⌘\, the button at the top left) and full or mini (View › Sidebar, Settings › General), kept on this Mac; it stays while an article is read (the Mac's list sits beside the article; the page's reader takes the whole page, so it hides there); full or mini by dragging its edge is the page's, not here yet
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
- here: Podcasts as the page has it (podcasts.js): Listening (Continue, here and in Audiobookshelf; New), Shows, Episodes (All, Unplayed, In progress, Played, Transcribed, Clipped; Newest, Oldest, Longest), Recordings and Audiobooks from Audiobookshelf, Clips; a show's page with Follow, its website and what it's about; its search (my shows and episodes, Audiobookshelf, Apple's directory); a row's round button plays it, the row opens its page
- here: Today's notices (Shabbat, the Kindle finished a book, a book read off the nightstand), the other goals' chips, minutes by source, the day's review, On this day, the nightstand (or the suggested three), Year 30's year, how fresh the sources are, a goal met or a milestone said once
- here: Today as a page across the window, with Year 29 under Year 30
- here: Review by a book or by whatever the Highlights filters show (a tag, favorites, a colour, a search), Review more, another round; a flashcard, tags and share as an image from the review
- here: Highlights: source, colour, tag, favorites and private filters, sort (newest, by book, oldest), export (Markdown, CSV, JSON, Anki), Review these
- here: a book's page: a note on the book, audiobook bookmarks, how often its highlights come back in review, export, review these, a fourth book on the nightstand asks which one steps off
- here: Books: the nightstand, Want to read (from Hardcover), Opened lately, the whole library, a search by title, author, series or shelf (/api/books/search)
- here: a book's audiobook (audiobooks.js, audiomap.py): Listen and Listen from Here on its page, "In the audiobook you're at …" on opening it, The Audiobook from Here in its More menu
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
- here: AniList (the client, Connect, the last update); the Instagram sign-in is gone, as on the page
- here: Reader apps (readerapps.js, greader.py): the server, the Google Reader API address and the username, each with Copy; Make a Password (shown once, with Copy), New Password and Remove (each asked first); when it was made and last used
- here: Send Feedback (Help menu)
- here: appearance: Daf's themes (a theme for light and one for dark, with the Mac or always one), kept in Daf for every device; books keep their own

## Everywhere

- here: search, the File menu's Add to Daf and Log Paper Minutes, offline with changes kept, Undo
- here: the player (player.js): episodes, Audiobookshelf's recordings and audiobooks, and read-aloud, along the bottom of the window, going on wherever I go (a book read aloud goes on after its window closes); a click opens the whole player (the picture, scrubbing, the speed, a sleep timer in minutes or at the end of the chapter, the chapters, the voice, Go to It); the media keys and Now Playing
- here: a search in every tab (find.js), in the toolbar: the Library and the Feed (on the server, the tabs counting what it finds, widened to All of the Library or All Feeds), Books, Home (the whole Library), Manga, a shelf, Paper pages, Torah, Sources, Stats, Podcasts, Highlights
- not yet: Recovery's search (asks first: Recovery is his to decide)
- here: the mini sidebar names each place under its icon, ☰ at its top opens the full one, and Pinned has Edit
- here: ⌘K: search everything (articles and the words in them, books, highlights, the vault), go anywhere, do something
- here: adding books and PDFs as files, dropping files and links on the window, pasting a link or copied files
- here: the shortcuts sheet (Help › Keyboard Shortcuts, ⌘/)

## The Sketchbook (2026-11-05)

- not yet: the Sketchbook beside a book, an article, a video, a PDF and a manga volume (web/sketchbook.js): a panel on the right whose width is dragged, a tab a chapter (following where you are) or a volume and General, typed text blocks (add, edit, move up and down, delete, type below), handwriting and pictures shown (the pen itself is tablet-only), time stamps that seek a video, the camera on a manga or PDF page, dictation (/api/sketchbook/dictate), all through /api/sketchbook

## The Edition (2026-11-09)

- here: Edition in the sidebar under Today (when edition.on or there's one), with done/total; a page across the window (edition.js): the date, the Hebrew date and the number, ten marks and the time left; the lead with its opening lines and the Today list beside it (under it when narrow); the other pieces as cards with their kind, why, 👍/👎 (POST /api/edition/vote) and Read; End of the edition; a piece opens in its own window (#read)
- here: the toolbar: past editions, Taste, Kindle / On Kindle (POST /api/edition/kindle), Make It Again (asked first) and Make It Now (POST /api/edition/build), looked at every five seconds while it's being made
- not yet: Taste's own topics (edition.js, PUT /api/edition/settings): Add a Topic (a name and, if given, its words: `topic_add: {name, words?}`; without words the server asks the model, so the button waits), Remove on every topic row, asked first (`topic_remove: name`), the list read again after either (GET /api/edition/taste; a topic of his carries `mine: true`), a topic's words as its tooltip
- here: Taste (#edition/taste): the last two weeks, what it learned from, Picking up on; Topics with their bars, rising/fading and Less/More/Mute, Name Them Again; the Mix (Every morning, Days, the steppers, Kindle, Chosen by the model) through PUT /api/edition/settings; Sources with Less/More/Mute, Mute by name or folder:Name, Muted with Unmute; the Pool (#28): its categories with their feeds and the last two days' posts, Mute / Unmute a category (folder:Pool · …); "none" for an up-to or at-least at 0

## Sound (2026-11-09)

- here: Sound in the book reader (sound.js): the wave button with the scene, Volume and Turn On / Turn Off Sound; on for books on this Mac until turned off; the place sent 1.2 s after the pages settle (POST /api/ebooks/{id}/sound), asked again every 5 s while it's reading; stops when the book closes
- here: the mixer in AVAudioEngine: an AVAudioPlayerNode a sound, its loop PAD to PAD + whole seconds, started somewhere in it, faded in and out over 4 s, the volume on top; the files kept on the Mac
- here: Today's Sound row beside the Kindle (GET /api/sound/kindle, seen in the last half hour): the book, the scene and the volume while it plays, Sound / Stop; it waits for the Kindle's next page and plays on with the window in the background

## What shows where in the Feed (2026-11-10)

- here: under Feed in the sidebar only what's pinned, in order (/api/docs/counts feed_pins), a pinned feed with its icon; feed_pins_hide_empty leaves out the empty ones but the one open; the Feed's count is feed_total; then Feeds
- here: the Feeds page (feeds.js, /api/feed/manage) as a Table: folders opening on their feeds, Hidden ones last under a Hidden row, A week, Show (Everywhere / Its folder / Hidden; a feed's from its folder shown faint), the pin, Edition (More / Normal / Less / Off, a feed's Like folder), …; the chips All, Everywhere, Its folder, Hidden, Quiet (30 days), Problems; search by title, folder or site; several picked: Show…, Edition…, Move To… (A New Folder…), Unfollow…, Clear; a double-click opens the folder's or feed's posts
- here: the menu on a folder or a feed (the sidebar's pins, the Feeds page): Pin / Unpin, Show (Like Its Folder for a feed), Edition, Mark All as Seen (and Older Than), for a feed Rename, Move To, its two switches, the site, the address, Unfollow; Feeds
- here: Settings › General › Under Feed: the pins with Up and Unpin, Feeds, Hide pins with nothing new
- here: Follow a Site's folders from /api/feed/folders?hidden=1
- the Mac has no Sources sheet (its sidebar was the source picker): the Feeds page stands in for it, Manage and the Hidden row included

## All Books (2026-11-10)

- here: All Books (#catalog, catalog.js, /api/catalog) first under Books in the sidebar (and in the mini one), Go › All Books ⇧⌘6, the palette, daf://go/catalog; a page across the window
- here: the table as an NSTableView: the columns from /api/catalog (Calibre's, its own columns, Daf's), default_columns until chosen, the title always there; a column's name sorts by it (numbers, dates and yes/no biggest first on the first click), dragging a name moves the column, dragging its edge sizes it (48–900); the cells as the page's: the cover beside the title (a private book's in italics), the series' number dimmed, stars with halves, dates (Published by the month), MB, the progress bar with its note, ✓
- here: the search in the toolbar, sent as q (250 ms after the typing stops, or at Return); an error is a red line over the table; the count in the window's subtitle (N books / N of M)
- here: Filter on the left: Find a Value, Clear, Added (this week, this month, last 30 days, this year, last year), Missing (no file, cover, tags, rating, series), then the facets with their counts, 30 a group until Show All; a click goes in → not → out (catalog.js's patterns); the groups left open are kept
- here: Columns: a right-click on the column names (tick on or off, Default Columns), or the Columns popover (the ones showing dragged into order, then the rest)
- here: Views (PUT /api/catalog/views): pick one (ticked while the page matches it), Save into “…”, Save as a View… (Replace asked), All Books, Newest First, Delete a View…; More: Export as CSV… (/api/catalog/export with the columns showing, also File › Export All Books as CSV…), Show Private Books
- here: kept on this Mac: the search, the order, the columns, their widths, Show Private Books and the view; the row picked and the scroll, for coming back
- here: a double-click or Return opens the book's page in Books (one Books doesn't list, without a file say, opens all the same)
- here (#38, editing): Edit Details (bookedit.js) as a sheet: from All Books (⌘I, the row's menu) and the book's page (cal: ids); GET /api/catalog/book/{cid}; the cover (Change Cover… a file as the PUT body, Cover from a Link… {url}), the files (format, size, download, … Convert to EPUB/AZW3/KEPUB/MOBI/PDF with the job asked every 2 s, Remove the X File… asked first), Add a File… (?name=, the raw body); the form: Title, Authors (A & B), Series and its number, Tags (chips, Return or a comma), Rating (halves shown, the same star clears), Publisher, Published (a date or none), Languages, Identifiers (type: value a line), Description, my columns by dtype (enumeration a picker, bool, int/float, datetime, rating, comments, text; multi a comma list; #isbn left out); suggestions from choices (textInputSuggestions); PUT only what changed; Save ⌘↩, Cancel Esc (asked when changed)
- here: several books: the table chooses several (⌘, ⇧, ⌘A); a bar under it with N chosen, Choose All N, Clear, Edit N Books…; the bulk sheet: Authors, Series + Number them from N in the table's order, Add Tags, Remove Tags (from the chosen books' tags), Rating + No Rating, Publisher, Published, Languages, my columns (No Change); POST /api/catalog/bulk with the ids in the table's order
- here: Find Details… (POST …/find, the job asked every 1.5 s): the title and author to search again, the answers with their cover (through /api/catalog/coverproxy), authors, year · publisher · series · pages and the source; one answer beside Now, a box a field (missing ones ticked, the same ones off, tags joined, identifiers only new kinds), Use This Cover; Use These fills the form, a ticked cover set at once
- here: covers in the table by /api/cover/{id}?v=cover_v; a new cover forgets the plain address's cached copy, and the book's page draws it again (dafBookEdited)
- here (#39, tidying): Filter's Tidy group (duplicate:true, title:~[âÃ�], authors:"~^[^&]+, "); the bar under the table: Merge… (2+), Remove…, Edit; the row's menu: Merge the N Chosen…, Remove from Calibre… / Remove the N Chosen from Calibre… (⌘⌫); Merge as a sheet, a radio a copy (cover, title, authors, formats · added · highlights), the one with a cover, then the most formats, then the first added picked; POST /api/catalog/merge {keep, ids}; Remove asked first ("Remove “…” from Calibre?" / N books, with the highlights Daf has) then POST /api/catalog/remove; Remove from Calibre… at the bottom of Edit Details, then All Books if the book's page was open; … › Calibre's Trash… (GET /api/catalog/trash, private=1 with Show Private Books), each with Put Back (POST /api/catalog/trash/restore); the bulk sheet's Turn “Last, First” names around (authors_flip, when Authors is empty)
