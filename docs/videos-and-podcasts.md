<sub>[Daf docs](README.md) › Using Daf</sub>

# Videos and podcasts

This page covers the things you watch and listen to: YouTube videos and Instagram reels saved to the Library, podcasts, and audiobook bookmarks. Daf doesn't try to be a video app or a podcast app. On the phone I still listen in AntennaPod. What Daf adds is the text, so a good minute of a talk can become a highlight like any line in a book.

## Videos

Videos I save show up under **Videos** in the Library. Open one and the player sits above its transcript, a line per caption with the time beside it. Click a line and the video jumps there, and **Follow along** keeps the transcript scrolling with the video.

The transcript comes from YouTube's own captions when there are any. When there aren't, Daf transcribes the audio itself with faster-whisper on the server, which is slow, so it only happens when you ask: **Get YouTube's captions** or **Transcribe on the server (slow)**. Long videos get their chapters as headings.

**Clip 30s** (or c) highlights the last thirty seconds of what you just heard, which is the BEST way I've found to keep something from a talk. The highlight keeps its time and the words that were said, and it goes into the review like any other.

Keys: Space plays and pauses, c clips, and ← → move ten seconds. The player is YouTube's privacy-mode embed, and **Watch on Invidious** opens it there instead.

Video time doesn't count toward the hour unless you switch on **Videos** in **Preferences → What counts toward the goal**. I keep it off, because watching isn't what Year 30 is about.

## Instagram reels

A reel worth keeping goes to Daf the same way a link does: **Share → Daf** in the Instagram app on the phone, the toolbar button or a highlight in the browser, or its link pasted into Daf. A minute later it's under **Videos** with everything that matters about it: the video itself, kept on my server (a reel can vanish from Instagram, so Daf doesn't count on it), its picture, the account it's from, the caption, and below the caption a transcript of what's said, with the time beside each line.

It plays standing up in Daf, and the rest works like a YouTube video: click a line to jump there, **Follow along**, **Clip 30s**, and highlights that go to the review and to the vault, in `Reference/instagram`, with the caption and the whole transcript. A reel with no speech, just words on the screen, has the caption and no transcript.

Instagram shows almost nothing to someone who isn't signed in, so Daf uses my own sign-in, which it keeps on the server and nowhere else. **Preferences → Instagram** has it:

- **Keep Daf signed in from my browser.** With that on, the [browser extension](browser-extension.md) sends instagram.com's cookies to Daf whenever I'm on instagram.com and they've changed. That's how Daf's sign-in never runs out: as long as I'm signed in to Instagram in Zen, so is Daf. Only Instagram's cookies, only to my Daf, and only when the switch is on.
- If Instagram does turn Daf's sign-in away, the reel waits instead of failing, the card says so, and so does the reel's page and the Sources page. Visiting instagram.com in Zen renews it, and every reel that waited comes in by itself.
- **Forget it** removes the sign-in from the server.
- In the apps, it's **Sign in to Instagram**: in Daf for Android (0.5.5 and later) on this same card, and in Daf for the Mac under **Settings → Connections → Instagram**. It opens Instagram's own sign-in page in a window of the app's, and once I'm in, the app hands the sign-in to Daf and closes the window. The app keeps nothing of Instagram itself.

## Podcasts

Daf speaks the small part of the gpodder.net sync API that AntennaPod uses, so AntennaPod can sync to Daf as if Daf were gpodder.net, and nothing about how you listen changes.

To connect it, go to **Preferences → Podcasts (AntennaPod)**, press **Make a password** and copy it (Daf shows it only once), then follow **Set up AntennaPod**, which has the exact server address and username to type into AntennaPod's synchronization settings.

If AntennaPod used to sync to Nextcloud's GPodder Sync app, which is how I had it, `daf podcasts-import` on the server brings that history over first: the subscriptions, the ones you dropped, and where you stopped in each episode. It only reads from Nextcloud, never writes, and running it again adds only what's new. Then switch AntennaPod's sync from Nextcloud to Daf.

From then on, the **Podcasts** page in the sidebar shows what I listened to lately and how far I got, my clips, and my shows. A show opens to its episodes. Listening shows up among the day's sittings, but it never counts toward the hour. That was a decision, not a missing feature: the hour is for reading.

## An episode's page

Any episode opens as a page in Daf, whether it's one from **Listened lately**, from a show, or a podcast episode in the Feed. The player sits on top, with the show's picture, and the transcript is under it, a line per stretch with the time and who's talking when the transcript knows. It works the way a YouTube video does here:

- Click a line's time and it plays from there. **Follow along** keeps the transcript scrolling with the audio.
- **−15** and **+30** skip the way AntennaPod does, and so do ← and →. The **1×** button steps through the speeds, and Daf remembers the last one.
- **Chapters**, when the episode has them, are headings in the transcript and a menu in the player.
- **Clip 30s** (or c) highlights the last thirty seconds. It works even before the transcript is there: the server transcribes just those thirty seconds and the highlight shows up in the Notebook a minute later.
- Space plays and pauses, and the Mac's media keys work too.

Where I stop goes back to AntennaPod as if I'd played it there, so the phone picks it up the next time AntennaPod syncs. And it works the other way round as well: an episode opens where I last stopped, in Daf or in AntennaPod, and says which.

The show notes come after the transcript. An episode that only lives in AntennaPod gets **Save to Library**, the same as a Feed item, and anything I highlight or clip in a Feed episode saves it to the Library anyway.

Daf for the Mac has the same page and the same **Podcasts** page. There, P plays and pauses, and the episode shows in Now Playing, so the keyboard's media keys and Control Center work too.

## Transcripts

A few shows put their own transcript in the feed (the Podcasting 2.0 tags). When they do, Daf uses theirs, and it's there in seconds, speakers and all. Only a few of mine do.

For everything else, Daf transcribes the episode on the server with faster-whisper. It's automatic for any episode I play, in AntennaPod or in Daf, and for any episode I open. It takes about a quarter of the episode's length, so an hour comes back in about fifteen minutes, and Hebrew works too. If I'd rather it only happened when I ask, I switch off **Transcribe episodes I play or open** in **Preferences → Podcasts**, and then each episode has a **Transcribe** button.

Search (⌘K) finds what was said, not just the titles.

When I highlight anything in an episode, its note goes to `Reference/podcasts` in the vault with the whole transcript, and every time in it is a link back into Daf at that moment.

## Clips from AntennaPod

When I'm out with the phone and something is worth keeping, I share it from AntennaPod "with position", or send a link with a time in it. Daf highlights the minute before that point on the episode's page, from the transcript if it has one and by transcribing that minute if not, in about thirty seconds. It goes into the review like any other highlight and into the episode's note in the vault.

I send these to my Signal bot, which recognizes a link with `#t=750`, AntennaPod's "Starting position: 00:12:30", or "clip" plus a link and a time. On the server, the same thing is `daf clip "the link and the time"`, and `daf jobs` lists the transcripts and clips that are waiting or done.

## Audiobook bookmarks

Bookmarks in Audiobookshelf work the same way. For each one, Daf transcribes the minute of the audiobook before the bookmark and keeps it as a highlight, shown as "Audiobook" with the time. If you title a bookmark with a sentence instead, that sentence becomes the highlight. Either way, it lands in the book's Notebook in reading order, next to the Kindle's highlights from the same book, and in the daily review.

Basically, if you hear something worth keeping, mark the spot and keep listening, and the words are waiting for you in Daf afterwards.

<sub>Next: [Highlights and review](highlights-and-review.md) →</sub>
