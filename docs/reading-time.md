<sub>[Daf docs](README.md) › Using Daf</sub>

# Where the minutes come from

This page explains where each of Today's minutes comes from, what counts toward the goal and what doesn't, and what to check when a number looks wrong. The short version: Daf adds up the Kindle, audiobooks, paper books and everything you read in Daf itself, and it leaves podcasts out.

## The Kindle

Kindle minutes come from KOReader's page turns. The Daf plugin sends them when the Kindle goes to sleep, when you close a book and when Wi-Fi connects, and it keeps them on the Kindle until then, so reading with Wi-Fi off loses nothing. Before the plugin existed Daf read KoInsight's stats database. All of that history is in Daf now, and KoInsight itself is retired (October 2026).

Page turns less than ten minutes apart make one sitting. If you have two copies or two editions of the same book on the Kindle, Daf treats them as one book (it matches them to the Calibre book by title), but it never mixes their page numbers, so the progress is always the copy you're actually reading.

## Audiobooks

Listening time comes from Audiobookshelf, which Daf reads every five minutes without changing anything in it. Audiobookshelf's own podcast library is a different thing: it's stored, never named, and never counted.

## Paper books

Paper minutes are the only ones Daf can't see for itself, so you tell it: **Log paper** on Today, or a text message to the Signal bot if you have one like mine. They go into a reading log note in the vault, which is the real record, and Daf reads them back from there. [Paper books](paper-books.md) has the details, including Shabbat.

## Reading in Daf

Time with a book, an article, a PDF or a manga volume open in Daf counts too. While you're reading, the page sends a short "I'm reading" signal every 15 seconds; Today and Stats show the time, nothing over the text does. It stops when you stop:

- an article counts while you've scrolled, clicked or pressed a key in the last minute and a half, and a book in the last two minutes;
- read-aloud counts the whole time it's playing, even if you're not touching anything;
- a hidden tab, a minimized window or a phone in your pocket counts nothing.

If you read with no signal, the minutes wait on the device and go to Daf with their own time once the network is back, so they land on the right day.

On Today these show up as "Books in Daf", "Articles in Daf" and "Manga in Daf". Each article is one sitting a day, however many times you open it.

## What counts toward the goal

**Preferences → What counts toward the goal** has a switch for each source:

- **Books on the Kindle**, KOReader reading time
- **Manga in Daf**
- **Audiobooks**, listening time from Audiobookshelf
- **Articles in Daf**
- **Paper books**
- **Videos**, time with a video open in Daf, off unless you switch it on
- **Podcasts**, never counted

Books read in Daf always count, so there's no switch for them. A source you switch off still shows on Today with its minutes, marked "not counted", which means you always see the whole picture and only the ring changes.

## Private books

Some books I keep private. A book whose title matches one of the words in my private list still counts toward the hour, but everywhere else it shows as "Private reading": not in the review, the morning message, the nightstand, the phone widget or on the Kindle. On the Highlights page, a **Show private books** box shows them when I want to see them.

The list lives in the server's settings file, `private_titles`, so it isn't something anyone can see from the app.

## Which day it belongs to

Daf stores every sitting with its exact time, and decides which day it belongs to by your **Home time zone** (Preferences → Days). If you travel, switch it when you land. Paper minutes logged with "shabbat" go on Saturday, however late on Saturday night you log them.

## When a number looks wrong

Look at the line at the bottom of Today first. It says how fresh each source is, and a Kindle that hasn't slept since you read is the usual answer: wake it, let it sleep again, and the minutes come in. The **Sources** page in the sidebar shows every source and its last answer, and on the server `daf doctor` prints the same thing. Basically, if a source is red there, that's where the missing minutes are.

<sub>Next: [Paper books](paper-books.md) →</sub>
