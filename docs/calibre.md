<sub>[Daf docs](README.md) › Using Daf</sub>

# Calibre in Daf

My books live in Calibre. Calibre-Web Automated runs it on the server, takes in new files and converts them, and for a long time I opened Calibre on the Mac whenever I wanted to look through the library properly or fix a book's details. I'd rather do all of that in Daf, next to the reading, so Daf has taken over Calibre's jobs: the library as a spreadsheet with Calibre's search, editing one book or many, covers, files and conversions, finding details online for one book or many, importing a list of books from somewhere else, renaming and combining tags, authors and series across the library, writing the details into the book files, and tidying: duplicates, merging, removing and Calibre's trash.

## All books

**All books**, at the top of **Books**, is laid out like Calibre's own main window, because that's the layout my hands know. Across the top is Calibre's toolbar: **Add books**, **Edit metadata**, **Convert books**, **Read**, **Find details** (Calibre's Download metadata), **Shelves**, **Merge books**, **Download** (Calibre's Save to disk), **Remove books**, in the Android app **Open with** (Calibre's Open With plugin: one of the book's files goes to another app on the tablet, like KOReader or a PDF reader, through Android's own Open with), and at the far end **Library**, with Check library, the tags, authors and series, writing details into the files, Count pages, the CSV export, private books and Calibre's trash. The buttons that need a book light up once I've chosen one. Under the toolbar is the search, with **Views**, **Sort** and **Columns** beside it.

Below that are Calibre's three panels: the **Tag browser** on the left, the books in the middle, and **Book details** on the right, which shows the book I chose last: its cover, title and author, **Read** (or **Continue** with how far I am), **Edit metadata**, how far along I am, and then the description, series, tags, publisher, pages, languages, formats and links, the same card as on the book's own page. Tapping an author, a tag or a series there searches for it. At the bottom is the status bar, with how many books there are and how many I've chosen, and the three switches Calibre has in that corner: **Tag browser**, **Book details** and **Cover grid**, which shows the books as covers instead of rows. On the Mac, a laptop or the tablet sideways, the panels sit side by side; on the tablet upright and the phone, the Tag browser and Book details open as sheets from the bottom.

The books themselves are a spreadsheet: one row a book, with the columns I choose. Every book Calibre has is there, including the ones without a file yet, and next to Calibre's own fields it has what Daf knows: the status from the book's vault note, how far along I am, when I last read it, how many highlights it has, and which shelves it's on. Private books stay out unless I turn on **Show private books** in the **Library** menu.

Clicking a column's name sorts by it, and clicking again turns the order around. It opens on **Added**, newest first, so whatever came in lately is at the top. Dragging the edge of a column's name makes it wider or narrower, and on the Mac or a laptop I can drag the name itself to move the column. **Columns** lists everything there is: Calibre's fields (title, authors, series, tags, rating, the dates, publisher, language, formats, size, ISBN, identifiers, cover), my own Calibre columns (Read, Pages, Collections and the KOReader ones), and Daf's. I tick the ones I want and drag them into order there too, which is the way to do it on the tablet.

A click or a tap on a row chooses that book alone, as in Calibre, and shows it in Book details; the box at the start of the row (or Cmd or Ctrl and a click) adds a book to the ones chosen or takes it out, and Shift chooses everything from the last one. The title opens the book's page in Daf, and so does a double-click anywhere on the row. When I come back, the table is where I left it.

## Searching the way Calibre does

The search box understands Calibre's search language, so anything I'd type in Calibre works here:

- Plain words look everywhere: the title, the authors, the series, the tags, the publisher and the shelves.
- `tags:history` finds a tag that contains "history", `tags:"=History"` only that exact tag, and `tags:~^hist` a pattern.
- `tags:false` finds books with no tags at all, `formats:false` books with no file, `cover:false` books with no cover, and `series:true` books that are in a series.
- Numbers compare: `rating:>=4`, `pages:<200`, `size:>10mb`, `highlights:>0`, `progress:>=50`.
- Dates are flexible: `added:thismonth`, `added:>30daysago`, `added:2025-03`, `published:<1950`, `last_read:thisyear`. The words are `today`, `yesterday`, `thisweek` (from Sunday), `thismonth`, `thisyear`, `lastmonth` and `lastyear`, and `date:` is the same as `added:`, as in Calibre.
- My own columns work with or without the `#`: `#read:=Finished`, `pages:>500`.
- `and`, `or`, `not` and brackets combine them: `tags:fiction and not status:"=Read"`, or `(added:thisyear or rating:5) -formats:false`.

