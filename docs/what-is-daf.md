<sub>[Daf docs](README.md) › Getting started</sub>

# What is Daf?

Daf is my reading app for one goal: an hour of reading a day for a year, from October 9, 2026, to October 8, 2027, which I call Year 30. It counts the minutes from everywhere I read, puts them in one ring, and brings my highlights back so the reading stays with me. "Daf" is Hebrew for a page, as in daf yomi, the page a day.

![Today in Daf](images/hero-light.png)
*Today: the ring, where the minutes came from, the sittings, and the daily review.*

## What it does

Most of my reading never happened in one app. Books are on a Kindle with KOReader, audiobooks are in Audiobookshelf, some books are on paper, and articles were in Read You and Readwise. Each of those knew a piece, and none of them could tell me whether I'd read for an hour today. Daf reads all of them and adds it up on the **Today** page.

Then it's a reader of its own, built after Readwise Reader. The Feed is my FreshRSS, the Library is Daf's own (it was my Karakeep), and every book in my Calibre library opens in Daf's own EPUB reader. Time spent reading in Daf counts too, so it doesn't matter where I pick up.

The third part is the highlights. Every highlight from every source ends up in one place: the Kindle's, the ones I make in Daf, the ones I make on web pages with the browser extension, audiobook bookmarks, photos of pages I marked in pencil, and the years of Readwise highlights from before. Five of them come back every day in the **Daily review**, and the first one comes to my phone in the morning.

Basically, instead of five apps that each know a little, I have ONE place that knows what I read, how long, and what I wanted to remember.

## What works where

Daf is a web app first. The Mac, Windows and Android apps wrap the same page and add what a web page can't do, and the Kindle has its own plugin.

| | Web | Mac app | Windows app | Android app | Kindle | Extension |
|---|---|---|---|---|---|---|
| Today, review, highlights, stats | Yes | Yes | Yes | Yes | Today's minutes, the review and the nightstand on the Daf tab | No |
| Reading books and articles | Yes | Yes | Yes | Yes | Books in KOReader | No |
| Reading time counted | While a reader is open | While a reader is open | While a reader is open | While a reader is open | Every page turn | No |
| Today's minutes always in sight | No | The menu bar | By the clock | The home-screen widget | The sleep screen | No |
| Saving links into Daf | The share menu, once installed | The share menu | Save a Link…, `daf://save` | The share sheet | No | The toolbar button, the right-click menu, Alt+Shift+S |
| Highlighting web pages | No | Safari, with the extension | No | No | No | Firefox, Zen, Chrome, Arc |
| Reading with no signal | Pages opened before, on https | Its own copy of Daf, what I'm reading and what I keep | Its own copy of Daf, what I'm reading and what I keep | Its own copy of Daf, what I'm reading and what I keep | Always | No |
| Notifications for new posts | No | Yes | Yes | Yes | No | No |

## What it connects to

Daf reads a lot of things it doesn't own, and it only changes something in them when you press the button for it, like marking an item read or unfollowing a feed in FreshRSS.

- **KOReader** on the Kindle, through the Daf plugin. The years before it came from KoInsight, which is retired now; that history is in Daf.
- **Audiobookshelf**, for listening time and bookmarks, read-only.
- **Calibre** (Calibre-Web-Automated), for the books, covers and files, read-only.
- **FreshRSS**, the Feed, through its Google Reader API.
- **Karakeep**, retired: the Library came from it in October 2026, and it's switched off now.
- **Hardcover**, for reading status, ratings, progress and lists.
- **Komga**, for manga.
- **AntennaPod**, which syncs podcasts to Daf as if Daf were gpodder.net.
- **Proton Mail Bridge**, for the newsletters I pick, read-only, and to send me the morning email.
- **My Obsidian vault**, where Daf writes highlights, notes and the paper reading log.
- **Sefaria**, for the parasha, the haftarah and the Hebrew dictionaries.
- **Kokoro**, running on my server, for read-aloud.
- **Claude**, on my own subscription, for Ask, the short summaries, the tags on what I save, flashcard suggestions and reading photos of paper pages.
- **A headless Chrome** on my server, for the saved pages that only show themselves to a real browser.
- **GitHub**, where **Send feedback** files its notes as issues.
- **Signal**, through my own bot, Ezer, for the morning highlight and for logging paper minutes.

## Next step

If you want to try it, start with [Install](install.md). If you'd rather see it in use first, read [A day with Daf](how-i-use-it.md).

<sub>Next: [A day with Daf](how-i-use-it.md) →</sub>
