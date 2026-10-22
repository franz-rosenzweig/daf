<sub>[Daf docs](README.md) › Using Daf</sub>

# Videos and podcasts

This page covers the things you watch and listen to: YouTube videos saved to the Library, podcasts from AntennaPod, and audiobook bookmarks. Daf doesn't try to be a video app or a podcast app. What it adds is the text, so a good minute of a talk can become a highlight like any line in a book.

## Videos

Videos I save show up under **Videos** in the Library. Open one and the player sits above its transcript, a line per caption with the time beside it. Click a line and the video jumps there, and **Follow along** keeps the transcript scrolling with the video.

The transcript comes from YouTube's own captions when there are any. When there aren't, Daf transcribes the audio itself with faster-whisper on the server, which is slow, so it only happens when you ask: **Get YouTube's captions** or **Transcribe on the server (slow)**. Long videos get their chapters as headings.

**Clip 30s** (or c) highlights the last thirty seconds of what you just heard, which is the BEST way I've found to keep something from a talk. The highlight keeps its time and the words that were said, and it goes into the review like any other.

Keys: Space plays and pauses, c clips, and ← → move ten seconds. The player is YouTube's privacy-mode embed, and **Watch on Invidious** opens it there instead.

Video time doesn't count toward the hour unless you switch on **Videos** in **Preferences → What counts toward the goal**. I keep it off, because watching isn't what Year 30 is about.

## Podcasts

Daf speaks the small part of the gpodder.net sync API that AntennaPod uses, so AntennaPod can sync to Daf as if Daf were gpodder.net, and nothing about how you listen changes.

To connect it, go to **Preferences → Podcasts (AntennaPod)**, press **Make a password** and copy it (Daf shows it only once), then follow **Set up AntennaPod**, which has the exact server address and username to type into AntennaPod's synchronization settings.

If AntennaPod used to sync to Nextcloud's GPodder Sync app, which is how I had it, `daf podcasts-import` on the server brings that history over first: the subscriptions, the ones you dropped, and where you stopped in each episode. It only reads from Nextcloud, never writes, and running it again adds only what's new. Then switch AntennaPod's sync from Nextcloud to Daf.

From then on, the **Podcasts** page in the sidebar shows **Clips**, **Listened lately** and **Subscriptions**. Listening shows up among the day's sittings, but it never counts toward the hour. That was a decision, not a missing feature: the hour is for reading.

## Clips from a podcast

When something in an episode is worth keeping, share it from AntennaPod "with position", or send a link with a time in it. Daf transcribes the minute before that point into a highlight, with the episode and the time, in about thirty seconds. It goes into the review like any other highlight and into a note in the vault.

I send these to my Signal bot, which recognizes a link with `#t=750`, AntennaPod's "Starting position: 00:12:30", or "clip" plus a link and a time. On the server, the same thing is `daf clip "the link and the time"`, and `daf jobs` lists the transcripts and clips that are waiting or done.

## Audiobook bookmarks

Bookmarks in Audiobookshelf work the same way. For each one, Daf transcribes the minute of the audiobook before the bookmark and keeps it as a highlight, shown as "Audiobook" with the time. If you title a bookmark with a sentence instead, that sentence becomes the highlight. Either way, it lands in the book's Notebook in reading order, next to the Kindle's highlights from the same book, and in the daily review.

Basically, if you hear something worth keeping, mark the spot and keep listening, and the words are waiting for you in Daf afterwards.

<sub>Next: [Highlights and review](highlights-and-review.md) →</sub>