If Daf can't make sense of something, like a date it doesn't know, the box goes red and the page says what it didn't understand.

## The Tag browser

The **Tag browser** is Calibre's, in Calibre's order: Authors, Languages, Series, Formats, Publishers, Rating and Tags, then my own Calibre columns, then **Saved searches** (my views), each with how many books have each value. After those come Daf's own: status, shelves, **Added** (this week, this month, the last 30 days, this year or last year), **Missing** (no file, no cover, no tags, no rating, no series) and **Tidy**. **Find** at the top narrows the long lists.

Clicking a value adds it to the search, so I can see exactly what it did and change it by hand. Clicking it a second time turns it into "not that" (it gets a minus and a line through it), and a third click takes it out again. **Clear** empties the search.

## Views

When I have a search, an order and a set of columns I'll want again, **Views › Save as a view…** keeps them under a name. Views live on the server, so the same ones are on the Mac, the tablet and the phone, and picking one puts everything back the way it was. Once I change something, the button goes back to saying "Views", and **Save into "…"** updates the view I started from. **All books, newest first** goes back to the start.

## Export

**⋯ › Export as CSV** downloads exactly what's on the screen, in its order and with its columns, as a spreadsheet file that Numbers, Excel or Google Sheets opens.

## Editing a book

**Edit details** is on every Calibre book's page in Daf, and in All books when I right-click a row (or hold it on the tablet). It has everything Calibre's own edit window has: the title, the authors (separated by "&", the way Calibre does it), the series and the book's number in it, the tags, my rating, the publisher, the date it was published, the languages, the identifiers (one per line, like `isbn: 978…`), the description, and my own Calibre columns (Read, Pages, Collections and the rest). The tags are little chips: I type one and press Enter or a comma, pick one from the list Calibre already has, or press the × to take one off. Nothing changes until I press **Save** (or ⌘↩), and only the fields I actually touched are sent.

The rating takes half stars: a tap on the left half of a star gives half of it. **Title sort** and **Author sort**, under the title and the authors, are what Calibre sorts by; Calibre fills them in by itself, and they're there for the times its guess is wrong ("Handbook, The"). The **description** is edited as it looks, with **Bold**, **Italic** and **List** above it, and it's saved as Calibre keeps it, so a description with italics and lists keeps them after an edit.

The left side has the cover and the files. **Change cover** takes an image from the device, and **Cover from a link** takes the address of one on the web. Under **Files**, each format has a download button and a **⋯** menu with **Convert to** EPUB, AZW3, KEPUB, MOBI or PDF, and **Remove**. **Add a file** puts another format on the same book, or replaces the one it has. A conversion takes from a few seconds to a minute, and the file shows up in the list when Calibre is done.

## Editing the book itself

**Edit details** changes what Calibre knows about a book. **Edit book** changes the book itself: its chapters, its styles, its pictures and its table of contents, the way Calibre's own Edit book does on the Mac. It's on the book's page (in the **⋯** menu in the new look) for any book that has an EPUB, AZW3 or KEPUB, and in All books' toolbar when one book is chosen, the way Calibre has it in its own toolbar. If a book has more than one of those, it asks which one I want to edit, and EPUB is the usual answer.

Nothing I do in there touches Calibre until I press **Save**. Daf works on a copy of the book, and what I type goes into that copy a moment after I stop typing, so if I close the editor or the tablet goes to sleep, the copy is still there with my changes the next time I open Edit book on that book. **Close** keeps a copy that has changes and quietly throws away one that doesn't. **Discard changes**, in the **⋯** menu, throws the copy away, and the book in Calibre stays exactly as it was. If the book's file changed in Calibre in the meantime (I converted it again, say), Daf asks whether to keep my copy or start again from Calibre's.

