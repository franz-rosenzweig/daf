<sub>[Daf docs](README.md) › Devices</sub>

# The Windows app

The Windows app is Daf in a Windows window, with Daf's menus in its title bar, today's minutes by the clock, notifications for new posts, and its own copy of Daf for when there's no connection. The page in the window is the same live site as in a browser, so everything in these docs works the same there. What the app adds is the part of a Windows app a web page can't be. It runs on Windows 10 (1809 or newer) and Windows 11, and it installs from the [releases](https://github.com/franz-rosenzweig/daf/releases) (see [Install](install.md#the-windows-app)).

## The window

The title bar takes the page's own colour and follows the theme, dark ones included, and Daf's menus sit in it, beside Windows' own minimize, maximize and close. You can drag the window from the empty part of the title bar, and it remembers its size and place. **F11** is full screen, and the manga reader's **Full screen** uses it too, leaving it again when you leave the reader.

Only Daf loads in the window. Any other link opens in your browser, `obsidian://` links open in Obsidian, and Daf's own files, like a PDF as printed, open in a window of their own. When the window is minimized, the page knows it's hidden, so it never counts minutes nobody read.

## With no connection

The app keeps its OWN copy of Daf on the PC, which means it opens and works with no connection at all, on a train or when the server is down. While it's online it saves Daf's screens and fonts, your lists, the articles you're reading with their pictures and the books you're reading, and it only fetches a file again when it changes. When Daf doesn't answer, the window moves to that copy on the same page, and what you do there (your place, highlights, notes) waits and goes to Daf when it's back. The app looks for Daf every 30 seconds, when the network changes and when the PC wakes, and then goes back to the live site by itself, which is also where videos play.

You can keep more for the road. An article's **⋯** menu and a book's menu have **Keep on this device**, and a manga series has a download button on each volume, so whatever you pick opens with no connection too, PDFs as printed included. **File › Settings… › With no connection** shows how much is on the PC and when it last updated, with **Update Now**. Anything nothing needs any more goes by itself after three weeks, so the copy doesn't keep growing.

## The menus

Every menu item calls the same command as the page's own buttons, and items that don't apply where you are are greyed out.

- **File:** **New Window** (Ctrl+N), **Add to Daf…** (Ctrl+O), **Save a Link…** (Ctrl+Shift+S), **Log Paper Minutes…** (Ctrl+Shift+P), **Export Highlights…** (Ctrl+Shift+E), **Settings…** (Ctrl+,), **Close Window** (Ctrl+W) and **Exit Daf**.
- **View:** Today Ctrl+1, Review Ctrl+2, Library Ctrl+3, Feed Ctrl+4, Highlights Ctrl+5, Books Ctrl+6 and Stats Ctrl+7, then **Shortlist**, **Torah**, **Paper Pages**, **Reading Goals…**, **Preferences**, **Contents**, **Side Panel**, **Typography**, **Reload Page** (Ctrl+R or F5) and **Full Screen** (F11).
- **Go:** **Back** (Alt+←, or the mouse's back button), **Forward** (Alt+→) and **Search** (Ctrl+K).
- **Reader:** **Highlight**, **Highlight with a Note**, **Bookmark This Page**, **Listen**, **Add to Shortlist**, **Tags…**, **Delete**, **Next** and **Previous**, and **Next in the List** and **Previous in the List**.
- **Help:** **Keyboard Shortcuts**, **Send Feedback…**, this page, and **About Daf**.

The page hears every key first, so Daf's single-letter keys (h, n, b, j and k, the arrows in a book) work exactly as in a browser, and typing an "h" in a note stays an "h". Back closes whatever is in front first, like search or a dialog, and only then goes to the page before.

## Today by the clock

The notification area, by the clock, has a ring that fills with today's minutes and turns green once the hour is done. Hold the pointer over it for "38 of 60 minutes today". Click it for the ring with "Year 30, day N", the day's highlight with its book, and **Open Daf**, **Review**, **Save a Link…**, **Log Paper Minutes…** and **Settings…**, and right-click it for the same with **Exit Daf**. It checks every five minutes, when the PC wakes and when you open it, and with no connection it shows what it last knew, dimmed after twenty minutes. If Windows hides the ring under the little arrow, drag it out next to the clock.

Closing Daf's last window leaves it there, the way the Mac app stays in the menu bar. **File › Exit Daf** or the ring's **Exit Daf** quits it.

## Saving links

**Save a Link…** (in the File menu and on the ring) takes a link, with the one on the clipboard already filled in, and puts it in the Library. Two links work from anywhere on the PC, which makes them good for a shortcut or a bookmarklet: `daf://save?url=…&title=…` saves a link, and `daf://go/review` (or any other page) opens Daf there. In the browser, the [browser extension](browser-extension.md) saves pages and highlights in one go.

## Notifications

If a feed is set to **Notify me of new posts** (in the Feed's sources, see [The Feed and the Library](feed-and-library.md)), the Windows app shows a notification for each new post, and clicking it opens the post in Daf. It looks for new posts with the ring's five-minute check. Windows' own **Settings → System → Notifications** can turn them off for Daf.

## Settings

**File › Settings…** has the address of your Daf, **Connect This PC**, the notification-area switch, and **Open Daf when you sign in to Windows**, where Daf starts quietly by the clock without a window. You don't have to connect by hand: once you sign in inside the window, the app makes a device token of its own for the ring, Save a Link and the notifications, kept encrypted for your Windows account. **Preferences → Account** in the page lists it as "Daf for Windows" with the PC's name, with **Disconnect**.

Basically, the Windows app is the web app with a real window and the minutes in sight all day, like the Mac app is on a Mac.

<sub>Next: [The Android app](android.md) →</sub>
