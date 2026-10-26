<sub>[Daf docs](README.md) › Using Daf</sub>

# Manga

This page covers reading manga in Daf. My manga live in Komga, which already scans the series and keeps track of where I am, so Daf doesn't copy anything out of it: Komga is the library, and Daf is a good place to read it, with the minutes counted like any other reading.

## Finding a volume

**Manga** in the sidebar shows **Keep reading**, the series you're partway through, and **All series** under it. Open a series for its volumes, and press **Keep reading** or **Read** on one to open it. Manga volumes don't show up in Books, so they don't crowd your novels.

In the Mac and Android apps, every volume on a series page has a download button, which keeps it on the device so it reads with no connection. While it downloads, the button shows how far along it is. On Android, **Settings → Books and manga on this device** shows how much is kept, and on the Mac it's **With no connection** in the app's Settings.

## The reader

The reader takes the whole screen, and I rebuilt it after Mihon and the other good manga readers, so it behaves the way a manga reader should:

- **Reading mode:** Right to left by default, Left to right, Vertical, Long strip for webtoons, or Strip with gaps.
- **Pages:** Auto shows two pages side by side when the screen is wider than it is tall, with a wide spread on its own. **Shift pairs by one** fixes a volume whose pairs start on the wrong page, and **Split wide pages** cuts spreads in two.
- **Scale:** Fit screen, Fit width, Fit height or Original size, with **Crop borders** to trim white margins.
- **Controls:** tap zones on the sides, swipes, double tap to zoom, and pinch.
- **Filters:** brightness, contrast, saturation, sepia, grayscale and invert, for scans that are too dark or too yellow.

Tap the middle of the page for the bars. **Reading settings** (S) has four tabs: **Reading**, **Controls**, **Display** and **Filters**. Your choices are kept for each series, so a webtoon stays a long strip and a manga stays right to left.

The **…** sheet has **Full screen**, **Show the tap zones**, **Save this page** and **Keys**. In the Android app, the volume keys turn pages too (**Volume keys** in Controls: Turn pages, Inverted or Off). On the Mac, **Full screen** uses the Mac's own full screen.

## Keys

| Key | Does |
|---|---|
| ← → | turn the page |
| Space / Page Down | next page |
| Page Up / Shift Space | previous page |
| Home / End | first / last page |
| [ ] | previous / next volume |
| M | show or hide the bars |
| T | all pages |
| S | settings |
| R, D, C | next reading mode, one or two pages, next scale |
| B | crop borders |
| A | auto scroll |
| F | full screen |
| Esc | close |

## Progress and minutes

Where you are goes back to Komga as the Kindle's account, which means the Kindle opens a volume where Daf left off. Daf also reads the progress from my other Komga account and shows whichever is further, so a chapter read in another app shows up too.

Time in the reader is "Manga in Daf" on Today, one sitting per series a day, and it counts toward the hour unless you switch it off in **What counts toward the goal**. Volumes read on the Kindle are grouped under their series too. They don't count toward a books goal unless you tick "Manga and comic volumes count as books" in Preferences.

Pages come from Komga shrunk to fit your screen and are kept on the server for next time, and on the device too, so turning pages is quick even on a phone.

## AniList

Once an hour a script on the server works out how far I've read each series, on the Kindle, in Daf or in Komga, and sets that on AniList. My files are mostly whole volumes and AniList counts chapters, so it turns "volume 5" into the chapter volume 5 ends on. It never lowers what AniList already has.

It signs in with Daf's AniList connection. To set it up, go to **Preferences → AniList**, make a client on AniList once (its Redirect URL is `https://<your Daf>/anilist`, no secret needed), paste its Client ID and press **Connect AniList**. The sign-in lasts a year, and the same button renews it. The card shows when the last update ran and what it set.

<sub>Next: [The Kindle](kindle.md) →</sub>
