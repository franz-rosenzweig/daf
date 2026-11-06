<sub>[Daf docs](README.md) › Using Daf</sub>

# Videos and podcasts

This page covers the things you watch and listen to: YouTube videos and Instagram reels saved to the Library, podcasts, the recordings and audiobooks in Audiobookshelf, and audiobook bookmarks. Daf doesn't try to be a video app. On the phone I still mostly listen in AntennaPod, but the Podcasts tab is where I find things, and anything plays in Daf too. What Daf adds is the text, so a good minute of a talk can become a highlight like any line in a book.

## Videos

Videos I save show up under **Videos** in the Library. Open one and the player sits above its transcript, a line per caption with the time beside it. Click a line and the video jumps there, and **Follow along** keeps the transcript scrolling with the video.

The transcript comes from YouTube's own captions when there are any. When there aren't, Daf transcribes the audio itself with faster-whisper on the server, which is slow, so it only happens when you ask: **Get YouTube's captions** or **Transcribe on the server (slow)**. Long videos get their chapters as headings.

**Clip 30s** (or c) highlights the last thirty seconds of what you just heard, which is the BEST way I've found to keep something from a talk. The highlight keeps its time and the words that were said, and it goes into the review like any other.

Keys: Space plays and pauses, c clips, and ← → move ten seconds. The player is YouTube's privacy-mode embed, and **Watch on Invidious** opens it there instead.

Video time doesn't count toward the hour unless you switch on **Videos** in **Preferences → What counts toward the goal**. I keep it off, because watching isn't what Year 30 is about.

## Instagram reels

