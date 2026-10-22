# Daf for Android

A WebView on the live site (`https://daf.tiresia.xyz` by default), which is the whole interface
and already has a phone layout. The app adds the hour on the home screen, Share into Daf, the
evening nudge, and the few things a page can't do from inside a WebView. The contract between
page and app is `docs/SHELL.md`; the brief is `docs/NATIVE.md`, round 2.

- **The app**: Daf between the status bar and the navigation bar (or the keyboard, which makes
  the window shorter so the page's bars stay on screen), in its own colours. Back goes through
  the page first (`window.dafBack()`: search, a dialog, a popover, a sheet, then the page before),
  and leaves only when there's nowhere to go. Only Daf loads in it: anything else goes to the
  browser, `obsidian://` to Obsidian. The user agent ends `Daf/<version> (Android shell)`.
- **The volume keys turn a book's pages** in the reader (`#ebook/…`): down for the next page, up
  for the one before, and the volume stays where it was.
- **Downloads** (the highlight exports, a book's file, the PDF as printed) go through the
  system's create-document screen, fetched with the window's sign-in. Blob links (Share as image's
  Download) come through `window.dafShell.download`, and **Share as image** reaches the share sheet.
- **The widget**, 2×2 or 4×2 from the same widget (it picks by size): a ring of today's minutes
  with the number in it and "Year 30 · day N" under it; on the 4×2, the day's highlight in a serif
  face and its book, or "That's the hour." once it's done. Material You colours, light or dark as
  the phone is. Tap the ring for Today, the highlight for Review. It asks `/api/phone/widget`
  every half hour (Android's own refresh), when the phone is unlocked (at most every 10 minutes,
  while Daf's process is alive), and when you leave the app; if Daf can't be reached it keeps the
  last numbers, dimmed.
- **Share into Daf**, in any app's share sheet as "Save to Daf": a link, or text with a link in
  it, goes to the Library (`/api/save`); a photo of a marked page goes to `/share`, becomes a
  paper page, and Daf opens on it while the lines are read.
- **Long-press the icon**: Review, Continue reading (the first book on the nightstand, once the
  widget has heard of it), Log paper, Settings.
- **The evening nudge**, off until it's switched on in Settings. Between 9 pm and 3 am, every 15
  minutes (Android's shortest interval for a job, and nothing sitting in the notification shade
  all evening), the phone looks at which app is in front. If it's Instagram, Reddit, X or Discord
  it asks `/api/phone/nudge`, and posts Daf's notification if Daf says so. Daf keeps the rules
  (one every 25 minutes, none once the hour is done) and counts what was shown and whether reading
  followed. It needs Usage Access (Settings has the button) and permission to post notifications.
  "Show one now" in Settings asks for one whatever the rules say.
- **Listening with the screen off**: read-aloud keeps going behind the lock screen, with its
  controls there, in the notification shade and on headphones (`Listen.java`).
- **Books on the phone** (`Offline.java`), for reading with no signal. A book opened in the app
  stays in the app's own storage, and so do the books being read (the nightstand, then the last
  four read anywhere) and any kept by hand (the book's … menu, Keep on this phone). The WebView
  and the page's service worker get a book's file from there, so it opens at once; its details
  come from Daf when it answers and from the phone's copy when it doesn't. A job every six hours,
  on Wi-Fi unless that's switched off, brings them up to date; a book that was only being read
  leaves three weeks after it was last opened. Settings → Books on this phone lists them.
  What's done offline (the place, highlights, notes, bookmarks) waits in the page's outbox and
  goes when Daf answers again, with the time it was done; Daf keeps the newer place.

## The token

The widget, Share into Daf and the nudge use a device token, never the window's cookie. Signing
in is all it takes: once the page is signed in and the phone has no token, the app makes one
itself (`POST /api/devices {"name": "android"}` with the window's sign-in), and Daf's Preferences
→ Account lists it as "Daf for Android", with Disconnect. Settings → Connect this phone does the
same by hand. The token is kept encrypted with a key in the phone's keystore (Server.java), the
way EncryptedSharedPreferences does it, without AndroidX.

Until the phone is connected, Share into Daf sends links through `/share` with the window's
sign-in instead.

## Build it

On the Mac: JDK 17 (temurin), the Android SDK in `~/android-sdk` (platform 36).

```sh
cd android
./release.sh                 # Daf-0.1.5.apk, signed with Dvarim's key as Moshe is
adb install -r Daf-0.1.5.apk
./gradlew assembleDebug      # the test build, "Daf dev" (xyz.tiresia.daf.debug), beside the real app
```

`release.sh` signs with `android/keystore.properties` if there is one, and otherwise with
Dvarim's (`dvarim/android/keystore.properties`, beside this repository). Git ignores both, and any
`*.keystore` and `*.apk`.

## Check it

```sh
tools/mac-sandbox.sh                          # on the server: a sandbox Daf, and the three arguments
android/check.sh http://<server>:8441 COOKIE TOKEN    # on the Mac, the phone plugged in and unlocked
```

It installs the test build and opens it on the sandbox (the phone reaches it through the Mac:
`adb reverse` and a forward in `check.py`), signs the page in with the sandbox's cookie over
DevTools, and checks: the user agent and `shell-android`, `window.dafShell` answering over the
message port, Share as image finding the share sheet, the phone's Back closing search before going
back, the volume keys turning a book's page without touching the volume, Share into Daf saving a
link, and the widget's numbers arriving when you leave the app. Leave the phone alone while it
runs; with it locked, the key checks are skipped. Remove the test build afterwards with
`adb uninstall xyz.tiresia.daf.debug`.

By hand, after that: put the 4×2 widget on the first screen and see it fill in, share a link from
Chrome and a photo of a marked page, and switch on the nudge and press Show one now.

## The pieces

| file | |
| --- | --- |
| `MainActivity.java` | the WebView, Back, the volume keys, downloads, pages opened from the widget and shortcuts |
| `Shell.java` | `window.dafShell` over a message port: share, download, openExternal |
| `Server.java` | the base URL, the token in the keystore, and the endpoints |
| `ShareActivity.java` | Save to Daf in the share sheet: links and photos |
| `Widget.java` | the widget in both sizes, its refresh, and the long-press shortcuts |
| `NudgeJob.java` | the evening nudge |
| `SettingsActivity.java` | the address, Connect this phone, the nudge and its permissions |
| `Daf.java` | the nudge's notification channel, and the widget asking again on unlock |
| `ShareProvider.java` | a file for the share sheet from the app's cache |
| `release.sh`, `check.sh`, `check.py` | the signed build and the check above |
