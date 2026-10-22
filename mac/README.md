# Daf for macOS

A native shell around the live site (`https://daf.tiresia.xyz` by default). The page stays the
whole interface; the shell adds a proper window, Daf's menus, today's minutes in the menu bar,
Save to Daf in the share menu, and the few things a page can't do from inside a web view.
The contract between the two is `docs/SHELL.md`; the brief is `docs/NATIVE.md`, round 1.

- **The window**, the way Readwise Reader's Mac app has it: a plain title bar with the traffic
  lights and "Daf", in the page's own colour (it follows the theme, Sepia and Black included),
  and the page below it. The empty part of a top bar moves the window too, and a double-click
  zooms it. The frame is remembered; at least 900 × 600. Only Daf loads in the window: any other address
  opens in the browser, `obsidian://` in Obsidian, and Daf's own files opened in a new tab (the
  PDF as printed) in a window of their own.
- **The menus**: File (New Window ⌘N, Add to Daf… ⌘O (the page's dialog: a link, a book or a PDF), Save a Link… ⇧⌘S, Log Paper Minutes… ⇧⌘P, Export
  Highlights… ⇧⌘E), View (Today ⌘1, Review ⌘2, Library ⌘3, Feed ⌘4, Highlights ⌘5, Books ⌘6,
  Stats ⌘7, Torah, Paper Pages, Preferences, Contents, Side Panel, Typography, zoom, Reload ⌘R,
  full screen ⌃⌘F), Go (Back ⌘[, Forward ⌘], Search ⌘K), Reader (Highlight, Highlight with a
  Note, Bookmark This Page, Listen, Next, Previous). Each item calls the page's own command
  (`window.dafCommand`), and what's greyed comes from `window.dafState()`.
- **Keys**: the page hears every key first, so Daf's own keys work as in a browser (h, n, b, j/k,
  the arrows in a book, ⌘K) and run once. A key the page leaves alone goes on to the menus. The
  Reader items show the page's single-letter keys, but a key without ⌘ or ⌃ never fires a menu
  item (`DafMainMenu`), so typing an "h" in a note stays an "h".
- **Today in the menu bar**: `38′`, or `60′ ✓` once the hour is done. Click it for the ring,
  "38 of 60 minutes today · Year 30, day N", the day's highlight with its book, and Open Daf,
  Review, Save a Link…, Log Paper Minutes…, Settings…. It asks `/api/phone/widget` every five
  minutes while the Mac is awake, on wake, and when the menu opens, and keeps the last answer,
  so offline it shows what it last knew (greyed after 20 minutes).
- **Save to Daf** in the share menu (Safari, Zen, anything that shares a link). The extension
  is sandboxed and holds no token: it hands the link to Daf as `daf://save?url=…&title=…`, Daf
  posts it to `/api/save`, and the menu bar says "Saved". `daf://go/review` opens a page, for
  Shortcuts.
- **Daf for Safari**: the browser extension (`extension/`, its Safari build) ships inside the
  app as `DafSafari.appex`. Tick it in Safari → Settings → Extensions (Daf → Safari Extension…
  opens that page) and allow it on every website. It needs no pasted token: the app makes one
  with its window's sign-in, a device called "safari", leaves it in the app group
  `<team>.xyz.tiresia.daf`, and the extension's native half hands it over. When Daf stops
  knowing it, the extension asks for a new one (`daf://connect-safari`). It needs a build signed
  with the Apple Development identity; an ad hoc one has no team, so no app group.
- **Downloads** (the highlight exports, a book's file, Share as image's Download) go to the save
  panel. **Share as image** reaches the system share sheet: `shell.js` stands in for
  `navigator.share` with `window.dafShell.share`.
- **Hidden means hidden**: a minimized, hidden or covered window leaves the page `hidden`, so
  Daf counts no minutes nobody read. Closing the window empties its page.
- **Open at login** (Settings), where Daf starts in the menu bar without a window.

