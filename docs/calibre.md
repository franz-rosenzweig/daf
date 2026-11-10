<sub>[Daf docs](README.md) › Using Daf</sub>

# Calibre in Daf

My books live in Calibre. Calibre-Web Automated runs it on the server, takes in new files and converts them, and for a long time I opened Calibre on the Mac whenever I wanted to look through the library properly. I'd rather do all of that in Daf, next to the reading, so Daf is slowly taking over Calibre's jobs. This page covers what's there so far.

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

## How it reads Calibre

Daf reads Calibre's database directly and never writes to it here. It reads it again only when the file changes, so the table is quick even with the whole library in it.
