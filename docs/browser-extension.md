<sub>[Daf docs](README.md) › Devices</sub>

# The browser extension

The Daf extension lets you highlight on any web page, the way the Readwise Reader extension does. Select some text, press **Highlight**, and the page goes into your Daf Library with that highlight on it. From there it's in the reading view, the daily review and the vault like any other highlight. Basically, instead of saving a link and highlighting it again in Daf later, you highlight it where you're reading it.

It works in Firefox and Zen, in Chrome and Arc, and in Safari through the Mac app. To install it, see [Install](install.md#the-browser-extension).

## Highlighting

- Select text and a **Highlight** button comes up next to it. Press it, or **Alt+H** (Option+H on the Mac), and it's highlighted; the button beside it highlights and opens a note. Nothing is kept until you do, so selecting text to copy it never saves the page. A small bar then comes up for the new highlight, so you can change the color, add a note or take it back.
- What selecting does is up to you, in the extension's **Options** under "When I select text":
  - **Ask** (the default): the Highlight button, as above.
  - **Nothing, until I press Alt+H**: no button at all. Alt+H, or right-click the selection and choose **Highlight in Daf**. On a touch screen you still get the button, since there's no key to press.
  - **Highlight it right away**: like Daf's own reader, a selection made with the mouse is highlighted as soon as you let go. Hold **Alt** while you select to only select; a single word still gets the button.
- Click a highlight to change the color (the same five as Daf), add a note and tags, or remove it. Removing it gives you an Undo for a few seconds.
- Tags are chips under the note, like in Daf: type one and press Enter, or pick one of your tags from the suggestions. ".tag" in the note works too.

## Instagram

If **Preferences → Instagram → Keep Daf signed in from my browser** is on in Daf, the extension keeps Daf's Instagram sign-in fresh, which is what lets Daf save reels (see [Videos and podcasts](videos-and-podcasts.md#instagram-reels)). When you're on instagram.com and signed in, it checks whether Daf has this browser's session and sends instagram.com's cookies if it doesn't. Daf only ever tells it a fingerprint of its session, never the session itself, and with the switch off nothing is sent. It needs the "cookies" permission, which came with version 0.6.

## The page panel

**Alt+Shift+H**, the list button on a highlight's bar, or "Show my highlights on the page" in the toolbar button opens a panel down the right side with every highlight on the page, in order, with notes and tags. Click one to jump to it, edit the note and tags right there, or remove it. Esc closes it.

## Saving the page

The FIRST highlight on a page saves the page to the Library, so there's nothing else to do. To save a page without highlighting anything, right-click it and pick **Save this page to Daf**, or press **Alt+Shift+S** (Option+Shift+S on the Mac). Right-clicking a link has **Save this link to Daf**, which saves the page it points to without opening it, and right-clicking selected text has **Highlight in Daf**.

The toolbar button shows a ✓ when the page is already in your Library, or the number of highlights once it has some. Clicking it tells you where the page is in Daf, saves it if it isn't there yet, and has **Open in Daf**.

When you come back to a page, your highlights are drawn on it again, including the ones you made in Daf's own reading view.

Saving sends Daf the page as you see it, so a paywalled article you're signed in to comes in whole, not as its teaser. Daf also reads the page itself from my server, signed in nowhere, and keeps whichever has more. For something saved before, the toolbar button's **Give Daf this page's text** does it now.

On a page that sends nothing worth keeping, Daf needs a few seconds to read it after it's saved. If you open it before that, it says it's reading the page, and the text comes in by itself.

## Connecting it to Daf

For Firefox, Zen, Chrome and Arc:

1. In Daf, go to **Preferences → Account**. Under "Connected devices" there's a "Browser extension" row. Press **Make a token** and copy it. Daf shows it only ONCE.
2. Click the Daf button in the browser's toolbar and choose **Options**.
3. Type your Daf's address, paste the token, and press **Save and connect**. It should say "Connected to Daf."

If the browser asks whether Daf can read the pages you visit, say yes, because that's how it draws the highlights. If you use it in two browsers, paste the same token into both: making a new token replaces the old one, so both would need the new one.

Safari needs none of this. The Mac app makes the token itself and hands it to the extension, as a device called "safari".

## If you lose a laptop

Press **Disconnect** next to the browser extension in **Preferences → Account**, and its token stops working right away.

The full notes on building, signing and testing the extension are in [extension/README.md](../extension/README.md).

<sub>Next: [Sharing, messages and the widget](phone-shortcuts.md) →</sub>
