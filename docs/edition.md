<sub>[Daf docs](README.md) › Using Daf</sub>

# The Edition

The Feed never ends, and that's the trouble with it. A few hundred posts come in every day, most of them aren't for me, and scrolling through them is how a reading hour turns into a scrolling hour. The Edition is the answer I wanted: a short paper every morning, ten pieces at most, chosen from everything new by what I actually read, watch and listen to. It has a lead, a front page and an end, and when I've read it I'm done.

## What's in it

**Edition** in the sidebar (and on the phone's bottom bar) opens today's. At the top is the date, the Hebrew date and the issue's number, and a row of ten marks that fill in as I get through it, with how much reading is left.

- **The lead** is the best read of the day, usually an article of five to twenty minutes, with its opening lines under the headline. Beside it, **Today** lists the whole edition, crossed off as I go.
- **The rest** come in a grid like a front page: articles, something on this week's parasha, and one **Wildcard** from a source I don't usually read, so the paper doesn't shrink to what I already know.
- **Everything in it is real text.** A feed that sends only a summary or a link gets its whole article fetched from the page before the Edition is chosen, and a piece whose page won't give its text (a robot check, a paywall, a link with nothing behind it) is left out. The text is kept, so it opens in full in Daf and goes to the Kindle in full. Videos and podcast episodes stay out unless **Videos** or **Podcasts** in the mix says otherwise.
- Every piece has a small line saying **why it's there**: "You've watched 24 Fireship videos", "This week's parasha", "You've opened 20 from The Conversation", or "Outside your usual" for the wildcard. These come only from what Daf actually knows, never made up.
- **👍 and 👎** under each piece tell the Edition more or less like this. A piece it showed me that I never opened counts a little against it too.
- **End of the edition** at the bottom is the end. The Feed is still there when I want it, but the Edition doesn't keep going.

Pieces open in Daf like anything else, so reading them counts toward the hour, and highlights work the same way. **Past editions** at the top goes back to earlier days, and the round arrow makes today's again from what's new now.

## How it chooses

Every morning, an hour before it's due, Daf gathers what's new: the last day or two of the Feed (Sunday's covers Shabbat too) and, when the mix asks for them, new uploads from the channels I subscribe to on Invidious (no Shorts, nothing live), the videos [iv-suggest](https://github.com/NeskireDK/iv-suggest) has put in my lanes there, and new episodes of the podcasts I follow in AntennaPod. Anything I've already opened or watched is left out, and so is anything muted.

Each candidate gets a score from my **taste**, which Daf builds from what I really do:

- documents I opened, read for a while, highlighted or saved in Daf, and what I read of Daf's articles on the Kindle;
- my watch history on Invidious, and the videos I put on my own playlists there (a "Blocked" list counts against);
- the episodes I played in AntennaPod and Audiobookshelf;
- the books I've been reading on the Kindle, lightly;
- my 👍 and 👎 on earlier editions, and the pieces I left alone.

Older habits fade, so the taste follows me as I change: by default something I did a month ago counts half as much as something I did today. Invidious keeps the order I watched in but not the dates, so Daf turns places into days with how many videos I really play a day, which iv-suggest records.

A piece's score is how well its words match what I finish, times how much its source means to me. That second part borrows from iv-suggest: it's on a log curve, so one podcast I've played ninety times doesn't leave every other source at nothing, and a source I've never touched gets a floor rather than a zero, because no history isn't the same as dislike. Words I've **taken up lately** (in a few things I engaged with these two weeks and much rarer before) give a piece a lift, which is how a new interest shows up within days instead of a month. A video from one of my iv-suggest lanes gets a little more, since iv-suggest already found it for me, and the topic's More or Less turns the whole thing up or down.

The best sixty or so candidates, a few from sources I don't know yet and the parasha's posts are checked for their whole text (fetched from the page when the feed sent less), and the ones that have it go to the model with the rules (how many videos, how many podcasts, at least one Torah piece, one wildcard, no more than two from one source). It picks the edition, orders it like a paper and writes the reasons from the facts it was given. If the model is off or doesn't answer, the same rules pick from the scores alone, and the reasons are made from the facts.

## Taste

**Taste**, at the top of the Edition, shows what Daf thinks I like, and it's where I change it. At the top, **Last 2 weeks** says how it's doing: how many pieces it showed, how many I opened and read, and my thumbs. **Picking up on** lists the words I've taken up lately.

- **Topics:** the subjects my reading falls into, each with how much of it lately and an arrow for rising or fading. **More**, **Less** and **Mute** turn one up, down or off. The model names the topics the first time from my taste and the topics I named in iv-suggest, and **Name them again** asks it again after my reading has moved on.
- **Sources:** the ones that count most, with what I've done with each ("24 watched", "20 opened"), and the same three buttons. **Mute** with a name, or with `folder:Releases` for a whole Feed folder, keeps something out for good; **Muted** lists them, each with **Unmute**.
- **Mix:** **Every morning** turns the daily edition on; **Days** (Sunday to Friday by default); how many **Pieces**, **Videos**, **Podcasts**, **Torah** and **Wildcard**; the **Longest piece**; how fast **Habits fade**; when it's **Ready by**; whether it goes to the **Kindle**; and whether it's **Chosen by the model**.

## On the Kindle

Each edition goes to the Kindle as one book, "Daf, Tuesday 10 November 2026", through the same plugin as Send to Kindle. It opens on a contents page with the sections and the reasons, then every piece Daf has text for. A video or an episode goes in as its transcript once Daf has it, so the Kindle copy waits up to 25 minutes for the transcripts before it's made. Highlights made on the Kindle come back to the articles, and the time I spend in it counts, which is how the Kindle teaches the Edition too.

## Setting it up

The Edition is off until **Every morning** is on. It needs nothing else for the Feed and the podcasts. For the YouTube channels it reads Invidious's own database, so two lines go in `daf.env`:

    DAF_INVIDIOUS_PSQL=docker exec -i invidious-db psql -U kemal -d invidious
    DAF_INVIDIOUS_USER=your-account

Without them the Edition simply leaves Invidious out. The model is the one in **Preferences → AI**. `daf edition` shows today's from the command line, `daf edition --build` makes one now, `--dry-run --json` shows what it would pick and the shortlist it chose from, and `daf edition --taste` prints the taste.
