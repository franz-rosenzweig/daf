<sub>[Daf docs](README.md) › Devices</sub>

# Sharing, messages and the widget

This page collects the small ways into Daf that don't need you to open it: sharing a link or a photo, the morning highlight on Signal, text and voice messages, the widget, and links for Shortcuts. They're the reason Daf fits into my day instead of being one more app to remember.

## Save to Daf

"Save to Daf" shows up in the share menu in three places: the Android app's share sheet, the Mac's share menu, and an Android phone where Daf is installed from Chrome (**Install app**). What happens depends on what you share:

- **A link**, or text with a link in it, goes to the Library, and Daf reads the page.
- **A photo** of a page you marked becomes a [paper page](paper-books.md#paper-pages-pencil-marks-into-highlights), and its marked lines become highlights.

A shared link waits in Daf for a moment and goes into the Library on the next sync, within five minutes. **Preferences → Phone → Shared to Daf** lists the last few.

## The morning highlight

Every morning, the first highlight of the day's review comes to my phone on Signal. It looks like this:

> today's highlight
>
> "Books are the treasured wealth of the world and the fit inheritance of generations and nations."
> — Walden, Henry David Thoreau
>
> Reply with "n:" and a thought, and it goes under this highlight in your vault. 4 more in today's review: …/#review

A reply that starts with "n:" becomes that highlight's note, in the review and in the vault. The message is sent by `daf morning --send`, which runs from a cron job on my server and hands the text to my Signal bot. The number of highlights a day is in **Preferences → Daily review**.

## Messages to my Signal bot

My Signal bot, Ezer, isn't part of Daf: it's a small script of mine that recognizes a few messages before anything else and calls the `daf` command line. These are the ones that reach Daf:

| I send | What happens | The command it runs |
|---|---|---|
| "read 40 paper", "paper 40" | 40 paper minutes today | `daf log-paper 40` |
| "shabbat 60" | an hour on Saturday | `daf log-paper 60 --shabbat` |
| "n: …" or "note: …" | a note under this morning's highlight, or else under the book on the Kindle, at its page | `daf note "n: …"` |
| a voice note | transcribed and filed under the book read on the Kindle in the last three hours | `daf voice-note FILE` |
| a photo captioned "page" or "page 112 middlemarch" | a paper page, read into highlights | `daf paper-page PHOTO --caption "…"` |
| a link with a time in it | the minute before that point, transcribed into a highlight | `daf clip "…"` |

If you run your own Daf and have your own way of sending a message to a script, those commands are the whole interface.

## The widget, the menu bar and the sleep screen

The point of all three is the same: the hour in sight, where you'd otherwise look at something else.

- **Android:** the home-screen widget, a ring of today's minutes and the day's highlight (see [The Android app](android.md#the-widget)).
- **Mac:** today's minutes in the menu bar, "38′" or "60′ ✓" (see [The Mac app](mac.md#today-in-the-menu-bar)).
- **Kindle:** today's minutes on the sleep screen (see [The Kindle](kindle.md#the-sleep-screen)).

## Shortcuts and long-presses

- **Android:** long-press the Daf icon for **Review**, **Continue reading**, **Log paper** and **Settings**.
- **Mac:** `daf://go/review` opens Daf on a page, and `daf://save?url=…` saves a link, so a Shortcut or a script can do either.
- **Anything else:** a device token from **Preferences → Phone → Make a token** lets a script or a Shortcut send a link to `POST /api/save`, or read today's minutes and the day's highlight from `GET /api/phone/widget`. The token is shown once, so copy it right away.

Basically, the share menu, a text message and a glance at the widget cover most days, and Daf itself is for when I sit down to read.

<sub>Next: [Your own server](server.md) →</sub>