A reel I share to Daf (**Share → Daf** in the Instagram app, the browser's toolbar button, or its link pasted in) is kept as its link, under **Videos**, and opens on Instagram. Daf doesn't fetch anything from Instagram itself: Instagram takes a sign-in used from a server for a stolen one and locks the account, so Daf keeps no Instagram sign-in at all. A reel Daf kept whole before that still plays in Daf, with its transcript.

## Podcasts

Daf speaks the small part of the gpodder.net sync API that AntennaPod uses, so AntennaPod can sync to Daf as if Daf were gpodder.net, and nothing about how you listen changes.

To connect it, go to **Preferences → Podcasts (AntennaPod)**, press **Make a password** and copy it (Daf shows it only once), then follow **Set up AntennaPod**, which has the exact server address and username to type into AntennaPod's synchronization settings.

If AntennaPod used to sync to Nextcloud's GPodder Sync app, which is how I had it, `daf podcasts-import` on the server brings that history over first: the subscriptions, the ones you dropped, and where you stopped in each episode. It only reads from Nextcloud, never writes, and running it again adds only what's new. Then switch AntennaPod's sync from Nextcloud to Daf.

Listening shows up among the day's sittings, but it never counts toward the hour. That was a decision, not a missing feature: the hour is for reading.

## The Podcasts tab

Along the top are the tab's parts:

- **Listening** is what I'm in the middle of, the last one I played first, whether it's an AntennaPod show, one of my recordings or an audiobook, and then **New**: the latest episodes from the shows I follow that I haven't played yet.
- **Shows** are the ones I follow, with how many episodes I haven't played. They sort by **Recent** (the newest episode first), **A–Z** or **Unplayed**.
- **Episodes** is every episode of every show I follow, and the chips narrow it to **Unplayed**, **In progress**, **Played**, **Transcribed** or **Clipped**. **Newest**, **Oldest** and **Longest** sort them.
- **Recordings** and **Audiobooks** come from Audiobookshelf, below.
- **Clips** are the highlights I've made in episodes.

Every episode row has its date and length, a bar for how far I got (or **Played**), and a tag when it has a transcript or clips. Tapping the row opens the episode's page, and the round button on the right plays it right there, without leaving the list.

A show's page has its picture, what it's about (**More** shows the rest), its website, how many episodes it has and when it last had a new one, and **Follow** or **Following**. Its episodes have the same chips and sorts, and the magnifying glass searches just that show.

## Finding things

The magnifying glass at the top of the tab searches everything at once. First what's mine: my shows, then my episodes, by their titles, their show notes and, when Daf has the transcript, what was actually said in them, the best matches first. Then my recordings and audiobooks in Audiobookshelf. And last, Apple's podcast directory, for shows I don't follow yet and their episodes.

Any episode in the results plays with its round button, and opens to its page like any other. A show from the directory opens to its page, and **Follow** there (or right under it in the results) adds it to my subscriptions. AntennaPod gets those from Daf, so the show turns up in AntennaPod the next time it syncs, and unfollowing one takes it out of AntennaPod the same way. If I don't want to wait, AntennaPod's synchronization settings can sync now.

## Recordings and audiobooks

The things I've put in Audiobookshelf myself are in the tab too, and they never mix with AntennaPod's shows. **Recordings** is Audiobookshelf's podcast library: each set of recordings is a tile, and it opens to its episodes, which sort and filter like a show's (when a recording has no date, **Oldest** goes by its number and then its title). **Audiobooks** is every audiobook, with how much is left; one that's also a book in Daf opens the book's page, and **Read** opens the book itself.

They play in Daf's player the same way an episode does, and an audiobook's files play as one, with its chapters in the player. Where I stop goes back to Audiobookshelf as I listen, the same way its own app does it, so Audiobookshelf and its apps carry on from there, and the time counts the way it always has: audiobooks toward the hour, the recordings not at all.

## An episode's page

Any episode opens as a page in Daf, whether it's from the Podcasts tab, a search, a show, or a podcast episode in the Feed. Its play button and the time sit on top, with the show's picture, and the transcript is under it, a line per stretch with the time and who's talking when the transcript knows. It works the way a YouTube video does here:

- Once it's playing, it plays in Daf's player along the bottom of the screen, so I can go anywhere else in Daf, or leave the app, and it keeps going. The bar has the picture, the title, back 15, play and pause, ahead 30 and ✕. Tapping it (or pulling it up) opens the whole player: the time to drag, the speed, a sleep timer (to the end of the chapter too), the chapters, and **Go to it**, which brings me back to the episode's page. Pulling it down puts it back.
- Click a line's time and it plays from there. **Follow along** keeps the transcript scrolling with the audio.
- **−15** and **+30** skip the way AntennaPod does, and so do ← and →. The **1×** button steps through the speeds, and Daf remembers the last one.
- **Chapters**, when the episode has them, are headings in the transcript and a menu in the player.
- **Clip 30s** (or c) highlights the last thirty seconds. It works even before the transcript is there: the server transcribes just those thirty seconds and the highlight shows up in the Notebook a minute later.
- Space plays and pauses, and the Mac's media keys work too.

Where I stop goes back to AntennaPod as if I'd played it there, so the phone picks it up the next time AntennaPod syncs. And it works the other way round as well: an episode opens where I last stopped, in Daf or in AntennaPod, and says which.

The show notes come after the transcript, and **Show notes** goes straight to them. An episode that only lives in AntennaPod gets **Save to Library**, the same as a Feed item, and anything I highlight or clip in a Feed episode saves it to the Library anyway.

Daf for the Mac has the same page and the same **Podcasts** page. There, P plays and pauses, and the episode shows in Now Playing, so the keyboard's media keys and Control Center work too.

## Transcripts

A few shows put their own transcript in the feed (the Podcasting 2.0 tags). When they do, Daf uses theirs, and it's there in seconds, speakers and all. Only a few of mine do.

For everything else, Daf transcribes the episode on the server with faster-whisper. It's automatic for any episode I play, in AntennaPod or in Daf, and for any episode I open from a show I follow. One I've only opened from the directory waits until I play it or press **Transcribe**. It takes about a quarter of the episode's length, so an hour comes back in about fifteen minutes, and Hebrew works too. If I'd rather it only happened when I ask, I switch off **Transcribe episodes I play or open** in **Preferences → Podcasts**, and then each episode has a **Transcribe** button.

Search (⌘K) finds what was said, not just the titles.

When I highlight anything in an episode, its note goes to `Reference/podcasts` in the vault with the whole transcript, and every time in it is a link back into Daf at that moment.

## Clips from AntennaPod

When I'm out with the phone and something is worth keeping, I share it from AntennaPod "with position", or send a link with a time in it. Daf highlights the minute before that point on the episode's page, from the transcript if it has one and by transcribing that minute if not, in about thirty seconds. It goes into the review like any other highlight and into the episode's note in the vault.

I send these to my Signal bot, which recognizes a link with `#t=750`, AntennaPod's "Starting position: 00:12:30", or "clip" plus a link and a time. On the server, the same thing is `daf clip "the link and the time"`, and `daf jobs` lists the transcripts and clips that are waiting or done.

## Audiobook bookmarks

Bookmarks in Audiobookshelf work the same way. For each one, Daf transcribes the minute of the audiobook before the bookmark and keeps it as a highlight, shown as "Audiobook" with the time. If you title a bookmark with a sentence instead, that sentence becomes the highlight. Either way, it lands in the book's Notebook in reading order, next to the Kindle's highlights from the same book, and in the daily review.

Basically, if you hear something worth keeping, mark the spot and keep listening, and the words are waiting for you in Daf afterwards.

<sub>Next: [Highlights and review](highlights-and-review.md) →</sub>
