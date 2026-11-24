<sub>[Daf docs](README.md) › Using Daf</sub>

# The Edition

The Feed never ends, and that's the trouble with it. A few hundred posts come in every day, most of them aren't for me, and scrolling through them is how a reading hour turns into a scrolling hour. The Edition is the answer I wanted: a short paper every morning, ten pieces at most, chosen from everything new by what I actually read, watch and listen to. It has a lead, a front page and an end, and when I've read it I'm done.

## What's in it

**Edition** in the sidebar (and on the phone's bottom bar) opens today's. At the top is the date, the Hebrew date and the issue's number, and a row of ten marks that fill in as I get through it, with how much reading is left.

- **The lead** is the best read of the day, usually an article of five to twenty minutes, with its opening lines under the headline. Beside it, **Today** lists the whole edition, crossed off as I go.
- **The news pages** come right after the lead: a piece from each of my **news desks**, the places I want the news from. They're chosen for being real reporting from the last day or so rather than for my taste, and within a desk a story about the city itself comes ahead of one about the wider region.
- **The rest** come in a grid like a front page: articles, something on this week's parasha, and one **Wildcard** from a source I don't usually read, so the paper doesn't shrink to what I already know. The order is a paper's too: the lead, the news, the features with a section's pieces side by side, the Torah column, and the wildcard at the back.
- **Second look** is the last page: up to two pieces from an earlier edition that I never opened, in case I missed something good. They come from papers two days to a month old. A piece from a day I didn't open the paper at all comes first, since I never saw it, ahead of one I passed by on a day I read others, and today's taste ranks them all again. Each piece gets one second look and no more, and the news and the Torah column don't come back, because they belong to their own day. The line under it says when it ran first: "Missed on Tuesday" for a day I didn't read, "Skipped on 17 November" for one I passed by.
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
- everything else I read, watch and listen to: the books I read on the Kindle and in Daf's reader, my audiobooks in Audiobookshelf, my Hardcover shelves (what I'm reading, what I've read and how I rated it, what I want to read), the manga I read in Daf or on the Kindle, the films and shows I watched on Jellyfin, and what I asked Seerr for;
- my 👍 and 👎 on earlier editions, and the pieces I left alone on days I read the paper. A day I didn't open it at all doesn't count against anything in it.

A title by itself tells Daf very little about which articles I'd want, so each of those comes with what it's about: a book's tags and description from Calibre, an audiobook's genres and description, a manga's genres from Komga or AniList, and a film's or a show's genres, keywords and summary. Fiction on a screen counts lightly and only by its genres and keywords, because a thriller's plot is all police and agents, and those are the words of the news. A documentary or a lecture counts fully, since it says much more about what I'd like to read. A show counts once however many episodes I watched, with more weight for more episodes. Books I've marked private stay out, and so does anything my private titles match. Some days a piece names something I'm in the middle of, such as an essay on the book I'm reading, and then its reason says so: "Goes with Middlemarch, which you're reading". It has to name the book, its author or the show, because matching on shared words tied a film about a war veteran to news about veterans.

Older habits fade, so the taste follows me as I change: by default something I did a month ago counts half as much as something I did today. Invidious keeps the order I watched in but not the dates, so Daf turns places into days with how many videos I really play a day, which iv-suggest records.

A piece's score is how well its words match what I finish, times how much its source means to me. That second part borrows from iv-suggest: it's on a log curve, so one podcast I've played ninety times doesn't leave every other source at nothing, and a source I've never touched gets a floor rather than a zero, because no history isn't the same as dislike. Words I've **taken up lately** (in a few things I engaged with these two weeks and much rarer before) give a piece a lift, which is how a new interest shows up within days instead of a month. A video from one of my iv-suggest lanes gets a little more, since iv-suggest already found it for me, and the topic's More or Less turns the whole thing up or down.

The best sixty or so candidates, a few from sources I don't know yet and the parasha's posts are checked for their whole text (fetched from the page when the feed sent less), and the ones that have it go to the model with the rules (how many videos, how many podcasts, at least one Torah piece, one wildcard, no more than two from one source). It picks the edition, orders it like a paper and writes the reasons from the facts it was given. If the model is off or doesn't answer, the same rules pick from the scores alone, and the reasons are made from the facts.

## The pool

My own Feed is what I chose to follow, and it's small: a day of it gives only a hundred or so pieces with real text, so the Edition kept choosing from the same few sites. The **pool** is a much wider set of feeds Daf reads only for the Edition, sorted into categories like Philosophy & Ideas, Jewish Thought & Torah, Israel & Middle East, AI & Technology, Science, History and Writing & Books. Every feed in it was checked first: it has to be alive and give real text, not a teaser or a link.

The pool stays out of the Feed. Its posts aren't in any Feed list or count, the reader apps don't see them, and they go after five days unless an Edition took them. A piece the Edition does take becomes an ordinary Feed post, so it opens, saves and highlights like any other. The pool's feeds are read every four hours instead of every half hour.

The pool is simply every folder set to **Hidden** on the [Feeds page](feed-and-library.md#what-shows-where), so a feed goes into it by putting it in one of those folders, or by setting the feed itself to Hidden. `daf pool-add list.json` adds a checked list, each feed into its category's folder, and makes a new folder Hidden. On the Taste page, **Pool** shows each hidden folder with its feeds and what came in the last two days, and **Mute** keeps a whole folder out. (Until November 10 a pool folder's name started with "Pool · "; Daf took that off and set those folders to Hidden.)

### The news desks

A news desk is a place I want the news from, and none are built in: they live in Daf's settings, under `edition.desks`, since they're my own places. Each one has a name (it becomes the section's name and the row in the **Mix**), how many pieces at least, the feeds that are always on it, the Feed folders it reads, whether every post in those folders counts or only the ones that name the place, the words that name the place, and the closer places that come first within it:

    "desks": [{"key": "home", "name": "Lisbon", "at_least": 1,
               "folders": ["Portugal"], "any": true, "sources": [],
               "words": ["lisbon", "portugal", "sintra", "porto"], "lean": ["lisbon"]}]

A story from any feed of mine counts too when its headline names the place. The pool is the natural home for a desk's feeds: a hidden folder of the local papers and newsrooms that give their whole stories in their feeds (`daf pool-add` with a checked list). When I move, the desk is the one thing to change.

## Taste

**Taste**, at the top of the Edition, shows what Daf thinks I like, and it's where I change it. At the top, **Last 2 weeks** says how it's doing: how many pieces it showed, how many I opened and read, and my thumbs. **Picking up on** lists the words I've taken up lately, and **Lately** the books, shows and films I'm in the middle of or just finished.

- **Topics:** the subjects my reading falls into, each with how much of it lately and an arrow for rising or fading. **More**, **Less** and **Mute** turn one up, down or off. The model names the topics the first time from my taste and the topics I named in iv-suggest, and **Name them again** asks it again after my reading has moved on.
- **Topics of my own:** the model only knows what I've already been reading, so when I want the paper to follow something new I type it into **Add a topic** under the list, "woodworking" for instance, and press **Add**. A topic is really a handful of words Daf looks for in titles and summaries. If I know which words I want, I put them in **Words**. If I leave that empty, Daf asks the model for fifteen or so, which takes a few seconds, and if the model is off it goes by the words in the name. A topic I add starts on **More**, so it counts from the next edition, and resting the pointer on any topic's name shows its words.
- **Removing a topic:** the **×** at the end of a row takes that topic off the list, the model's or mine, after asking. It stays gone, because **Name them again** replaces only the model's topics: mine are kept as I set them, and a name I removed isn't brought back. If I change my mind I add it again.
- **Sources:** the ones that count most, with what I've done with each ("24 watched", "20 opened"), and the same three buttons. **Mute** with a name, or with `folder:Releases` for a whole Feed folder, keeps something out for good; **Muted** lists them, each with **Unmute**.
- **Mix:** **Every morning** turns the daily edition on; **Days** (Sunday to Friday by default); how many **Pieces**, **Videos**, **Podcasts**, **Torah**, pieces from each news desk (a row with the desk's name), **Wildcard** and **Second look** (up to three, never more than a third of the paper); the **Longest piece**; how fast **Habits fade**; when it's **Ready by**; whether it goes to the **Kindle**; and whether it's **Chosen by the model**.

## On the Kindle

Each edition goes to the Kindle as one book, "Daf, Tuesday 10 November 2026", through the same plugin as Send to Kindle. It opens on a front page set like a paper's: the name, a dateline with the issue's number and the Hebrew date, a photograph, the lead with its opening lines, and then every other piece with its section, where it's from, how long it is and why it's there. Each headline is a link, so a tap opens that piece, and every piece ends with **Front page**, which brings me back. The photograph is the first real one in the paper's order, usually the lead's own; a logo, a title card or a banner doesn't count. If the paper has no photograph at all, the front page goes without one. The book also has a cover drawn the same way, with the name, the date, the photograph and the headlines that fit, which is what the Kindle's library shows for it. After the front page come the pieces Daf has text for. A video or an episode goes in as its transcript once Daf has it, so the Kindle copy waits up to 25 minutes for the transcripts before it's made. Highlights made on the Kindle come back to the articles, and the time I spend in it counts, which is how the Kindle teaches the Edition too.

The Kindle doesn't wait for me to pick it up. When it goes to sleep, the Daf plugin sets an alarm for a quarter past the edition's **Ready by** hour on the next edition day, which Daf tells it. The alarm wakes it behind the sleep screen; it turns on the Wi-Fi if it has to, brings in the edition, sets the next alarm and goes back to sleep, all in a minute or two and without changing what the screen shows. If the edition wasn't there yet, it tries again every half hour until late morning. It never wakes on a day without an edition. The plugin needs to be on the Kindle from November 20, 2026 or later for this.

## To listen to

The Edition is also a morning programme I can hear on a walk or a bike ride. Once the paper is made, the model writes it as a script for one voice: the day, a quick run through the headlines, then every piece in the paper's order, each told in a few minutes from its own text, and a line at the end on what's most worth reading in full. It keeps to what the pieces say and adds nothing of its own. Kokoro reads it in the same voice as Listen, which takes about as long as the episode plays, so it's ready half an hour or so after the paper, long before I'm out the door. If the model is off, the episode is made from each piece's opening lines instead.

It comes as a private podcast. Every piece is a chapter, so the skip button on my earphones moves from story to story, and each chapter's link opens the piece in Daf when I want to read it properly. The episode carries its own transcript, which the podcast app can show and Daf keeps on the episode's page, so nothing has to transcribe it.

What I listen to counts. AntennaPod tells Daf what I played through its sync, and a piece whose chapter I heard most of counts as opened, both for the row of marks at the top of the paper and for the taste. A chapter I skipped stays unopened, the same as a piece I passed by in the paper.

It can also be a conversation. With two hosts set in `"audio_hosts"`, each with a name, one of Kokoro's voices and a speed, the model writes it as a morning podcast between them instead: one brings most of the stories and the other comes at each one fresh, reacting, asking what I'd ask and pushing back when something doesn't add up. The facts still come only from the pieces; what the hosts think about them is said as their own take. Each turn is read in its host's voice, and the transcript says who's talking.

Hebrew words are the weak spot. The voice is an English one, so the script spells Hebrew names and places the way they're said, with hyphens and apostrophes (Kir-yat Sh'mo-na), which helps a lot but isn't perfect.

To set it up, `"audio": true` goes in the Edition's settings (and `"audio_minutes"` for a length other than twenty minutes, and for two hosts something like `"audio_hosts": [{"name": "Ada", "voice": "bf_emma", "speed": 1.2}, {"name": "Ben", "voice": "am_michael", "speed": 1.2}]`), and `daf listen-feed` prints the feed's address, which goes into the podcast app as a new podcast by its address. The address has its own key in it, so the app needs no sign-in; running `daf listen-feed` again makes a new address and the old one stops working. Episodes are kept for two weeks. `daf edition --audio` makes today's now.

## Setting it up

The Edition is off until **Every morning** is on. It needs nothing else for the Feed and the podcasts. For the YouTube channels it reads Invidious's own database, so two lines go in `daf.env`:

    DAF_INVIDIOUS_PSQL=docker exec -i invidious-db psql -U kemal -d invidious
    DAF_INVIDIOUS_USER=your-account

Without them the Edition simply leaves Invidious out. Jellyfin and Seerr need their keys where Daf reads keys from (`DAF_SECRET_FILES` or `daf.env`): `JELLYFIN_URL`, `JELLYFIN_API_KEY` and `JELLYFIN_USER` (my account there, which is also how Daf knows which Seerr requests are mine), and `DAF_SEERR_KEY` (or `HOMEPAGE_VAR_JELLYSEERR_KEY`) with `DAF_SEERR_URL` if Seerr isn't on port 5055. Without them those two are left out too, and the rest still counts. The model is the one in **Preferences → AI**. `daf edition` shows today's from the command line, `daf edition --build` makes one now, `--dry-run --json` shows what it would pick and the shortlist it chose from, and `daf edition --taste` prints the taste.
