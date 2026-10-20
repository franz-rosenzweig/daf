# The shell contract

How Daf's page and a native shell (`mac/`, `android/`) talk to each other. The page is the
live site; a shell is a window around it plus the few things a page can't do. Dvarim and
Moshe have `BRIDGE.md` for a folder; Daf has no folder, so this is all there is.

The page's half is `web/shell.js`. It does nothing unless the user agent says a shell is
there, so a browser never sees any of it.

## 1. The user agent

The shell appends one of these to WebView's user agent:

- `Daf/<version> (macOS shell)`
- `Daf/<version> (Android shell)`

`shell.js` then puts `shell` and `shell-mac` or `shell-android` on `<html>`. The page makes no
room for anything: the Mac window has a plain title bar above the page, in the page's colour
(Readwise Reader's way), and `shell.js` tells it when the theme changes. The empty part of a
top bar moves the window too (§5).

## 2. `window.dafShell`: the shell's, the page calls it

On the Mac the shell defines it at document start, before the page's own scripts run, over
WebKit's `dafShell` message handler. On Android `shell.js` defines it, and the calls go over a
message port the app posts to the main frame as soon as the page shows, addressed to Daf's
origin (`Shell.java`); if nothing has come back on it when the page has finished loading
(`shell.js` wasn't listening yet), the app posts another. A document's ports stay open until
the next document starts, so a call answers on the port it came on. A port reaches only the page it was posted to, so a frame inside the page (a
video) can't call the app. Calls made before the port arrives wait for it.

| Call | What it does | Answers |
| --- | --- | --- |
| `dafShell.can(op)` | Whether this shell has `op`. A missing op means: do what a browser would. | boolean |
| `share({text?, url?, png?, name?})` | The system share sheet. `png` is base64 without the `data:` prefix. | Promise → `true`, or `false` if nothing was shared |
| `download(url)` or `download({name, mime, base64})` | Saves a file through the save panel (Mac) or the create-document screen (Android). A URL is fetched with the window's own cookie. | Promise → `true`, or `false` if cancelled |
| `openExternal(url)` | Opens `http`, `https`, `mailto` or `obsidian` links in the browser or the app they belong to. | Promise → `true` |
| `notify({title, text, route})` | A system notification; tapping it opens `#route`. Not built: nothing in the page needs it yet. | Promise → `true` |
| `fullscreen()` | Mac: the window's own full screen (macOS full screen), for the manga reader's Full screen; leaving the reader leaves it again. Android doesn't list it: the reader is already immersive there. | Promise → `true` when it went full screen |
| `alerts()` | Notifications for new posts in the feeds set to notify (the sources sheet's feed editor). The shell asks the system for permission once; from then on the app asks `/api/phone/feed-news` with its token (Android every 15 minutes, the Mac with the menu bar's five-minute look) and posts one notification a post, which opens it in Daf. It stops by itself once no feed is set to notify. | Promise → `true` if the system lets Daf notify |
| `media({state, title, sub})` | Android: what read-aloud is doing (`playing`, `paused`, `stopped`). `shell.js` sends it by itself; the app keeps playing behind the lock screen and shows the controls there, which press the page's own buttons (`listen:play`, `listen:pause`, `listen:next`, `listen:prev`, `listen:stop`). | Promise → `true` |
| `haptic(kind)` | A tap felt in the hand: `confirm`, `reject` or `tick`. Android only; `shell.js` sends it for the review's Keep and Less often, the bottom tabs and the highlight bar. | Promise → `true` if the phone felt it |
| `bars({bg, dark})` | Android: the status and navigation bars behind the theme's background (`#rrggbb`), with dark or light icons. `shell.js` sends it by itself, at load and on `themes.js`'s `daf-theme` event; the app keeps it for the phone's current mode, so the next start paints it from the first frame. | Promise → `true`, or `false` for a colour it can't read |
| `reading({volumeKeys, ownMenu})` | Android: how reading goes on this device. `volumeKeys`: the volume buttons turn pages in a book or the manga reader (Preferences → Reader, off unless turned on; the app keeps the last value for its next start), and never while music or read-aloud plays. `ownMenu`: the page's own text menu stands in for Android's, which then comes up empty (true only with an article or a book open and nothing editable in focus). `shell.js` sends it when the port arrives and whenever either changes. | Promise → `true` |
| `offline({op, id?, on?, size?})` | What's kept on the device for no network, on both shells. `list` (what's there), `has` (a book), `keep` (a book; `on: false` lets it go), `doc` (an article, from the reader's ⋯ menu, with its pictures and, for a PDF, its file), `manga` (a volume, `size` its page width, 600–2400), `sync` (everything now). Android also keeps every book opened in it and the books being read, and gives the WebView and the service worker a book's file from the phone; the Mac keeps the books being read, and its copy (`daf-app://app/`) answers from what's kept. | Promise → `{books: [{id, title, size, kept}], manga: [{id, title, series, state, done, total, bytes}], docs: [{id, pinned}], app: {ready, version, at}, data, bytes, synced}`, or `{has}` |

`dafShell.version` is the shell's version and `dafShell.platform` is `"mac"` or `"android"`.

Both shells answer `share`, `download`, `openExternal`, `alerts` and `offline`; the Mac `fullscreen`; Android `haptic`, `media`, `screen`, `bars` and `reading`. The Mac needs no `bars`: its title bar is see-through, so the page's own colours are the window's.

In the manga reader, Android's volume keys reach the page as `window`'s `daf-volume` event (`detail.dir` 1 for down, -1 for up), so the reader's own "Volume keys" setting decides; the Mac's Next and Previous menu items send PageDown and PageUp. While the reader is open, the Mac turns off the two-finger Back swipe, and Android keeps the middle of each side edge (200dp) for the page's own swipes.

**Offline.** Writes the book reader makes with no network (its place, highlights and their notes,
colours and tags, bookmarks) wait in `app.js`'s outbox, in order, and go when the network is back
with the time they were made (`at`). The server keeps the newer place, so one sent late doesn't
replace the Kindle's. This is the page's own, so it works in a browser too; the shell adds the books.

Both shells also start with no network at all, from a copy of Daf kept on the device: every file in
`web/` (from `/api/app-files`, fetched again only when its hash changes), Daf's own fonts among them,
plus what `/api/offline/plan` names (the lists, the articles being read with their pictures, the
books' details). A list asked for in a way that wasn't kept falls back to the kept one with the same
`where`, `tab`, `kind`, `cat` and `feed`. Android answers from the copy whenever the network is down
(`AppFiles`, `DataStore`). The Mac can't step in front of `https`, so when Daf doesn't answer, the
window moves to the copy at `daf-app://app/` (`LocalCopy.swift`), at the same route; it checks Daf
every 30 seconds and on wake, sends the outbox, then moves back to the live site. Writes made on
the copy fail as they would with no network, so the outbox keeps them. Each sync also brings the
articles kept by hand up to date (one deleted in Daf goes), keeps a PDF's own file with its article, and
lets go of what nothing names any more (not the plan, not what's kept by hand, not their pictures, PDFs
or manga pages) once it hasn't been kept or read on the device for three weeks; reading it offline
starts its three weeks again. A kept file is found by its address whether the path came
percent-encoded (as the page asks, `kk%3A…`) or not (as the plan names it). The copy's page starts with the
live page's localStorage (the theme among it, `daf.themeVars`), taken after each live load; a newer
snapshot replaces what the copy had.

**Speed, online too** (docs/OPERATIONS.md "Speed"). The page's service worker answers from the device
first: the page and its files (`daf-shell-<version>`, from `/sw.js`'s fingerprint), pictures (`daf-img-v1`)
and book files (`daf-books-v1`), and the pages draw their kept data first (`DafCore.swr`). The paths stay
as they were (`/api/ebooks/{id}/file`, `/api/manga/books/{id}/pages/{n}?size=…`); in the Android app
those two pass the worker by, because the app keeps them itself. index.html is served with fingerprinted
script addresses (`?v=`); the copy in `/api/app-files` is the file as it is.

With `share`, `shell.js` also stands in for `navigator.share` and `navigator.canShare`, so
the page's own Share buttons (Share as image in `hl.js`) reach the native sheet without a
change to the page.

## 3. `window.dafCommand(name)`: the page's, the shell calls it

This is how the shell's menus work. It answers `true` if the page did something and `false`
if the command doesn't apply where the page is now.

| Name | Does |
| --- | --- |
| `go:today` `go:review` `go:library` `go:feed` `go:highlights` `go:books` `go:stats` `go:torah` `go:paper` `go:prefs` | Goes there |
| `go:library/starred` and other deeper pages | Goes there too (the Shortlist, Preferences → Goals: `go:prefs/goals`, a book: `go:book/<id>`) |
| `back` | The same as `dafBack()` |
| `search` | ⌘K's search |
| `toc`, `panel`, `aa` | Contents, the side panel and Typography, in an article or a book |
| `listen` | Read aloud, or stop |
| `highlight`, `note` | Highlights the selection or, in an article, the paragraph in focus; `note` adds a note |
| `bookmark` | Bookmarks the page in a book |
| `next`, `prev` | The next or previous page in a book, and the next or previous paragraph in an article |
| `nextdoc`, `prevdoc` | The next or previous item of the list an article was opened from |
| `star` | The Shortlist (★): on or off for the article, or the selected row of the Library |
| `listen:play` `listen:pause` `listen:next` `listen:prev` `listen:stop` | Read-aloud's own buttons, in an article or a book |
| `paper` | Log paper minutes… |
| `add` | Add to Daf…: a link, a book or a PDF |
| `export` | Opens the highlight export (on Highlights) |
| `keys` | Shows the keyboard shortcuts for where you are |
| `delete`, `undo`, `tag` | In an article, or on the selected row of a list (or the rows picked with x): delete it, take back the last Done, Later, Shortlist or Delete, or open its tags |
| `feedback` | Send feedback… (filed as an issue on the repo) |

The commands that press a key (`highlight`, `note`, `next`, `prev`, `toc`, `star`, `delete`, `undo`, `tag`) press the one bound now in Preferences → Keyboard (`web/keys.js`), so a menu item keeps working after a shortcut changes. `dafState().can` also has `delete`, `undo` and `tag`.

## 4. `window.dafState()` and `window.dafBack()`

`dafState()` answers what a menu needs, so items can be greyed and ticked:

```js
{ route: "read", title: "…", signedIn: true, minutes: 38, goal: 60,
  reader: "article" | "book" | null, listening: false, starred: false, canBack: true,
  keys: { highlight: "h", note: "n", tag: "t", delete: "d", nextdoc: "J", … },
  can: { toc, panel, aa, listen, highlight, note, bookmark, next, prev, nextdoc, prevdoc, star, delete, undo, tag, export } }
```

`minutes` is what Today counts, and stays `null` until the page has loaded it. `keys` holds the
keys bound now in Preferences → Keyboard for the article, the book or the list in front (`e.key`:
"J" is Shift-J, "" is none), so the Mac's Reader menu shows the key that works.

`dafBack()` closes whatever is in front (search, a dialog, a popover, the highlight bar, a
sheet in the book reader). If nothing is open it goes back in history, if there's a Daf page
to go back to. It answers `false` when there's nowhere to go, so Android can leave the app
and the Mac can beep.

## 5. What the shell does on its own

- **Only Daf in the window:** the base URL's origin. Any other address, including
  `target=_blank` and `window.open`, goes to the browser. `obsidian://` goes to Obsidian.
- **Daf's own pages in a new window:** `target=_blank` to Daf itself (the PDF as printed,
  `/api/docs/<id>/pdf`) opens in a window of its own, with the same sign-in.
- **Downloads:** `<a download>`, `Content-Disposition: attachment` and `blob:` links go to the
  save panel, with the name the server or the page gave.
- **Moving the window (Mac):** a press on an empty part of `.top`, `.brand` or the strip above
  the sidebar posts `drag` (`zoom` on a double press) to the `dafWindow` handler.
- **Hidden means hidden:** a minimized, covered or hidden window must leave
  `document.visibilityState` at `hidden`, or Daf counts minutes nobody read. WKWebView and
  Android's WebView both do this by default; the shells' self-tests check it.
- **One sign-in:** the page's own form and its `daf` cookie, in the default (persistent) data
  store.
- **Native surfaces use a device token, never the cookie:** the menu bar, the share extension
  and the Android widget send `Authorization: Bearer <token>` to `/api/phone/widget` and
  `/api/save` (`docs/NATIVE.md` has the endpoints). The token is in the Keychain on the Mac and
  in EncryptedSharedPreferences on Android.
