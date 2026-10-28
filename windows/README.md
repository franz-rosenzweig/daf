# Daf for Windows

A native shell around the live site (`https://daf.tiresia.xyz` by default), as the Mac's
web-view app (`mac/`) and the Android app are: the page stays the whole interface, and the
shell adds a proper window, Daf's menus, today's minutes in the notification area, alerts for
new posts, `daf://` links, and a copy of Daf for when there's no connection. C# and WinUI 3
(Windows App SDK 1.8), with the page in WebView2. The contract between page and shell is
`docs/SHELL.md`; what a person sees is `docs/windows.md`.

- **The window**: the page under one tall title bar in the page's own colour (`dafShell.bars`,
  which `shell.js` sends at load and on each theme change) holding the icon, the menus and the
  window's name ("<page> - Daf", dimmed while another window is in front), with Windows'
  caption buttons and their Snap Layouts. The frame is remembered; at least 900 × 600. Only Daf
  loads in the window: any other address opens in the browser, `obsidian://` in Obsidian, and
  Daf's own files opened in a new tab (the PDF as printed) in a window of their own.
- **Full screen is one state**: F11 and View › Full Screen, the page's own Fullscreen API (focus
  mode) and the manga reader's Full screen (`dafShell.fullscreen`, left again with the reader)
  all set the same full-screen presenter, the title bar shows exactly when the window isn't
  full screen (also when Windows changes it, Win+↓), coming out of it leaves the page's too, and
  a note says for three seconds which key leaves.
- **The menus**: File, Edit, View, Reader and Help, the Windows set, with the Mac's items in them
  and Ctrl for ⌘ (the Mac's Go is View › Go To, Back and Forward). Each item calls the page's
  own command (`window.dafCommand`); what's greyed comes from `window.dafState()`. Edit's Cut,
  Copy, Paste and Select All press their keys in the page; its Undo is the box's own while one
  is being typed in, and Daf's `undo` otherwise. The page hears every key first: the keys with
  Ctrl reach the shell only if the page leaves them alone, and the Reader's single letters are
  the page's. Alt and a menu's letter opens it, Alt alone moves to the menus, Esc goes back, and
  choosing an item gives the keyboard back to the page. The browser's own keys are off (with
  `--devtools`, F12 comes back). Alt+←, Ctrl+[ and the mouse's back button go through
  `window.dafBack()`, which closes what's in front first.
- **Text size**: Ctrl+Plus, Ctrl+Minus, Ctrl+0 and Ctrl with the wheel are the reading text's
  size, Aa's (`dafCommand('text:bigger' | 'text:smaller' | 'text:reset')`), never the browser's
  zoom of the whole window; the manga reader and PDFs keep them for their pages. WebView2's zoom
  control stays on, because with it off WebView2 keeps those keys from the page.
- **Right-click** on words chosen in an article or a book has Daf's Highlight and Highlight with
  a Note above Copy; the browser's own items (Back, Reload, Save as, Print, Share…) are gone.
- **`window.dafShell`**, defined before the page's scripts run, over WebView2's web messages:
  `share` (Windows' share sheet, so Share as image works through `shell.js`'s stand-in for
  `navigator.share`), `download` and every `<a download>`, attachment and blob link (the save
  dialog), `openExternal`, `alerts`, `fullscreen`, `offline` and `bars`. Not the phone's:
  `haptic`, `media`, `screen`, `reading` and `ink` aren't there, so the page does what a browser would.
- **Hidden means hidden**: a minimized window's page is hidden (the web view goes with it),
  so Daf counts no minutes nobody read. Closing a window empties its page.
- **Today in the notification area**: a ring drawn for the day's minutes (the goal's green once
  met, dimmed when the answer is twenty minutes old), "Daf: 38 of 60 minutes today" as its tip,
  a panel on a click (the ring, the day, the highlight, Open Daf, Review, Save a Link…, Log
  Paper Minutes…, Settings…) and a menu on a right-click. `/api/phone/widget` every five
  minutes, on wake and when the panel opens. With it on, Daf stays when its last window closes.
