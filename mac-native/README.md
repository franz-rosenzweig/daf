# Daf Native (the Mac trial)

This is Daf for the Mac made the way a Mac app is made: SwiftUI and AppKit, with the system's own window, sidebar, toolbar, search, inspector and Settings, instead of the web page in a window. It sits beside the regular Daf app (`mac/`) as its own app, **Daf Native** (`xyz.tiresia.daf.native`), so I can use both for a few days and decide.

It talks to Daf the same way the page does, through Daf's own API, so nothing changes on the server and everything I do in it shows up everywhere else.

## What's native

- **The window.** The sidebar has Today, the Library's Inbox, Later and Archive, the Feed and its folders with their counts, and Books. Search sits at the top of the sidebar, the inspector (⌥⌘I) has an article's details, summary, tags and highlights, and Settings has the address and sign-in.
- **Today.** The minutes ring with the main goal, Year 30 so far, the week as a chart against the goal, today's reading, and what to keep reading.
- **Lists.** The Library and the Feed, with pictures, minutes and progress. Right-click (or the toolbar) for Archive, Read Later, Mark Seen, Save to Library, Open the Original.
- **The article reader.** Native text in a column, the way Apple Books lays it out: headings, lists, quotes, pictures and captions, my highlights in their colours. Select and press **H** (or right-click → Highlight) to highlight; right-click a highlight to remove it. It keeps my place in Daf and counts my reading time exactly as the page does (15 seconds at a time, while I'm actually reading).
- **PDFs** open in Apple's own PDF view.

## What's still the page

Books, manga, videos and podcasts open as Daf's own pages inside the window (without the page's sidebar). They count reading time and keep their place themselves, as in a browser.

## Not yet

Offline, the menu bar's minutes, Save to Daf in the share menu and the Safari extension (the regular app still has all of those), Review, Highlights, Stats and Preferences.

## Building it

On the Mac:

    cd mac-native && ./build.sh

That makes `build/Daf Native.app`, signed ad hoc. `./selftest.sh BASE COOKIE` runs the app against a sandbox Daf (never the real one) and writes `build/selftest/log.txt` with a picture of each step. A tailnet sandbox needs macOS's local-network permission for the app; an SSH tunnel to the Mac's own 127.0.0.1 avoids that.
