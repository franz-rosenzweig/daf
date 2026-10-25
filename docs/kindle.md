<sub>[Daf docs](README.md) › Devices</sub>

# The Kindle

The Kindle is where I read most of my books, in KOReader, and the Daf plugin for KOReader is what connects it to everything else. It sends the reading time and my highlights, puts today's minutes on the sleep screen, gives KOReader a Home page, Shelves and a Daf tab with the review and the nightstand, and carries my place and my highlights between the Kindle and Daf. To install it, see [Install](install.md#the-kindle-plugin).

## What it sends

The plugin sends KOReader's page turns to Daf when the Kindle goes to sleep, when you close a book, and when Wi-Fi connects. With Wi-Fi off they wait on the Kindle and go next time, so nothing is lost. A sitting shows up on Today a few seconds after the Kindle sleeps, which is the easiest way to check that everything works.

The highlights go with the reading time. KOReader keeps them in a notes file next to each book, and the plugin sends each book's highlights and notes whenever that file has changed, plus the book that's open, straight from memory. The first time, it sends every book in the history at once, a few dozen per send. A highlight you delete on the Kindle goes from Daf too. (Before October 2026 Daf read the notes files from a Syncthing copy and from KoInsight; the highlights KoInsight collected still fill in older books.)

## The menu

Everything is under **Tools → Daf**:

- **Home:** opens Home, below.
- **Open Home when KOReader starts and after a book:** on or off.
- **Open Daf:** the Daf tab, below.
- **Get my place and highlights from Daf:** for the book that's open, does by hand what normally happens when you open it.
- **Today: 38 of 60 minutes:** the count, at a glance.
- **Send reading time and highlights now:** sends the page turns and any changed highlights right away. It says "Sent N page turns to Daf" or "Daf is up to date", and how many books' highlights went.
- **Show today's minutes on the sleep screen:** on or off. Turning it off puts back the screensaver message you had before.
- **Open Daf on the first wake of the morning:** the first time you wake the Kindle each morning, it opens on the Daf tab.

Three actions are also in KOReader's gestures, under **Gestures → pick a gesture → General**: "Daf: open Home", "Daf: open the Daf screen" and "Daf: send reading time".

## Home

Home is what the Kindle opens to: when KOReader starts and whenever I close a book. It's drawn for e-ink in black and white, and in night mode it's white on black like the rest of KOReader, with the book covers keeping their own look.

- **The top line:** the time, the date with the Hebrew date (like "9 Cheshvan"), and the battery.
- **Today:** today's minutes toward my goal in Daf ("2 of 90 minutes") with a bar under it, how many are left, and Year 30 so far. The goal is whatever the main minutes goal is in Daf's Goals, and the Kindle picks up a change the next time it's on Wi-Fi. Tap it for the Daf tab. On the right, "Shabbat: Lech-Lecha ›" opens the Torah shelf.
- **Continue reading:** the book I was in last, big, with how far I am, when I last read it, and **Resume**.
- **Lately:** the next five books from KOReader's history, with how far I am in each, and **History ›**.
- **The bar at the bottom:** Home, **Shelves**, **History**, **Daf** (the review and the nightstand) and **Search**.

That's all on purpose: the review lives on the Daf tab and the shelves on Shelves. The house icon at the top of KOReader's file browser opens Home too, so it's always one tap away.

### Gestures

KOReader's gestures work on Home, Shelves and the Daf tab the way they do in the file browser: the edge swipes for the frontlight and its warmth, two-finger swipes, multiswipes, holding a corner, and tapping a corner. The one exception is a tap on the bar at the bottom: the Home and Search buttons sit in the bottom corners, so a tap there is the button. Over a book, the book's own gestures apply.

### KOReader's menu, with everything in it

On Home, Shelves and the Daf tab, KOReader's menu is where it always is: swipe down from the top edge, or tap the line with the time. It's the whole menu, with every plugin's settings in it.

Some of KOReader's settings normally only show up while a book is open, even though they're for every book. The plugin puts them in the menu outside a book too, in the same places: **Settings → Status bar**; **Settings → Taps and gestures → Links**, **Page turns** and **Long-press on text**; and **Search → Settings → Translation settings** and **Fulltext search settings**. What you change there is what the next book opens with. Things that really are about one book (fonts, margins, the table of contents) are still only in the book.

### Shelves

**Shelves** shows the folders in the home folder as big tiles with their drawings and how many books each has, the Nightstand first. A folder opens as its books, three across and two down, a page at a time: swipe, or tap ‹ and ›. A folder inside it shows first, as a tile, and opens the same way. Each book has its cover, its title, and either a dot for New, how far I am, or ✓ Finished. At the top are the order (Newest first, Title, Author, Last read; tap to change it), **All**, **Reading**, **New** and **Finished**. ‹ at the top goes back up, and from the top back to Home.

