<sub>[Daf docs](README.md) › Using Daf</sub>

# Calibre in Daf

My books live in Calibre. Calibre-Web Automated runs it on the server, takes in new files and converts them, and for a long time I opened Calibre on the Mac whenever I wanted to look through the library properly or fix a book's details. I'd rather do all of that in Daf, next to the reading, so Daf has taken over Calibre's jobs: the library as a spreadsheet with Calibre's search, editing one book or many, covers, files and conversions, finding details online for one book or many, renaming and combining tags, authors and series across the library, writing the details into the book files, and tidying: duplicates, merging, removing and Calibre's trash.

## All books

**All books**, at the top of **Books**, is the whole library as a spreadsheet: one row a book, with the columns I choose. Every book Calibre has is there, including the ones without a file yet, and next to Calibre's own fields it has what Daf knows: the status from the book's vault note, how far along I am, when I last read it, how many highlights it has, and which shelves it's on. Private books stay out unless I turn on **Show private books** in the **⋯** menu.

Clicking a column's name sorts by it, and clicking again turns the order around. It opens on **Added**, newest first, so whatever came in lately is at the top. Dragging the edge of a column's name makes it wider or narrower, and on the Mac or a laptop I can drag the name itself to move the column. **Columns** lists everything there is: Calibre's fields (title, authors, series, tags, rating, the dates, publisher, language, formats, size, ISBN, identifiers, cover), my own Calibre columns (Read, Pages, Collections and the KOReader ones), and Daf's. I tick the ones I want and drag them into order there too, which is the way to do it on the tablet.

The title opens the book's page in Daf, and so does a double-click anywhere on the row. When I come back, the table is where I left it.

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

## Filter

**Filter** opens Calibre's tag browser beside the table, and on the tablet and phone as a sheet from the bottom. It has quick ones (**Added** this week, this month, the last 30 days, this year or last year, and **Missing**: no file, no cover, no tags, no rating, no series) and then every status, tag, author, series, format, language, publisher, rating, shelf and Calibre column, each with how many books have it. **Find a value** narrows the long lists.

Clicking a value adds it to the search, so I can see exactly what it did and change it by hand. Clicking it a second time turns it into "not that" (it gets a minus and a line through it), and a third click takes it out again. **Clear** empties the search.

## Views

When I have a search, an order and a set of columns I'll want again, **Views › Save as a view…** keeps them under a name. Views live on the server, so the same ones are on the Mac, the tablet and the phone, and picking one puts everything back the way it was. Once I change something, the button goes back to saying "Views", and **Save into "…"** updates the view I started from. **All books, newest first** goes back to the start.

## Export

**⋯ › Export as CSV** downloads exactly what's on the screen, in its order and with its columns, as a spreadsheet file that Numbers, Excel or Google Sheets opens.

## Editing a book

**Edit details** is on every Calibre book's page in Daf, and in All books when I right-click a row (or hold it on the tablet). It has everything Calibre's own edit window has: the title, the authors (separated by "&", the way Calibre does it), the series and the book's number in it, the tags, my rating, the publisher, the date it was published, the languages, the identifiers (one per line, like `isbn: 978…`), the description, and my own Calibre columns (Read, Pages, Collections and the rest). The tags are little chips: I type one and press Enter or a comma, pick one from the list Calibre already has, or press the × to take one off. Nothing changes until I press **Save** (or ⌘↩), and only the fields I actually touched are sent.

The left side has the cover and the files. **Change cover** takes an image from the device, and **Cover from a link** takes the address of one on the web. Under **Files**, each format has a download button and a **⋯** menu with **Convert to** EPUB, AZW3, KEPUB, MOBI or PDF, and **Remove**. **Add a file** puts another format on the same book, or replaces the one it has. A conversion takes from a few seconds to a minute, and the file shows up in the list when Calibre is done.

## Shelves and collections

Rows can be dragged onto shelves and onto Calibre's Collections: one row, or every chosen row at once. **Shelves** in the bar at the bottom ticks them on and off instead. [Books and shelves](books-and-shelves.md#dragging-books-onto-shelves) has the details.

## Several books at once

In All books, each row has a box at its left. A click on a row chooses it the way a spreadsheet does: on its own, with ⌘ (or Ctrl) one more, and with Shift every row from the last one I clicked. On the tablet and the phone a tap adds the row or takes it out. The box in the header chooses everything the table shows.

