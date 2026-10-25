<sub>[Daf docs](README.md) › Devices</sub>

# The Mac app

The Mac app is Daf in a proper Mac window, with Daf's own menus, today's minutes in the menu bar, "Save to Daf" in the share menu, and the Safari extension inside it. The page in the window is the same live site as in a browser, so everything in these docs works the same there. What the app adds is the part of a Mac app a web page can't be. It runs on macOS 13 or newer, and you build it from the repository (see [Install](install.md#the-mac-app)).

## The window

The window looks like Readwise Reader's Mac app: a plain title bar with the traffic lights and "Daf", in the page's own color, which follows the theme, Paper and Black included. You can drag the window from any empty part of a top bar, and double-click to zoom it. It remembers its size and place.

Only Daf loads in the window. Any other link opens in your browser, `obsidian://` links open in Obsidian, and Daf's own files, like a PDF as printed, open in a window of their own. When the window is minimized, hidden or covered, the page knows it's hidden, so it never counts minutes nobody read.

## Focus mode

**Focus Mode** (⇧⌘F, the **[ ]** button in a reader's toolbar, F in a book and Shift F in an article) puts what you're reading on the whole screen, as the page's does: the window goes full screen, the sidebar and the list go, the side panels close, and the menu bar and the toolbar hide until the pointer goes to the top of the screen. The same again, or Esc, leaves it.

## With no connection

The app keeps its OWN copy of Daf on the Mac, which means it opens and works with no connection at all, on a plane or when the server is down. While it's online it saves Daf's screens and fonts, your lists, the articles you're reading with their pictures and the books you're reading, and it only fetches a file again when it changes. When Daf doesn't answer, the window moves to that copy on the same page, and what you do there (your place, highlights, notes) waits and goes to Daf when it's back. The app looks for Daf every 30 seconds and when the Mac wakes, and then goes back to the live site by itself, which is also where videos play.

You can keep more for the road, like on the phone. An article's **⋯** menu and a book's menu have **Keep on this device**, and a manga series has a download button on each volume, so whatever you pick opens with no connection too, PDFs as printed included. **Daf → Settings… → With no connection** shows how much is on the Mac and when it last updated, with **Update Now**. Anything nothing needs any more goes by itself after three weeks, so the copy doesn't keep growing.

## The menus

Every menu item calls the same command as the page's own buttons, and items that don't apply where you are are greyed out.

- **Daf:** **Settings…** (⌘,), **Reading Goals…** and **Safari Extension…**.
- **File:** **New Window** (⌘N), **Add to Daf…** (⌘O), **Save a Link…** (⇧⌘S), **Log Paper Minutes…** (⇧⌘P) and **Export Highlights…** (⇧⌘E).
- **View:** Today ⌘1, Review ⌘2, Library ⌘3, Feed ⌘4, Highlights ⌘5, Books ⌘6 and Stats ⌘7, then **Shortlist**, **Torah**, **Paper Pages**, **Hide Sidebar** (⌃⌘S), **Contents**, **Side Panel**, **Typography**, zoom, **Reload Page** (⌘R), full screen and **Focus Mode** (⇧⌘F).
- **Go:** **Back** (⌘[), **Forward** (⌘]) and **Search** (⌘K).
- **Reader:** **Highlight**, **Highlight with a Note**, **Bookmark This Page**, **Listen**, **Add to Shortlist**, **Tags…**, **Delete**, **Next** and **Previous**, and **Next in the List** and **Previous in the List**.
- **Help:** **Keyboard Shortcuts** and **Send Feedback…**.

The page hears every key first, so Daf's single-letter keys (h, n, b, j and k, the arrows in a book) work exactly as in a browser, and typing an "h" in a note stays an "h".

## Today in the menu bar

The menu bar shows today's minutes, "38′", and "60′ ✓" once the hour is done. Click it for the ring with "38 of 60 minutes today · Year 30, day N", the day's highlight with its book, and **Open Daf**, **Review**, **Save a Link…**, **Log Paper Minutes…** and **Settings…**. It checks every five minutes while the Mac is awake, on wake, and when you open it, and with no connection it shows what it last knew, greyed after twenty minutes.

## Save to Daf

"Save to Daf" is in the share menu of Safari, Zen and any app that shares a link, and the link goes to the Library, with "Saved" in the menu bar. If it doesn't show up, turn it on in **System Settings → General → Login Items & Extensions → Sharing** (on macOS 13, **Privacy & Security → Extensions → Sharing**).

Two links work from anywhere on the Mac, which makes them good for Shortcuts: `daf://save?url=…&title=…` saves a link, and `daf://go/review` (or any other page) opens Daf there.

## Safari

The browser extension's Safari version comes inside the app, so there's nothing to download and no token to paste. Open **Daf → Safari Extension…**, tick **Daf** in Safari's extensions, and allow it on every website. See [The browser extension](browser-extension.md) for what it does.

## Settings

**Daf → Settings…** has the address of your Daf, **Connect This Mac**, which gives the menu bar and "Save to Daf" a device token of their own, the menu bar switch, and **Open at login**, where Daf starts quietly in the menu bar without a window. **Preferences → Account** in the page lists the Mac as "Daf for Mac", with **Disconnect**.

## Notifications

If a feed is set to **Notify me of new posts** (in the Feed's sources, see [The Feed and the Library](feed-and-library.md)), the Mac app shows a notification for each new post, and clicking it opens the post in Daf. It looks for new posts with the menu bar's five-minute check.

Basically, the Mac app is the web app with a real window and the minutes in sight all day. If you only install one of the apps, I'd make it this one if you work at a Mac, and the [Android app](android.md) if your phone is where the distractions are.

<sub>Next: [The Android app](android.md) →</sub>