The screen has three parts. On the left are the book's files, grouped the way Calibre groups them: **Text** in reading order, then **Styles**, **Images**, **Fonts** and **Other** (the OPF, the NCX and the rest). In the middle is the code, coloured the way a code editor colours HTML, CSS and XML, with undo for each file. On the right is a live preview of the chapter I'm in, with its styles and pictures, and it catches up whenever I stop typing. When I'm in a stylesheet, the preview keeps showing the last chapter, so I can watch what the CSS does to it. On the tablet held upright the preview sits under the code and the files slide in from **Files**, and on the phone **Files**, **Code** and **Preview** are tabs at the bottom. Tapping a picture shows it with its size. Each file's **⋯** has **Rename** and **Remove**, and Calibre fixes the links to a renamed file everywhere in the book.

**Search** opens find and replace, which works like Calibre's: in the current file, in all the text files, or in all the styles, with **Regex** and **Match case**. **Find** goes to the next match and moves on to the next file when this one runs out, **Replace** changes the one that's chosen and goes to the next, **Replace all** changes them all at once, and **Count** says how many there are and in how many files. The regular expressions are Calibre's kind, so `\1` in the replacement puts back what the first brackets found.

**Contents** shows the book's table of contents. I can rename an entry by typing in it, tap one to choose it and then move it up and down or in and out with the arrows, remove it, or tap the file name beside it to point it at another place. **Add** puts a new entry after the chosen one: I pick the chapter and then the spot in it (the top, or any heading or paragraph that has an id), and if I don't type a title it takes the heading's words. **Generate** builds the whole thing again from the major headings, from all the headings, or from the files, using Calibre's own code. Nothing is written until I press **Save** in that sheet.

**Check** runs Calibre's Check book and lists the errors, warnings and information it finds. Tapping one opens that file at that line and shows Calibre's explanation underneath. **Fix all** is there when Calibre knows how to fix some of them itself.

The **⋯** menu has Calibre's Polish tools: **Subset fonts**, **Compress images** (losslessly), **Remove unused CSS**, **Smarten punctuation** and **Upgrade book internals** (EPUB 2 to EPUB 3). Each one shows Calibre's report when it's done. **Add a file** puts a picture, a font, a stylesheet or a chapter into the book, next to the others of its kind. Before any tool changes the book, Daf keeps a checkpoint, so **Undo** in the report, or **Checkpoints** in the menu, goes back to how it was before.

**Save** (or ⌘S) has Calibre build the book again and put it in place of the file it came from, the same way adding a file does, so Calibre records it and the reader in Daf opens the edited book. An AZW3 is edited as an EPUB inside and saved as an AZW3 again, and a KEPUB is edited without Kobo's extra markup, which Calibre puts back on Save. Highlights I've made in Daf are anchored to their places in the book, so after big changes to a chapter's structure some of them may land a little off.

## Shelves and collections

Rows can be dragged onto shelves and onto Calibre's Collections: one row, or every chosen row at once. **Shelves** in the toolbar ticks them on and off instead. [Books and shelves](books-and-shelves.md#dragging-books-onto-shelves) has the details.

## Several books at once

In All books, each row has a box at its left. A click on a row chooses it the way a spreadsheet does: on its own, with ⌘ (or Ctrl) one more, and with Shift every row from the last one I clicked. On the tablet and the phone a tap adds the row or takes it out. The box in the header chooses everything the table shows.