- **The device token**: once the window is signed in and the PC has none, the app makes one
  itself (`POST /api/devices {"name": "windows-<pc>"}` with the window's sign-in), as Android
  does, and keeps it with DPAPI for this Windows user. Settings has Connect This PC, Forget the
  Token and a box to paste one from `daf kindle-token`. A token Daf no longer knows (Disconnect in
  Preferences → Account) is forgotten, and stays so until Connect.
- **Alerts for new posts**: `/api/phone/feed-news` with the five-minute look, each post a
  Windows notification (the Windows App SDK's, which works for an unpackaged app); a click
  opens it in Daf, starting Daf if it isn't running.
- **`daf://`**: `daf://save?url=…&title=…` saves a link (`/api/save`), `daf://go/review` opens
  a page. The installer and each start register them for this Windows user. Daf runs once per
  person: a second start hands its link to the Daf already running (`Program.cs`).
- **With no connection** (`LocalCopy.cs`, `Daf.Core/Keeper.cs`), the Mac's way: every file of
  `web/` (from `/api/app-files`, checked by its SHA-1 and fetched again only when it changes),
  what `/api/offline/plan` names, and what's kept by hand, in `%LOCALAPPDATA%\Daf\Copy`. When
  Daf doesn't answer (no connection, or Cloudflare's 502–530), the window moves to
  `https://daf-app.example/` at the same route, which WebView2 answers from the copy
  (`WebResourceRequested`): the page's files, `/api/` through to Daf with the window's
  cookie or from what was kept, and a write Daf can't take fails as a lost connection does, so the
  page's outbox keeps it. The copy's page starts with the live page's localStorage and has no
  service worker. It checks Daf every 30 seconds, on a network change and on wake, sends the
  outbox, then moves back.

## Build it

On GitHub: every push that touches `windows/`, `web/` or `daf/` runs the Windows workflow
(`.github/workflows/windows.yml`), and the run keeps the installer and a portable zip, with the
self-test's results, what it saved and a picture of its window. A tag `windows-vX.Y.Z` also
makes the release.

On a Windows PC with the .NET 10 SDK, and for the self-test Python 3.12 with Daf's
requirements (`pip install fastapi uvicorn python-multipart pypdf Pillow trafilatura`), and
for the installer Inno Setup 6:

```powershell
windows\build.ps1            # build\Daf is the app; build\out the installer
```

The installer is for one person and needs no administrator: it copies the app to
`%LOCALAPPDATA%\Programs\Daf`. Settings, the sign-in (WebView2's own profile), the token, the
copy and `daf.log` are in `%LOCALAPPDATA%\Daf`. The app isn't signed, so Windows says the
publisher is unknown the first time: More info › Run anyway.

## Test it

```powershell
dotnet run --project windows\Tests     # Daf.Core, against a stand-in Daf on 127.0.0.1
windows\selftest.ps1                   # the built app, on a sandbox Daf made from this checkout
```

The tests cover the address and `daf://` links, the token kept with DPAPI, the widget's numbers
and words, the copy's files (one name whether a path came percent-encoded or not, a list's
any-key, three weeks before what nothing names goes, pictures pointed at the copy, no path out
of it), and the copy kept up to date from a stand-in Daf: the screens checked by their hashes,
the plan, books, articles and manga volumes kept by hand, and the copy's `/api/` sent on with
the sign-in.

The self-test starts `tools/sandbox.py` on an empty state of its own, with a made-up password
(never the real Daf, whose outside writes the sandbox also stands in for), and runs the real
app on it with `--selftest`, nobody at the keyboard. It checks: the user agent, `shell-windows`
and `dafShell`'s calls; the title bar in the page's colour and following its theme, its five
menus and the window's name; View › Review and Ctrl+3, Ctrl+K staying the page's, the Reader
items greyed away from a reader; Ctrl+Plus, Ctrl+Minus, Ctrl with the wheel and Ctrl+0 changing
the reading text's size and never the browser's zoom; Back closing search before going back,
and the mouse's back button; a minimized window's page going hidden and coming back; links out,
`obsidian://`, and Daf's own file in a window of its own; `dafShell.download`, an
`<a download>`, a blob link and a URL saved; share; full screen as one state (the reader's, F11
in and out, and the page's own Fullscreen API then View › Full Screen, both out); the token
made by itself and today's minutes with it; the ring in the notification area and its
panel; alerts answering; `daf://save`, and a second start handing `daf://go/stats` to the
first; Settings; the copy of every file of `web/` and the plan; and then, with the sandbox
stopped, the window moving to the copy at the same page, signed in, its data from the PC, no
service worker, a write waiting in the outbox, and with the sandbox started again, back to the
live site.

What it can't check: the share sheet and the save dialog themselves (it saves to a folder
instead), a notification appearing and its click, a window covered by another (only minimized),
the right-click menu, the menus opened from the keyboard, the real Daf's https and its service
worker, and anything that needs a person at the PC. Its keys are sent through DevTools
(`Input.dispatchKeyEvent`), inside the page, so they show the page and the shell agree on a key
but can't prove a real key gets past WebView2 the same way. A notification-area check passes
on a machine with no taskbar, and says so.

## The pieces

| file | |
| --- | --- |
| `Daf/Program.cs` | one Daf per person: a second start hands over its link |
| `Daf/App.xaml.cs` | the app: launching, what started it, quitting |
| `Daf/ShellWindow.xaml.cs` | a window: the title bar, the page, its messages, links out, Back, full screen, the copy and back, the token |
| `Daf/Menus.cs` | the menus and what their items call |
| `Daf/ShellServices.cs` | `window.dafShell`, and downloads |
| `Daf/Scripts.cs` | what goes into the page before its own scripts |
| `Daf/LocalCopy.cs` | `https://daf-app.example/`, and coming back |
| `Daf/Today.cs`, `Tray.cs`, `TodayPanel.cs` | today's minutes, the ring and its panel |
| `Daf/FeedNews.cs` | alerts for new posts |
| `Daf/SaveLink.cs`, `Dialogs.cs`, `SettingsWindow.cs`, `Settings.cs` | Save a Link…, the shell's own dialogs and settings |
| `Daf/SelfTest.cs` | the self-test |
| `Daf.Core/` | the address, links, the token, Daf's endpoints, the copy (`CopyStore`, `Keeper`) |
| `Tests/` | Daf.Core's tests |
| `selftest.ps1`, `build.ps1`, `installer.iss`, `tools/make-icon.ps1` | the self-test, the build, the installer, the icon from `design/icon/final` |

Later: signing, so Windows knows the publisher; an ARM64 build; updates from the releases;
Daf in the Share menu (it needs the app packaged); listening with Windows' media keys.