When anything is chosen, a bar comes up at the bottom with **Edit N books**. That sheet changes them all at once: the authors, the series (with **Number them from 1 in the table's order**, which is how I put a series in order: sort the table the way I want and then number), **Add tags** and **Remove tags** (the ones already on the chosen books are offered), the rating or **No rating**, the publisher, the date, the languages, and my own columns. Anything I leave empty stays as it is on each book.

## Find details

**Find details**, at the top of the edit sheet, asks two places at once: Hardcover, which Daf is already connected to, and Calibre's own download sources (Google, Amazon, Edelweiss and Open Library). It takes up to half a minute. The answers come back as a list with their covers, and the title and author at the top can be changed and searched again when the book's own are wrong.

Picking an answer puts it side by side with what the book has now, one row a field. The ones the book is missing are ticked already, and the rest I tick myself. Rows where both say the same thing are greyed out. Tags are added to the ones the book has rather than replacing them, and identifiers only add the kinds the book doesn't have yet. The found cover can be ticked too. **Use these** puts it all into the edit sheet so I can look it over before I **Save**. The covers in the list come through Daf's server, so the tablet never talks to Amazon or Google itself.

## Find details for many books

With books chosen in All books, **Find details** in the bar at the bottom looks all of them up at once and fills in only what each one is missing. I tick what to fill in (publisher, date, description, tags, series, languages, identifiers, pages and cover), and **Look up** goes through the books four at a time, asking Hardcover and Calibre's quicker sources (Google, Open Library and Edelweiss). It takes a few seconds a book.

It only takes an answer when it's surely the same book: the same title (subtitles aside) by the same author, so a study guide or a different book with a similar name never gets in. A field the book already has is never changed, tags are only added to a book that has none, and identifiers only add kinds the book doesn't have, so a wrong ISBN stays until I fix it myself. The results list each book with what would go in and where it came from. I untick any I don't want, and nothing changes until **Save**. Books with nothing to fill in are listed at the bottom, with why.

## Tags, authors and series

**⋯ › Tags, authors and series** lists every tag, author, series, publisher and my own name columns (Collections, Reading) across the whole library, each with how many books have it. Clicking the number shows those books in the table.

At the top, **Look alike** groups names that are probably the same thing written differently: "Self Help", "Self-Help" and "selfhelp"; "Thriller" and "Thrillers"; "J. R. R. Tolkien", "J.R.R. Tolkien" and "J R R Tolkien"; "Patai, Raphael" and "Raphael Patai". Each group has the name to keep (the most used one first) and **Combine**. Clicking any name lets me rename it right there, and renaming it to a name that already exists combines the two. With several ticked, the bar at the bottom has **Combine** and **Delete** (a tag, series or publisher comes off every book that has it; an author can only be renamed). When an author's name changes, Calibre moves the books' folders to match.

## The details inside the book files

Calibre keeps a book's details in its database, but each EPUB, AZW3 or PDF also carries its own copy inside it, and that copy is what the Kindle and other reading apps show. Whenever Daf changes a book (an edit, a cover, a combined tag, filled-in details, a merge), Calibre writes the new details into that book's files too, a minute or so later and in the background, so a big edit doesn't wait for it. **⋯ › Write details into every file** does it for the whole library at once, which is worth doing once so the files match what Calibre has. While it's working, the ⋯ menu says how many are left.

A book that's already on the Kindle keeps its old copy until it's sent again.

## Tidying the library

The **Filter** panel has a **Tidy** group next to **Missing**. **Possible duplicates** finds books with the same title (subtitles and punctuation aside) by the same author. **Odd characters** finds titles with garbled letters, like "â€™" where an apostrophe should be. **Last name first** finds authors written as "Patai, Raphael", which Calibre then files under a folder of that name. To fix those in one go, I choose them all and tick **Turn "Last, First" names around** in the multi-book editor. Names like "…, Inc." or "…, Ph.D." are left alone.

With two or more books chosen, the bar at the bottom also has **Merge** and **Remove**. **Merge** is for copies of one book. I pick the copy to keep (Daf suggests the one with a cover and the most files), and it takes the others' files it doesn't have yet, their tags and identifiers, and anything else it was missing. Then the others go. In Daf, their highlights, shelves, notes and my place in them move over to the kept copy. **Remove** takes books out of Calibre, and so does **Remove from Calibre** at the bottom of the edit sheet. Daf says first if a book has highlights, which stay in Daf.

Nothing is lost straight away. Removed and merged books go to Calibre's own trash, and **⋯ › Calibre's trash** lists what's there, newest first, with **Put back**, which returns a book exactly as it was, files and all. Calibre empties its trash after a couple of weeks.

## How Daf changes Calibre

Daf reads Calibre's database directly for the table, and reads it again only when the file changes, so the table is quick even with the whole library in it.

Daf never writes to that database itself. Every change goes to Calibre: Daf runs a short script with Calibre's own tools inside the Calibre-Web Automated container, and Calibre does the work the same way it would in its own window. That means the book's folder moves when the title or the author changes, the sort fields follow, covers are stored the way Calibre stores them, and the `metadata.opf` file beside each book is written again. One change runs at a time. Calibre-Web Automated's own imports go through Calibre too, so the two never write over each other.

Calibre-Web Automated fills in details from the web only for books it's importing, so it doesn't undo what I've edited. Its weekly Hardcover refresh of the whole library is off, and it should stay off for the same reason.