With several books chosen, **Edit metadata** in the toolbar opens the sheet for all of them, which changes them all at once: the authors, the series (with **Number them from 1 in the table's order**, which is how I put a series in order: sort the table the way I want and then number), **Add tags** and **Remove tags** (the ones already on the chosen books are offered), the rating or **No rating**, the publisher, the date, the languages, and my own columns. Anything I leave empty stays as it is on each book.

In that sheet, **Series**, **Publisher** and **Languages** each have **None**, which clears that field on every chosen book. **Find and replace**, at the bottom, changes words in the title, the authors, the series, the tags or the publisher of every chosen book: what to find, what to put instead, and **Regular expression** and **Match case** when I want them. Under it, before anything is saved, each book that would change is listed with its old value struck through and its new one beside it.

**Convert books** in the toolbar turns every chosen book into EPUB, AZW3, KEPUB, MOBI or PDF, each from its best file (a book that has the format already is left alone; a toast says when they're done), and **Download** gives each book's EPUB (or its best other file): one book as itself, several in a zip. A book that only came as a KFX, the Kindle's own format, converts too, because Daf's Calibre has the same KFX Input plugin I have in Calibre on the Mac.

**EpubMerge** in the toolbar makes one new book out of the chosen books' EPUBs, a set of stories or a whole series in one file, and it does it the way Calibre's EpubMerge plugin does, because it is that plugin, running inside Daf's Calibre. The sheet lists the books in the order they'll go in (the series order when they're all in one series), and the arrows move a book up or down, while × takes it out. The title starts as the plugin's own, which is the series' name when they all share one and otherwise the first book's title with "Anthology" after it, and the authors are everyone's. I can change both. **Contents** keeps each book's chapters under its title in the table of contents, or puts them all on one level, and **Description** lists the titles, or the titles with each book's description. The cover is the first book's. The books I merged stay as they were, and the new one comes up chosen in All books when it's done. A book without an EPUB is shown greyed out and left out, so I convert it first.

## Find details

**Find details**, at the top of the edit sheet, is Calibre's own Download metadata, run by Calibre itself. It asks every source Calibre has on: Google and Amazon, plus the plugins I use in Calibre on the Mac too, Goodreads and Goodreads More Tags (which turns a book's Goodreads shelves into tags). Calibre merges what they say about the same edition and puts the answers in its own order, and Daf shows them that way, with the sources each answer came from. Hardcover's answers come after Calibre's, only the ones that are surely the same book. Calibre's built-in sources are kept up to date once a day, the way the Calibre app updates them for itself, so they work the way they do on the Mac. It takes up to half a minute, and the title and author at the top can be changed and searched again when the book's own are wrong.

Picking an answer also asks every cover source for that edition (Amazon, Google, Goodreads, Open Library and Apple Books covers), like Calibre's cover grid: each cover with where it came from and its size, the biggest first, beside the one the book has now. I tap the one I want.

Picking an answer puts it side by side with what the book has now, one row a field. The ones the book is missing are ticked already, and the rest I tick myself. Rows where both say the same thing are greyed out. Tags are added to the ones the book has rather than replacing them, and identifiers only add the kinds the book doesn't have yet. **Use these** puts it all into the edit sheet so I can look it over before I **Save**, and puts the chosen cover on the book. The covers come through Daf's server, so the tablet never talks to Amazon or Google itself.

## Find details for many books

With several books chosen in All books, **Find details** in the toolbar looks all of them up at once and fills in only what each one is missing. I tick what to fill in (publisher, date, description, tags, series, languages, identifiers, pages and cover), and **Look up** goes through the books four at a time, asking Calibre's sources the way its own bulk Download metadata does (every source it has on), then Hardcover. For a book without a cover, Calibre picks the best cover from all its cover sources. It takes several seconds a book.

It only takes an answer when it's surely the same book: the same title (subtitles aside) by the same author, so a study guide or a different book with a similar name never gets in. A field the book already has is never changed, tags are only added to a book that has none, and identifiers only add kinds the book doesn't have, so a wrong ISBN stays until I fix it myself. The results list each book with what would go in and where it came from. I untick any I don't want, and nothing changes until **Save**. Books with nothing to fill in are listed at the bottom, with why.

## Importing a list

**⋯ › Import list**, at the top of All books, does what Calibre's Import List plugin does on the Mac. I give it a list of books from somewhere else, it finds the ones I already have, and then I decide what happens to both kinds: the ones I don't have can come in as empty books (a Calibre record with no file yet), and the ones I do have can get a tag or go on a shelf.

The list can come in four ways. **Text** is for anything I can paste: one book a line, written as "Middlemarch by George Eliot", "George Eliot - Middlemarch", "Middlemarch - George Eliot", "Middlemarch / George Eliot" or "Middlemarch (George Eliot)", or columns copied out of a spreadsheet, or just an ISBN. A number at the start of a line ("12.") is dropped, and a series written the Goodreads way, "(Coastal Fictions, #2)", becomes the series and its number. On **Automatic** each line is read on its own, and when a dash could go either way, Daf goes the way the rest of the list goes and checks it against the authors I already have. When the whole list is in one form I can pick that form instead, and **Pattern** takes a regular expression with named parts, `(?P<title>…)`, `(?P<authors>…)`, `(?P<series>…)`, `(?P<series_index>…)`, `(?P<isbn>…)` and `(?P<published>…)`, the way the plugin does. An ISBN on its own gets its title and author from Hardcover.

**File** takes a CSV or tab-separated file, like the exports from Goodreads or StoryGraph or a spreadsheet of my own. Daf guesses the separator and which column is which from the headings and shows the first rows, and I can change any of it before going on.

**Web page** fetches a page and picks the books out of it. The **Site** list has the plugin's ready-made pages that still work: Amazon's bestsellers and new releases by genre (the US and the UK), Goodreads' lists, shelves, awards, most read and popular this month or this year, the New York Times e-book bestsellers, and Wikipedia's Hugo and Nebula winners. Any other page of those sites works too, because Daf knows them by their address, and `{1-5}` in an address reads pages 1 to 5. For a site Daf doesn't know, **XPath** takes the plugin's XPaths for the rows and for each field. Amazon and Goodreads only send the first part of a long page to a plain fetch, so an Amazon bestseller list gives the top 30 and Goodreads' popular pages the top 15. The New York Times turns Daf away now and then, and trying again a little later usually works. Fantastic Fiction, which the plugin also had, now asks every visitor to prove they're a person, so it isn't there.

**Hardcover** lists my Hardcover lists and my shelves there (Want to read, Currently reading, Read and the rest).

**Next** shows every book on the list beside what it matched in the library. Daf matches the way the plugin does: by the ISBN or the Hardcover or Goodreads id first, then by title and author from strict to forgiving, so capitals, accents, a "The" at the start, punctuation, a subtitle and initials don't get in the way, and "Eliot, George" is the same as "George Eliot". The little label on each match says how it was found: Exact, Close, Loose, Title (the list had no author) or the identifier it went by. When the library has two copies, both are in a list to choose from. The list's title and author can be fixed right in the row, and Daf matches it again. **Change** (or **Find**, for a book with no match) searches the library to pick the right book by hand, or sets it to **Not in the library**. A row I untick is left out of everything, and the buttons at the top show all the rows, only the ones in the library, or only the ones that aren't.

**Next** again is what to do with them. For the books that aren't in the library, **Add as empty books** makes a Calibre record for each one with the title, the authors and whatever else the list had (the series and its number, the date, the ISBN and the Hardcover or Goodreads id), the same as Calibre's own Add empty book. **Read: Planning** puts them on my Read column's Planning, and a **Tag** and a **Shelf** can go on them too (one of Daf's own shelves, since Hardcover doesn't know an empty book yet). For the books already in the library, I can add a **Tag** or put them on a **Shelf**, a Hardcover list included, or on a **New shelf…**. The Kindle's shelves aren't offered, since an empty book has no file to send. Nothing changes until **Import**. When it's done, **Show in All books** shows the new books with all of them chosen, ready for **Find details** to fill in their descriptions and covers.

## Tags, authors and series

**⋯ › Tags, authors and series** lists every tag, author, series, publisher and my own name columns (Collections, Reading) across the whole library, each with how many books have it. Clicking the number shows those books in the table.

At the top, **Look alike** groups names that are probably the same thing written differently: "Self Help", "Self-Help" and "selfhelp"; "Thriller" and "Thrillers"; "J. R. R. Tolkien", "J.R.R. Tolkien" and "J R R Tolkien"; "Patai, Raphael" and "Raphael Patai". Each group has the name to keep (the most used one first) and **Combine**. Clicking any name lets me rename it right there, and renaming it to a name that already exists combines the two. With several ticked, the bar at the bottom has **Combine** and **Delete** (a tag, series or publisher comes off every book that has it; an author can only be renamed). When an author's name changes, Calibre moves the books' folders to match.

## The details inside the book files

Calibre keeps a book's details in its database, but each EPUB, AZW3 or PDF also carries its own copy inside it, and that copy is what the Kindle and other reading apps show. Whenever Daf changes a book (an edit, a cover, a combined tag, filled-in details, a merge), Calibre writes the new details into that book's files too, a minute or so later and in the background, so a big edit doesn't wait for it. **⋯ › Write details into every file** does it for the whole library at once, which is worth doing once so the files match what Calibre has. While it's working, the ⋯ menu says how many are left.

A book that's already on the Kindle keeps its old copy until it's sent again.

## Tidying the library

The **Filter** panel has a **Tidy** group next to **Missing**. **Possible duplicates** finds books with the same title (subtitles and punctuation aside) by the same author. **Odd characters** finds titles with garbled letters, like "â€™" where an apostrophe should be. **Last name first** finds authors written as "Patai, Raphael", which Calibre then files under a folder of that name. To fix those in one go, I choose them all and tick **Turn "Last, First" names around** in the multi-book editor. Names like "…, Inc." or "…, Ph.D." are left alone.

With two or more books chosen, **Merge books** and **Remove books** in the toolbar work on them. **Merge books** is for copies of one book. I pick the copy to keep (Daf suggests the one with a cover and the most files), and it takes the others' files it doesn't have yet, their tags and identifiers, and anything else it was missing. Then the others go. In Daf, their highlights, shelves, notes and my place in them move over to the kept copy. **Remove** takes books out of Calibre, and so does **Remove from Calibre** at the bottom of the edit sheet. Daf says first if a book has highlights, which stay in Daf.

Nothing is lost straight away. Removed and merged books go to Calibre's own trash, and **⋯ › Calibre's trash** lists what's there, newest first, with **Put back**, which returns a book exactly as it was, files and all. Calibre empties its trash after a couple of weeks.

## Check library

**Library › Check library**, in the toolbar, compares Calibre's records with its folders, the way Calibre's own Check library does, and changes nothing: files a book lists that aren't there, books without a file, covers missing, a book's folder missing, book files in a folder that its book doesn't list, and folders no book points to. Each book in the list opens its page.

Under those it lists what Calibre's Quality Check plugin would: books with no description, no ISBN, no page count or no language, titles in capitals, and books by "Unknown". And **Read column differs from Daf** lists the books where Calibre's Read column and the book's status in Daf disagree (Calibre says Dropped, Daf says To read), with both, to settle by hand.

## What Daf keeps up in Calibre

At each sync Daf keeps a few things in Calibre in step, through Calibre itself:

- **The Read column** follows each book's status in Daf (which follows Hardcover and the book's note): To read is Planning, Reading is Reading, Read is Finished, Paused is Paused, Dropped is Dropped. A book with nothing in the column gets Daf's status, and from then on, when the status changes in Daf (I start a book, finish it), the column follows. Where the two already disagreed, Daf leaves the column alone and Check library lists the book. Maybe counts as agreeing with To read.
- **The KOReader columns**, the two that Calibre's KOReader Sync plugin fills: **KOReader Progress** shows how far I am in each book, the way Daf knows it from everywhere I read (the Kindle, Daf's own reader), and **Reading** shows the status in KOReader's words: reading, complete, or abandoned (KOReader's On hold) for a paused book. To read and Dropped have no KOReader word, so Daf leaves that column alone for those books.
- **Page counts**: a book with an EPUB and nothing in the Pages column gets one, counted the way Calibre's Count Pages plugin does by default (its text, about 2,170 characters a page), a few books each sync. For any chosen books, **Library › Count pages** counts them again.

`calibre_keep: false` in the settings turns all of it off.

## How Daf changes Calibre

Daf reads Calibre's database directly for the table, and reads it again only when the file changes, so the table is quick even with the whole library in it.

Daf never writes to that database itself. Every change goes to Calibre: Daf runs a short script with Calibre's own tools inside the Calibre-Web Automated container, and Calibre does the work the same way it would in its own window. That means the book's folder moves when the title or the author changes, the sort fields follow, covers are stored the way Calibre stores them, and the `metadata.opf` file beside each book is written again. One change runs at a time. Calibre-Web Automated's own imports go through Calibre too, so the two never write over each other.

Calibre-Web Automated fills in details from the web only for books it's importing, so it doesn't undo what I've edited. Its weekly Hardcover refresh of the whole library is off, and it should stay off for the same reason.