## The token

The menu bar and Save to Daf use a device token, never the window's cookie. Settings → **Connect
This Mac** makes one: it calls `POST /api/devices {"name": "mac"}` with the window's own sign-in
and keeps the answer in the login keychain. Preferences → Account in the page lists it as "Daf
for Mac", with Disconnect. A token from `daf kindle-token mac` on the server can be pasted instead.

With an ad hoc signature the Keychain asks once after each new build whether Daf may read its
own token, because the signature changed. An Apple Development identity (Xcode → Settings →
Accounts, a free personal team is enough) keeps the signature stable, and `build.sh` finds it.

## Build it

macOS 13 or newer, the Command Line Tools (`xcode-select --install`) and `brew install xcodegen`.

```sh
cd mac
./build.sh                                   # build/Daf.app, in about ten seconds
cp -R build/Daf.app /Applications/ && open /Applications/Daf.app
```

Save to Daf shows up in the share menu once Daf has run from `/Applications`. If it doesn't, turn
it on in System Settings → General → Login Items & Extensions → Sharing (on macOS 13, Privacy &
Security → Extensions → Sharing).

`xcodegen generate` in `mac/` makes `Daf.xcodeproj` from `project.yml` for anyone who would rather
use Xcode; both builds read the same settings. The project file and the Info.plists it writes are
not in git.

## Test it

```sh
# on the server: a sandbox Daf on the tailnet, and the three arguments for the test
tools/mac-sandbox.sh
# on the Mac
mac/selftest.sh http://<server>:8441 COOKIE TOKEN          # or e.g. … TOKEN keys,book
```

It builds the app with `SelfTest/` linked in, as its own app (`xyz.tiresia.daf.selftest`, so Daf
can stay open), signs in with the sandbox's cookie, and checks what a person would press and
see: the user agent and `window.dafShell`, the title bar in the page's colour and following its theme, ⌘1–⌘7, ⌘K once,
⌘[ closing search before going back, h and ] staying the page's, ⇧⌘P, the menus with the mouse,
an article's Reader items, a book drawn by foliate-js in WebKit and Reader → Next turning its page, the page
going hidden when the window is minimized or Daf is hidden, links going outside, downloads and
exports, the share sheet, the menu bar's minutes (and keeping them offline), `daf://save`, and
Connect This Mac. It takes the keyboard for about a minute; leave the Mac alone while it runs.
Pictures of each window land in `build/selftest/out`.

The service worker needs a secure origin, so against the tailnet sandbox the test reports it
missing; on `https://daf.tiresia.xyz` WKWebView registers it and it takes control (checked
2026-10-09), so offline reading works in the app as in the browser.

Never point it at the real Daf: it opens books (which saves a place), saves a link and makes a
device token.

## The pieces

| file | |
| --- | --- |
| `Daf/DafApp.swift` | the app: launching, at login, `daf://` links, reopening |
| `Daf/Window.swift` | the window, the traffic lights, moving it from the page's bars, links out, alerts and file pickers |
| `Daf/Menus.swift` | the menu bar and what its items call |
| `Daf/ShellServices.swift` | `window.dafShell` (share, download, openExternal) and downloads |
| `Daf/MenuBar.swift` | today's minutes in the menu bar, and the menu behind them |
| `Daf/Server.swift` | the base URL, the device token in the Keychain, and the two endpoints |
| `Daf/SaveLink.swift` | Save a Link…, and `daf://save` from the share extension |
| `Daf/SettingsWindow.swift` | the address, Connect This Mac, the menu bar and login switches |
| `DafShare/ShareViewController.swift` | Save to Daf in the share menu |
| `build.sh`, `project.yml` | the build, with or without Xcode |
| `AppIcon.iconset`, `icon-1024.png` | the icon, from `design/icon/final` (Tree D: the beech rooted in two books) |
| `selftest.sh`, `SelfTest/` | the test above; never built into the app |
