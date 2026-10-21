# Daf in the browser

This is the Daf extension, which works like the Readwise Reader one. I select text on any web page, hit "Highlight", and the page goes into my Daf Library with that highlight on it. From there it shows up in the reading view, in the daily review and in the vault like any other Daf highlight. Basically, instead of saving the link and highlighting it again in Daf later, I just highlight it where I'm reading it.

It works in Zen and Firefox, and in Chrome and Arc too.

## Using it

- Select some text and a "Highlight" button comes up next to it: click it or press **Alt+H**. Nothing is saved until I do, so selecting something to copy it doesn't put the page in Daf (it used to, which is why this changed in 0.5). A little bar comes up for the new highlight, so I can change the color, add a note or take it back.
- Options → "When I select text" has three choices: **Ask** (the button, the default), **Nothing, until I press Alt+H** (no button; Alt+H or right-click → Highlight in Daf), and **Highlight it right away** (like Daf's reader; hold **Alt**/Option while selecting to only select).
- Click a highlight to change the color (the same five as Daf), add a note and tags, or remove it. Removing it gives you an Undo for a few seconds.
- Tags are chips under the note, like in Daf: type one and hit Enter, or pick one of my existing tags from the suggestions. ".tag" in the note still works too.
- **Alt+Shift+H**, the list button on a highlight's bar, or "Show my highlights on the page" in the toolbar button opens a panel down the right side with every highlight on the page, in order, with notes and tags. Click one to jump to it; I can edit the note and tags or remove it right there. Esc closes it.
- The FIRST highlight on a page saves the page to the Library, so there's nothing else to do.
- To save a page without highlighting anything, I right-click and pick **Save this page to Daf**, or press **Alt+Shift+S** (Option+Shift+S on the Mac). Right-clicking a link has **Save this link to Daf**, which saves the page it points to without opening it, and right-clicking selected text has **Highlight in Daf**.
- The toolbar button shows a ✓ when the page is already in my Library, or the number of highlights once it has some. Clicking it tells me where the page is in Daf, saves it, and has "Open in Daf".
- When I come back to a page, my highlights are drawn on it again, including the ones I made in Daf's own reading view.

Daf keeps the page as I see it, which means a paywalled article I'm signed in to comes in whole. A link saved from the right-click menu is read by Daf itself a moment later, so if I open it in Daf right away it can still be empty; a minute later the text is there.

## Making the files

On morten:

    cd /srv/dev/daf/extension && ./build.sh

That makes `dist/`, which has a folder and a file for each browser: `dist/firefox` and `dist/daf-extension.xpi` for Zen and Firefox, and `dist/chromium` and `dist/daf-extension.zip` for Chrome and Arc. To get them onto the Mac:

    scp -r morten:/srv/dev/daf/extension/dist ~/Daf-extension

## Zen or Firefox, just to try it

Open `about:debugging`, click "This Firefox" (in Zen it's the same page), then "Load Temporary Add-on…" and pick `daf-extension.xpi`. It works right away, but it's gone the next time Zen restarts, which is fine for trying it out.

## Zen or Firefox, for good

Firefox (and Zen, which is built on it) only keeps add-ons that Mozilla has signed. Signing it "unlisted" means Mozilla signs the file and gives it back, and it never shows up on their site. It's free and usually takes a few minutes.

1. Sign in at addons.mozilla.org (a Mozilla account), open the Developer Hub once and accept the agreement, then make an API key at https://addons.mozilla.org/developers/addon/api/key/. You get a "JWT issuer" and a "JWT secret".
2. Put them in the vault's `.claude/.env`, next to the Hardcover key:

       AMO_JWT_ISSUER=user:12345678:123
       AMO_JWT_SECRET=…

3. On morten: `extension/sign.sh`. It packs the extension, sends it to Mozilla, waits for the signed file, keeps it in `extension/signed/`, and Daf's Preferences download it from then on.
4. In Zen: download it from Preferences → Account → Browser extension → Firefox or Zen, then `about:addons` → the gear → "Install Add-on From File…".

Mozilla won't sign the same version twice, so for the next change bump `"version"` in `manifest.json` first.

## Chrome or Arc

Open `chrome://extensions` (Arc: `arc://extensions`), turn on "Developer mode" at the top right, click "Load unpacked" and pick the `dist/chromium` folder. That's it. Chrome may nag about developer extensions now and then; that's normal.

## Safari

Safari's version comes inside the Daf Mac app (mac/, "Daf for Safari"), so there's nothing to download and no token to paste.

1. In Safari: Settings → Extensions, tick **Daf**. (Or in the Daf app: Daf → Safari Extension…, which opens that page.)
2. Next to it, under "Permissions", set it to **Allow on every website**, or Safari asks site by site.

When it's ticked, the extension asks the Daf app for Daf's address and a token. The app makes one with the sign-in in its window (the device is called "safari", so the Zen one stays as it is) and passes it over. If you ever disconnect "safari" in Preferences, the extension asks the app for a new one by itself.

The extension's files are the same as Zen's; `build.sh` gives Safari's build `safari.js`, which does the asking.

## Connecting it to Daf

1. In Daf, go to Preferences, then Account. Under "Connected devices" there's a "Browser extension" row. Click "Make a token" and copy the token. Daf only shows it ONCE.
2. Click the Daf button in the toolbar and choose "Options" (or right-click the button and pick Options).
3. The address is already `https://daf.tiresia.xyz`. Paste the token, then "Save and connect". It should say "Connected to Daf." The tailnet address (`http://100.91.202.11:8440`) works too, but only while you're on Tailscale.

If the browser asks whether Daf can read the pages you visit, say yes; that's how it draws the highlights. Zen might ask when you hit "Save and connect". To change Alt+H, it's `about:addons` → gear → "Manage Extension Shortcuts" in Zen, and `chrome://extensions/shortcuts` in Chrome.

If you use it in two browsers, paste the same token into both. Making a new token replaces the old one, which means both browsers need the new one. If you ever lose a laptop, hit "Disconnect" next to the browser extension in Daf and that token stops working right away.

Go make the token in Daf first and keep that tab open while you set up the extension.