The covers come up with the page, all at once. Most of them come from the ones Project: Title already saved on the Kindle, which means nothing has to open the books, and while I'm looking at a page the next one gets its covers ready, so swiping is instant too. A book nothing has a cover for yet (a new download, say) gets opened ONCE in the background to find it, and its cover shows up a moment later while I can keep tapping around. After that the Kindle keeps it, even if I move the book to another shelf.

Everything KOReader's file browser does with files works here too:

- **Hold a book or a shelf** for KOReader's own dialog: Cut, Copy, Paste, Rename, Delete, Select, the book's status (Reading, On hold, Finished), Collections, Book information, the cover and the description.
- **Move to shelf…**, at the bottom of that dialog, lists every shelf (shelves inside shelves are indented); tap one and the book goes there, with its highlights and its place. It's in the dialog in KOReader's own file browser, history and search too.
- **After Cut or Copy**, every shelf you open shows a bar, "Moving: Meditations", with **Put it here** and **Cancel**.
- **Files ▾** has **New shelf here…**, **Select several…** (KOReader's browser at that folder, ready to pick several books and move or delete them together) and **Open in the file browser**.

A book on my private list never shows on Home, in Continue reading or in Lately, and on a shelf it's just its file name with no cover. A few seconds after Home comes up, the Kindle quietly gets every book's shelf cover ready, a few at a time between taps, and it waits whenever I'm reading. Basically, after the first day, every shelf opens with its covers already there. It works with Wi-Fi off from the last answer Daf gave; the Hebrew date and the parasha show once Daf has answered that day.

## The sleep screen

When the Kindle sleeps, the screensaver message becomes three lines: "Daf", then today's minutes, like "38 of 60 minutes today" or "That's the hour: 64 minutes today", then "Year 30, day N · H hours so far". It counts the Kindle's own minutes even with Wi-Fi off, plus what Daf said about the rest of the day the last time it had a connection.

## The Daf tab

The Daf tab is Daf drawn for e-ink, in black and white, like Home, with the bar at the bottom:

- **Today:** the minutes "of 60 minutes today" with "That's the hour." or how many to go, then the Kindle's share and everything else, and Year 30 so far. A line says when it last heard from Daf, with **Refresh**.
- **Review:** today's highlights one at a time, with **‹**, **Less often**, **Keep** and **›**, or swipe across it. It says "N of M done", and what you do here counts exactly like the review in Daf. A short highlight gets bigger type.
- **Nightstand:** the three books on your nightstand, or the books lately on the Kindle if it's empty. Tap one to open it.

It draws from the last answer it got, so it works with Wi-Fi off too, and taps made offline are sent on the next sync.

## Your place, both ways

When you open a book in KOReader, the plugin asks Daf about it. If you read further in Daf's own reader since the last page turn on the Kindle, and it's more than a percent away, the Kindle asks "You read further in Daf: 45%, “Chapter 4” (Oct 11, 21:40). Go there?", with **Go there** and **Stay here**. **Stay here** is remembered, so it won't ask again for that spot.

It works the other way in Daf: if the Kindle is further along, Daf's reader offers to go to the Kindle's page.

## Highlights, both ways

Highlights you make in Daf's reader are added to the book on the Kindle as KOReader highlights, with their notes, the next time you open it, and the Kindle says "Added 3 highlights you made in Daf". KOReader draws every color gray, so on the Kindle they all look the same. If an edition is different enough that a highlight can't be found, it says so.

Highlights you make on the Kindle come into Daf, into the review, the book's Notebook and the vault. A voice note or a "n:" text to my Signal bot while I'm reading goes under the book that's open on the Kindle, at the page I'm on.

## Books from Daf

Syncthing is off on the Kindle, so the Kindle picks up new books from Daf by itself. When I put a book on the Kindle from Daf, it waits there until the next time the Kindle syncs over Wi-Fi: when Wi-Fi comes on, when I close a book, when Home refreshes, or when I press **Send reading time and highlights now** in Tools → Daf. Then the Kindle downloads it into the shelf I picked, makes that shelf if it isn't there yet, and a short message says "Daf put 2 books on your Kindle." Any shelf I have open updates by itself, and the new book gets its cover a moment later.

The download happens in the background, which means I can keep reading or tapping around while a big file comes in, and it never downloads while the Kindle is going to sleep. If the book is already on that shelf, the Kindle just tells Daf it's there. If a DIFFERENT file by that name is already there, it leaves the one on the Kindle alone, and the same goes for a file over 200 MB, one there isn't room for, or one that comes in broken: Daf gets told why, and it tries again on the next sync.

The Kindle also tells Daf which shelves it has, so the shelf list in Daf is the Kindle's real one.

## Articles on the Kindle

**Send to the Kindle** in Daf makes an EPUB of one article or a digest of several, and it comes in with the Kindle's next Wi-Fi sync, into a "Daf" shelf (see [The Feed and the Library](feed-and-library.md#send-to-kindle)). Reading it counts as reading those articles, and highlights come back to them.

If something seems stuck, wake the Kindle with Wi-Fi on, open **Tools → Daf**, and press **Send reading time now**.

<sub>Next: [The Mac app](mac.md) →</sub>
